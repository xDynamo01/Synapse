use crate::{
    contracts::{CoreError, CoreResult, MemoryKind, MemoryStatus, Provenance, bounded, scope},
    store,
};
use rusqlite::{Transaction, params};
use serde_json::{Value, json};

pub fn put(
    tx: &Transaction<'_>,
    project_scope: &str,
    key: &str,
    kind: &MemoryKind,
    content: &str,
    expected_revision: u64,
    provenance: &Provenance,
    status: &MemoryStatus,
) -> CoreResult<Value> {
    scope(project_scope)?;
    bounded(key, "key", 256)?;
    bounded(content, "content", 32_768)?;
    bounded(&provenance.source_type, "source_type", 64)?;
    bounded(&provenance.source_id, "source_id", 256)?;
    bounded(&provenance.evidence, "evidence", 2048)?;
    if expected_revision >= i64::MAX as u64 {
        return Err(CoreError::invalid("Invalid expected revision"));
    }
    let current: i64 = tx.query_row(
        "SELECT COALESCE(MAX(revision),0) FROM memory WHERE scope=?1 AND key=?2",
        params![project_scope, key],
        |r| r.get(0),
    )?;
    if current as u64 != expected_revision {
        return Err(CoreError::new(
            "revision_conflict",
            "Canonical memory revision changed",
        ));
    }
    let revision = current + 1;
    let kind = serde_json::to_value(kind)?.as_str().unwrap().to_owned();
    let status = serde_json::to_value(status)?.as_str().unwrap().to_owned();
    let provenance_json = serde_json::to_string(provenance)?;
    tx.execute("INSERT INTO memory(scope,key,revision,kind,content,status,provenance) VALUES(?1,?2,?3,?4,?5,?6,?7)",params![project_scope,key,revision,kind,content,status,provenance_json])?;
    store::event(
        tx,
        "memory_revision_created",
        json!({"scope":project_scope,"key":key,"revision":revision,"kind":kind,"status":status}),
    )?;
    Ok(
        json!({"scope":project_scope,"key":key,"revision":revision,"kind":kind,"content":content,"status":status,"provenance":provenance}),
    )
}

pub fn get(
    tx: &Transaction<'_>,
    project_scope: &str,
    context_reference: &str,
    key: &str,
) -> CoreResult<Value> {
    scope(project_scope)?;
    scope(context_reference)?;
    bounded(key, "key", 256)?;
    if project_scope != context_reference {
        return Err(CoreError::new(
            "context_denied",
            "Explicit context does not match the memory scope",
        ));
    }
    let mut q=tx.prepare("SELECT revision,kind,content,status,provenance FROM memory WHERE scope=?1 AND key=?2 ORDER BY revision")?;
    let rows = q.query_map(params![project_scope, key], |r| {
        Ok((
            r.get::<_, i64>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, String>(3)?,
            r.get::<_, String>(4)?,
        ))
    })?;
    let mut revisions = Vec::new();
    for row in rows {
        let (revision, kind, content, status, provenance) = row?;
        revisions.push(json!({"revision":revision,"kind":kind,"content":content,"status":status,"provenance":serde_json::from_str::<Value>(&provenance)?}));
    }
    if revisions.is_empty() {
        return Err(CoreError::new(
            "not_found",
            "Memory key not found in context",
        ));
    }
    Ok(json!({"scope":project_scope,"key":key,"revisions":revisions}))
}
