//! Durable pre-integration coordinator. Only Core may advance this state.
use std::path::Path;

use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

use crate::{
    candidate, checks, context,
    contracts::{CandidateArtifact, CoreError, CoreResult, MissionContract, bounded},
    conversation::{Launch, Purpose},
    planner, runner, skills, store,
};

const ACTIVE: &str = "('generating','checking','reviewing')";
pub(crate) const INTERNAL_PREFIX: &str = "internal-mission-";

pub(crate) enum Next {
    Check(runner::Launch),
    Review(Launch),
}

pub(crate) fn approved(tx: &Transaction<'_>, id: &str) -> CoreResult<(MissionContract, String)> {
    bounded(id, "mission_id", 128)?;
    let row: Option<(String, String, String)> = tx
        .query_row(
            "SELECT contract,contract_digest,state FROM missions WHERE id=?1",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()?;
    let (contract, digest, status) = row.ok_or_else(|| {
        CoreError::new(
            "capability_unavailable",
            "No sealed execution policy for mission",
        )
    })?;
    let contract: MissionContract = serde_json::from_str(&contract)?;
    if contract.execution.is_none() {
        return Err(CoreError::new(
            "capability_unavailable",
            "Mission has no sealed execution policy",
        ));
    }
    if status != "approved"
        || !contract
            .actions
            .iter()
            .any(|action| action == "mission_generate")
    {
        return Err(CoreError::new(
            "permission_denied",
            "Mission is not approved for generation",
        ));
    }
    planner::validate_seal(tx, id, &contract)?;
    if store::digest(&contract)? != digest {
        return Err(CoreError::new(
            "contract_conflict",
            "Approved mission digest differs",
        ));
    }
    Ok((contract, digest))
}

pub(crate) fn stage_id(mission: &str, stage: &str) -> CoreResult<String> {
    Ok(format!(
        "{INTERNAL_PREFIX}{}",
        store::digest(&(mission, stage))?
    ))
}

pub(crate) fn start(
    tx: &Transaction<'_>,
    mission: &str,
    ai_busy: bool,
) -> CoreResult<(Value, Launch)> {
    let (contract, digest) = approved(tx, mission)?;
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM mission_runs WHERE mission_id=?1)",
        [mission],
        |row| row.get(0),
    )?;
    if exists {
        return Err(CoreError::new(
            "already_exists",
            "Mission already has a run",
        ));
    }
    let busy: bool = tx.query_row(
        &format!("SELECT EXISTS(SELECT 1 FROM mission_runs r WHERE status IN {ACTIVE}
            OR (status='review_ready' AND auto_integrate=1 AND NOT EXISTS(
                 SELECT 1 FROM mission_integrations i WHERE i.mission_id=r.mission_id))
            UNION ALL SELECT 1 FROM mission_integrations WHERE status IN ('publishing','postchecking','rolling_back'))"),
        [],
        |row| row.get(0),
    )?;
    if ai_busy || busy {
        return Err(CoreError::new(
            "mission_run_busy",
            "Another run or model job is active",
        ));
    }
    let id = stage_id(mission, "generation")?;
    let mut launch = candidate::generation(&id, &contract)?;
    if let Some(skill) = &contract.skill {
        launch
            .messages
            .insert(1, skills::guidance_for_scope(tx, &contract.scope, skill)?);
        launch.messages = context::finalize_candidate(launch.messages)?;
    }
    tx.execute(
        "INSERT INTO mission_runs(mission_id,contract_digest,status,ai_id,auto_integrate)
         VALUES(?1,?2,'generating',?3,1)",
        params![mission, digest, id],
    )?;
    store::event(tx, "mission_run_started", json!({"mission_id":mission}))?;
    Ok((get(tx, mission)?, launch))
}

