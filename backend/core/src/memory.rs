use crate::{
    contracts::{CoreError, CoreResult, MemoryKind, MemoryStatus, Provenance, bounded, scope},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

pub(crate) fn put(
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
    let result = json!({"scope":project_scope,"key":key,"revision":revision,"kind":kind,"content":content,"status":status,"provenance":provenance});
    tx.execute("INSERT INTO memory(scope,key,revision,kind,content,status,provenance) VALUES(?1,?2,?3,?4,?5,?6,?7)",params![project_scope,key,revision,kind,content,status,provenance_json])?;
    let origin = store::event(
        tx,
        "memory_revision_created",
        json!({"scope":project_scope,"key":key,"revision":revision,"kind":kind,"status":status}),
    )?;
    tx.execute(
        "UPDATE memory SET origin_cursor=?4 WHERE scope=?1 AND key=?2 AND revision=?3",
        params![project_scope, key, revision, origin as i64],
    )?;
    Ok(result)
}

pub(crate) fn get(
    tx: &Transaction<'_>,
    project_scope: &str,
    context_reference: &str,
    key: &str,
    after_revision: u64,
    limit: u32,
) -> CoreResult<Value> {
    explicit_gate(project_scope, context_reference, key)?;
    if after_revision > i64::MAX as u64 || !(1..=100).contains(&limit) {
        return Err(CoreError::invalid(
            "Invalid memory revision cursor or limit (1..100)",
        ));
    }
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM memory WHERE scope=?1 AND key=?2)",
        params![project_scope, key],
        |r| r.get(0),
    )?;
    if !exists {
        return Err(CoreError::new(
            "not_found",
            "Memory key not found in context",
        ));
    }
    let mut q=tx.prepare("SELECT revision,kind,content,status,provenance FROM memory WHERE scope=?1 AND key=?2 AND revision>?3 ORDER BY revision LIMIT ?4")?;
    let rows = q.query_map(
        params![
            project_scope,
            key,
            after_revision as i64,
            (limit + 1) as i64
        ],
        |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, String>(3)?,
                r.get::<_, String>(4)?,
            ))
        },
    )?;
    let mut revisions = Vec::new();
    let mut bytes = 0;
    let mut next_revision = after_revision;
    let mut has_more = false;
    for row in rows {
        let (revision, kind, content, status, provenance) = row?;
        if revisions.len() >= limit as usize {
            has_more = true;
            break;
        }
        let record = json!({"revision":revision,"kind":kind,"content":content,"status":status,"provenance":serde_json::from_str::<Value>(&provenance)?});
        let size = serde_json::to_vec(&record)?.len();
        if bytes + size > 220_000 {
            if revisions.is_empty() {
                return Err(CoreError::new(
                    "response_too_large",
                    "A stored memory record exceeds page byte budget",
                ));
            }
            has_more = true;
            break;
        }
        bytes += size;
        next_revision = revision as u64;
        revisions.push(record);
    }
    Ok(
        json!({"scope":project_scope,"key":key,"revisions":revisions,"next_revision":next_revision,"has_more":has_more}),
    )
}

fn explicit_gate(project_scope: &str, context_reference: &str, key: &str) -> CoreResult<()> {
    scope(project_scope)?;
    scope(context_reference)?;
    bounded(key, "key", 256)?;
    if project_scope != context_reference {
        return Err(CoreError::new(
            "context_denied",
            "Explicit context does not match the memory scope",
        ));
    }
    Ok(())
}

/// Exact, explicitly granted read; inactive latest revisions never fall back to history.
pub(crate) fn latest_active(
    tx: &Transaction<'_>,
    project_scope: &str,
    context_reference: &str,
    key: &str,
) -> CoreResult<Value> {
    explicit_gate(project_scope, context_reference, key)?;
    let record: Option<(i64, String, String, String)> = tx.query_row(
        "SELECT revision,kind,content,status FROM memory WHERE scope=?1 AND key=?2 ORDER BY revision DESC LIMIT 1",
        params![project_scope,key],
        |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?)),
    ).optional()?;
    let (revision, kind, content, status) =
        record.ok_or_else(|| CoreError::new("not_found", "Memory key not found in context"))?;
    if status != "active" {
        return Err(CoreError::new(
            "context_inactive",
            "Latest memory revision is not active",
        ));
    }
    Ok(json!({"scope":project_scope,"key":key,"revision":revision,"kind":kind,"content":content}))
}
