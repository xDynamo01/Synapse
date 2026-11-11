//! Core-only publication of reviewed candidate bytes and verified compensation.
use std::path::Path;

use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

use crate::{
    candidate, checks,
    contracts::{CandidateArtifact, CoreError, CoreResult, MissionContract, ToolOperation},
    mission_run, runner,
    store::{self, Store},
    tools,
};

const ACTIVE: &str = "('publishing','postchecking','rolling_back')";

struct Snapshot {
    contract: MissionContract,
    contract_digest: String,
    candidate_digest: String,
    artifacts: Vec<CandidateArtifact>,
}

fn snapshot(tx: &Transaction<'_>, mission: &str) -> CoreResult<Snapshot> {
    let (contract, contract_digest) = mission_run::approved(tx, mission)?;
    let row: Option<(String, String, String, String)> = tx
        .query_row(
            "SELECT contract_digest,candidate_digest,candidate,review FROM mission_runs
         WHERE mission_id=?1 AND status='review_ready' AND auto_integrate=1",
            [mission],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()?;
    let Some((sealed_contract, candidate_digest, serialized, review)) = row else {
        return Err(CoreError::new(
            "permission_denied",
            "No reviewed candidate is authorized",
        ));
    };
    let artifacts: Vec<CandidateArtifact> = serde_json::from_str(&serialized)?;
    candidate::validate_artifacts(&contract, &artifacts)?;
    if sealed_contract != contract_digest
        || candidate_digest != store::digest(&artifacts)?
        || candidate::parse_review(&review)?["approved"] != true
        || contract.rollback != "owned verified removal"
        || !contract
            .actions
            .iter()
            .any(|action| action == "artifact_create")
    {
        return Err(CoreError::new(
            "permission_denied",
            "Candidate or approval has changed",
        ));
    }
    if let Some(pin) = &contract.skill {
        let raw: Option<(String, String)> = tx
            .query_row(
                "SELECT manifest,digest FROM skills WHERE scope=?1 AND id=?2 AND version=?3",
                params![pin.scope, pin.id, pin.version],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let Some((raw, digest)) = raw else {
            return Err(CoreError::new(
                "permission_denied",
                "Pinned integration Skill is missing",
            ));
        };
        let skill: crate::contracts::SkillManifest = serde_json::from_str(&raw)?;
        if pin.scope != contract.scope
            || digest != pin.digest
            || store::digest(&skill)? != digest
            || !skill.tools.iter().any(|tool| tool == "artifact_create")
            || !skill
                .permissions
                .iter()
                .any(|permission| permission == "artifact_create")
        {
            return Err(CoreError::new(
                "permission_denied",
                "Pinned Skill does not allow integration",
            ));
        }
    }
    Ok(Snapshot {
        contract,
        contract_digest,
        candidate_digest,
        artifacts,
    })
}

fn transition(
    tx: &Transaction<'_>,
    mission: &str,
    status: &str,
    error: Option<&str>,
) -> CoreResult<()> {
    tx.execute(
        "UPDATE mission_integrations SET status=?2,error=?3,check_id=NULL WHERE mission_id=?1",
        params![mission, status, error],
    )?;
    store::event(
        tx,
        "mission_integration_state",
        json!({"mission_id":mission,"status":status,"error":error}),
    )?;
    Ok(())
}

fn original_check(
    tx: &Transaction<'_>,
    mission: &str,
    data: &Snapshot,
    index: u32,
) -> CoreResult<Value> {
    let check = checks::get(
        tx,
        &mission_run::stage_id(mission, &format!("check-{index}"))?,
    )?;
    if !mission_run::valid_check(&check, &data.contract_digest, &data.candidate_digest, index) {
        return Err(CoreError::new(
            "precheck_unavailable",
            "A matching precheck receipt is required",
        ));
    }
    Ok(check)
}

fn create(artifact: &CandidateArtifact) -> ToolOperation {
    ToolOperation::Create {
        path: artifact.path.clone(),
        content: artifact.content.clone(),
    }
}

fn read(artifact: &CandidateArtifact) -> ToolOperation {
    ToolOperation::Read {
        path: artifact.path.clone(),
    }
}

fn reserve_conflict(tx: &Transaction<'_>, target: &str, exclude: Option<&str>) -> CoreResult<bool> {
    Ok(tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM tool_intents WHERE target=?1 COLLATE NOCASE AND status='prepared' AND request_id IS NOT ?2
        UNION ALL SELECT 1 FROM recovery_writes r JOIN tool_intents i ON i.request_id=r.intent_id
        WHERE i.target=?1 COLLATE NOCASE AND r.status='prepared')",
        params![target,exclude], |row| row.get(0),
    )?)
}

