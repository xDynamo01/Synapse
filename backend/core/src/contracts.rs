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
    ProjectRegister {
        scope: String,
        root: String,
    },
    ProjectGet {
        scope: String,
    },
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
    MissionPlanStart {
        mission_id: String,
        scope: String,
        model_id: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        model_memory_budget_bytes: Option<u64>,
        objective: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        skill: Option<SkillPin>,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        context: Vec<ContextReference>,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        git_edit_paths: Vec<String>,
        review_model_id: String,
        review_generation: Generation,
    },
    MissionPlanGet {
        mission_id: String,
    },
    MissionPropose {
        mission_id: String,
        contract: MissionContract,
    },
    MissionApprove {
        mission_id: String,
        contract_digest: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        swarm: Option<SwarmConsent>,
    },
    MissionCancel {
        mission_id: String,
        reason: String,
    },
    MissionRevoke {
        mission_id: String,
        reason: String,
    },
    BrowserOriginRequest {
        mission_id: String,
        destination: String,
    },
    BrowserReadBegin {
        mission_id: String,
        destination: String,
    },
    BrowserDownloadBegin {
        mission_id: String,
        destination: String,
    },
    BrowserSessionReadBegin {
        mission_id: String,
        destination: String,
        session_handle: String,
    },
    BrowserDispatchAuthorize {
        mission_id: String,
        attempt: u64,
        destination: String,
        method: BrowserNetworkMethod,
    },
    BrowserLoginBegin {
        mission_id: String,
        page: String,
        action: String,
        probe: String,
        expected_text: String,
        credential_handle: String,
    },
    BrowserReadFinish {
        mission_id: String,
        attempt: u64,
        outcome: BrowserReadOutcome,
    },
    BrowserOriginDecide {
        mission_id: String,
        challenge: u64,
        allow: bool,
    },
    MissionGet {
        mission_id: String,
    },
    ProjectCheckStart {
        mission_id: String,
        check_index: u32,
        artifacts: Vec<CandidateArtifact>,
    },
    ProjectCheckGet {
        check_id: String,
    },
    ProjectCheckCancel {
        check_id: String,
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
    ModelRoute {
        capability: String,
        memory_budget_bytes: u64,
    },
    ModelGet {
        model_id: String,
    },
    SkillRegister {
        skill: SkillManifest,
    },
    SkillInspect {
        package: SkillPackage,
    },
    SkillInstall {
        package: SkillPackage,
        inspected_digest: String,
    },
    SkillRevise {
        parent: SkillPin,
        version: String,
        instructions: String,
        rationale: String,
    },
    SkillBenchmarkCase {
        proposal_cursor: u64,
        model_id: String,
        prompt: String,
        expected: String,
        candidate: bool,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        evaluation_scope: Option<String>,
    },
    SkillMissionEvidence {
        mission_id: String,
    },
    SkillGlobalPromote {
        proposal_cursor: u64,
        reviewed_instructions_digest: String,
    },
    SkillBenchmarkReceipt {
        proposal_cursor: u64,
    },
    SkillBenchmarkReview {
        proposal_cursor: u64,
        cases: Vec<SkillBenchmarkPair>,
    },
    SkillReview {
        proposal_cursor: u64,
        review: SkillReviewEvidence,
    },
    SkillActive {
        scope: String,
        skill_id: String,
    },
    SkillRollback {
        current: SkillPin,
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
    ConversationStart {
        chat_id: String,
        model_id: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        model_memory_budget_bytes: Option<u64>,
        content: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        skill: Option<SkillPin>,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        context: Vec<ContextReference>,
    },
    VoiceTranslatorStart {
        session_id: String,
        source_language: VoiceLanguage,
        target_language: VoiceLanguage,
    },
    VoiceTranslatorGet {
        session_id: String,
    },
    VoiceTranslatorStop {
        session_id: String,
    },
    VoiceTurnStart {
        session_id: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        chat_id: Option<String>,
        model_id: String,
        text: String,
        language: VoiceLanguage,
        #[serde(default, skip_serializing_if = "is_false")]
        overlap: bool,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        skill: Option<SkillPin>,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        context: Vec<ContextReference>,
    },
    VoiceTranslationGet {
        job_id: String,
    },
    JobGet {
        job_id: String,
    },
    LearningGet {
        source_job_id: String,
    },
    JobCancel {
        job_id: String,
    },
    MissionExecute {
        mission_id: String,
    },
    MissionRunGet {
        mission_id: String,
    },
    MissionRecoveryInspect {
        mission_id: String,
    },
    MissionRecoveryResolve {
        mission_id: String,
        mode: MissionRecoveryMode,
    },
    ToolExecute {
        mission_id: String,
        operation: ToolOperation,
    },
    ToolRecovery {
        intent_id: String,
        mode: RecoveryMode,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        expected_current_hash: Option<String>,
    },
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MissionRecoveryMode {
    Finalize,
    Rollback,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecoveryMode {
    Inspect,
    Finalize,
    Restore,
    SafeAbandon,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ToolOperation {
    List { path: String },
    Read { path: String },
    Create { path: String, content: String },
    Replace { path: String, content: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SkillPin {
    pub scope: String,
    pub id: String,
    pub version: String,
    pub digest: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ContextReference {
    pub scope: String,
    pub key: String,
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
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SwarmConsent {
    Direct,
    Recommended,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BrowserNetworkMethod {
    Get,
    Post,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BrowserReadOutcome {
    Collected,
    Redirected,
    Uncertain,
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
    #[serde(default, skip_serializing_if = "std::collections::BTreeMap::is_empty")]
    pub artifact_digests: std::collections::BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "std::collections::BTreeMap::is_empty")]
    pub artifact_previous_digests: std::collections::BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub skill: Option<SkillPin>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution: Option<MissionExecutionSpec>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelManifest {
    pub id: String,
    pub provider: String,
    pub endpoint: String,
    pub capabilities: Vec<String>,
    pub memory_bytes: u64,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "generation_if_present"
    )]
    pub generation: Option<Generation>,
}
fn generation_if_present<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<Option<Generation>, D::Error> {
    Generation::deserialize(deserializer).map(Some)
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Generation {
    pub max_output_tokens: u32,
    pub timeout_ms: u64,
    pub reasoning_effort: ReasoningEffort,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReasoningEffort {
    ProviderDefault,
    None,
    Low,
    Medium,
    High,
}
impl Default for Generation {
    fn default() -> Self {
        Self {
            max_output_tokens: 1024,
            timeout_ms: 10000,
            reasoning_effort: ReasoningEffort::ProviderDefault,
        }
    }
}
impl Generation {
    pub fn validate(&self) -> CoreResult<()> {
        if !(1..=4096).contains(&self.max_output_tokens)
            || !(250..=120000).contains(&self.timeout_ms)
        {
            return Err(CoreError::invalid("Invalid generation limits"));
        }
        Ok(())
    }
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
#[serde(deny_unknown_fields)]
pub struct SkillBenchmarkPair {
    pub baseline_job: String,
    pub candidate_job: String,
    pub expected: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SkillReviewEvidence {
    pub reviewer: String,
    pub benchmark: String,
    pub baseline: u32,
    pub candidate: u32,
    pub regressions: u32,
    pub approved: bool,
}

/// A declarative package submitted for review before registration.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SkillPackage {
    pub manifest: SkillManifest,
    pub license: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_url: Option<String>,
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

fn is_false(value: &bool) -> bool {
    !value
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum VoiceLanguage {
    #[serde(rename = "pt-BR")]
    PtBr,
    #[serde(rename = "en-US")]
    EnUs,
}

impl VoiceLanguage {
    pub(crate) fn tag(self) -> &'static str {
        match self {
            Self::PtBr => "pt-BR",
            Self::EnUs => "en-US",
        }
    }

    pub(crate) fn name(self) -> &'static str {
        match self {
            Self::PtBr => "Brazilian Portuguese",
            Self::EnUs => "US English",
        }
    }
}

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

/// Data-only planner output. No content, command, grant or approval fields.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MissionPlan {
    pub summary: String,
    pub artifacts: Vec<PlannedArtifact>,
    pub checks: Vec<PlannedCheck>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlannedArtifact {
    pub path: String,
    pub purpose: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlannedCheck {
    pub kind: CheckKind,
    pub entrypoint: String,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CheckKind {
    PythonUnittest,
    RustTest,
    PythonCompile,
    JsonValidate,
    GameLevelValidate,
    TomlValidate,
    PythonManifestValidate,
    CsvValidate,
    SvgValidate,
    MarkdownValidate,
    WebvttValidate,
}

impl CheckKind {
    pub(crate) fn extension(self) -> &'static str {
        match self {
            Self::PythonUnittest | Self::PythonCompile => "py",
            Self::RustTest => "rs",
            Self::JsonValidate | Self::GameLevelValidate => "json",
            Self::TomlValidate | Self::PythonManifestValidate => "toml",
            Self::CsvValidate => "csv",
            Self::SvgValidate => "svg",
            Self::MarkdownValidate => "md",
            Self::WebvttValidate => "vtt",
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MissionExecutionSpec {
    pub plan_id: String,
    pub primary_model: ModelManifest,
    pub primary_model_digest: String,
    pub review_model: ModelManifest,
    pub review_model_digest: String,
    pub review_generation: Generation,
    pub artifacts: Vec<PlannedArtifact>,
    pub checks: Vec<PlannedCheck>,
    pub limits: MissionExecutionLimits,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateArtifact {
    pub path: String,
    pub content: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MissionExecutionLimits {
    pub per_file_bytes: u32,
    pub total_bytes: u32,
    pub check_timeout_ms: u64,
    pub preparation_timeout_ms: u64,
    pub max_tool_asset_bytes: u64,
    pub job_memory_bytes: u64,
    pub owned_processes: u32,
    pub check_output_bytes: u32,
    pub generation_attempts: u32,
}
impl Default for MissionExecutionLimits {
    fn default() -> Self {
        Self {
            per_file_bytes: 8192,
            total_bytes: 24576,
            check_timeout_ms: 30000,
            preparation_timeout_ms: 120000,
            max_tool_asset_bytes: 2147483648,
            job_memory_bytes: 512 * 1024 * 1024,
            owned_processes: 8,
            check_output_bytes: 32768,
            generation_attempts: 1,
        }
    }
}
