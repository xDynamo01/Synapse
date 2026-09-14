export type BackendConnectionState = "connecting" | "ready" | "degraded" | "disconnected" | "error";
export type ConversationRuntimeState =
  | "idle"
  | "restoring"
  | "sending"
  | "streaming"
  | "completed"
  | "cancelled"
  | "failed"
  | "disconnected";

export type VoiceCaptureState = "idle" | "recording" | "transcribing" | "failed";
export type ConversationModeState =
  | "inactive"
  | "idle"
  | "listening"
  | "capturing"
  | "finalizing"
  | "transcribing"
  | "generating"
  | "synthesizing"
  | "processing"
  | "speaking"
  | "cooldown"
  | "interrupted"
  | "failed";

export type AttachmentStageState = "selecting" | "staging" | "ready" | "failed";

export type FrontendConversationErrorCode =
  | "network_disconnected"
  | "generation_failed"
  | "scope_mismatch"
  | "invalid_conversation"
  | "backend_unavailable"
  | "history_restore_failure"
  | "cancel_failed"
  | "stream_interrupted"
  | "unknown";

export interface FrontendConversationError {
  code: FrontendConversationErrorCode;
  message: string;
  retryable: boolean;
}

export interface CommandDiscoveryItem {
  tool_id: string;
  display_name: string;
  description: string;
  category: string;
  available: boolean;
  requires_approval: boolean;
  risk_level: string;
  reason_unavailable?: string | null;
  execution_kind?: "ui" | "project_scope" | "operational" | "unsupported";
  argument_schema?: "none" | "project_id";
  opens_surface?: "activity" | "insight" | "settings" | "project_files" | null;
  requires_backend_authority?: boolean;
}

export interface CommandDiscoveryCatalog {
  agent_id: string;
  total_tools: number;
  available_tools: number;
  unavailable_tools: number;
  approval_required_tools: number;
  generated_at: string;
  tools: CommandDiscoveryItem[];
}

export interface ProjectManifestSummary {
  project_id: string;
  name: string;
  description: string;
  root_reference: string;
  owner: string;
  default_policy_id: string;
  primary_agent_id?: string | null;
  status?: string;
  metadata: Record<string, unknown>;
}

export interface ProjectListResult {
  projects: ProjectManifestSummary[];
  total: number;
}

export type ProjectKnowledgeIngestionStatus =
  | "queued"
  | "reading"
  | "chunking"
  | "indexing"
  | "ready"
  | "failed"
  | "stale"
  | "removed";

export type ProjectKnowledgeSemanticStatus =
  | "unconfigured"
  | "available"
  | "loading"
  | "ready"
  | "unavailable"
  | "incompatible"
  | "failed"
  | "degraded";

export interface ProjectKnowledgeDocument {
  document_id: string;
  project_id: string;
  workspace_id: string;
  display_name: string;
  created_at: string;
  current_version_id?: string | null;
  status: ProjectKnowledgeIngestionStatus;
}

export interface ProjectKnowledgeDocumentVersion {
  version_id: string;
  document_id: string;
  project_id: string;
  workspace_id: string;
  attachment_id: string;
  conversation_id?: string | null;
  session_id?: string | null;
  source_checksum: string;
  parser_version: string;
  chunker_version: string;
  indexer_version: string;
  status: ProjectKnowledgeIngestionStatus;
  queued_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  chunk_count: number;
  failure_code?: string | null;
  failure_message?: string | null;
  superseded_by?: string | null;
}

export interface ProjectKnowledgeEmbeddingCapability {
  status: ProjectKnowledgeSemanticStatus;
  provider_id: string;
  model_id: string;
  model_version: string;
  dimension: number;
  semantic_index_version: string;
  normalization_version?: string;
  learned_semantic?: boolean;
  configured?: boolean;
  loaded?: boolean;
  device?: string;
  reason?: string | null;
}

export interface ProjectKnowledgeDocumentRecord {
  document: ProjectKnowledgeDocument;
  version: ProjectKnowledgeDocumentVersion | null;
  facts: Record<string, unknown>;
}

export interface ProjectKnowledgeDocumentsResult {
  schema: "project-knowledge-documents-v1";
  workspace_id: string;
  project_id: string;
  documents: ProjectKnowledgeDocumentRecord[];
  capabilities: {
    lexical: { available: boolean; status: string };
    canonical: ProjectKnowledgeEmbeddingCapability;
    learned_semantic: ProjectKnowledgeEmbeddingCapability;
    hybrid: { available: boolean; fallback_available: boolean };
  };
  retrieval_policy: {
    explicit_retrieval_required: boolean;
    listing_queries_knowledge: boolean;
    listing_generates_query_embedding: boolean;
  };
}