pub(crate) fn get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "mission_id", 128)?;
    let result = tx
        .query_row(
            "SELECT contract_digest,status,candidate_digest,check_index,check_id,review,error
         FROM mission_runs WHERE mission_id=?1",
            [id],
            |row| {
                let status: String = row.get(1)?;
                let check_id: Option<String> = row.get(4)?;
                Ok((
                    json!({
                        "mission_id":id, "contract_digest":row.get::<_,String>(0)?,
                        "status":status, "candidate_digest":row.get::<_,Option<String>>(2)?,
                        "completed_checks":row.get::<_,u32>(3)?,
                        "active_check_id":if status == "checking" {check_id.as_deref()} else {None},
                        "failed_check_id":if status == "failed" {check_id.as_deref()} else {None},
                        "error":row.get::<_,Option<String>>(6)?,
                    }),
                    row.get::<_, Option<String>>(5)?,
                ))
            },
        )
        .optional()?;
    let (mut result, review) =
        result.ok_or_else(|| CoreError::new("not_found", "Mission run not found"))?;
    result["review"] = review
        .map(|value| serde_json::from_str(&value))
        .transpose()?
        .unwrap_or(Value::Null);
    if let Some((status, post_index, check_id, error)) = tx
        .query_row(
            "SELECT status,post_index,check_id,error FROM mission_integrations WHERE mission_id=?1",
            [id],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, u32>(1)?,
                    row.get::<_, Option<String>>(2)?,
                    row.get::<_, Option<String>>(3)?,
                ))
            },
        )
        .optional()?
    {
        result["status"] = json!(status);
        result["completed_postchecks"] = json!(post_index);
        result["active_check_id"] = json!(check_id);
        result["error"] = json!(error);
        let mut statement = tx.prepare(
            "SELECT f.intent_id,f.status,json_extract(o.operation,'$.path')
            FROM mission_integration_files f JOIN intent_operations o ON o.request_id=f.intent_id
            WHERE f.mission_id=?1 ORDER BY f.position",
        )?;
        let files = statement.query_map([id], |row| Ok(json!({
            "intent_id":row.get::<_,String>(0)?,"status":row.get::<_,String>(1)?,"path":row.get::<_,String>(2)?
        })))?.collect::<Result<Vec<_>,_>>()?;
        result["integration_files"] = json!(files);
    }
    Ok(result)
}

fn fail(tx: &Transaction<'_>, mission: &str, error: &str) -> CoreResult<()> {
    tx.execute(
        "UPDATE mission_runs SET status='failed',error=?2,ai_id=NULL WHERE mission_id=?1",
        params![mission, error],
    )?;
    store::event(
        tx,
        "mission_run_failed",
        json!({"mission_id":mission,"error":error}),
    )?;
    Ok(())
}

