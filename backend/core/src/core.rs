use crate::{
    chats, checks,
    contracts::*,
    conversation, integration, learning, memory, mission_recovery, mission_run, missions, planner,
    registry, runner,
    store::{self, Store},
    tools, worker,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::sync::{
    Arc,
    mpsc::{self, Receiver},
};

struct Active {
    id: String,
    stop: Arc<worker::Stop>,
    result: Receiver<Result<String, String>>,
    purpose: conversation::Purpose,
    outcome: Option<Result<String, String>>,
}

/// Local human client entrypoint. Never expose dispatch to worker output.
pub struct Core {
    store: Store,
    workspace_root: PathBuf,
    active: Option<Active>,
    check: Option<runner::Active>,
    check_event: Option<runner::Event>,
}
impl Core {
    pub fn open(state_dir: impl AsRef<Path>, workspace_root: impl AsRef<Path>) -> CoreResult<Self> {
        let workspace_root = workspace_root
            .as_ref()
            .canonicalize()
            .map_err(|_| CoreError::invalid("Workspace must exist"))?;
        if !workspace_root.is_dir() {
            return Err(CoreError::invalid("Workspace must be a directory"));
        }
        Ok(Self {
            store: Store::open(state_dir.as_ref(), &workspace_root)?,
            workspace_root,
            active: None,
            check: None,
            check_event: None,
        })
    }
    pub fn dispatch(&mut self, request: Request) -> Response {
        if let Err(error) = self.poll_project_check().and_then(|()| self.drain()) {
            return Response::failure(Some(request.request_id), self.event_cursor(), error);
        }
        if matches!(
            &request.command,
            Command::ConversationStart { .. }
                | Command::Inference { .. }
                | Command::MissionPlanStart { .. }
                | Command::MissionExecute { .. }
        ) && self
            .active
            .as_ref()
            .is_some_and(|a| a.purpose == conversation::Purpose::Learning)
        {
            let active = self.active.take().unwrap();
            active.stop.cancel();
            let _ = active.result.recv();
            let outcome = (|| -> CoreResult<()> {
                let tx = self.store.transaction()?;
                learning::requeue(&tx, &active.id)?;
                tx.commit()?;
                Ok(())
            })();
            if let Err(error) = outcome {
                return Response::failure(Some(request.request_id), self.event_cursor(), error);
            }
        }
        let id = Some(request.request_id.clone());
        let result = self.dispatch_durable(&request);
        let response = match result {
            Ok(response) => {
                if response.ok {
                    if let Command::JobCancel { job_id } = &request.command {
                        if let Some(active) = &self.active {
                            if active.id == *job_id
                                && !matches!(
                                    active.purpose,
                                    conversation::Purpose::MissionGenerate
                                        | conversation::Purpose::MissionReview
                                )
                            {
                                active.stop.cancel();
                            }
                        }
                    }
                }
                response
            }
            Err(error) => Response::failure(id, self.store.event_cursor().unwrap_or(0), error),
        };
        if response.ok {
            if let Command::MissionCancel { mission_id, .. }
            | Command::MissionRevoke { mission_id, .. } = &request.command
            {
                if let Some(active) = &self.active {
                    let stage = match active.purpose {
                        conversation::Purpose::MissionGenerate => Some("generation"),
                        conversation::Purpose::MissionReview => Some("review"),
                        _ => None,
                    };
                    if stage
                        .and_then(|stage| mission_run::stage_id(mission_id, stage).ok())
                        .as_ref()
                        == Some(&active.id)
                    {
                        active.stop.cancel();
                    }
                }
            }
        }
        let _ = self.advance_mission();
        let _ = self.advance_integration();
        if self.active.is_none() {
            let next = (|| -> CoreResult<Option<conversation::Launch>> {
                let tx = self.store.transaction()?;
                let next = learning::start(&tx)?;
                tx.commit()?;
                Ok(next)
            })();
            if let Ok(Some(launch)) = next {
                self.launch(launch);
            }
        }
        response
    }
    pub fn event_cursor(&self) -> u64 {
        self.store.event_cursor().unwrap_or(0)
    }
    fn dispatch_durable(&mut self, request: &Request) -> CoreResult<Response> {
        if request.version != PROTOCOL_VERSION {
            return Err(CoreError::new(
                "unsupported_version",
                "Only protocol version 1 is supported",
            ));
        }
        bounded(&request.request_id, "request_id", 128)?;
        if serde_json::to_vec(request)?.len() > MAX_REQUEST_BYTES {
            return Err(CoreError::new(
                "request_too_large",
                "Request exceeds 65536 bytes",
            ));
        }
        if request.request_id.starts_with(mission_run::INTERNAL_PREFIX)
            && matches!(
                &request.command,
                Command::ToolExecute { .. }
                    | Command::ToolRecovery { .. }
                    | Command::ProjectCheckStart { .. }
            )
        {
            return Err(CoreError::invalid("Reserved internal effect request ID"));
        }
        let digest = store::digest(request)?;
        if matches!(&request.command, Command::ToolRecovery { .. }) {
            return match self.recover_artifact(request, &digest) {
                Ok(response) => Ok(response),
                Err(error) => self.cache_create_failure(request, &digest, error),
            };
        }
        if matches!(
            &request.command,
            Command::ToolExecute {
                operation: ToolOperation::Replace { .. },
                ..
            }
        ) {
            return match self.replace_artifact(request, &digest) {
                Ok(response) => Ok(response),
                Err(error) => self.cache_create_failure(request, &digest, error),
            };
        }
        if matches!(
            &request.command,
            Command::ToolExecute {
                operation: ToolOperation::Create { .. },
                ..
            }
        ) {
            return match self.create_artifact(request, &digest) {
                Ok(response) => Ok(response),
                Err(error) => self.cache_create_failure(request, &digest, error),
            };
        }
        let mut pending = None;
        let mut check_launch = None;
        let stop = self
            .check
            .as_ref()
            .filter(|active| match &request.command {
                Command::ProjectCheckCancel { check_id } => active.id == *check_id,
                Command::MissionCancel { mission_id, .. }
                | Command::MissionRevoke { mission_id, .. } => active.mission_id == *mission_id,
                _ => false,
            })
            .map(runner::Active::control);
        let guard = stop.as_ref().map(|control| control.lock_resume());
        let busy = self.active.is_some();
        let state_dir = self.store.state_dir.clone();
        let tx = self.store.transaction()?;
        let receipt: Option<(String, i64)> = tx
            .query_row(
                "SELECT digest,LENGTH(CAST(response AS BLOB)) FROM receipts WHERE request_id=?1",
                [&request.request_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        if let Some((prior, response_len)) = receipt {
            if prior != digest {
                return Err(CoreError::new(
                    "idempotency_conflict",
                    "Request ID already binds a different payload",
                ));
            }
            if response_len < 0 || response_len as usize > MAX_RESULT_BYTES + 2_000 {
                return Err(CoreError::new(
                    "response_too_large",
                    "Stored response exceeds byte budget",
                ));
            }
            let response: String = tx.query_row(
                "SELECT response FROM receipts WHERE request_id=?1",
                [&request.request_id],
                |r| r.get(0),
            )?;
            return Ok(serde_json::from_str(&response)?);
        }
        let intent: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM tool_intents WHERE request_id=?1 UNION ALL SELECT 1 FROM recovery_writes WHERE request_id=?1)",
            [&request.request_id],
            |r| r.get(0),
        )?;
        if intent {
            return Err(CoreError::new(
                "idempotency_conflict",
                "Request ID is bound to a tool intent",
            ));
        }
        tx.execute_batch("SAVEPOINT domain_request")?;
        let outcome = dispatch_tx(
            &tx,
            &request.command,
            &self.workspace_root,
            &state_dir,
            &request.request_id,
            busy,
            &mut pending,
            &mut check_launch,
        )
        .and_then(|result| {
            if serde_json::to_vec(&result)?.len() > MAX_RESULT_BYTES {
                Err(CoreError::new(
                    "response_too_large",
                    "Result exceeds response byte budget",
                ))
            } else {
                Ok(result)
            }
        });
        if outcome.is_err() {
            tx.execute_batch("ROLLBACK TO domain_request")?;
        }
        tx.execute_batch("RELEASE domain_request")?;
        let cursor = store::cursor(&tx)?;
        let response = match outcome {
            Ok(result) => Response {
                version: PROTOCOL_VERSION,
                request_id: Some(request.request_id.clone()),
                ok: true,
                event_cursor: cursor,
                result: Some(result),
                error: None,
            },
            Err(error) => Response::failure(Some(request.request_id.clone()), cursor, error),
        };
        tx.execute(
            "INSERT INTO receipts(request_id,digest,response) VALUES(?1,?2,?3)",
            params![
                request.request_id,
                digest,
                serde_json::to_string(&response)?
            ],
        )?;
        tx.commit()?;
        if response.ok {
            if let Some(control) = &stop {
                control.signal_cancel();
            }
            if let Some(launch) = check_launch {
                self.check = Some(runner::Active::start(launch));
            }
        }
        drop(guard);
        if let Some(launch) = pending {
            self.launch(launch);
        }
        Ok(response)
    }
    fn cache_create_failure(
        &mut self,
        request: &Request,
        digest: &str,
        error: CoreError,
    ) -> CoreResult<Response> {
        let tx = self.store.transaction()?;
        let bound: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM receipts WHERE request_id=?1 UNION ALL SELECT 1 FROM tool_intents WHERE request_id=?1 UNION ALL SELECT 1 FROM recovery_writes WHERE request_id=?1)", [&request.request_id], |r| r.get(0))?;
        let response =
            Response::failure(Some(request.request_id.clone()), store::cursor(&tx)?, error);
        if !bound {
            tx.execute(
                "INSERT INTO receipts(request_id,digest,response) VALUES(?1,?2,?3)",
                params![
                    request.request_id,
                    digest,
                    serde_json::to_string(&response)?
                ],
            )?;
        }
        tx.commit()?;
        Ok(response)
    }
    fn recover_artifact(&mut self, request: &Request, digest: &str) -> CoreResult<Response> {
        let Command::ToolRecovery {
            intent_id,
            mode,
            expected_current_hash,
        } = &request.command
        else {
            unreachable!()
        };
        let state_dir = self.store.state_dir.clone();
        let tx = self.store.transaction()?;
        let receipt: Option<(String, String)> = tx
            .query_row(
                "SELECT digest,response FROM receipts WHERE request_id=?1",
                [&request.request_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        if let Some((prior, response)) = receipt {
            if prior != digest {
                return Err(CoreError::new(
                    "idempotency_conflict",
                    "Request ID already binds a different payload",
                ));
            }
            return Ok(serde_json::from_str(&response)?);
        }
        let bound: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM tool_intents WHERE request_id=?1)",
            [&request.request_id],
            |r| r.get(0),
        )?;
        if bound {
            return Err(CoreError::new(
                "idempotency_conflict",
                "Request ID is bound to a tool intent",
            ));
        }
        let pending: Option<(String, String, String)> = tx
            .query_row(
                "SELECT request_digest,intent_id,status FROM recovery_writes WHERE request_id=?1",
                [&request.request_id],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .optional()?;
        if let Some((d, id, status)) = &pending {
            if d != digest || id != intent_id {
                return Err(CoreError::new(
                    "idempotency_conflict",
                    "Recovery ID already binds a different payload",
                ));
            }
            if status != "prepared" {
                return Err(CoreError::new(
                    "recovery_required",
                    "Recovery request is no longer active",
                ));
            }
        }
        if matches!(mode, RecoveryMode::SafeAbandon) && expected_current_hash.is_none() {
            let restore: Option<(String,String,String,String,String,String,Vec<u8>,String)> = tx.query_row("SELECT r.intent_id,r.expected_hash,r.status,i.mission_id,i.target,b.operation,b.backup,b.identity FROM recovery_writes r JOIN tool_intents i ON i.request_id=r.intent_id JOIN replacement_backups b ON b.request_id=i.request_id WHERE r.request_id=?1", [intent_id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?,r.get(5)?,r.get(6)?,r.get(7)?))).optional()?;
            if let Some((
                original,
                expected,
                restore_status,
                mission,
                target,
                raw,
                backup,
                identity,
            )) = restore
            {
                if restore_status != "prepared" {
                    return Err(CoreError::new(
                        "recovery_required",
                        "Restore is not prepared",
                    ));
                }
                let operation: ToolOperation = serde_json::from_str(&raw)?;
                tools::authorize(&tx, &mission, &operation)?;
                if tools::sha(&backup) != tools::previous_digest(&tx, &mission, &operation)? {
                    return Err(CoreError::new(
                        "recovery_required",
                        "Backup verification failed",
                    ));
                }
                let mut broker = tools::prepare(&self.workspace_root, &state_dir, &operation)?;
                let (current_identity, current) = broker.replacement_snapshot()?;
                if broker.target() != target
                    || current_identity != identity
                    || tools::sha(&current) != expected
                {
                    return Err(CoreError::new(
                        "recovery_required",
                        "Restore effect is ambiguous",
                    ));
                }
                tx.execute(
                    "UPDATE recovery_writes SET status='abandoned' WHERE request_id=?1",
                    [intent_id],
                )?;
                return Self::recovery_receipt(
                    tx,
                    request,
                    digest,
                    json!({"intent_id":intent_id,"original_intent_id":original,"status":"abandoned"}),
                );
            }
        }
        let row: Option<(String,String,String,String,String)> = tx.query_row("SELECT request_digest,mission_id,target,content_digest,status FROM tool_intents WHERE request_id=?1", [intent_id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))).optional()?;
        let (original_digest, mission, target, new_hash, status) =
            row.ok_or_else(|| CoreError::new("not_found", "Intent not found"))?;
        let saved: Option<(String,String,String,Vec<u8>)> = tx.query_row("SELECT operation,identity,previous_digest,backup FROM replacement_backups WHERE request_id=?1", [intent_id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))).optional()?;
        if matches!(mode, RecoveryMode::Inspect) {
            if expected_current_hash.is_some() {
                return Err(CoreError::invalid("Unexpected current hash"));
            }
            let result = json!({"intent_id":intent_id,"mission_id":mission,"target":target,"status":status,"kind":if saved.is_some(){"replace"}else{"create"}});
            return Self::recovery_receipt(tx, request, digest, result);
        }
        if matches!(mode, RecoveryMode::SafeAbandon) {
            if expected_current_hash.is_some() || status != "prepared" || saved.is_some() {
                return Err(CoreError::new(
                    "recovery_required",
                    "Only a prepared no-effect create can be released",
                ));
            }
            let raw: Option<String> = tx
                .query_row(
                    "SELECT operation FROM intent_operations WHERE request_id=?1",
                    [intent_id],
                    |r| r.get(0),
                )
                .optional()?;
            let operation: ToolOperation = serde_json::from_str(&raw.ok_or_else(|| {
                CoreError::new("recovery_required", "Create operation unavailable")
            })?)?;
            if !matches!(operation, ToolOperation::Create { .. }) {
                return Err(CoreError::new("recovery_required", "Not a create"));
            }
            tools::authorize(&tx, &mission, &operation)?;
            let broker = tools::prepare(&self.workspace_root, &state_dir, &operation)?;
            if broker.target() != target || !broker.create_is_absent()? {
                return Err(CoreError::new(
                    "recovery_required",
                    "Create target is not absent",
                ));
            }
            tx.execute(
                "UPDATE tool_intents SET status='abandoned' WHERE request_id=?1",
                [intent_id],
            )?;
            return Self::recovery_receipt(
                tx,
                request,
                digest,
                json!({"intent_id":intent_id,"status":"abandoned"}),
            );
        }
        let (raw, identity, old_hash, backup) = saved.ok_or_else(|| {
            CoreError::new(
                "recovery_required",
                "Verified replacement backup unavailable",
            )
        })?;
        if backup.len() > 32768 || tools::sha(&backup) != old_hash {
            return Err(CoreError::new(
                "recovery_required",
                "Backup verification failed",
            ));
        }
        let operation: ToolOperation = serde_json::from_str(&raw)?;
        let pin = tools::authorize(&tx, &mission, &operation)?;
        if !matches!(&operation, ToolOperation::Replace { content, .. } if tools::sha(content.as_bytes()) == new_hash)
        {
            return Err(CoreError::new(
                "recovery_required",
                "Replacement intent digest differs",
            ));
        }
        if tools::previous_digest(&tx, &mission, &operation)? != old_hash {
            return Err(CoreError::new(
                "recovery_required",
                "Approved previous digest differs",
            ));
        }
        let mut broker = tools::prepare(&self.workspace_root, &state_dir, &operation)?;
        let (current_identity, current) = broker.replacement_snapshot()?;
        if broker.target() != target || current_identity != identity {
            return Err(CoreError::new(
                "recovery_required",
                "Target identity differs",
            ));
        }
        let current_hash = tools::sha(&current);
        if matches!(mode, RecoveryMode::Finalize) {
            let restoring: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM recovery_writes WHERE intent_id=?1 AND status='prepared')", [intent_id], |r| r.get(0))?;
            if restoring {
                return Err(CoreError::new("recovery_required", "Restore is unresolved"));
            }
            if expected_current_hash.is_some() || status != "prepared" || current_hash != new_hash {
                return Err(CoreError::new(
                    "recovery_required",
                    "Replacement cannot be finalized",
                ));
            }
            let result = json!({"mission_id":mission,"skill":pin,"sha256":new_hash,"bytes":current.len(),"readback_verified":true});
            store::event(
                &tx,
                "tool_effect",
                json!({"request_id":intent_id,"mission_id":mission,"action":"artifact_replace","target":target,"sha256":new_hash,"skill":result["skill"]}),
            )?;
            tx.execute(
                "UPDATE tool_intents SET status='confirmed' WHERE request_id=?1",
                [intent_id],
            )?;
            let original = Response {
                version: PROTOCOL_VERSION,
                request_id: Some(intent_id.clone()),
                ok: true,
                event_cursor: store::cursor(&tx)?,
                result: Some(result),
                error: None,
            };
            tx.execute(
                "INSERT INTO receipts(request_id,digest,response) VALUES(?1,?2,?3)",
                params![
                    intent_id,
                    original_digest,
                    serde_json::to_string(&original)?
                ],
            )?;
            return Self::recovery_receipt(
                tx,
                request,
                digest,
                json!({"intent_id":intent_id,"status":"confirmed"}),
            );
        }
        if !matches!(mode, RecoveryMode::Restore) || (status != "prepared" && status != "confirmed")
        {
            return Err(CoreError::new(
                "recovery_required",
                "Restore unavailable for intent",
            ));
        }
        let other_pending: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM tool_intents WHERE target=?1 COLLATE NOCASE AND status='prepared' AND request_id<>?2 UNION ALL SELECT 1 FROM recovery_writes r JOIN tool_intents i ON i.request_id=r.intent_id WHERE i.target=?1 COLLATE NOCASE AND r.status='prepared' AND r.request_id<>?3)", params![target,intent_id,request.request_id], |r| r.get(0))?;
        if other_pending {
            return Err(CoreError::new(
                "recovery_required",
                "Another target intent is unresolved",
            ));
        }
        if pending.is_some() {
            if current_hash != old_hash {
                return Err(CoreError::new(
                    "recovery_required",
                    "Interrupted restore requires inspection",
                ));
            }
            tx.execute(
                "UPDATE recovery_writes SET status='confirmed' WHERE request_id=?1",
                [&request.request_id],
            )?;
            tx.execute(
                "UPDATE tool_intents SET status='restored' WHERE request_id=?1",
                [intent_id],
            )?;
            store::event(
                &tx,
                "tool_restore",
                json!({"request_id":request.request_id,"intent_id":intent_id,"sha256":old_hash}),
            )?;
            return Self::recovery_receipt(
                tx,
                request,
                digest,
                json!({"intent_id":intent_id,"status":"restored","sha256":old_hash}),
            );
        }
        let expected = expected_current_hash.as_deref().unwrap_or(&new_hash);
        if current_hash != expected {
            return Err(CoreError::new(
                "recovery_required",
                "Current content differs from expected snapshot",
            ));
        }
        tx.execute("INSERT INTO recovery_writes(request_id,request_digest,intent_id,expected_hash,status) VALUES(?1,?2,?3,?4,'prepared')", params![request.request_id,digest,intent_id,current_hash])?;
        tx.commit()?;
        #[cfg(feature = "test-fault-injection")]
        if std::env::var_os("SYNAPSE_TEST_CRASH_BEFORE_RESTORE").is_some() {
            std::process::exit(86);
        }
        let tx = self.store.transaction()?;
        tools::authorize(&tx, &mission, &operation)?;
        broker.replacement_write(&backup).map_err(|_| {
            CoreError::new("recovery_required", "Restore outcome requires inspection")
        })?;
        #[cfg(feature = "test-fault-injection")]
        if std::env::var_os("SYNAPSE_TEST_CRASH_AFTER_RESTORE").is_some() {
            std::process::exit(86);
        }
        tx.execute(
            "UPDATE recovery_writes SET status='confirmed' WHERE request_id=?1",
            [&request.request_id],
        )?;
        tx.execute(
            "UPDATE tool_intents SET status='restored' WHERE request_id=?1",
            [intent_id],
        )?;
        store::event(
            &tx,
            "tool_restore",
            json!({"request_id":request.request_id,"intent_id":intent_id,"sha256":old_hash}),
        )?;
        Self::recovery_receipt(
            tx,
            request,
            digest,
            json!({"intent_id":intent_id,"status":"restored","sha256":old_hash}),
        )
    }
    fn recovery_receipt(
        tx: Transaction<'_>,
        request: &Request,
        digest: &str,
        result: Value,
    ) -> CoreResult<Response> {
        let response = Response {
            version: PROTOCOL_VERSION,
            request_id: Some(request.request_id.clone()),
            ok: true,
            event_cursor: store::cursor(&tx)?,
            result: Some(result),
            error: None,
        };
        tx.execute(
            "INSERT INTO receipts(request_id,digest,response) VALUES(?1,?2,?3)",
            params![
                request.request_id,
                digest,
                serde_json::to_string(&response)?
            ],
        )?;
        tx.commit()?;
        Ok(response)
    }
    fn replace_artifact(&mut self, request: &Request, digest: &str) -> CoreResult<Response> {
        let Command::ToolExecute {
            mission_id,
            operation,
        } = &request.command
        else {
            unreachable!()
        };
        let ToolOperation::Replace { content, .. } = operation else {
            unreachable!()
        };
        if content.len() > 32768 {
            return Err(CoreError::invalid("Content exceeds 32768 bytes"));
        }
        let state_dir = self.store.state_dir.clone();
        let tx = self.store.transaction()?;
        let prior: Option<(String, String)> = tx
            .query_row(
                "SELECT digest,response FROM receipts WHERE request_id=?1",
                [&request.request_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        if let Some((d, response)) = prior {
            if d != digest {
                return Err(CoreError::new(
                    "idempotency_conflict",
                    "Request ID already binds a different payload",
                ));
            }
            return Ok(serde_json::from_str(&response)?);
        }
        let recovery_bound: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM recovery_writes WHERE request_id=?1)",
            [&request.request_id],
            |r| r.get(0),
        )?;
        if recovery_bound {
            return Err(CoreError::new(
                "idempotency_conflict",
                "Request ID is bound to recovery",
            ));
        }
        let prior: Option<String> = tx
            .query_row(
                "SELECT request_digest FROM tool_intents WHERE request_id=?1",
                [&request.request_id],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(d) = prior {
            return Err(if d == digest {
                CoreError::new(
                    "recovery_required",
                    "Prepared replacement requires recovery",
                )
            } else {
                CoreError::new(
                    "idempotency_conflict",
                    "Request ID already binds a different payload",
                )
            });
        }
        let pin = tools::authorize(&tx, mission_id, operation)?;
        let approved_previous = tools::previous_digest(&tx, mission_id, operation)?;
        let mut broker = tools::prepare(&self.workspace_root, &state_dir, operation)?;
        let target = broker.target();
        let reserved: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM tool_intents WHERE target=?1 COLLATE NOCASE AND status='prepared' UNION ALL SELECT 1 FROM recovery_writes r JOIN tool_intents i ON i.request_id=r.intent_id WHERE i.target=?1 COLLATE NOCASE AND r.status='prepared')", [&target], |r| r.get(0))?;
        if reserved {
            return Err(CoreError::new("recovery_required", "Target is reserved"));
        }
        let (identity, backup) = broker.replacement_snapshot()?;
        if tools::sha(&backup) != approved_previous {
            return Err(CoreError::new(
                "permission_denied",
                "Previous artifact digest differs",
            ));
        }
        tx.execute("INSERT INTO tool_intents(request_id,request_digest,mission_id,target,content_digest,status) VALUES(?1,?2,?3,?4,?5,'prepared')", params![request.request_id,digest,mission_id,target,tools::sha(content.as_bytes())])?;
        tx.execute("INSERT INTO replacement_backups(request_id,operation,identity,previous_digest,backup) VALUES(?1,?2,?3,?4,?5)", params![request.request_id,serde_json::to_string(operation)?,identity,approved_previous,backup])?;
        tx.commit()?;
        #[cfg(feature = "test-fault-injection")]
        if std::env::var_os("SYNAPSE_TEST_CRASH_BEFORE_REPLACE").is_some() {
            std::process::exit(86);
        }
        let tx = self.store.transaction()?;
        tools::authorize(&tx, mission_id, operation)?;
        let (stored_identity, stored_hash, stored_backup): (String,String,Vec<u8>) = tx.query_row("SELECT identity,previous_digest,backup FROM replacement_backups WHERE request_id=?1", [&request.request_id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?)))?;
        let (current_identity, current_backup) = broker.replacement_snapshot()?;
        if stored_identity != identity
            || current_identity != identity
            || stored_hash != approved_previous
            || tools::sha(&stored_backup) != approved_previous
            || stored_backup != backup
            || current_backup != backup
        {
            return Err(CoreError::new(
                "recovery_required",
                "Persisted backup or target verification failed",
            ));
        }
        broker.replacement_write(content.as_bytes()).map_err(|_| {
            CoreError::new("recovery_required", "Replacement outcome requires recovery")
        })?;
        #[cfg(feature = "test-fault-injection")]
        if std::env::var_os("SYNAPSE_TEST_CRASH_AFTER_REPLACE").is_some() {
            std::process::exit(86);
        }
        let result = json!({"mission_id":mission_id,"skill":pin,"sha256":tools::sha(content.as_bytes()),"bytes":content.len(),"readback_verified":true});
        store::event(
            &tx,
            "tool_effect",
            json!({"request_id":request.request_id,"mission_id":mission_id,"action":"artifact_replace","target":target,"sha256":result["sha256"],"skill":result["skill"]}),
        )?;
        #[cfg(feature = "test-fault-injection")]
        if std::env::var_os("SYNAPSE_TEST_CRASH_BEFORE_REPLACE_CONFIRM").is_some() {
            std::process::exit(86);
        }
        tx.execute(
            "UPDATE tool_intents SET status='confirmed' WHERE request_id=?1",
            [&request.request_id],
        )?;
        let response = Response {
            version: PROTOCOL_VERSION,
            request_id: Some(request.request_id.clone()),
            ok: true,
            event_cursor: store::cursor(&tx)?,
            result: Some(result),
            error: None,
        };
        tx.execute(
            "INSERT INTO receipts(request_id,digest,response) VALUES(?1,?2,?3)",
            params![
                request.request_id,
                digest,
                serde_json::to_string(&response)?
            ],
        )?;
        tx.commit()?;
        Ok(response)
    }
    fn create_artifact(&mut self, request: &Request, digest: &str) -> CoreResult<Response> {
        let Command::ToolExecute {
            mission_id,
            operation,
        } = &request.command
        else {
            unreachable!()
        };
        let ToolOperation::Create { content, .. } = operation else {
            unreachable!()
        };
        let state = self.store.state_dir.clone();
        let tx = self.store.transaction()?;
        let prior: Option<(String, String)> = tx
            .query_row(
                "SELECT digest,response FROM receipts WHERE request_id=?1",
                [&request.request_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        if let Some((d, response)) = prior {
            if d != digest {
                return Err(CoreError::new(
                    "idempotency_conflict",
                    "Request ID already binds a different payload",
                ));
            }
            return Ok(serde_json::from_str(&response)?);
        }
        let recovery_bound: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM recovery_writes WHERE request_id=?1)",
            [&request.request_id],
            |r| r.get(0),
        )?;
        if recovery_bound {
            return Err(CoreError::new(
                "idempotency_conflict",
                "Request ID is bound to recovery",
            ));
        }
        let prior: Option<String> = tx
            .query_row(
                "SELECT request_digest FROM tool_intents WHERE request_id=?1",
                [&request.request_id],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(d) = prior {
            if d != digest {
                return Err(CoreError::new(
                    "idempotency_conflict",
                    "Request ID already binds a different payload",
                ));
            }
            return Err(CoreError::new(
                "recovery_required",
                "Prepared artifact requires manual recovery",
            ));
        }
        let pin = tools::authorize(&tx, mission_id, operation)?;
        if content.len() > 32768 {
            return Err(CoreError::invalid("Content exceeds 32768 bytes"));
        }
        let broker = tools::prepare(&self.workspace_root, &state, operation)?;
        let target = broker.target();
        let reserved: bool = tx.query_row("SELECT EXISTS(SELECT 1 FROM tool_intents WHERE target=?1 COLLATE NOCASE AND status='prepared' UNION ALL SELECT 1 FROM recovery_writes r JOIN tool_intents i ON i.request_id=r.intent_id WHERE i.target=?1 COLLATE NOCASE AND r.status='prepared')", [&target], |r| r.get(0))?;
        if reserved {
            return Err(CoreError::new(
                "recovery_required",
                "Target reserved by a prepared artifact",
            ));
        }
        tx.execute("INSERT INTO tool_intents(request_id,request_digest,mission_id,target,content_digest,status) VALUES(?1,?2,?3,?4,?5,'prepared')", params![request.request_id,digest,mission_id,target,tools::sha(content.as_bytes())])?;
        tx.execute(
            "INSERT INTO intent_operations(request_id,operation) VALUES(?1,?2)",
            params![request.request_id, serde_json::to_string(operation)?],
        )?;
        tx.commit()?;
        #[cfg(feature = "test-fault-injection")]
        if std::env::var_os("SYNAPSE_TEST_CRASH_AFTER_TOOL_PREPARE").is_some() {
            std::process::exit(86);
        }
        let tx = self.store.transaction()?;
        tools::authorize(&tx, mission_id, operation)?;
        let mut result = broker.execute(operation).map_err(|_| {
            CoreError::new(
                "recovery_required",
                "Artifact outcome is ambiguous; manual recovery required",
            )
        })?;
        result["mission_id"] = json!(mission_id);
        result["skill"] = pin;
        store::event(
            &tx,
            "tool_effect",
            json!({"request_id":request.request_id,"mission_id":mission_id,"action":"artifact_create","target":target,"sha256":result["sha256"],"skill":result["skill"]}),
        )?;
        tx.execute(
            "UPDATE tool_intents SET status='confirmed' WHERE request_id=?1",
            [&request.request_id],
        )?;
        let response = Response {
            version: PROTOCOL_VERSION,
            request_id: Some(request.request_id.clone()),
            ok: true,
            event_cursor: store::cursor(&tx)?,
            result: Some(result),
            error: None,
        };
        tx.execute(
            "INSERT INTO receipts(request_id,digest,response) VALUES(?1,?2,?3)",
            params![
                request.request_id,
                digest,
                serde_json::to_string(&response)?
            ],
        )?;
        tx.commit()?;
        Ok(response)
    }
    fn launch(&mut self, launch: conversation::Launch) {
        let id = launch.id.clone();
        let purpose = launch.purpose;
        let stop = Arc::new(worker::Stop::default());
        let (sender, result) = mpsc::sync_channel(1);
        let worker_stop = stop.clone();
        std::thread::spawn(move || {
            let _ = sender.send(worker::run(launch, worker_stop));
        });
        self.active = Some(Active {
            id,
            stop,
            result,
            purpose,
            outcome: None,
        });
    }
    pub fn poll_project_check(&mut self) -> CoreResult<()> {
        let Some(active) = &self.check else {
            return Ok(());
        };
        if self.check_event.is_none() {
            self.check_event = Some(match active.events.try_recv() {
                Ok(event) => event,
                Err(mpsc::TryRecvError::Empty) => return Ok(()),
                Err(mpsc::TryRecvError::Disconnected) => runner::Event::Finished(runner::Outcome {
                    receipt: None,
                    error: Some("worker_interrupted"),
                    cleanup_complete: false,
                }),
            });
        }
        let tx = self.store.transaction()?;
        match self.check_event.as_ref().unwrap() {
            runner::Event::Prepared(digest) => {
                let approved = integration::allow_tool(&tx, &active.id, digest)?
                    && checks::prepare(&tx, &active.id, digest)?;
                tx.commit()?;
                if approved {
                    let _ = active.permit.try_send(());
                } else {
                    active.cancel();
                }
            }
            runner::Event::Finished(outcome) => {
                checks::finish(&tx, &active.id, outcome)?;
                tx.commit()?;
                self.check.take().unwrap().join();
            }
        }
        self.check_event = None;
        Ok(())
    }
    fn advance_mission(&mut self) -> CoreResult<()> {
        let state = self.store.state_dir.clone();
        let tx = self.store.transaction()?;
        let next = mission_run::advance(
            &tx,
            &state,
            &self.workspace_root,
            self.active.is_some(),
            self.check.is_some(),
        )?;
        tx.commit()?;
        match next {
            Some(mission_run::Next::Check(launch)) => {
                self.check = Some(runner::Active::start(launch))
            }
            Some(mission_run::Next::Review(launch)) => self.launch(launch),
            None => {}
        }
        Ok(())
    }

    fn advance_integration(&mut self) -> CoreResult<()> {
        if let Some(launch) =
            integration::advance(&mut self.store, &self.workspace_root, self.check.is_some())?
        {
            self.check = Some(runner::Active::start(launch));
        }
        Ok(())
    }

    /// The standalone host can finish already-started jobs without a client.
    pub fn poll_local_host(&mut self) -> CoreResult<()> {
        self.drain()?;
        self.poll_mission()
    }

    pub fn poll_mission(&mut self) -> CoreResult<()> {
        self.poll_project_check()?;
        if self.active.as_ref().is_some_and(|active| {
            matches!(
                active.purpose,
                conversation::Purpose::MissionGenerate | conversation::Purpose::MissionReview
            )
        }) {
            self.drain()?;
        }
        self.advance_mission()?;
        self.advance_integration()
    }

    fn drain(&mut self) -> CoreResult<()> {
        let Some(active) = &mut self.active else {
            return Ok(());
        };
        if active.outcome.is_none() {
            active.outcome = Some(match active.result.try_recv() {
                Ok(outcome) => outcome,
                Err(mpsc::TryRecvError::Empty) => return Ok(()),
                Err(mpsc::TryRecvError::Disconnected) => Err("worker_crashed".into()),
            });
        }
        let outcome = active.outcome.clone().unwrap();
        let id = active.id.clone();
        let tx = self.store.transaction()?;
        match active.purpose {
            conversation::Purpose::Learning => learning::complete(&tx, &id, outcome)?,
            conversation::Purpose::Conversation => conversation::complete(&tx, &id, outcome)?,
            conversation::Purpose::MissionPlan => planner::complete(&tx, &id, outcome)?,
            purpose @ (conversation::Purpose::MissionGenerate
            | conversation::Purpose::MissionReview) => {
                mission_run::complete(&tx, &id, purpose, outcome)?
            }
        }
        tx.commit()?;
        self.active = None;
        Ok(())
    }
    pub fn dispatch_line(&mut self, line: &[u8]) -> Response {
        let cursor = self.store.event_cursor().unwrap_or(0);
        if line.len() > MAX_REQUEST_BYTES {
            return Response::failure(
                None,
                cursor,
                CoreError::new("request_too_large", "Request exceeds 65536 bytes"),
            );
        }
        let parsed = serde_json::from_slice::<Request>(line).and_then(|request| {
            let mut value = serde_json::from_slice::<Value>(line)?;
            // Empty explicit context is equivalent to its omitted wire form.
            if matches!(&request.command, Command::ConversationStart { context, .. } | Command::MissionPlanStart { context, .. } if context.is_empty())
                && value["command"]["context"] == json!([])
            {
                value["command"].as_object_mut().unwrap().remove("context");
            }
            // Internally tagged unit variants can silently ignore extra fields.
            // Reconstructing the envelope rejects those fields at every depth.
            if serde_json::to_value(&request)? != value {
                return Err(<serde_json::Error as serde::de::Error>::custom(
                    "Unknown or noncanonical fields",
                ));
            }
            Ok(request)
        });
        match parsed {
            Ok(request) => self.dispatch(request),
            Err(_) => Response::failure(
                None,
                cursor,
                CoreError::invalid("Malformed request or unknown fields"),
            ),
        }
    }
}
impl Drop for Core {
    fn drop(&mut self) {
        if let Some(check) = self.check.take() {
            check.cancel();
            let id = check.id.clone();
            let observed = check.join();
            let outcome = match self.check_event.take() {
                Some(runner::Event::Finished(outcome)) => Some(outcome),
                _ => observed,
            };
            if let Some(outcome) = outcome {
                let _ = (|| -> CoreResult<()> {
                    let tx = self.store.transaction()?;
                    checks::shutdown(&tx, &id, &outcome)?;
                    tx.commit()?;
                    Ok(())
                })();
            }
        }
        if let Some(active) = &self.active {
            active.stop.cancel();
        }
    }
}