pub(crate) fn bind_approval(
    tx: &Transaction<'_>,
    mission: &str,
    workspace: &Path,
    state: &Path,
) -> CoreResult<()> {
    let raw: String = tx.query_row(
        "SELECT contract FROM missions WHERE id=?1",
        [mission],
        |row| row.get(0),
    )?;
    let contract: MissionContract = serde_json::from_str(&raw)?;
    let Some(policy) = contract.execution else {
        return Ok(());
    };
    if cfg!(windows) {
        let path = &policy
            .artifacts
            .first()
            .ok_or_else(|| CoreError::invalid("Plan has no artifacts"))?
            .path;
        let broker = tools::prepare(
            workspace,
            state,
            &ToolOperation::Read { path: path.clone() },
        )?;
        tx.execute(
            "INSERT INTO mission_workspace_approvals(mission_id,identity) VALUES(?1,?2)",
            params![mission, broker.root_identity()?],
        )?;
    }
    Ok(())
}

fn require_non_git(workspace: &Path) -> CoreResult<()> {
    for ancestor in workspace.ancestors() {
        match std::fs::symlink_metadata(ancestor.join(".git")) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            _ => {
                return Err(CoreError::new(
                    "workspace_unsupported",
                    "Automatic integration requires a non-Git workspace",
                ));
            }
        }
    }
    Ok(())
}

fn preflight(
    tx: &Transaction<'_>,
    mission: &str,
    workspace: &Path,
    state: &Path,
) -> CoreResult<String> {
    let data = snapshot(tx, mission)?;
    require_non_git(workspace)?;
    let expected: Option<String> = tx
        .query_row(
            "SELECT identity FROM mission_workspace_approvals WHERE mission_id=?1",
            [mission],
            |row| row.get(0),
        )
        .optional()?;
    let expected = expected.ok_or_else(|| {
        CoreError::new(
            "workspace_approval_unavailable",
            "Approval lacks a Workspace identity",
        )
    })?;
    for index in 0..data.contract.execution.as_ref().unwrap().checks.len() as u32 {
        original_check(tx, mission, &data, index)?;
    }
    let mut root_identity = None;
    for artifact in &data.artifacts {
        let broker = tools::prepare(workspace, state, &create(artifact))?;
        let current = broker.root_identity()?;
        if current != expected
            || root_identity
                .as_ref()
                .is_some_and(|identity| identity != &current)
        {
            return Err(CoreError::new(
                "workspace_changed",
                "Workspace identity changed during preflight",
            ));
        }
        root_identity = Some(current);
        if reserve_conflict(tx, &broker.target(), None)? || !broker.create_is_absent()? {
            return Err(CoreError::new(
                "artifact_conflict",
                "An integration target is already occupied or reserved",
            ));
        }
    }
    root_identity.ok_or_else(|| CoreError::invalid("Candidate contains no artifacts"))
}

