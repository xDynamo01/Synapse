use std::path::Path;

use rusqlite::{OptionalExtension, Transaction};
use serde_json::{Value, json};

use crate::{
    contracts::{CoreError, CoreResult, ToolOperation, bounded},
    store, tools,
};

pub(crate) struct JournalEntry {
    pub position: u32,
    pub intent_id: String,
    pub journal_status: String,
    pub identity: Option<String>,
    pub intent_status: String,
    pub target: String,
    pub expected_sha256: String,
    pub path: String,
    pub content: String,
    pub replacement: bool,
}

pub(crate) fn journal(
    tx: &Transaction<'_>,
    mission: &str,
    contract_digest: &str,
    candidate_digest: Option<&str>,
) -> CoreResult<Vec<JournalEntry>> {
    let mut statement = tx.prepare(
        "SELECT f.intent_id,f.status,f.identity,i.status,i.target,i.content_digest,o.operation,
        i.request_digest,i.mission_id,f.position
        FROM mission_integration_files f JOIN tool_intents i ON i.request_id=f.intent_id
        JOIN intent_operations o ON o.request_id=f.intent_id
        WHERE f.mission_id=?1 ORDER BY f.position",
    )?;
    let mut rows = statement.query([mission])?;
    let mut entries = Vec::new();
    while let Some(row) = rows.next()? {
        let intent_id: String = row.get(0)?;
        let journal_status: String = row.get(1)?;
        let identity: Option<String> = row.get(2)?;
        let intent_status: String = row.get(3)?;
        let target: String = row.get(4)?;
        let expected_sha256: String = row.get(5)?;
        let operation: ToolOperation = serde_json::from_str(&row.get::<_, String>(6)?)?;
        let request_digest: String = row.get(7)?;
        let intent_mission: String = row.get(8)?;
        if intent_mission != mission
            || request_digest != store::digest(&(contract_digest, candidate_digest, &operation))?
        {
            return Err(CoreError::new("journal_mismatch", "Create intent changed"));
        }
        let (path, content, replacement) = match operation {
            ToolOperation::Create { path, content } => (path, content, false),
            ToolOperation::Replace { path, content } => (path, content, true),
            _ => {
                return Err(CoreError::new(
                    "journal_mismatch",
                    "Expected a publication intent",
                ));
            }
        };
        if tools::sha(content.as_bytes()) != expected_sha256 {
            return Err(CoreError::new(
                "journal_mismatch",
                "Create intent digest changed",
            ));
        }

        entries.push(JournalEntry {
            position: row.get(9)?,
            intent_id,
            journal_status,
            identity,
            intent_status,
            target,
            expected_sha256,
            path,
            content,
            replacement,
        });
    }
    let expected: u32 = tx.query_row(
        "SELECT COUNT(*) FROM mission_integration_files WHERE mission_id=?1",
        [mission],
        |row| row.get(0),
    )?;
    if entries.len() != expected as usize || entries.len() > 16 {
        return Err(CoreError::new(
            "journal_mismatch",
            "Incomplete integration journal",
        ));
    }
    Ok(entries)
}

pub(crate) fn inspect(
    tx: &Transaction<'_>,
    mission: &str,
    workspace: &Path,
    state: &Path,
) -> CoreResult<Value> {
    bounded(mission, "mission_id", 128)?;
    let (status, error, root_identity, contract_digest, candidate_digest) = tx
        .query_row(
            "SELECT i.status,i.error,i.workspace_identity,r.contract_digest,r.candidate_digest
            FROM mission_integrations i JOIN mission_runs r ON r.mission_id=i.mission_id
            WHERE i.mission_id=?1",
            [mission],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<String>>(1)?,
                    row.get::<_, Option<String>>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, Option<String>>(4)?,
                ))
            },
        )
        .optional()?
        .ok_or_else(|| CoreError::new("not_found", "Mission integration not found"))?;

    let entries = journal(tx, mission, &contract_digest, candidate_digest.as_deref())?;
    let mut files = Vec::new();
    for entry in entries {
        let JournalEntry {
            intent_id,
            journal_status,
            identity,
            intent_status,
            target,
            expected_sha256,
            path,
            content,
            ..
        } = entry;
        let observation = (|| {
            let broker = tools::prepare(
                workspace,
                state,
                &ToolOperation::Read { path: path.clone() },
            )?;
            if Some(broker.root_identity()?.as_str()) != root_identity.as_deref()
                || broker.target() != target
            {
                return Err(CoreError::new(
                    "workspace_changed",
                    "Workspace or journal target changed",
                ));
            }
            if broker.create_is_absent()? {
                return Ok(("absent", None, None));
            }
            let observed = broker.read_owned_guarded()?;
            let classification = match identity.as_deref() {
                _ if observed.bytes != content.as_bytes() => "changed",
                Some(expected) if expected == observed.identity => "verified_owned",
                Some(_) => "changed",
                None => "matching_bytes_unproven",
            };
            Ok((
                classification,
                Some(tools::sha(&observed.bytes)),
                Some(observed.identity),
            ))
        })();
        let (classification, observed_sha256, observed_identity, observation_error) =
            match observation {
                Ok((classification, digest, identity)) => (classification, digest, identity, None),
                Err(error) => ("unreadable", None, None, Some(error.code)),
            };
        files.push(json!({
            "path":path,"intent_id":intent_id,"journal_status":journal_status,
            "intent_status":intent_status,"identity_recorded":identity.is_some(),
            "expected_identity":identity,"observed_identity":observed_identity,
            "expected_sha256":expected_sha256,"observed_sha256":observed_sha256,
            "classification":classification,"observation_error":observation_error,
        }));
    }
    Ok(json!({"mission_id":mission,"status":status,"error":error,"files":files}))
}