/// Focused handlers must use this transaction, never open their own writer.
fn dispatch_tx(
    tx: &Transaction<'_>,
    command: &Command,
    _workspace_root: &Path,
    state_dir: &Path,
    request_id: &str,
    busy: bool,
    pending: &mut Option<conversation::Launch>,
    check_launch: &mut Option<runner::Launch>,
) -> CoreResult<Value> {
    match command {
        Command::Health => {
            let storage_schema: u32 = tx.pragma_query_value(None, "user_version", |r| r.get(0))?;
            Ok(
                json!({"identity":"A.R.T.E.M.I.S.","protocol_version":1,"storage_schema":storage_schema,"journal_mode":"wal","synchronous":"full"}),
            )
        }
        Command::EventsRead { after, limit } => store::events_read(tx, *after, *limit),
        Command::ProjectRegister { scope, root } => {
            crate::projects::register(tx, scope, root, state_dir)
        }
        Command::ProjectGet { scope } => crate::projects::get(tx, scope, state_dir),
        Command::ChatCreate {
            chat_id,
            title,
            scope,
        } => chats::create(tx, chat_id, title, scope),
        Command::ChatGet {
            chat_id,
            after,
            limit,
        } => chats::get(tx, chat_id, after.unwrap_or(0), limit.unwrap_or(50)),
        Command::MessageAppend {
            chat_id,
            message_id,
            role,
            content,
        } => chats::append(tx, chat_id, message_id, role, content),
        Command::MemoryPut {
            scope,
            key,
            kind,
            content,
            expected_revision,
            provenance,
            status,
        } => memory::put(
            tx,
            scope,
            key,
            kind,
            content,
            *expected_revision,
            provenance,
            status,
        ),
        Command::MemoryGet {
            scope,
            context_reference,
            key,
            after_revision,
            limit,
        } => memory::get(
            tx,
            scope,
            context_reference,
            key,
            after_revision.unwrap_or(0),
            limit.unwrap_or(50),
        ),
        Command::MissionPlanStart {
            mission_id,
            scope,
            model_id,
            objective,
            skill,
            context,
            review_model_id,
            review_generation,
        } => {
            if busy {
                return Err(CoreError::new(
                    "worker_busy",
                    "One inference job is already running",
                ));
            }
            let (result, launch) = planner::start(
                tx,
                request_id,
                mission_id,
                scope,
                model_id,
                objective,
                skill.as_ref(),
                context,
                review_model_id,
                review_generation,
            )?;
            *pending = Some(launch);
            Ok(result)
        }
        Command::MissionPlanGet { mission_id } => planner::get(tx, mission_id),
        Command::MissionPropose {
            mission_id,
            contract,
        } => missions::propose(tx, mission_id, contract),
        Command::MissionApprove {
            mission_id,
            contract_digest,
        } => {
            let result = missions::approve(tx, mission_id, contract_digest)?;
            integration::bind_approval(tx, mission_id, _workspace_root, state_dir)?;
            Ok(result)
        }
        Command::MissionCancel { mission_id, reason } => {
            let result = missions::stop(tx, mission_id, "cancelled", reason)?;
            checks::stop_mission(tx, mission_id, "cancelled")?;
            mission_run::stop(tx, mission_id, "cancelled")?;
            integration::stop(tx, mission_id, "cancelled")?;
            Ok(result)
        }
        Command::MissionRevoke { mission_id, reason } => {
            let result = missions::stop(tx, mission_id, "revoked", reason)?;
            checks::stop_mission(tx, mission_id, "revoked")?;
            mission_run::stop(tx, mission_id, "revoked")?;
            integration::stop(tx, mission_id, "revoked")?;
            Ok(result)
        }
        Command::MissionGet { mission_id } => missions::get(tx, mission_id),
        Command::ProjectCheckStart {
            mission_id,
            check_index,
            artifacts,
        } => {
            let (result, launch) = checks::start(
                tx,
                request_id,
                mission_id,
                *check_index,
                artifacts,
                state_dir,
                _workspace_root,
            )?;
            *check_launch = Some(launch);
            Ok(result)
        }
        Command::ProjectCheckGet { check_id } => checks::get(tx, check_id),
        Command::ProjectCheckCancel { check_id } => checks::cancel(tx, check_id),
        Command::ModelRegister { model } => registry::model_register(tx, model),
        Command::ModelsList { after, limit } => {
            registry::models_list(tx, after.unwrap_or(0), limit.unwrap_or(50))
        }
        Command::ModelGet { model_id } => registry::model_get(tx, model_id),
        Command::SkillRegister { skill } => registry::skill_register(tx, skill),
        Command::SkillsList {
            scope,
            after,
            limit,
        } => registry::skills_list(tx, scope, after.unwrap_or(0), limit.unwrap_or(50)),
        Command::SkillGet {
            scope,
            skill_id,
            version,
        } => registry::skill_get(tx, scope, skill_id, version),
        Command::CapabilitiesList => Ok(registry::capabilities()),
        Command::Inference { model_id, prompt } => {
            if busy {
                return Err(CoreError::new(
                    "worker_busy",
                    "One inference job is already running",
                ));
            }
            let (result, launch) =
                conversation::start(tx, request_id, None, model_id, prompt, None, &[])?;
            *pending = Some(launch);
            Ok(result)
        }
        Command::ConversationStart {
            chat_id,
            model_id,
            content,
            skill,
            context,
        } => {
            if busy {
                return Err(CoreError::new(
                    "worker_busy",
                    "One inference job is already running",
                ));
            }
            let (result, launch) = conversation::start(
                tx,
                request_id,
                Some(chat_id),
                model_id,
                content,
                skill.as_ref(),
                context,
            )?;
            *pending = Some(launch);
            Ok(result)
        }
        Command::JobGet { job_id } => conversation::get(tx, job_id),
        Command::LearningGet { source_job_id } => learning::get(tx, source_job_id),
        Command::JobCancel { job_id } => conversation::cancel(tx, job_id),
        Command::MissionExecute { mission_id } => {
            let (result, launch) = mission_run::start(tx, mission_id, busy)?;
            *pending = Some(launch);
            Ok(result)
        }
        Command::MissionRunGet { mission_id } => mission_run::get(tx, mission_id),
        Command::MissionRecoveryInspect { mission_id } => {
            mission_recovery::inspect(tx, mission_id, _workspace_root, state_dir)
        }
        Command::MissionRecoveryResolve { mission_id, mode } => {
            integration::resolve(tx, mission_id, *mode, _workspace_root, state_dir)
        }
        Command::ToolExecute {
            mission_id,
            operation,
        } => {
            let pin = tools::authorize(tx, mission_id, operation)?;
            let broker = tools::prepare(_workspace_root, state_dir, operation)?;
            tools::authorize(tx, mission_id, operation)?;
            let mut result = broker.execute(operation)?;
            result["mission_id"] = json!(mission_id);
            result["skill"] = pin;
            store::event(
                tx,
                "tool_observation",
                json!({"request_id":request_id,"mission_id":mission_id,"action":tools::details(operation).0,"target":broker.target(),"skill":result["skill"]}),
            )?;
            Ok(result)
        }
        Command::ToolRecovery { .. } => unreachable!(),
    }
}
