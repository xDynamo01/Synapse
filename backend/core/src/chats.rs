use crate::{
    contracts::{CoreError, CoreResult, MessageRole, bounded, scope},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

pub(crate) fn create(
    tx: &Transaction<'_>,
    id: &str,
    title: &str,
    project_scope: &str,
) -> CoreResult<Value> {
    bounded(id, "chat_id", 128)?;
    bounded(title, "title", 512)?;
    scope(project_scope)?;
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM chats WHERE id=?1)",
        [id],
        |r| r.get(0),
    )?;
    if exists {
        return Err(CoreError::new("already_exists", "Chat ID already exists"));
    }
    tx.execute(
        "INSERT INTO chats(id,title,scope) VALUES(?1,?2,?3)",
        params![id, title, project_scope],
    )?;
    store::event(
        tx,
        "chat_created",
        json!({"chat_id":id,"scope":project_scope}),
    )?;
    Ok(json!({"chat_id":id,"title":title,"scope":project_scope}))
}

pub(crate) fn get(tx: &Transaction<'_>, id: &str, after: u64, limit: u32) -> CoreResult<Value> {
    bounded(id, "chat_id", 128)?;
    if after > i64::MAX as u64 || !(1..=100).contains(&limit) {
        return Err(CoreError::invalid("Invalid chat cursor or limit (1..100)"));
    }
    let chat: Option<(String, String)> = tx
        .query_row("SELECT title,scope FROM chats WHERE id=?1", [id], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .optional()?;
    let (title, project_scope) =
        chat.ok_or_else(|| CoreError::new("not_found", "Chat not found"))?;
    let mut q = tx.prepare("SELECT sequence,id,role,content FROM messages WHERE chat_id=?1 AND sequence>?2 ORDER BY sequence LIMIT ?3")?;
    let rows = q.query_map(params![id, after as i64, (limit + 1) as i64], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, String>(3)?,
        ))
    })?;
    let mut messages = Vec::new();
    let mut bytes = 0;
    let mut next_cursor = after;
    let mut has_more = false;
    for row in rows {
        let (sequence, message_id, role, content) = row?;
        if messages.len() >= limit as usize {
            has_more = true;
            break;
        }
        let message =
            json!({"sequence":sequence,"message_id":message_id,"role":role,"content":content});
        let size = serde_json::to_vec(&message)?.len();
        if bytes + size > 220_000 {
            if messages.is_empty() {
                return Err(CoreError::new(
                    "response_too_large",
                    "A stored message exceeds page byte budget",
                ));
            }
            has_more = true;
            break;
        }
        bytes += size;
        next_cursor = sequence as u64;
        messages.push(message);
    }
    Ok(
        json!({"chat_id":id,"title":title,"scope":project_scope,"messages":messages,"next_cursor":next_cursor,"has_more":has_more}),
    )
}

pub(crate) fn append(
    tx: &Transaction<'_>,
    chat_id: &str,
    id: &str,
    role: &MessageRole,
    content: &str,
) -> CoreResult<Value> {
    bounded(chat_id, "chat_id", 128)?;
    bounded(id, "message_id", 128)?;
    bounded(content, "content", 32_768)?;
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM chats WHERE id=?1)",
        [chat_id],
        |r| r.get(0),
    )?;
    if !exists {
        return Err(CoreError::new("not_found", "Chat not found"));
    }
    let duplicate: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM messages WHERE id=?1)",
        [id],
        |r| r.get(0),
    )?;
    if duplicate {
        return Err(CoreError::new(
            "already_exists",
            "Message ID already exists",
        ));
    }
    let role = serde_json::to_value(role)?.as_str().unwrap().to_owned();
    tx.execute(
        "INSERT INTO messages(id,chat_id,role,content) VALUES(?1,?2,?3,?4)",
        params![id, chat_id, role, content],
    )?;
    store::event(
        tx,
        "message_appended",
        json!({"chat_id":chat_id,"message_id":id,"role":role}),
    )?;
    Ok(json!({"chat_id":chat_id,"message_id":id,"role":role,"content":content}))
}
