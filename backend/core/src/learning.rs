use crate::{
    contracts::{CoreError, CoreResult, Generation},
    conversation::Launch,
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Batch {
    candidates: Vec<Candidate>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Candidate {
    key: String,
    kind: String,
    content: String,
}

fn credential(s: &str) -> bool {
    let s = s.to_ascii_lowercase();
    [
        "password",
        "passwd",
        "senha",
        "api_key",
        "api-key",
        "api key",
        "token",
        "access_token",
        "secret",
        "private key",
        "private-key",
        "private_key",
        "-----begin",
        "bearer ",
    ]
    .iter()
    .any(|p| s.contains(p))
}

pub(crate) fn start(tx: &Transaction<'_>) -> CoreResult<Option<Launch>> {
    let row: Option<(String,String,String,String,String,String)> = tx.query_row(
        "SELECT l.source_job_id,j.model_id,j.endpoint,j.generation,m.content,m.id FROM learning_jobs l JOIN ai_jobs j ON j.id=l.source_job_id JOIN messages m ON m.id=j.user_message_id WHERE l.status='queued' ORDER BY j.source_cursor LIMIT 1", [],
        |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?))).optional()?;
    let Some((id, model_id, endpoint, generation, content, _)) = row else {
        return Ok(None);
    };
    let generation: Generation = serde_json::from_str(&generation)?;
    tx.execute("UPDATE learning_jobs SET status='running',attempts=attempts+1,error=NULL WHERE source_job_id=?1", [&id])?;
    Ok(Some(Launch {
        id,
        model_id,
        endpoint,
        generation,
        learning: true,
        messages: vec![
            json!({"role":"system","content":"Select up to eight durable facts, constraints or decisions stated by the human. Return JSON candidates with lowercase subject slug key, kind, and exact short source quote as content. Return an empty list when none. Exclude credentials, secrets, transient commands, failed attempts and assistant text. Never infer or paraphrase."}),
            json!({"role":"user","content":content}),
        ],
    }))
}

pub(crate) fn requeue(tx: &Transaction<'_>, id: &str) -> CoreResult<()> {
    tx.execute("UPDATE learning_jobs SET status='queued',attempts=MAX(0,attempts-1),error=NULL WHERE source_job_id=?1 AND status='running'", [id])?;
    Ok(())
}

pub(crate) fn get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    let row: Option<(String,i64,Option<String>,i64)> = tx.query_row("SELECT status,attempts,error,(SELECT COUNT(*) FROM learning_conflicts WHERE source_job_id=?1) FROM learning_jobs WHERE source_job_id=?1", [id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional()?;
    let (status, attempts, error, conflicts) =
        row.ok_or_else(|| CoreError::new("not_found", "Learning job not found"))?;
    let mut statement = tx
        .prepare("SELECT key,reason FROM learning_conflicts WHERE source_job_id=?1 ORDER BY key")?;
    let pending = statement.query_map([id], |r| Ok(json!({"key":r.get::<_,String>(0)?,"reason":r.get::<_,String>(1)?,"status":"pending"})))?.collect::<Result<Vec<_>,_>>()?;
    Ok(
        json!({"source_job_id":id,"status":status,"attempts":attempts,"error":error,"conflicts":conflicts,"pending_conflicts":pending}),
    )
}

pub(crate) fn complete(
    tx: &Transaction<'_>,
    id: &str,
    outcome: Result<String, String>,
) -> CoreResult<()> {
    let row: Option<(String,String,String,i64)> = tx.query_row("SELECT c.scope,m.content,m.id,j.source_cursor FROM learning_jobs l JOIN ai_jobs j ON j.id=l.source_job_id JOIN chats c ON c.id=j.chat_id JOIN messages m ON m.id=j.user_message_id WHERE l.source_job_id=?1 AND l.status='running'", [id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional()?;
    let Some((scope, source, message_id, cursor)) = row else {
        return Ok(());
    };
    let text = match outcome {
        Ok(v) => v,
        Err(code) => {
            tx.execute("UPDATE learning_jobs SET status=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,error=?2 WHERE source_job_id=?1",params![id,code])?;
            return Ok(());
        }
    };
    let batch = serde_json::from_str::<Batch>(&text);
    let valid = batch.as_ref().is_ok_and(|batch| {
        batch.candidates.len() <= 8
            && batch.candidates.iter().all(|c| {
                !c.key.is_empty()
                    && c.key.len() <= 64
                    && c.key.bytes().all(|b| {
                        b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_'
                    })
                    && matches!(c.kind.as_str(), "fact" | "constraint" | "decision")
                    && !c.content.trim().is_empty()
                    && c.content.len() <= 512
                    && source.contains(&c.content)
                    && !credential(&c.key)
                    && !credential(&c.content)
            })
            && batch
                .candidates
                .iter()
                .enumerate()
                .all(|(i, c)| batch.candidates[..i].iter().all(|p| p.key != c.key))
    });
    if !valid {
        tx.execute("UPDATE learning_jobs SET status='failed',error='invalid_candidates' WHERE source_job_id=?1",[id])?;
        store::event(
            tx,
            "learning_failed",
            json!({"source_job_id":id,"code":"invalid_candidates"}),
        )?;
        return Ok(());
    }
    let batch = batch.unwrap();
    for c in &batch.candidates {
        let current: Option<(i64,String,String,i64)> = tx.query_row("SELECT revision,kind,content,origin_cursor FROM memory WHERE scope=?1 AND key=?2 ORDER BY revision DESC LIMIT 1",params![scope,c.key],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional()?;
        if let Some((_, kind, content, origin)) = &current {
            if *origin > cursor || kind != &c.kind {
                tx.execute(
                    "INSERT INTO learning_conflicts VALUES(?1,?2,?3,?4)",
                    params![
                        id,
                        scope,
                        c.key,
                        if *origin > cursor {
                            "stale_source"
                        } else {
                            "kind_conflict"
                        }
                    ],
                )?;
                continue;
            }
            if content == &c.content {
                tx.execute(
                    "UPDATE memory SET origin_cursor=?4 WHERE scope=?1 AND key=?2 AND revision=?3",
                    params![scope, c.key, current.as_ref().unwrap().0, cursor],
                )?;
                continue;
            }
        }
        let rev = current.map_or(1, |v| v.0 + 1);
        let provenance = json!({"source_type":"conversation_user","source_id":message_id,"source_job_id":id,"evidence":c.content});
        tx.execute("INSERT INTO memory(scope,key,revision,kind,content,status,provenance,origin_cursor) VALUES(?1,?2,?3,?4,?5,'active',?6,?7)",params![scope,c.key,rev,c.kind,c.content,provenance.to_string(),cursor])?;
        store::event(
            tx,
            "memory_revision_created",
            json!({"scope":scope,"key":c.key,"revision":rev,"kind":c.kind,"status":"active"}),
        )?;
    }
    tx.execute(
        "UPDATE learning_jobs SET status='succeeded',error=NULL WHERE source_job_id=?1",
        [id],
    )?;
    store::event(tx, "learning_succeeded", json!({"source_job_id":id}))?;
    Ok(())
}
