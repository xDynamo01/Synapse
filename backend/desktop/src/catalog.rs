use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub fn matching_skill_packages(catalog: &Value, objective: &str) -> Vec<Value> {
    let words = |text: &str| -> BTreeSet<String> {
        text.split(|character: char| !character.is_alphanumeric())
            .filter(|word| word.chars().count() >= 3)
            .map(str::to_lowercase)
            .collect()
    };
    let objective = words(objective);
    let Some(packages) = catalog["packages"].as_array() else {
        return Vec::new();
    };
    let mut matches: Vec<_> = packages
        .iter()
        .filter_map(|package| {
            let name = package["name"].as_str()?;
            package["url"].as_str()?;
            let score = words(name).intersection(&objective).count();
            (score > 0).then_some((score, package))
        })
        .collect();
    matches.sort_by_key(|(score, _)| std::cmp::Reverse(*score));
    matches
        .into_iter()
        .take(5)
        .map(|(_, package)| package.clone())
        .collect()
}

#[derive(Default)]
pub struct Catalog {
    pub chats: BTreeMap<String, String>,
    pub missions: BTreeSet<String>,
    pub projects: BTreeSet<String>,
    pub skills: BTreeMap<String, Vec<Value>>,
    active_skills: BTreeMap<(String, String), Value>,
    memory: BTreeMap<String, BTreeSet<String>>,
}

impl Catalog {
    pub fn observe(&mut self, event: &Value) {
        let payload = &event["payload"];
        if let Some(id) = payload["mission_id"].as_str() {
            self.missions.insert(id.into());
        }
        let Some(scope) = payload["scope"].as_str() else {
            return;
        };
        match event["kind"].as_str() {
            Some("workspace_project_registered") => {
                self.projects.insert(scope.into());
            }
            Some("skill_active_changed") => {
                if let Some(id) = payload["skill_id"].as_str() {
                    self.active_skills
                        .insert((scope.into(), id.into()), payload["active"].clone());
                }
            }
            Some("skill_registered") => {
                if let (Some(id), Some(version), Some(digest)) = (
                    payload["skill_id"].as_str(),
                    payload["version"].as_str(),
                    payload["digest"].as_str(),
                ) {
                    self.skills
                        .entry(scope.into())
                        .or_default()
                        .push(json!({"scope":scope,"id":id,"version":version,"digest":digest}));
                }
            }
            Some("chat_created") => {
                if let Some(id) = payload["chat_id"].as_str() {
                    self.chats.insert(id.into(), scope.into());
                }
            }
            Some("memory_revision_created") => {
                if let Some(key) = payload["key"].as_str() {
                    let keys = self.memory.entry(scope.into()).or_default();
                    if payload["status"] == "active" {
                        keys.insert(key.into());
                    } else {
                        keys.remove(key);
                    }
                }
            }
            _ => {}
        }
    }

    pub fn is_active_skill(&self, pin: &Value) -> bool {
        let (Some(scope), Some(id)) = (pin["scope"].as_str(), pin["id"].as_str()) else {
            return false;
        };
        self.active_skills.get(&(scope.into(), id.into())) == Some(pin)
    }

    /// Match project names after an explicit project mention, using only metadata.
    /// Core resolves the exact references and rechecks status in the same transaction.
    pub fn references(&self, message: &str) -> Result<Vec<Value>, &'static str> {
        let words = normalized(message);
        let matching: Vec<_> = self
            .memory
            .iter()
            .filter(|(scope, keys)| {
                let Some(name) = scope.strip_prefix("project:") else {
                    return false;
                };
                !keys.is_empty()
                    && ["projeto", "project"].iter().any(|prefix| {
                        words.contains(&format!(" {prefix} {} ", normalized(name).trim()))
                    })
            })
            .collect();
        let (scope, keys) = match matching.as_slice() {
            [] => return Ok(vec![]),
            [single] => *single,
            _ => {
                return Err(
                    "Mais de um projeto corresponde à mensagem. Selecione o projeto e a chave de memória.",
                );
            }
        };
        if keys.len() > 16 {
            return Err(
                "O projeto tem mais de 16 memórias ativas. Selecione uma chave de memória.",
            );
        }
        Ok(keys
            .iter()
            .map(|key| json!({"scope":scope,"key":key}))
            .collect())
    }
}

fn normalized(text: &str) -> String {
    let words: String = text
        .to_lowercase()
        .chars()
        .map(|ch| if ch.is_alphanumeric() { ch } else { ' ' })
        .collect();
    format!(
        " {} ",
        words.split_whitespace().collect::<Vec<_>>().join(" ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_skill_suggestions_rank_matching_names() {
        let entries = json!({"packages":[
            {"name":"Python","url":"https://example.com/python"},
            {"name":"Python Testes","url":"https://example.com/tests"},
            {"name":"Rust","url":"https://example.com/rust"}
        ]});
        let matches = matching_skill_packages(&entries, "Criar testes em PYTHON");
        assert_eq!(matches.len(), 2);
        assert_eq!(matches[0]["name"], "Python Testes");
        assert_eq!(matches[1]["name"], "Python");
        assert!(matching_skill_packages(&entries, "Escrever documentação").is_empty());
    }

    #[test]
    fn project_memory_requires_an_explicit_unambiguous_mention() {
        let mut catalog = Catalog::default();
        let event = |scope, status| json!({"kind":"memory_revision_created","payload":{"scope":scope,"key":"decisao","status":status}});
        catalog.observe(&event("project:meu-projeto", "active"));
        assert!(
            catalog
                .references("Como está meu projeto?")
                .unwrap()
                .is_empty()
        );
        assert_eq!(
            catalog
                .references("Como está o projeto Meu Projeto?")
                .unwrap(),
            vec![json!({"scope":"project:meu-projeto","key":"decisao"})]
        );
        catalog.observe(&event("project:meu", "active"));
        assert!(
            catalog
                .references("Como está o projeto Meu Projeto?")
                .is_err()
        );
        catalog.observe(&event("project:meu", "resolved"));
        assert_eq!(
            catalog
                .references("Como está o projeto Meu Projeto?")
                .unwrap()
                .len(),
            1
        );
    }
}
