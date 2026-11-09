use crate::{
    chats,
    contracts::*,
    memory, missions, registry,
    store::{self, Store},
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

/// Local human client entrypoint. Never expose dispatch to worker output.
pub struct Core {
    store: Store,
    workspace_root: PathBuf,
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
        })
    }
    pub fn dispatch(&mut self, request: Request) -> Response {
        let id = Some(request.request_id.clone());
        let result = self.dispatch_durable(&request);
        match result {
            Ok(response) => response,
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
        let tx = self.store.transaction()?;
        let receipt: Option<(String, i64)> = tx
            .query_row(
                "SELECT digest,LENGTH(response) FROM receipts WHERE request_id=?1",
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
        let outcome = dispatch_tx(&tx, &request.command, &self.workspace_root).and_then(|result| {
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
        Ok(response)
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

/// Focused handlers must use this transaction, never open their own writer.
fn dispatch_tx(
    tx: &Transaction<'_>,
    command: &Command,
    _workspace_root: &Path,
) -> CoreResult<Value> {
    match command {
        Command::Health => Ok(
            json!({"identity":"A.R.T.E.M.I.S.","protocol_version":1,"storage_schema":1,"journal_mode":"wal","synchronous":"full"}),
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
        Command::ModelsList => registry::models_list(tx),
        Command::SkillRegister { skill } => registry::skill_register(tx, skill),
        Command::SkillsList { scope } => registry::skills_list(tx, scope),
        Command::CapabilitiesList => Ok(registry::capabilities()),
        Command::Inference { .. } => Err(CoreError::new(
            "capability_unavailable",
            "Inference worker is not installed/integrated",
        )),
        Command::MissionExecute { .. } => Err(CoreError::new(
            "capability_unavailable",
            "Mission tool execution is not integrated",
        )),
    }
}
