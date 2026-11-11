//! Approval and durable state for the private project check worker.
use std::path::Path;

use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

use crate::{
    candidate,
    contracts::{CandidateArtifact, CheckKind, CoreError, CoreResult, MissionContract, bounded},
    planner, runner, store,
};

pub(crate) fn start(
    tx: &Transaction<'_>,
    id: &str,
    mission_id: &str,
    check_index: u32,
    candidates: &[CandidateArtifact],
    state: &Path,
    workspace: &Path,
) -> CoreResult<(Value, runner::Launch)> {
    bounded(mission_id, "mission_id", 128)?;
    let row: Option<(String, String, String)> = tx
        .query_row(
            "SELECT contract,contract_digest,state FROM missions WHERE id=?1",
            [mission_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()?;
    let (serialized, contract_digest, status) =
        row.ok_or_else(|| CoreError::new("not_found", "Mission not found"))?;
    let contract: MissionContract = serde_json::from_str(&serialized)?;
    if status != "approved"
        || !contract
            .actions
            .iter()
            .any(|action| action == "project_check")
    {
        return Err(CoreError::new(
            "permission_denied",
            "Mission is not approved for project checks",
        ));
    }
    if store::digest(&contract)? != contract_digest {
        return Err(CoreError::new(
            "contract_conflict",
            "Mission contract differs from approved digest",
        ));
    }
    let policy = contract.execution.as_ref().ok_or_else(|| {
        CoreError::new(
            "permission_denied",
            "Mission has no sealed execution policy",
        )
    })?;
    planner::validate_seal(tx, mission_id, &contract)?;
    let recipe = policy
        .checks
        .get(check_index as usize)
        .ok_or_else(|| CoreError::invalid("Check index is outside the approved plan"))?;

    candidate::validate_artifacts(&contract, candidates)?;
    let busy: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM project_checks WHERE cleanup='pending')",
        [],
        |row| row.get(0),
    )?;
    if busy {
        return Err(CoreError::new(
            "project_check_busy",
            "A project check is running or cleaning up",
        ));
    }
    let tools = runner::Tools::configure(&recipe.kind).map_err(|code| {
        CoreError::new(code, "The required native check toolchain is unavailable")
    })?;
    let mut artifacts = candidates.to_vec();
    artifacts.sort_unstable_by(|left, right| left.path.cmp(&right.path));
    let candidate_digest = store::digest(&artifacts)?;
    let check_digest = store::digest(&(&contract_digest, check_index, recipe, &policy.limits))?;
    let parent = if matches!(recipe.kind, CheckKind::RustTest) {
        match std::env::var_os("SYNAPSE_CHECK_RUST_RUN_ROOT") {
            Some(value) if Path::new(&value).is_absolute() => std::fs::canonicalize(value)
                .ok()
                .filter(|path| path.is_dir())
                .ok_or_else(|| CoreError::new("run_path_unavailable", "Invalid Rust run root"))?,
            Some(_) => {
                return Err(CoreError::new(
                    "run_path_unavailable",
                    "Rust run root must be absolute",
                ));
            }
            None => state.to_owned(),
        }
    } else {
        state.to_owned()
    };
    let root_digest = store::digest(&(state.to_string_lossy(), id, &candidate_digest))?;
    let run_name = format!("Synapse.Check.{}", &root_digest[..32]);
    let root = parent.join(&run_name);
    let workspace_path = workspace.to_string_lossy();
    if root
        .ancestors()
        .any(|path| path.to_string_lossy().eq_ignore_ascii_case(&workspace_path))
    {
        return Err(CoreError::new(
            "run_path_unavailable",
            "Check staging must be outside the Workspace",
        ));
    }
    tx.execute(
        "INSERT INTO project_checks(id,mission_id,contract_digest,check_index,candidate_digest,check_digest,run_name,run_directory,status,cleanup)
         VALUES(?1,?2,?3,?4,?5,?6,?7,?8,'running','pending')",
        params![id, mission_id, contract_digest, check_index, candidate_digest, check_digest, run_name, root.to_string_lossy().as_ref()],
    )?;
    store::event(
        tx,
        "project_check_started",
        json!({"check_id": id, "mission_id": mission_id}),
    )?;
    let result = get(tx, id)?;
    Ok((
        result,
        runner::Launch {
            id: id.into(),
            mission_id: mission_id.into(),
            root,
            profile_name: run_name,
            artifacts,
            recipe: recipe.clone(),
            tools,
        },
    ))
}

