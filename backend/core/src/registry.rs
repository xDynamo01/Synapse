use crate::{
    contracts::{CoreError, CoreResult, ModelManifest, SkillManifest, bounded, scope},
    store,
};
use rusqlite::{Transaction, params};
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

pub(crate) fn models_list(tx: &Transaction<'_>) -> CoreResult<Value> {
    let mut q = tx.prepare("SELECT manifest FROM models ORDER BY id")?;
    let rows = q.query_map([], |r| r.get::<_, String>(0))?;
    let mut models = Vec::new();
    for row in rows {
        models.push(json!({"manifest":serde_json::from_str::<Value>(&row?)?,"operational":false}));
    }
    Ok(json!({"models":models}))
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

pub(crate) fn skills_list(tx: &Transaction<'_>, project_scope: &str) -> CoreResult<Value> {
    scope(project_scope)?;
    let mut q =
        tx.prepare("SELECT manifest,digest FROM skills WHERE scope=?1 ORDER BY id,version")?;
    let rows = q.query_map([project_scope], |r| {
        Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
    })?;
    let mut skills = Vec::new();
    for row in rows {
        let (manifest, digest) = row?;
        skills.push(json!({"manifest":serde_json::from_str::<Value>(&manifest)?,"digest":digest,"operational":false}));
    }
    Ok(json!({"scope":project_scope,"skills":skills}))
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
