use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_REQUEST_BYTES: usize = 65_536;
pub const MAX_RESULT_BYTES: usize = 240_000;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub version: u32,
    pub request_id: String,
    pub command: Command,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    Health,
    EventsRead {
        after: u64,
        limit: u32,
    },
    ChatCreate {
        chat_id: String,
        title: String,
        scope: String,
    },
    ChatGet {
        chat_id: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        after: Option<u64>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        limit: Option<u32>,
    },
    MessageAppend {
        chat_id: String,
        message_id: String,
        role: MessageRole,
        content: String,
    },
    MemoryPut {
        scope: String,
        key: String,
        kind: MemoryKind,
        content: String,
        expected_revision: u64,
        provenance: Provenance,
        status: MemoryStatus,
    },
    MemoryGet {
        scope: String,
        context_reference: String,
        key: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        after_revision: Option<u64>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        limit: Option<u32>,
    },
    MissionPropose {
        mission_id: String,
        contract: MissionContract,
    },
    MissionApprove {
        mission_id: String,
        contract_digest: String,
    },
    MissionCancel {
        mission_id: String,
        reason: String,
    },
    MissionRevoke {
        mission_id: String,
        reason: String,
    },
    MissionGet {
        mission_id: String,
    },
    ModelRegister {
        model: ModelManifest,
    },
    ModelsList {
        #[serde(default, skip_serializing_if = "Option::is_none")]
        after: Option<u64>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        limit: Option<u32>,
    },
    ModelGet {
        model_id: String,
    },
    SkillRegister {
        skill: SkillManifest,
    },
    SkillsList {
        scope: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        after: Option<u64>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        limit: Option<u32>,
    },
    SkillGet {
        scope: String,
        skill_id: String,
        version: String,
    },
    CapabilitiesList,
    Inference {
        model_id: String,
        prompt: String,
    },
    MissionExecute {
        mission_id: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MessageRole {
    User,
    Assistant,
    System,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryKind {
    Constraint,
    Decision,
    Fact,
    ReproducedIssue,
    RootCause,
    Recovery,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryStatus {
    Active,
    Resolved,
    Superseded,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub source_type: String,
    pub source_id: String,
    pub evidence: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MissionContract {
    pub version: u32,
    pub scope: String,
    pub objective: String,
    pub actions: Vec<String>,
    pub resources: Vec<String>,
    pub rollback: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelManifest {
    pub id: String,
    pub provider: String,
    pub endpoint: String,
    pub capabilities: Vec<String>,
    pub memory_bytes: u64,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SkillManifest {
    pub id: String,
    pub version: String,
    pub scope: String,
    pub provenance: String,
    pub tools: Vec<String>,
    pub permissions: Vec<String>,
    pub instructions: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Response {
    pub version: u32,
    pub request_id: Option<String>,
    pub ok: bool,
    pub event_cursor: u64,
    pub result: Option<Value>,
    pub error: Option<CoreError>,
}
impl Response {
    pub fn failure(request_id: Option<String>, cursor: u64, error: CoreError) -> Self {
        Self {
            version: PROTOCOL_VERSION,
            request_id,
            ok: false,
            event_cursor: cursor,
            result: None,
            error: Some(error),
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoreError {
    pub code: String,
    pub message: String,
}
impl CoreError {
    pub fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
    pub fn invalid(message: &str) -> Self {
        Self::new("invalid_request", message)
    }
}
impl std::fmt::Display for CoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for CoreError {}
impl From<rusqlite::Error> for CoreError {
    fn from(_: rusqlite::Error) -> Self {
        Self::new("storage_error", "Database operation failed")
    }
}
impl From<serde_json::Error> for CoreError {
    fn from(_: serde_json::Error) -> Self {
        Self::invalid("Invalid JSON contract")
    }
}
pub type CoreResult<T> = Result<T, CoreError>;

pub fn bounded(value: &str, name: &str, max: usize) -> CoreResult<()> {
    if value.trim().is_empty() || value.len() > max || value.contains('\0') {
        return Err(CoreError::invalid(&format!("Invalid {name}")));
    }
    Ok(())
}
pub fn scope(value: &str) -> CoreResult<()> {
    bounded(value, "scope", 256)?;
    if !value.starts_with("project:") || value.len() == "project:".len() {
        return Err(CoreError::invalid(
            "An exact project:<id> scope is required",
        ));
    }
    Ok(())
}