pub(crate) fn get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "check_id", 128)?;
    let result = tx.query_row(
        "SELECT mission_id,contract_digest,check_index,candidate_digest,check_digest,tool_digest,status,cleanup,receipt,error
         FROM project_checks WHERE id=?1",
        [id], |row| {
            Ok((json!({
                "check_id":id,"mission_id":row.get::<_,String>(0)?,"contract_digest":row.get::<_,String>(1)?,
                "check_index":row.get::<_,u32>(2)?,"candidate_digest":row.get::<_,String>(3)?,
                "check_digest":row.get::<_,String>(4)?,"tool_digest":row.get::<_,Option<String>>(5)?,
                "status":row.get::<_,String>(6)?,"cleanup":row.get::<_,String>(7)?,
                "error":row.get::<_,Option<String>>(9)?,
            }), row.get::<_,Option<String>>(8)?))
        },
    ).optional()?;
    let (mut value, receipt) =
        result.ok_or_else(|| CoreError::new("not_found", "Project check not found"))?;
    value["receipt"] = receipt
        .map(|json| serde_json::from_str(&json))
        .transpose()?
        .unwrap_or(Value::Null);
    Ok(value)
}

pub(crate) fn cancel(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    let status = get(tx, id)?;
    if status["status"] != "running" {
        return Err(CoreError::new(
            "invalid_transition",
            "Only a running project check can be cancelled",
        ));
    }
    tx.execute(
        "UPDATE project_checks SET status='cancelled',error='cancelled' WHERE id=?1",
        [id],
    )?;
    store::event(tx, "project_check_cancelled", json!({"check_id": id}))?;
    get(tx, id)
}

pub(crate) fn stop_mission(tx: &Transaction<'_>, mission: &str, status: &str) -> CoreResult<()> {
    let id = tx.query_row(
        "UPDATE project_checks SET status=?2,error=?2 WHERE mission_id=?1 AND status='running' RETURNING id",
        params![mission, status], |row| row.get::<_,String>(0),
    ).optional()?;
    if let Some(id) = id {
        store::event(
            tx,
            "project_check_stopped",
            json!({"check_id": id, "status": status}),
        )?;
    }
    Ok(())
}

pub(crate) fn prepare(tx: &Transaction<'_>, id: &str, digest: &str) -> CoreResult<bool> {
    Ok(tx.execute(
        "UPDATE project_checks SET tool_digest=?2 WHERE id=?1 AND status='running' AND tool_digest IS NULL
         AND EXISTS(SELECT 1 FROM missions WHERE id=project_checks.mission_id
            AND state='approved' AND contract_digest=project_checks.contract_digest)",
        params![id, digest],
    )? == 1)
}

pub(crate) fn finish(tx: &Transaction<'_>, id: &str, outcome: &runner::Outcome) -> CoreResult<()> {
    let status = if outcome.error.is_none() && outcome.cleanup_complete {
        "succeeded"
    } else {
        "failed"
    };
    let cleanup = if outcome.cleanup_complete {
        "complete"
    } else {
        "unverified"
    };
    let receipt = outcome
        .receipt
        .as_ref()
        .map(serde_json::to_string)
        .transpose()?;
    tx.execute(
        "UPDATE project_checks SET cleanup=?2,
         receipt=CASE WHEN status='running' THEN ?3 ELSE receipt END,
         error=CASE WHEN status='running' THEN ?4 ELSE error END,
         status=CASE WHEN status='running' THEN ?5 ELSE status END
         WHERE id=?1 AND cleanup='pending'",
        params![id, cleanup, receipt, outcome.error, status],
    )?;
    store::event(
        tx,
        "project_check_finished",
        json!({"check_id":id,"cleanup":cleanup}),
    )?;
    Ok(())
}

pub(crate) fn shutdown(
    tx: &Transaction<'_>,
    id: &str,
    outcome: &runner::Outcome,
) -> CoreResult<()> {
    if outcome.error == Some("cancelled") {
        tx.execute(
            "UPDATE project_checks SET status='interrupted',error='core_shutdown'
         WHERE id=?1 AND status='running'",
            [id],
        )?;
    }
    finish(tx, id, outcome)
}

pub(crate) fn interrupt(tx: &Transaction<'_>) -> CoreResult<()> {
    let rows = {
        let mut update = tx.prepare(
            "UPDATE project_checks SET cleanup='unverified',
             error=CASE WHEN status='running' THEN 'worker_interrupted' ELSE error END,
             status=CASE WHEN status='running' THEN 'interrupted' ELSE status END
             WHERE cleanup='pending' RETURNING id",
        )?;
        update
            .query_map([], |row| row.get::<_, String>(0))?
            .collect::<Result<Vec<_>, _>>()?
    };
    for id in rows {
        store::event(
            tx,
            "project_check_interrupted",
            json!({"check_id":id,"cleanup":"unverified"}),
        )?;
    }
    Ok(())
}
