use crate::{
    chats,
    contracts::*,
    conversation, memory, missions, registry,
    store::{self, Store},
    worker,
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
}

/// Local human client entrypoint. Never expose dispatch to worker output.
pub struct Core {
    store: Store,
    workspace_root: PathBuf,
    active: Option<Active>,
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
        })
    }
    pub fn dispatch(&mut self, request: Request) -> Response {
        if let Err(error) = self.drain() {
            return Response::failure(Some(request.request_id), self.event_cursor(), error);
        }
        let id = Some(request.request_id.clone());
        let result = self.dispatch_durable(&request);
        match result {
            Ok(response) => {
                if response.ok {
                    if let Command::JobCancel { job_id } = &request.command {
                        if let Some(active) = &self.active {
                            if active.id == *job_id {
                                active.stop.cancel();
                            }
                        }
                    }
                }
                response
            }
            Err(error) => Response::failure(id, self.store.event_cursor().unwrap_or(0), error),
        }
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
        let digest = store::digest(request)?;
        let mut pending = None;
        let busy = self.active.is_some();
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
        tx.execute_batch("SAVEPOINT domain_request")?;
        let outcome = dispatch_tx(
            &tx,
            &request.command,
            &self.workspace_root,
            &request.request_id,
            busy,
            &mut pending,
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
        if let Some(launch) = pending {
            self.launch(launch);
        }
        Ok(response)
    }
    fn launch(&mut self, launch: conversation::Launch) {
        let id = launch.id.clone();
        let stop = Arc::new(worker::Stop::default());
        let (sender, result) = mpsc::sync_channel(1);
        let worker_stop = stop.clone();
        std::thread::spawn(move || {
            let _ = sender.send(worker::run(launch, worker_stop));
        });
        self.active = Some(Active { id, stop, result });
    }
    fn drain(&mut self) -> CoreResult<()> {
        let Some(active) = &self.active else {
            return Ok(());
        };
        let outcome = match active.result.try_recv() {
            Ok(outcome) => outcome,
            Err(mpsc::TryRecvError::Empty) => return Ok(()),
            Err(mpsc::TryRecvError::Disconnected) => Err("worker_crashed".into()),
        };
        let id = active.id.clone();
        let tx = self.store.transaction()?;
        conversation::complete(&tx, &id, outcome)?;
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
            let value = serde_json::from_slice::<Value>(line)?;
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
    request_id: &str,
    busy: bool,
    pending: &mut Option<conversation::Launch>,
) -> CoreResult<Value> {
    match command {
        Command::Health => Ok(
            json!({"identity":"A.R.T.E.M.I.S.","protocol_version":1,"storage_schema":2,"journal_mode":"wal","synchronous":"full"}),
        ),
        Command::EventsRead { after, limit } => store::events_read(tx, *after, *limit),
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
        Command::MissionPropose {
            mission_id,
            contract,
        } => missions::propose(tx, mission_id, contract),
        Command::MissionApprove {
            mission_id,
            contract_digest,
        } => missions::approve(tx, mission_id, contract_digest),
        Command::MissionCancel { mission_id, reason } => {
            missions::stop(tx, mission_id, "cancelled", reason)
        }
        Command::MissionRevoke { mission_id, reason } => {
            missions::stop(tx, mission_id, "revoked", reason)
        }
        Command::MissionGet { mission_id } => missions::get(tx, mission_id),
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
            let (result, launch) = conversation::start(tx, request_id, None, model_id, prompt)?;
            *pending = Some(launch);
            Ok(result)
        }
        Command::ConversationStart {
            chat_id,
            model_id,
            content,
        } => {
            if busy {
                return Err(CoreError::new(
                    "worker_busy",
                    "One inference job is already running",
                ));
            }
            let (result, launch) =
                conversation::start(tx, request_id, Some(chat_id), model_id, content)?;
            *pending = Some(launch);
            Ok(result)
        }
        Command::JobGet { job_id } => conversation::get(tx, job_id),
        Command::JobCancel { job_id } => conversation::cancel(tx, job_id),
        Command::MissionExecute { .. } => Err(CoreError::new(
            "capability_unavailable",
            "Mission tool execution is not integrated",
        )),
    }
}
