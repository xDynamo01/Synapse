use crate::contracts::{CoreError, CoreResult};
use rusqlite::{Connection, Transaction, TransactionBehavior, params};
use serde::Serialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    path::{Path, PathBuf},
    time::Duration,
};

/// Sole authoritative SQLite connection. Workers must never receive it or its path.
pub(crate) struct Store {
    connection: Connection,
    _ownership_lock: File,
    pub(crate) state_dir: PathBuf,
}
impl Store {
    pub(crate) fn open(state_dir: &Path, workspace_root: &Path) -> CoreResult<Self> {
        std::fs::create_dir_all(state_dir)
            .map_err(|_| CoreError::new("storage_error", "Cannot create state directory"))?;
        let canonical_state = state_dir
            .canonicalize()
            .map_err(|_| CoreError::new("storage_error", "Cannot resolve state directory"))?;
        let ownership_lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .open(canonical_state.join(".synapse-core.lock"))
            .map_err(|_| CoreError::new("storage_error", "Cannot open state lock"))?;
        ownership_lock.try_lock().map_err(|_| {
            CoreError::new(
                "state_in_use",
                "State directory is owned by another Core process",
            )
        })?;
        let mut connection = Connection::open(canonical_state.join("core.sqlite3"))?;
        connection.busy_timeout(Duration::from_secs(5))?;
        connection.pragma_update(None, "foreign_keys", "ON")?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        connection.pragma_update(None, "synchronous", "FULL")?;
        let tx = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let version: u32 = tx.pragma_query_value(None, "user_version", |r| r.get(0))?;
        if version > 3 {
            return Err(CoreError::new(
                "unsupported_storage_version",
                "Database schema is newer than this Core",
            ));
        }
        if version == 0 {
            tx.execute_batch("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE receipts(request_id TEXT PRIMARY KEY,digest TEXT NOT NULL,response TEXT NOT NULL);
CREATE TABLE events(cursor INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT NOT NULL,scope TEXT NOT NULL);
CREATE TABLE messages(sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,chat_id TEXT NOT NULL REFERENCES chats(id),role TEXT NOT NULL,content TEXT NOT NULL);
CREATE TABLE memory(scope TEXT NOT NULL,key TEXT NOT NULL,revision INTEGER NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,provenance TEXT NOT NULL,PRIMARY KEY(scope,key,revision));
CREATE TABLE missions(id TEXT PRIMARY KEY,contract TEXT NOT NULL,contract_digest TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('proposed','approved','cancelled','revoked')),reason TEXT);
CREATE TABLE models(id TEXT PRIMARY KEY,manifest TEXT NOT NULL);
CREATE TABLE skills(id TEXT NOT NULL,version TEXT NOT NULL,scope TEXT NOT NULL,manifest TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(scope,id,version));
PRAGMA user_version=1;")?;
            tx.execute(
                "INSERT INTO metadata VALUES('workspace_root',?1)",
                [workspace_root.to_string_lossy().as_ref()],
            )?;
        }
        if version < 2 {
            tx.execute_batch("CREATE TABLE ai_jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,chat_id TEXT,model_id TEXT NOT NULL,status TEXT NOT NULL,result TEXT,error TEXT,user_message_id TEXT,assistant_message_id TEXT); PRAGMA user_version=2;")?;
        }
        if version < 3 {
            tx.execute_batch("CREATE TABLE tool_intents(request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, mission_id TEXT NOT NULL, target TEXT NOT NULL, content_digest TEXT NOT NULL, status TEXT NOT NULL); CREATE UNIQUE INDEX active_tool_target ON tool_intents(target) WHERE status='prepared'; PRAGMA user_version=3;")?;
        }
        let recorded: String = tx.query_row(
            "SELECT value FROM metadata WHERE key='workspace_root'",
            [],
            |r| r.get(0),
        )?;
        if recorded != workspace_root.to_string_lossy() {
            return Err(CoreError::new(
                "workspace_mismatch",
                "State belongs to another workspace",
            ));
        }
        let interrupted: Vec<String> = {
            let mut statement =
                tx.prepare("SELECT id FROM ai_jobs WHERE status='running' ORDER BY id")?;
            statement
                .query_map([], |r| r.get(0))?
                .collect::<Result<_, _>>()?
        };
        for id in interrupted {
            tx.execute(
                "UPDATE ai_jobs SET status='interrupted',error='worker_interrupted' WHERE id=?1",
                [&id],
            )?;
            event(&tx, "ai_job_interrupted", json!({"job_id":id}))?;
        }
        tx.commit()?;
        Ok(Self {
            connection,
            _ownership_lock: ownership_lock,
            state_dir: canonical_state,
        })
    }
    /// Domain extensions share this writer and one transaction per dispatcher request.
    pub(crate) fn transaction(&mut self) -> CoreResult<Transaction<'_>> {
        Ok(self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?)
    }
    pub(crate) fn event_cursor(&self) -> CoreResult<u64> {
        cursor(&self.connection)
    }
}
pub(crate) fn digest<T: Serialize>(value: &T) -> CoreResult<String> {
    Ok(Sha256::digest(serde_json::to_vec(value)?)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}
pub(crate) fn cursor(conn: &Connection) -> CoreResult<u64> {
    Ok(
        conn.query_row("SELECT COALESCE(MAX(cursor),0) FROM events", [], |r| {
            r.get::<_, i64>(0)
        })? as u64,
    )
}
pub(crate) fn event(tx: &Transaction<'_>, kind: &str, payload: Value) -> CoreResult<u64> {
    tx.execute(
        "INSERT INTO events(kind,payload) VALUES(?1,?2)",
        params![kind, payload.to_string()],
    )?;
    Ok(tx.last_insert_rowid() as u64)
}
pub(crate) fn events_read(tx: &Transaction<'_>, after: u64, limit: u32) -> CoreResult<Value> {
    if after > i64::MAX as u64 || !(1..=200).contains(&limit) {
        return Err(CoreError::invalid("Invalid event cursor or limit (1..200)"));
    }
    let mut q = tx.prepare(
        "SELECT cursor,kind,payload FROM events WHERE cursor>?1 ORDER BY cursor LIMIT ?2",
    )?;
    let rows = q.query_map(params![after as i64, limit], |r| {
        Ok((
            r.get::<_, i64>(0)? as u64,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
        ))
    })?;
    let mut events = Vec::new();
    for row in rows {
        let (cursor, kind, payload) = row?;
        events.push(
            json!({"cursor":cursor,"kind":kind,"payload":serde_json::from_str::<Value>(&payload)?}),
        );
    }
    Ok(
        json!({"events":events,"next_cursor":events.last().map(|v|v["cursor"].as_u64().unwrap()).unwrap_or(after)}),
    )
}