export interface ProjectKnowledgeDocumentMutationResult {
  schema:
    | "project-knowledge-document-remove-result-v1"
    | "project-knowledge-document-reindex-result-v1";
  workspace_id: string;
  document?: ProjectKnowledgeDocument;
  version?: ProjectKnowledgeDocumentVersion;
}

export interface ProviderModelOption {
  provider_id: string;
  provider_status: string;
  provider_active: boolean;
  model_id: string;
  model_status: string;
  runtime: string;
  origin: string;
  availability_state: string;
  is_default: boolean;
}

export interface LMStudioTelemetryEntry {
  occurred_at?: string;
  provider_id?: string;
  model_name?: string;
  conversation_id?: string;
  phase?: string;
  status?: string;
  current_operation?: string;
  current_task?: string;
  input_count?: number;
  output_count?: number;
  total_count?: number;
  latency_ms?: number;
  first_output_ms?: number;
  output_rate?: number;
  raw_line?: string;
}

export interface LMStudioStatus {
  config: Record<string, unknown>;
  health: Record<string, unknown>;
  telemetry?: {
    recent?: LMStudioTelemetryEntry[];
  };
}

export interface FrontendIssue {
  code: string;
  message: string;
  detail?: string;
}

export interface FrontendBootstrap {
  schema: "frontend-v2-bootstrap-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  onboarding_required: boolean;
  primary_agent_state: string;
  usable_primary_agent: boolean;
  primary_agent: PrimaryAgentSummary | null;
  conversation: ConversationRecord | null;
  resume_token: string | null;
  provider_model_options: ProviderModelOption[];
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface PrimaryAgentSummary {
  agent_id: string;
  name: string;
  role: string;
  kind: string;
}

export interface FirstAgentRequest {
  agent_id: string;
  display_name: string;
  role: string;
  workspace_id: string;
  default_provider?: string | null;
  default_model?: string | null;
  system_prompt?: string | null;
}

export interface FirstAgentResult {
  schema: "frontend-v2-first-agent-result-v1";
  status: "ready";
  workspace_id: string;
  agent: Record<string, unknown>;
  primary_profile: {
    agent_id: string;
    workspace_id: string;
    conversation_id: string;
    status: string;
  };
  bootstrap: unknown;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface ConversationRecord {
  conversation_id: string;
  participants: string[];
  title?: string | null;
  status: string;
  revision: number;
  metadata: Record<string, unknown>;
}

export interface ConversationPagination {
  offset: number;
  limit: number;
  returned: number;
  has_more: boolean;
  next_offset: number | null;
  has_older: boolean;
  previous_offset: number | null;
  known_total?: number;
}

export interface ConversationSummary {
  conversation_id: string;
  summary: string;
  message_count: number;
  last_message_id: string | null;
  updated_at: string;
  status: string;
  source_message_ids: string[];
  model: string | null;
  provider: string | null;
  conversation_revision: number;
  error: Record<string, unknown> | null;
}

export interface ConversationMessage {
  message_id: string;
  conversation_id: string;
  sender_agent_id: string;
  receiver_agent_id: string;
  role: string;
  status: string;
  payload: {
    body?: string;
    role?: string;
    [key: string]: unknown;
  };
  attachments?: ConversationAttachment[];
  created_at?: string;
  updated_at?: string;
}

export interface ConversationAttachment {
  attachment_id: string;
  filename: string;
  mime_type: string;
  size: number;
  storage_ref: string;
  checksum: string;
  conversation_id: string;
  owner_id: string;
}

export interface AttachmentStageResult {
  schema: "frontend-v2-attachment-stage-result-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversation_id: string;
  attachment: ConversationAttachment;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface AttachmentStageRequest {
  filename: string;
  mime_type: string;
  size: number;
  content_base64: string;
  workspace_id: string;
  project_id?: string | null;
  session_id?: string | null;
}

export interface ConversationState {
  schema: "frontend-v2-conversation-state-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  primary_agent_id: string;
  conversation: ConversationRecord;
  messages: ConversationMessage[];
  pagination: ConversationPagination;
  summary: ConversationSummary;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface ConversationHistory {
  schema: "frontend-v2-conversation-history-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversation: ConversationRecord;
  messages: ConversationMessage[];
  pagination: ConversationPagination;
  summary: ConversationSummary;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface ConversationIndexItem {
  conversation: ConversationRecord;
  message_count: number;
  last_message: ConversationMessage | null;
  preview: string;
}

export interface ConversationIndex {
  schema: "frontend-v2-conversation-index-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversations: ConversationIndexItem[];
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface ConversationDeleteResult {
  schema: "frontend-v2-conversation-delete-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversation_id: string;
  deleted: boolean;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface ConversationClearHistoryResult {
  schema: "frontend-v2-conversation-clear-history-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  deleted: number;
  conversation_ids: string[];
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface TextTurnRequest {
  content: string;
  workspace_id: string;
  project_id?: string | null;
  session_id?: string | null;
  target_agent_id?: string | null;
  model_provider_id?: string | null;
  model_name?: string | null;
  attachments?: ConversationAttachment[];
  idempotency_key?: string | null;
}

export interface TextTurnResult {
  schema: "frontend-v2-text-turn-result-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversation_id: string;
  agent_id: string;
  result: Record<string, unknown>;
  history: ConversationMessage[];
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export type StreamEventType =
  | "turn_started"
  | "generation_started"
  | "chunk_received"
  | "generation_completed"
  | "generation_cancelled"
  | "generation_failed";

export interface TextStreamEvent {
  schema: "frontend-v2-text-stream-event-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  type: StreamEventType;
  conversation_id: string | null;
  content?: string;
  streaming_mode?: string;
  error?: {
    code: string;
    message: string;
  };
  idempotency_key?: string | null;
}

export interface CancelTurnResult {
  schema: "frontend-v2-turn-cancel-result-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversation_id: string;
  idempotency_key: string;
  status: "cancel_requested";
  cancelled_message: ConversationMessage | null;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface VoiceTranscriptionRequest {
  audio_base64: string;
  audio_format: string;
  workspace_id: string;
  project_id?: string | null;
  session_id?: string | null;
  conversation_id?: string | null;
  language?: string | null;
  duration_ms?: number | null;
}

export interface VoiceTranscriptionResult {
  schema: "frontend-v2-voice-transcription-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  conversation_id: string | null;
  recording_id: string;
  transcript: string;
  provider_id: string | null;
  language: string | null;
  duration_ms: number | null;
  status: string;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export interface VoiceConversationTurnRequest {
  audio_base64: string;
  audio_format: string;
  workspace_id: string;
  project_id?: string | null;
  session_id?: string | null;
  conversation_id: string;
  language?: string | null;
  voice_session_id?: string | null;
  idempotency_key?: string | null;
}

export interface VoiceConversationTurnResult {
  schema: "frontend-v2-voice-conversation-turn-v1";
  workspace_id: string;
  project_id: string | null;
  session_id: string | null;
  voice_session_id: string;
  conversation_id: string;
  recording_id: string;
  status: string;
  transcript: string;
  response: string;
  user_message_id: string | null;
  assistant_message_id: string | null;
  synthesis_id: string;
  tts: {
    status: string;
    provider_id: string | null;
    voice_id: string | null;
    audio_base64: string | null;
    audio_format: string | null;
    duration_ms: number | null;
  };
  messages: ConversationMessage[];
  pagination: ConversationPagination;
  summary: ConversationSummary;
  degraded: FrontendIssue[];
  errors: FrontendIssue[];
}

export type OperationalEntityKind =
  | "project"
  | "agent"
  | "worker"
  | "swarm"
  | "mission"
  | "task"
  | "tool-execution"
  | "memory-source"
  | "context-source"
  | "communication"
  | "approval"
  | "evaluation"
  | "runtime"
  | "voice-session";

export type OperationalStatus =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "approval-needed"
  | "unavailable"
  | "unknown";

export type OperationalRelationKind =
  | "parent"
  | "delegation"
  | "communication"
  | "tool-use"
  | "context-use"
  | "evaluation";

export type OperationalFactKind =
  | "upsert-entity"
  | "remove-entity"
  | "upsert-relation"
  | "remove-relation"
  | "mark-degraded"
  | "clear-degraded";

export interface OperationalResourceSummary {
  files: number;
  memories: number;
  toolResults: number;
}

export interface OperationalEntity {
  entityId: string;
  kind: OperationalEntityKind;
  role: string;
  status: OperationalStatus;
  label: string;
  currentTask?: string | null;
  currentOperation?: string | null;
  startedAt?: string | null;
  parentEntityId?: string | null;
  missionId?: string | null;
  resources: OperationalResourceSummary;
  metadata: Record<string, string | number | boolean | null>;
}

export interface OperationalRelation {
  relationId: string;
  sourceEntityId: string;
  targetEntityId: string;
  kind: OperationalRelationKind;
  active: boolean;
}

export interface ProjectActivitySnapshot {
  format: "project-activity-snapshot-v1";
  projectId: string;
  revision: number;
  observedAt: string;
  entities: OperationalEntity[];
  relations: OperationalRelation[];
  degraded: boolean;
  degradationReasons: string[];
  lastEventId: string | null;
}

export interface OperationalFact {
  formatVersion: "project-activity-event-v1";
  eventId: string;
  projectId: string;
  revision: number;
  occurredAt: string;
  kind: OperationalFactKind;
  sourceReference: string;
  entity?: OperationalEntity | null;
  entityId?: string | null;
  relation?: OperationalRelation | null;
  relationId?: string | null;
  degradationReason?: string | null;
  correlationReference?: string | null;
  metadata: Record<string, string | number | boolean | null>;
}

export interface ActivityEventsResult {
  snapshot: ProjectActivitySnapshot;
  events: OperationalFact[];
  cursor: string | null;
  resynchronized: boolean;
}

export interface InsightEvidence {
  source: string;
  metric: string;
  value: string | number | boolean | null;
  unit?: string | null;
  observed_at?: string | null;
}

export interface InsightCPUInfo {
  model: string;
  architecture: string;
  physical_cores: number | null;
  logical_threads: number;
  usage_percent: number | null;
  frequency_mhz?: number | null;
  temperature_celsius?: number | null;
}

export interface InsightMemoryInfo {
  total_bytes: number;
  available_bytes: number;
  used_bytes: number;
  usage_percent: number;
  swap_total_bytes: number;
  swap_used_bytes: number;
  swap_percent: number;
}

export interface InsightGPUInfo {
  name: string;
  vendor: string;
  provider: string;
  driver?: string | null;
  memory_total_bytes?: number | null;
  memory_used_bytes?: number | null;
  memory_free_bytes?: number | null;
  usage_percent?: number | null;
  temperature_celsius?: number | null;
  capabilities: string[];
  limitations: string[];
}

export interface InsightHardwareSnapshot {
  provider: string;
  collected_at: string;
  cpu: InsightCPUInfo;
  memory: InsightMemoryInfo;
  gpus: InsightGPUInfo[];
  limitations: string[];
}

export interface InsightModelRecommendation {
  task: string;
  model_id: string | null;
  provider_id: string | null;
  status: string;
  reason: string;
  source?: string | null;
  estimated_ram_gb?: number | null;
  estimated_vram_gb?: number | null;
  evidence: InsightEvidence[];
}

export interface InsightModelCapabilityReport {
  checked_at: string;
  available_models: number;
  online_providers: number;
  providers: Record<string, unknown>[];
  recommendations: InsightModelRecommendation[];
  limitations: string[];
}

export interface InsightDiagnosticFinding {
  code: string;
  severity: string;
  summary: string;
  evidence: InsightEvidence[];
  recommendation?: string | null;
}

export interface InsightDiagnosticsReport {
  generated_at: string;
  status: string;
  findings: InsightDiagnosticFinding[];
  limitations: string[];
}

export interface InsightReport {
  generated_at: string;
  hardware: InsightHardwareSnapshot;
  models: InsightModelCapabilityReport;
  diagnostics: InsightDiagnosticsReport;
  providers: Record<string, unknown>[];
  integrations: Record<string, boolean>;
  limitations: string[];
}

export interface ModelHubDefaults {
  default_chat_model: string | null;
  default_provider: string | null;
  preferred_runtime: string | null;
  updated_at?: string | null;
}

export interface ModelCatalogEntry {
  id: string;
  name: string;
  provider: string;
  runtime: string;
  origin: string;
  type: string;
  availability_state: string;
  chat_usable: boolean;
  status: string;
  is_default?: boolean;
  estimated_ram_gb?: number | null;
  estimated_vram_gb?: number | null;
}

export interface ModelProviderInfo {
  provider_id: string;
  display_name: string;
  status: string;
  endpoint: string | null;
  active: boolean;
  default_model: string | null;
  model_count: number;
  last_refreshed_at: string | null;
}

export interface ProviderSetting {
  provider_id: string;
  display_name: string;
  provider_kind: string;
  enabled: boolean;
  endpoint: string;
  default_model: string | null;
  has_api_key: boolean;
  masked_key: string | null;
  status: string;
  updated_at: string | null;
  last_tested_at: string | null;
  test_message: string | null;
  metadata: Record<string, unknown>;
}

export interface VoiceSettings {
  schema_version: number;
  provider_id: string | null;
  stt_provider_id: string | null;
  stt_model: string | null;
  stt_device: string;
  stt_compute_type: string;
  language: string;
  tts_provider_id: string | null;
  tts_model: string | null;
  default_tts_voice: string | null;
  preferred_voice_gender: string | null;
  tts_speed: number | null;
  vad_enabled: boolean;
  store_raw_audio: boolean;
  conversation_mode_defaults: Record<string, unknown>;
  enabled: boolean;
}

export interface VoiceProviderSummary {
  provider_id: string;
  adapter_id: string;
  adapter_type: string;
  status: string;
  enabled: boolean;
  health: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface VoicePackEntry {
  voice_id: string;
  display_name: string;
  language: string;
  locale: string;
  voice_profile: Record<string, unknown>;
  provider: string;
  engine: string;
  asset_reference: string;
  version: string;
  checksum: string;
  license: string;
  provenance: string;
  usable: boolean;
  status: string;
  reason: string | null;
  metadata: Record<string, unknown>;
}

export interface VoicePackManifest {
  pack_id: string;
  display_name: string;
  version: string;
  provider: string;
  engine: string;
  voices: VoicePackEntry[];
  status: string;
  reason: string | null;
  metadata: Record<string, unknown>;
}

export type MoMOperation = "conversation" | "coding" | "reasoning" | "review" | "summary";

export interface MoMRoute {
  operation: MoMOperation;
  provider: string;
  model: string;
}

export interface MoMConfiguration {
  workspace_id: string;
  primary_agent_id: string;
  enabled: boolean;
  revision: number;
  routes: MoMRoute[];
}

export interface MoMConfigurationUpdate {
  workspace_id: string;
  enabled: boolean;
  expected_revision: number;
  routes: MoMRoute[];
}

export interface SettingsSnapshot {
  personalization?: { agent_id: string; display_name: string; system_prompt: string } | null;
  models: {
    defaults: ModelHubDefaults;
    catalog: ModelCatalogEntry[];
    providers: ModelProviderInfo[];
    provider_settings: ProviderSetting[];
  };
  voice: {
    settings: VoiceSettings;
    providers: VoiceProviderSummary[];
    packs: VoicePackManifest[];
    voices: VoicePackEntry[];
  };
}

export interface UpdateModelDefaultsRequest {
  default_chat_model?: string | null;
  default_provider?: string | null;
  preferred_runtime?: string | null;
}

export interface UpdateProviderSettingRequest {
  enabled?: boolean | null;
  endpoint?: string | null;
  default_model?: string | null;
  api_key?: string | null;
}

export interface UpdateVoiceSettingsRequest {
  enabled?: boolean | null;
  stt_provider_id?: string | null;
  stt_model?: string | null;
  language?: string | null;
  tts_provider_id?: string | null;
  default_tts_voice?: string | null;
  preferred_voice_gender?: string | null;
  vad_enabled?: boolean | null;
  store_raw_audio?: boolean | null;
}

export type NotificationSeverity = "info" | "success" | "warning" | "critical";
export type NotificationCategory =
  | "approval"
  | "communication"
  | "agent"
  | "scheduler"
  | "daemon"
  | "system"
  | "task"
  | "security"
  | "unknown";

export interface NotificationRecord {
  id: string;
  title: string;
  message: string;
  severity: NotificationSeverity;
  source: string;
  category: NotificationCategory;
  schema_version: number;
  record_type: "notification";
  read: boolean;
  read_at: string | null;
  correlation_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WindowControlsApi {
  minimize(): Promise<void>;
  toggleMaximize(): Promise<boolean>;
  isMaximized(): Promise<boolean>;
  onMaximizedChange(callback: (maximized: boolean) => void): () => void;
  close(): Promise<void>;
}

export interface NativeFilePickerResult {
  status: "selected" | "cancelled" | "failed";
  filename?: string;
  mime_type?: string;
  size?: number;
  content_base64?: string;
  error?: string;
}

export interface SynapseNativeApi {
  backendBaseUrl(): Promise<string>;
  reportBootstrap(status: "ready" | "onboarding" | "degraded" | "failed"): Promise<void>;
  pickAttachmentFile(): Promise<NativeFilePickerResult>;
  window: WindowControlsApi;
}

declare global {
  interface Window {
    synapse?: SynapseNativeApi;
  }
}
