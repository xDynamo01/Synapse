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
        if version > 11 {
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
        if version < 4 {
            tx.execute_batch("CREATE TABLE replacement_backups(request_id TEXT PRIMARY KEY REFERENCES tool_intents(request_id), operation TEXT NOT NULL, identity TEXT NOT NULL, previous_digest TEXT NOT NULL, backup BLOB NOT NULL); CREATE TABLE intent_operations(request_id TEXT PRIMARY KEY REFERENCES tool_intents(request_id), operation TEXT NOT NULL); CREATE TABLE recovery_writes(request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, intent_id TEXT NOT NULL REFERENCES tool_intents(request_id), expected_hash TEXT NOT NULL, status TEXT NOT NULL); PRAGMA user_version=4;")?;
        }
        if version < 5 {
            tx.execute_batch("ALTER TABLE ai_jobs ADD COLUMN generation TEXT NOT NULL DEFAULT '{\"max_output_tokens\":1024,\"timeout_ms\":10000,\"reasoning_effort\":\"provider_default\"}'; PRAGMA user_version=5;")?;
        }
        if version < 6 {
            tx.execute_batch("ALTER TABLE ai_jobs ADD COLUMN endpoint TEXT NOT NULL DEFAULT ''; ALTER TABLE ai_jobs ADD COLUMN source_cursor INTEGER NOT NULL DEFAULT 0; ALTER TABLE memory ADD COLUMN origin_cursor INTEGER NOT NULL DEFAULT 0; CREATE TABLE learning_jobs(source_job_id TEXT PRIMARY KEY REFERENCES ai_jobs(id), status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT); CREATE TABLE learning_conflicts(source_job_id TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(source_job_id,scope,key)); PRAGMA user_version=6;")?;
            // Existing manual records predate origin tracking; place them after all
            // existing source events rather than allowing an old extraction to win.
            tx.execute(
                "UPDATE memory SET origin_cursor=(SELECT COALESCE(MAX(cursor),0) FROM events)",
                [],
            )?;
        }
        if version < 7 {
            tx.execute_batch("ALTER TABLE ai_jobs ADD COLUMN skill TEXT; PRAGMA user_version=7;")?;
        }
        if version < 8 {
            tx.execute_batch(
                "ALTER TABLE ai_jobs ADD COLUMN context TEXT; PRAGMA user_version=8;",
            )?;
        }
        if version < 9 {
            tx.execute_batch("CREATE TABLE mission_plans(mission_id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL REFERENCES ai_jobs(id),snapshot TEXT NOT NULL,plan TEXT,sealed_contract TEXT); PRAGMA user_version=9;")?;
        }
        if version < 10 {
            tx.execute_batch("
CREATE TABLE project_checks(
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    contract_digest TEXT NOT NULL,
    check_index INTEGER NOT NULL,
    candidate_digest TEXT NOT NULL,
    check_digest TEXT NOT NULL,
    tool_digest TEXT,
    run_name TEXT NOT NULL UNIQUE,
    run_directory TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','cancelled','revoked','interrupted')),
    cleanup TEXT NOT NULL CHECK(cleanup IN ('pending','complete','unverified')),
    receipt TEXT,
    error TEXT
);
CREATE UNIQUE INDEX one_active_project_check ON project_checks((1)) WHERE cleanup='pending';
PRAGMA user_version=10;")?;
        }
        if version < 11 {
            tx.execute_batch("
CREATE TABLE mission_runs(
    mission_id TEXT PRIMARY KEY REFERENCES missions(id),
    contract_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('generating','checking','reviewing','review_ready','failed','rejected','cancelled','revoked','interrupted')),
    ai_id TEXT UNIQUE,
    candidate TEXT,
    candidate_digest TEXT,
    check_index INTEGER NOT NULL DEFAULT 0,
    check_id TEXT UNIQUE REFERENCES project_checks(id),
    review TEXT,
    error TEXT
);
CREATE UNIQUE INDEX one_active_mission_run ON mission_runs((1)) WHERE status IN ('generating','checking','reviewing');
PRAGMA user_version=11;")?;
        }
        tx.execute("UPDATE learning_jobs SET status=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,error='worker_interrupted' WHERE status='running'", [])?;
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
        crate::checks::interrupt(&tx)?;
        crate::mission_run::interrupt(&tx)?;
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