pub(crate) fn advance(
    store: &mut Store,
    workspace: &Path,
    check_busy: bool,
) -> CoreResult<Option<runner::Launch>> {
    let state = store.state_dir.clone();
    let tx = store.transaction()?;
    let row: Option<(String, String)> = tx
        .query_row(
            &format!("SELECT mission_id,status FROM mission_integrations WHERE status IN {ACTIVE}"),
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((mission, status)) = row else {
        let ready: Option<String> = tx.query_row(
            "SELECT r.mission_id FROM mission_runs r WHERE r.status='review_ready' AND auto_integrate=1
             AND NOT EXISTS(SELECT 1 FROM mission_integrations i WHERE i.mission_id=r.mission_id)
             ORDER BY r.rowid LIMIT 1",
            [], |row| row.get(0),
        ).optional()?;
        if let Some(mission) = ready {
            tx.execute(
                "INSERT INTO mission_integrations(mission_id,status) VALUES(?1,'publishing')",
                [&mission],
            )?;
            match preflight(&tx, &mission, workspace, &state) {
                Ok(identity) => {
                    tx.execute(
                        "UPDATE mission_integrations SET workspace_identity=?2 WHERE mission_id=?1",
                        params![mission, identity],
                    )?;
                    store::event(
                        &tx,
                        "mission_integration_started",
                        json!({"mission_id":mission}),
                    )?;
                }
                Err(error) => transition(&tx, &mission, "failed", Some(&error.code))?,
            }
        }
        tx.commit()?;
        return Ok(None);
    };
    let ambiguous: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM mission_integration_files WHERE mission_id=?1 AND status IN ('prepared','removing'))",
        [&mission], |row| row.get(0),
    )?;
    if ambiguous {
        transition(
            &tx,
            &mission,
            "recovery_required",
            Some("unfinished_effect_intent"),
        )?;
        tx.commit()?;
        return Ok(None);
    }
    tx.commit()?;
    match status.as_str() {
        "publishing" => publish_one(store, workspace, &state, &mission)?,
        "postchecking" => return postcheck(store, workspace, &state, &mission, check_busy),
        "rolling_back" => rollback_one(store, workspace, &state, &mission)?,
        _ => unreachable!(),
    }
    Ok(None)
}

fn verify_workspace(tx: &Transaction<'_>, mission: &str, identity: &str) -> CoreResult<()> {
    let expected: String = tx.query_row(
        "SELECT workspace_identity FROM mission_integrations WHERE mission_id=?1",
        [mission],
        |row| row.get(0),
    )?;
    if identity != expected {
        return Err(CoreError::new(
            "workspace_changed",
            "Workspace identity changed after preflight",
        ));
    }
    Ok(())
}

fn known_failure(tx: &Transaction<'_>, mission: &str, error: &str) -> CoreResult<()> {
    let has_files: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM mission_integration_files WHERE mission_id=?1 AND status='confirmed')",
        [mission], |row| row.get(0),
    )?;
    transition(
        tx,
        mission,
        if has_files { "rolling_back" } else { "failed" },
        Some(error),
    )
}