pub(crate) fn complete(
    tx: &Transaction<'_>,
    id: &str,
    purpose: Purpose,
    output: Result<String, String>,
) -> CoreResult<()> {
    let expected = match purpose {
        Purpose::MissionGenerate => "generating",
        Purpose::MissionReview => "reviewing",
        _ => return Err(CoreError::invalid("Unexpected candidate worker purpose")),
    };
    let row: Option<(String, String)> = tx
        .query_row(
            "SELECT mission_id,contract_digest FROM mission_runs WHERE ai_id=?1 AND status=?2",
            params![id, expected],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((mission, digest)) = row else {
        return Ok(());
    };
    let Ok((contract, current)) = approved(tx, &mission) else {
        return fail(tx, &mission, "approval_unavailable");
    };
    if digest != current {
        return fail(tx, &mission, "contract_conflict");
    }
    let Ok(output) = output else {
        return fail(tx, &mission, "model_job_failed");
    };
    if purpose == Purpose::MissionGenerate {
        let artifacts = match candidate::parse_generation(&output, &contract) {
            Ok(artifacts) => artifacts,
            Err(_) => return fail(tx, &mission, "invalid_generated_candidate"),
        };

        let digest = store::digest(&artifacts)?;
        tx.execute(
            "UPDATE mission_runs SET status='checking',candidate=?2,candidate_digest=?3,ai_id=NULL WHERE mission_id=?1",
            params![mission,serde_json::to_string(&artifacts)?,digest],
        )?;
        store::event(
            tx,
            "mission_candidate_sealed",
            json!({"mission_id":mission,"candidate_digest":digest}),
        )?;
    } else {
        let review = match candidate::parse_review(&output) {
            Ok(review) => review,
            Err(_) => return fail(tx, &mission, "invalid_review"),
        };
        let status = if review["approved"] == true {
            "review_ready"
        } else {
            "rejected"
        };
        tx.execute(
            "UPDATE mission_runs SET status=?2,review=?3,ai_id=NULL WHERE mission_id=?1",
            params![mission, status, serde_json::to_string(&review)?],
        )?;
        store::event(
            tx,
            "mission_candidate_reviewed",
            json!({"mission_id":mission,"status":status}),
        )?;
    }
    Ok(())
}

pub(crate) fn advance(
    tx: &Transaction<'_>,
    state: &Path,
    workspace: &Path,
    ai_busy: bool,
    check_busy: bool,
) -> CoreResult<Option<Next>> {
    let row = tx
        .query_row(
            "SELECT mission_id,contract_digest,candidate,candidate_digest,check_index,check_id
         FROM mission_runs WHERE status='checking'",
            [],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, u32>(4)?,
                    row.get::<_, Option<String>>(5)?,
                ))
            },
        )
        .optional()?;
    let Some((mission, digest, serialized, candidate_digest, mut index, check_id)) = row else {
        return Ok(None);
    };
    let Ok((contract, current)) = approved(tx, &mission) else {
        fail(tx, &mission, "approval_unavailable")?;
        return Ok(None);
    };
    let artifacts: Vec<CandidateArtifact> = serde_json::from_str(&serialized)?;
    if current != digest || store::digest(&artifacts)? != candidate_digest {
        fail(tx, &mission, "candidate_identity_mismatch")?;
        return Ok(None);
    }
    if let Some(id) = check_id {
        let check = checks::get(tx, &id)?;
        if check["cleanup"] == "pending" {
            return Ok(None);
        }
        if !valid_check(&check, &digest, &candidate_digest, index) {
            fail(
                tx,
                &mission,
                check["error"].as_str().unwrap_or("candidate_check_failed"),
            )?;
            return Ok(None);
        }
        index += 1;
        tx.execute(
            "UPDATE mission_runs SET check_index=?2,check_id=NULL WHERE mission_id=?1",
            params![mission, index],
        )?;
    }
    let recipes = &contract.execution.as_ref().unwrap().checks;
    if (index as usize) < recipes.len() {
        if check_busy {
            return Ok(None);
        }
        let id = stage_id(&mission, &format!("check-{index}"))?;
        match checks::start(tx, &id, &mission, index, &artifacts, state, workspace) {
            Ok((_, launch)) => {
                tx.execute(
                    "UPDATE mission_runs SET check_id=?2 WHERE mission_id=?1",
                    params![mission, id],
                )?;
                return Ok(Some(Next::Check(launch)));
            }
            Err(error) if error.code == "project_check_busy" => return Ok(None),
            Err(error)
                if matches!(
                    error.code.as_str(),
                    "toolchain_unavailable" | "containment_unavailable" | "run_path_unavailable"
                ) =>
            {
                fail(tx, &mission, &error.code)?;
                return Ok(None);
            }
            Err(error) => return Err(error),
        }
    }
    if ai_busy {
        return Ok(None);
    }
    let mut evidence = Vec::with_capacity(recipes.len());
    for index in 0..recipes.len() as u32 {
        let check = checks::get(tx, &stage_id(&mission, &format!("check-{index}"))?)?;
        if !valid_check(&check, &digest, &candidate_digest, index) {
            fail(tx, &mission, "candidate_check_failed")?;
            return Ok(None);
        }
        evidence.push(check);
    }
    let id = stage_id(&mission, "review")?;
    let launch = match candidate::review(&id, &contract, &artifacts, &evidence) {
        Ok(launch) => launch,
        Err(_) => {
            fail(tx, &mission, "review_input_invalid")?;
            return Ok(None);
        }
    };
    tx.execute(
        "UPDATE mission_runs SET status='reviewing',ai_id=?2 WHERE mission_id=?1",
        params![mission, id],
    )?;
    store::event(tx, "mission_review_started", json!({"mission_id":mission}))?;
    Ok(Some(Next::Review(launch)))
}

pub(crate) fn valid_check(check: &Value, contract: &str, candidate: &str, index: u32) -> bool {
    check["status"] == "succeeded"
        && check["cleanup"] == "complete"
        && check["contract_digest"] == contract
        && check["candidate_digest"] == candidate
        && check["check_index"] == index
        && check["tool_digest"]
            .as_str()
            .is_some_and(|digest| digest.len() == 64)
        && check["receipt"]["token"]["lpac"] == true
}

pub(crate) fn stop(tx: &Transaction<'_>, mission: &str, status: &str) -> CoreResult<()> {
    tx.execute(
        &format!("UPDATE mission_runs SET status=?2,error=?2,ai_id=NULL,check_id=NULL WHERE mission_id=?1 AND (status IN {ACTIVE} OR status='review_ready')"),
        params![mission,status],
    )?;
    Ok(())
}

pub(crate) fn interrupt(tx: &Transaction<'_>) -> CoreResult<()> {
    tx.execute(
        &format!("UPDATE mission_runs SET status='interrupted',error='core_interrupted',ai_id=NULL,check_id=NULL WHERE status IN {ACTIVE}"),
        [],
    )?;
    Ok(())
}
