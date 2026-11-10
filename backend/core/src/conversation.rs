use crate::{
    chats,
    contracts::{CoreError, CoreResult, Generation, MessageRole, ModelManifest, bounded},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

pub(crate) struct Launch {
    pub id: String,
    pub model_id: String,
    pub endpoint: String,
    pub messages: Vec<Value>,
    pub generation: Generation,
    pub learning: bool,
}

fn message_id(job_id: &str, role: &str) -> String {
    let hash = Sha256::digest(job_id.as_bytes());
    format!(
        "ai-{}-{role}",
        hash.iter().map(|b| format!("{b:02x}")).collect::<String>()
    )
}

pub(crate) fn start(
    tx: &Transaction<'_>,
    id: &str,
    chat_id: Option<&str>,
    model_id: &str,
    prompt: &str,
) -> CoreResult<(Value, Launch)> {
    bounded(id, "job_id", 128)?;
    bounded(model_id, "model_id", 128)?;
    bounded(prompt, "prompt", 32_768)?;
    let manifest: Option<String> = tx
        .query_row("SELECT manifest FROM models WHERE id=?1", [model_id], |r| {
            r.get(0)
        })
        .optional()?;
    let manifest: ModelManifest = serde_json::from_str(
        &manifest.ok_or_else(|| CoreError::new("model_unavailable", "Model is not registered"))?,
    )?;
    if manifest.provider != "lm_studio" || !manifest.capabilities.iter().any(|c| c == "chat") {
        return Err(CoreError::new(
            "model_unavailable",
            "Model has no supported chat provider",
        ));
    }
    let mut user_message_id = None;
    let mut assistant_message_id = None;
    let mut source_cursor = 0;
    if let Some(chat_id) = chat_id {
        // The chat must already exist; append validates its ID and content.
        let user = message_id(id, "user");
        chats::append(tx, chat_id, &user, &MessageRole::User, prompt)?;
        source_cursor = store::cursor(tx)?;
        user_message_id = Some(user);
        assistant_message_id = Some(message_id(id, "assistant"));
    }
    let messages = if let Some(chat_id) = chat_id {
        let mut statement = tx.prepare(
            "SELECT role,content FROM messages WHERE chat_id=?1 ORDER BY sequence LIMIT 65",
        )?;
        let rows = statement.query_map([chat_id], |r| {
            Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
        })?;
        let mut messages = Vec::new();
        let mut bytes = 2usize;
        for row in rows {
            let (role, content) = row?;
            let message = json!({"role":role,"content":content});
            bytes += serde_json::to_vec(&message)?.len() + usize::from(!messages.is_empty());
            messages.push(message);
            if messages.len() > 64 || bytes > 48_000 {
                return Err(CoreError::invalid(
                    "Conversation context exceeds 64 messages or 48000 bytes",
                ));
            }
        }
        messages
    } else {
        vec![json!({"role":"user","content":prompt})]
    };
    if serde_json::to_vec(&messages)?.len() > 48_000 {
        return Err(CoreError::invalid(
            "Conversation context exceeds 64 messages or 48000 bytes",
        ));
    }
    let generation = manifest.generation.unwrap_or_default();
    generation.validate()?;
    tx.execute("INSERT INTO ai_jobs(id,kind,chat_id,model_id,status,user_message_id,assistant_message_id,generation,endpoint,source_cursor) VALUES(?1,?2,?3,?4,'running',?5,?6,?7,?8,?9)", params![id, if chat_id.is_some() {"conversation"} else {"inference"}, chat_id, model_id, user_message_id, assistant_message_id, serde_json::to_string(&generation)?,manifest.endpoint,source_cursor as i64])?;
    store::event(
        tx,
        "ai_job_started",
        json!({"job_id":id,"model_id":model_id,"chat_id":chat_id}),
    )?;
    Ok((
        json!({"job_id":id,"status":"running"}),
        Launch {
            id: id.into(),
            model_id: model_id.into(),
            endpoint: manifest.endpoint,
            messages,
            generation,
            learning: false,
        },
    ))
}

pub(crate) fn get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "job_id", 128)?;
    let mut job = tx.query_row("SELECT kind,chat_id,model_id,status,result,error,user_message_id,assistant_message_id,generation FROM ai_jobs WHERE id=?1", [id], |r| Ok((json!({"job_id":id,"kind":r.get::<_,String>(0)?,"chat_id":r.get::<_,Option<String>>(1)?,"model_id":r.get::<_,String>(2)?,"status":r.get::<_,String>(3)?,"content":r.get::<_,Option<String>>(4)?,"error":r.get::<_,Option<String>>(5)?,"user_message_id":r.get::<_,Option<String>>(6)?,"assistant_message_id":r.get::<_,Option<String>>(7)?}), r.get::<_,String>(8)?))).optional()?.ok_or_else(|| CoreError::new("not_found", "AI job not found"))?;
    job.0["generation"] = serde_json::from_str(&job.1)?;
    Ok(job.0)
}

pub(crate) fn cancel(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "job_id", 128)?;
    let changed = tx.execute(
        "UPDATE ai_jobs SET status='cancelled',error='cancelled' WHERE id=?1 AND status='running'",
        [id],
    )?;
    if changed > 0 {
        store::event(tx, "ai_job_cancelled", json!({"job_id":id}))?;
    }
    get(tx, id)
}

pub(crate) fn complete(
    tx: &Transaction<'_>,
    id: &str,
    outcome: Result<String, String>,
) -> CoreResult<()> {
    let row: Option<(String, Option<String>, Option<String>)> = tx
        .query_row(
            "SELECT status,chat_id,assistant_message_id FROM ai_jobs WHERE id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .optional()?;
    let Some((status, chat_id, assistant_id)) = row else {
        return Ok(());
    };
    if status != "running" {
        return Ok(());
    }
    match outcome {
        Ok(content) => {
            if let (Some(chat_id), Some(assistant_id)) = (&chat_id, &assistant_id) {
                chats::append(
                    tx,
                    &chat_id,
                    &assistant_id,
                    &MessageRole::Assistant,
                    &content,
                )?;
            }
            tx.execute(
                "UPDATE ai_jobs SET status='succeeded',result=?2 WHERE id=?1",
                params![id, content],
            )?;
            store::event(tx, "ai_job_succeeded", json!({"job_id":id}))?;
            if chat_id.is_some() {
                tx.execute(
                    "INSERT INTO learning_jobs(source_job_id,status) VALUES(?1,'queued')",
                    [id],
                )?;
            }
        }
        Err(code) => {
            tx.execute(
                "UPDATE ai_jobs SET status='failed',error=?2 WHERE id=?1",
                params![id, code],
            )?;
            store::event(tx, "ai_job_failed", json!({"job_id":id,"code":code}))?;
        }
    }
    Ok(())
}