fn publish_one(store: &mut Store, workspace: &Path, state: &Path, mission: &str) -> CoreResult<()> {
    let tx = store.transaction()?;
    if let Err(error) = require_non_git(workspace) {
        transition(&tx, mission, "recovery_required", Some(&error.code))?;
        return Ok(tx.commit()?);
    }
    let data = snapshot(&tx, mission)?;
    let position: u32 = tx.query_row(
        "SELECT COUNT(*) FROM mission_integration_files WHERE mission_id=?1",
        [mission],
        |row| row.get(0),
    )?;
    if position as usize == data.artifacts.len() {
        transition(&tx, mission, "postchecking", None)?;
        return Ok(tx.commit()?);
    }
    let artifact = &data.artifacts[position as usize];
    let operation = create(artifact);
    let broker = match tools::prepare(workspace, state, &operation) {
        Ok(broker) => broker,
        Err(error) => {
            known_failure(&tx, mission, &error.code)?;
            return Ok(tx.commit()?);
        }
    };
    if verify_workspace(&tx, mission, &broker.root_identity()?).is_err() {
        transition(&tx, mission, "recovery_required", Some("workspace_changed"))?;
        return Ok(tx.commit()?);
    }
    let target = broker.target();
    if reserve_conflict(&tx, &target, None)? || !broker.create_is_absent()? {
        known_failure(&tx, mission, "artifact_conflict")?;
        return Ok(tx.commit()?);
    }
    let intent = mission_run::stage_id(mission, &format!("publish-{position}"))?;
    let id_occupied: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM tool_intents WHERE request_id=?1
         UNION ALL SELECT 1 FROM recovery_writes WHERE request_id=?1)",
        [&intent],
        |row| row.get(0),
    )?;
    if id_occupied {
        known_failure(&tx, mission, "intent_id_conflict")?;
        return Ok(tx.commit()?);
    }
    let content_digest = tools::sha(artifact.content.as_bytes());
    let intent_digest =
        store::digest(&(&data.contract_digest, &data.candidate_digest, &operation))?;
    tx.execute("INSERT INTO tool_intents(request_id,request_digest,mission_id,target,content_digest,status)
        VALUES(?1,?2,?3,?4,?5,'prepared')",params![intent,intent_digest,mission,target,content_digest])?;
    tx.execute(
        "INSERT INTO intent_operations(request_id,operation) VALUES(?1,?2)",
        params![intent, serde_json::to_string(&operation)?],
    )?;
    tx.execute("INSERT INTO mission_integration_files(mission_id,position,intent_id,status) VALUES(?1,?2,?3,'prepared')",
        params![mission,position,intent])?;
    tx.commit()?;

    #[cfg(feature = "test-fault-injection")]
    if std::env::var_os("SYNAPSE_TEST_CRASH_AFTER_MISSION_PUBLISH_PREPARE").is_some() {
        std::process::exit(87);
    }

    let tx = store.transaction()?;
    let authorized = snapshot(&tx, mission)?;
    if authorized.candidate_digest != data.candidate_digest
        || authorized.contract_digest != data.contract_digest
    {
        transition(
            &tx,
            mission,
            "recovery_required",
            Some("candidate_identity_mismatch"),
        )?;
        return Ok(tx.commit()?);
    }
    if let Err(error) = require_non_git(workspace) {
        tx.execute(
            "UPDATE tool_intents SET status='aborted' WHERE request_id=?1",
            [&intent],
        )?;
        tx.execute(
            "UPDATE mission_integration_files SET status='removed' WHERE intent_id=?1",
            [&intent],
        )?;
        known_failure(&tx, mission, &error.code)?;
        return Ok(tx.commit()?);
    }
    match broker.create_owned(artifact.content.as_bytes()) {
        Ok((identity, bytes)) if bytes == artifact.content.as_bytes() => {
            #[cfg(feature = "test-fault-injection")]
            if std::env::var_os("SYNAPSE_TEST_CRASH_AFTER_MISSION_PUBLISH_WRITE").is_some() {
                std::process::exit(88);
            }
            tx.execute("UPDATE mission_integration_files SET identity=?2,status='confirmed' WHERE intent_id=?1",
                params![intent,identity])?;
            store::event(
                &tx,
                "tool_effect",
                json!({"request_id":intent,"mission_id":mission,
                "action":"artifact_create","target":target,"sha256":content_digest}),
            )?;
        }
        Err(error) if error.code == "artifact_conflict" => {
            tx.execute(
                "UPDATE tool_intents SET status='aborted' WHERE request_id=?1",
                [&intent],
            )?;
            tx.execute(
                "UPDATE mission_integration_files SET status='removed' WHERE intent_id=?1",
                [&intent],
            )?;
            known_failure(&tx, mission, "artifact_conflict")?;
        }
        _ => transition(
            &tx,
            mission,
            "recovery_required",
            Some("publish_outcome_ambiguous"),
        )?,
    }
    Ok(tx.commit()?)
}

struct Readback {
    artifacts: Vec<CandidateArtifact>,
    _pins: Vec<(tools::Broker, tools::OwnedRead)>,
}

fn readback(
    tx: &Transaction<'_>,
    workspace: &Path,
    state: &Path,
    mission: &str,
    data: &Snapshot,
) -> CoreResult<Readback> {
    let mut pins = Vec::with_capacity(data.artifacts.len());
    let mut result = Vec::with_capacity(data.artifacts.len());
    for (position, artifact) in data.artifacts.iter().enumerate() {
        let identity: String = tx.query_row(
            "SELECT identity FROM mission_integration_files WHERE mission_id=?1 AND position=?2 AND status='confirmed'",
            params![mission,position as u32], |row| row.get(0),
        )?;
        let broker = tools::prepare(workspace, state, &read(artifact))?;
        verify_workspace(tx, mission, &broker.root_identity()?)?;
        let observed = broker.read_owned_guarded()?;
        if observed.identity != identity || observed.bytes != artifact.content.as_bytes() {
            return Err(CoreError::new(
                "ownership_conflict",
                "Published artifact changed after creation",
            ));
        }
        let content = String::from_utf8(observed.bytes.clone())
            .map_err(|_| CoreError::invalid("Artifact is not UTF-8"))?;
        pins.push((broker, observed));
        result.push(CandidateArtifact {
            path: artifact.path.clone(),
            content,
        });
    }
    Ok(Readback {
        artifacts: result,
        _pins: pins,
    })
}

