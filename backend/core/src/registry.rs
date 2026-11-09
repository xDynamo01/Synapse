use crate::{
    contracts::{CoreError, CoreResult, ModelManifest, SkillManifest, bounded, scope},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

pub(crate) fn model_register(tx: &Transaction<'_>, model: &ModelManifest) -> CoreResult<Value> {
    bounded(&model.id, "model_id", 128)?;
    bounded(&model.provider, "provider", 128)?;
    bounded(&model.endpoint, "endpoint", 1024)?;
    if model.capabilities.is_empty() || model.capabilities.len() > 32 {
        return Err(CoreError::invalid("Invalid model capabilities"));
    }
    for capability in &model.capabilities {
        bounded(capability, "capability", 128)?;
    }
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM models WHERE id=?1)",
        [&model.id],
        |r| r.get(0),
    )?;
    if exists {
        return Err(CoreError::new(
            "already_exists",
            "Model ID already registered",
        ));
    }
    tx.execute(
        "INSERT INTO models(id,manifest) VALUES(?1,?2)",
        params![model.id, serde_json::to_string(model)?],
    )?;
    store::event(tx, "model_registered", json!({"model_id":model.id}))?;
    Ok(json!({"model":model,"operational":false}))
}

fn page(after: u64, limit: u32) -> CoreResult<()> {
    if after > i64::MAX as u64 || !(1..=100).contains(&limit) {
        return Err(CoreError::invalid(
            "Invalid registry cursor or limit (1..100)",
        ));
    }
    Ok(())
}

pub(crate) fn models_list(tx: &Transaction<'_>, after: u64, limit: u32) -> CoreResult<Value> {
    page(after, limit)?;
    let mut q =
        tx.prepare("SELECT rowid,manifest FROM models WHERE rowid>?1 ORDER BY rowid LIMIT ?2")?;
    let rows = q.query_map(params![after as i64, (limit + 1) as i64], |r| {
        Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?))
    })?;
    let mut models = Vec::new();
    let mut bytes = 0;
    let mut next_cursor = after;
    let mut has_more = false;
    for row in rows {
        let (cursor, raw) = row?;
        if models.len() >= limit as usize {
            has_more = true;
            break;
        }
        let manifest: ModelManifest = serde_json::from_str(&raw)?;
        let item = json!({"id":manifest.id,"provider":manifest.provider,"capabilities":manifest.capabilities,"memory_bytes":manifest.memory_bytes,"operational":false});
        let size = serde_json::to_vec(&item)?.len();
        if bytes + size > 220_000 {
            if models.is_empty() {
                return Err(CoreError::new(
                    "response_too_large",
                    "A model summary exceeds page byte budget",
                ));
            }
            has_more = true;
            break;
        }
        bytes += size;
        next_cursor = cursor as u64;
        models.push(item);
    }
    Ok(json!({"models":models,"next_cursor":next_cursor,"has_more":has_more}))
}

pub(crate) fn model_get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "model_id", 128)?;
    let manifest: Option<String> = tx
        .query_row("SELECT manifest FROM models WHERE id=?1", [id], |r| {
            r.get(0)
        })
        .optional()?;
    let manifest = manifest.ok_or_else(|| CoreError::new("not_found", "Model not found"))?;
    Ok(json!({"model":serde_json::from_str::<Value>(&manifest)?,"operational":false}))
}

pub(crate) fn skill_register(tx: &Transaction<'_>, skill: &SkillManifest) -> CoreResult<Value> {
    bounded(&skill.id, "skill_id", 128)?;
    bounded(&skill.version, "skill_version", 64)?;
    scope(&skill.scope)?;
    bounded(&skill.provenance, "skill_provenance", 2048)?;
    bounded(&skill.instructions, "skill_instructions", 32_768)?;
    if skill.tools.len() > 64 || skill.permissions.len() > 64 {
        return Err(CoreError::invalid("Skill declarations exceed limits"));
    }
    for tool in &skill.tools {
        bounded(tool, "skill_tool", 128)?;
    }
    for permission in &skill.permissions {
        bounded(permission, "skill_permission", 128)?;
    }
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM skills WHERE scope=?1 AND id=?2 AND version=?3)",
        params![skill.scope, skill.id, skill.version],
        |r| r.get(0),
    )?;
    if exists {
        return Err(CoreError::new(
            "already_exists",
            "Skill version is immutable",
        ));
    }
    let digest = store::digest(skill)?;
    tx.execute(
        "INSERT INTO skills(id,version,scope,manifest,digest) VALUES(?1,?2,?3,?4,?5)",
        params![
            skill.id,
            skill.version,
            skill.scope,
            serde_json::to_string(skill)?,
            digest
        ],
    )?;
    store::event(
        tx,
        "skill_registered",
        json!({"skill_id":skill.id,"version":skill.version,"scope":skill.scope,"digest":digest}),
    )?;
    Ok(json!({"skill":skill,"digest":digest,"operational":false}))
}

pub(crate) fn skills_list(
    tx: &Transaction<'_>,
    project_scope: &str,
    after: u64,
    limit: u32,
) -> CoreResult<Value> {
    scope(project_scope)?;
    page(after, limit)?;
    let mut q = tx.prepare("SELECT rowid,id,version,digest FROM skills WHERE scope=?1 AND rowid>?2 ORDER BY rowid LIMIT ?3")?;
    let rows = q.query_map(
        params![project_scope, after as i64, (limit + 1) as i64],
        |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, String>(3)?,
            ))
        },
    )?;
    let mut skills = Vec::new();
    let mut bytes = 0;
    let mut next_cursor = after;
    let mut has_more = false;
    for row in rows {
        let (cursor, id, version, digest) = row?;
        if skills.len() >= limit as usize {
            has_more = true;
            break;
        }
        let item = json!({"id":id,"version":version,"scope":project_scope,"digest":digest,"operational":false});
        let size = serde_json::to_vec(&item)?.len();
        if bytes + size > 220_000 {
            if skills.is_empty() {
                return Err(CoreError::new(
                    "response_too_large",
                    "A Skill summary exceeds page byte budget",
                ));
            }
            has_more = true;
            break;
        }
        bytes += size;
        next_cursor = cursor as u64;
        skills.push(item);
    }
    Ok(json!({"scope":project_scope,"skills":skills,"next_cursor":next_cursor,"has_more":has_more}))
}

pub(crate) fn skill_get(
    tx: &Transaction<'_>,
    project_scope: &str,
    id: &str,
    version: &str,
) -> CoreResult<Value> {
    scope(project_scope)?;
    bounded(id, "skill_id", 128)?;
    bounded(version, "skill_version", 64)?;
    let row: Option<(String, String)> = tx
        .query_row(
            "SELECT manifest,digest FROM skills WHERE scope=?1 AND id=?2 AND version=?3",
            params![project_scope, id, version],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()?;
    let (manifest, digest) =
        row.ok_or_else(|| CoreError::new("not_found", "Skill version not found"))?;
    Ok(
        json!({"skill":serde_json::from_str::<Value>(&manifest)?,"digest":digest,"operational":false}),
    )
}

pub(crate) fn capabilities() -> Value {
    json!({"capabilities":[
        {"id":"core_storage","status":"operational"},
        {"id":"chats","status":"operational"},
        {"id":"canonical_memory","status":"operational"},
        {"id":"mission_contracts","status":"operational"},
        {"id":"model_registry","status":"operational"},
        {"id":"skill_registry","status":"operational"},
        {"id":"inference","status":"unavailable"},
        {"id":"mission_execution","status":"unavailable"}
    ]})
}