fn postcheck(
    store: &mut Store,
    workspace: &Path,
    state: &Path,
    mission: &str,
    busy: bool,
) -> CoreResult<Option<runner::Launch>> {
    let tx = store.transaction()?;
    let data = snapshot(&tx, mission)?;
    let (mut index, check_id, error): (u32, Option<String>, Option<String>) = tx.query_row(
        "SELECT post_index,check_id,error FROM mission_integrations WHERE mission_id=?1",
        [mission],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
    )?;
    if let Some(id) = check_id {
        let check = checks::get(&tx, &id)?;
        if check["cleanup"] == "pending" {
            return Ok(None);
        }
        let pre = original_check(&tx, mission, &data, index)?;
        if !mission_run::valid_check(&check, &data.contract_digest, &data.candidate_digest, index)
            || check["tool_digest"] != pre["tool_digest"]
        {
            known_failure(
                &tx,
                mission,
                error
                    .as_deref()
                    .or_else(|| check["error"].as_str())
                    .unwrap_or("postcheck_failed"),
            )?;
            tx.commit()?;
            return Ok(None);
        }
        index += 1;
        tx.execute(
            "UPDATE mission_integrations SET post_index=?2,check_id=NULL WHERE mission_id=?1",
            params![mission, index],
        )?;
    }

    let readback = match readback(&tx, workspace, state, mission, &data) {
        Ok(artifacts) => artifacts,
        Err(_) => {
            transition(
                &tx,
                mission,
                "recovery_required",
                Some("published_artifact_changed"),
            )?;
            tx.commit()?;
            return Ok(None);
        }
    };
    if index as usize == data.contract.execution.as_ref().unwrap().checks.len() {
        tx.execute("UPDATE tool_intents SET status='confirmed' WHERE request_id IN
            (SELECT intent_id FROM mission_integration_files WHERE mission_id=?1 AND status='confirmed')",[mission])?;
        transition(&tx, mission, "integrated", None)?;
        tx.commit()?;
        return Ok(None);
    }
    if busy {
        tx.commit()?;
        return Ok(None);
    }
    let id = mission_run::stage_id(mission, &format!("post-check-{index}"))?;
    let launch = match checks::start(
        &tx,
        &id,
        mission,
        index,
        &readback.artifacts,
        state,
        workspace,
    ) {
        Ok((_, launch)) => launch,
        Err(error) if error.code == "project_check_busy" => {
            tx.commit()?;
            return Ok(None);
        }
        Err(error) => {
            known_failure(&tx, mission, &error.code)?;
            tx.commit()?;
            return Ok(None);
        }
    };
    tx.execute(
        "UPDATE mission_integrations SET check_id=?2 WHERE mission_id=?1",
        params![mission, id],
    )?;
    tx.commit()?;
    Ok(Some(launch))
}

pub(crate) fn allow_tool(tx: &Transaction<'_>, check: &str, digest: &str) -> CoreResult<bool> {
    let row: Option<(String,u32)> = tx.query_row(
        "SELECT mission_id,post_index FROM mission_integrations WHERE check_id=?1 AND status='postchecking'",
        [check], |row| Ok((row.get(0)?,row.get(1)?)),
    ).optional()?;
    let Some((mission, index)) = row else {
        return Ok(true);
    };
    let data = snapshot(tx, &mission)?;
    let approved = original_check(tx, &mission, &data, index)?["tool_digest"] == digest;
    #[cfg(feature = "test-fault-injection")]
    let approved = approved && std::env::var_os("SYNAPSE_TEST_REJECT_POSTCHECK_TOOL").is_none();
    if !approved {
        tx.execute(
            "UPDATE mission_integrations SET error='postcheck_tool_changed' WHERE mission_id=?1",
            [mission],
        )?;
    }
    Ok(approved)
}

fn rollback_one(
    store: &mut Store,
    workspace: &Path,
    state: &Path,
    mission: &str,
) -> CoreResult<()> {
    let tx = store.transaction()?;
    if let Err(error) = require_non_git(workspace) {
        transition(&tx, mission, "recovery_required", Some(&error.code))?;
        return Ok(tx.commit()?);
    }
    let data = snapshot(&tx, mission)?;
    let row: Option<(u32,String,String)> = tx.query_row(
        "SELECT position,intent_id,identity FROM mission_integration_files WHERE mission_id=?1 AND status='confirmed'
         ORDER BY position DESC LIMIT 1",
        [mission], |row| Ok((row.get(0)?,row.get(1)?,row.get(2)?)),
    ).optional()?;
    let Some((position, intent, identity)) = row else {
        let error: Option<String> = tx.query_row(
            "SELECT error FROM mission_integrations WHERE mission_id=?1",
            [mission],
            |row| row.get(0),
        )?;
        transition(&tx, mission, "rolled_back", error.as_deref())?;
        return Ok(tx.commit()?);
    };
    let artifact = &data.artifacts[position as usize];
    let broker = match tools::prepare(workspace, state, &read(artifact)) {
        Ok(broker) => broker,
        Err(_) => {
            transition(
                &tx,
                mission,
                "recovery_required",
                Some("rollback_path_changed"),
            )?;
            return Ok(tx.commit()?);
        }
    };
    if verify_workspace(&tx, mission, &broker.root_identity()?).is_err() {
        transition(&tx, mission, "recovery_required", Some("workspace_changed"))?;
        return Ok(tx.commit()?);
    }
    if reserve_conflict(&tx, &broker.target(), Some(&intent))? {
        transition(
            &tx,
            mission,
            "recovery_required",
            Some("rollback_target_reserved"),
        )?;
        return Ok(tx.commit()?);
    }
    tx.execute(
        "UPDATE mission_integration_files SET status='removing' WHERE intent_id=?1",
        [&intent],
    )?;
    tx.execute(
        "UPDATE tool_intents SET status='prepared' WHERE request_id=?1",
        [&intent],
    )?;
    tx.commit()?;

    let tx = store.transaction()?;
    let authorized = snapshot(&tx, mission)?;
    if authorized.candidate_digest != data.candidate_digest
        || authorized.contract_digest != data.contract_digest
    {
        transition(
            &tx,
            mission,
            "recovery_required",
            Some("candidate_identity_mismatch"),
        )?;
        return Ok(tx.commit()?);
    }
    if let Err(error) = require_non_git(workspace) {
        transition(&tx, mission, "recovery_required", Some(&error.code))?;
        return Ok(tx.commit()?);
    }
    match broker.delete_owned(&identity, artifact.content.as_bytes()) {
        Ok(()) => {
            tx.execute(
                "UPDATE mission_integration_files SET status='removed' WHERE intent_id=?1",
                [&intent],
            )?;
            tx.execute(
                "UPDATE tool_intents SET status='compensated' WHERE request_id=?1",
                [&intent],
            )?;
            store::event(
                &tx,
                "mission_artifact_removed",
                json!({"mission_id":mission,"intent_id":intent,"path":artifact.path}),
            )?;
        }
        Err(_) => transition(
            &tx,
            mission,
            "recovery_required",
            Some("rollback_ownership_unverified"),
        )?,
    }
    Ok(tx.commit()?)
}

pub(crate) fn stop(tx: &Transaction<'_>, mission: &str, status: &str) -> CoreResult<()> {
    let running: bool = tx.query_row(
        &format!("SELECT EXISTS(SELECT 1 FROM mission_integrations WHERE mission_id=?1 AND status IN {ACTIVE})"),
        [mission], |row| row.get(0),
    )?;
    if running {
        let has_files: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM mission_integration_files WHERE mission_id=?1 AND status<>'removed')",
            [mission], |row| row.get(0),
        )?;
        transition(
            tx,
            mission,
            if has_files {
                "recovery_required"
            } else {
                status
            },
            Some(status),
        )?;
    }
    Ok(())
}

pub(crate) fn interrupt(tx: &Transaction<'_>) -> CoreResult<()> {
    tx.execute(
        &format!("UPDATE mission_integrations SET status='recovery_required',error='core_interrupted',check_id=NULL WHERE status IN {ACTIVE}"),
        [],
    )?;
    tx.execute(
        "UPDATE mission_runs SET status='interrupted',error='core_interrupted',auto_integrate=0 WHERE status='review_ready' AND auto_integrate=1
         AND NOT EXISTS(SELECT 1 FROM mission_integrations i WHERE i.mission_id=mission_runs.mission_id)",
        [],
    )?;
    Ok(())
}
