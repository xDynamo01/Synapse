import type {
  AttachmentStageRequest,
  AttachmentStageResult,
  CommandDiscoveryCatalog,
  ActivityEventsResult,
  CancelTurnResult,
  ConversationClearHistoryResult,
  ConversationDeleteResult,
  ConversationHistory,
  ConversationIndex,
  ConversationState,
  FirstAgentRequest,
  FirstAgentResult,
  FrontendBootstrap,
  InsightReport,
  ModelCatalogEntry,
  ModelHubDefaults,
  ModelProviderInfo,
  NotificationRecord,
  OperationalFact,
  ProviderSetting,
  ProjectListResult,
  ProjectManifestSummary,
  ProjectActivitySnapshot,
  SettingsSnapshot,
  TextStreamEvent,
  TextTurnRequest,
  TextTurnResult,
  UpdateModelDefaultsRequest,
  UpdateProviderSettingRequest,
  UpdateVoiceSettingsRequest,
  VoiceConversationTurnRequest,
  VoiceConversationTurnResult,
  VoicePackEntry,
  VoicePackManifest,
  VoiceProviderSummary,
  VoiceSettings,
  VoiceTranscriptionRequest,
  VoiceTranscriptionResult
} from "./types.js";

export class SynapseClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details: unknown
  ) {
    super(message);
    this.name = "SynapseClientError";
  }
}

/** Keep optional backend collections total at the renderer boundary. Older or
 * degraded sidecars may omit empty arrays; UI code must never crash on that. */
function normalizeEnvelope<T extends object>(value: T): T {
  const record = value as Record<string, unknown>;
  for (const key of ["degraded", "errors", "messages", "conversations", "provider_model_options"]) {
    if (record[key] === undefined || record[key] === null) {
      record[key] = [];
    }
  }
  return value;
}

export class SynapseFrontendClient {
  constructor(private readonly baseUrl: string) {}

  async bootstrap(): Promise<FrontendBootstrap> {
    return normalizeEnvelope(await this.get<FrontendBootstrap>("/api/frontend/bootstrap"));
  }

  async createFirstAgent(payload: FirstAgentRequest): Promise<FirstAgentResult> {
    return this.post<FirstAgentResult>("/api/frontend/first-agent", payload);
  }

  async openConversation(payload: {
    workspace_id: string;
    project_id?: string | null;
    session_id?: string | null;
    conversation_id?: string | null;
    title?: string | null;
    history_limit?: number;
  }): Promise<ConversationState> {
    return normalizeEnvelope(await this.post<ConversationState>("/api/frontend/conversations/open", payload));
  }

  async submitTextTurn(conversationId: string, payload: TextTurnRequest): Promise<TextTurnResult> {
    return normalizeEnvelope(await this.post<TextTurnResult>(
      `/api/frontend/conversations/${encodeURIComponent(conversationId)}/turns`,
      payload
    ));
  }

  async streamTextTurn(
    conversationId: string,
    payload: TextTurnRequest,
    onEvent: (event: TextStreamEvent) => void,
    signal?: AbortSignal
  ): Promise<void> {
    const response = await fetch(
      this.url(`/api/frontend/conversations/${encodeURIComponent(conversationId)}/turns/stream`),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal
      }
    );
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    if (!response.body) {
      throw new SynapseClientError("Streaming response did not include a body.", response.status, null);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        buffer = consumeNdjson(buffer, onEvent);
      }
      buffer += decoder.decode();
      consumeNdjson(buffer, onEvent, true);
    } finally {
      reader.releaseLock();
    }
  }

  async history(
    conversationId: string,
    params: { workspace_id: string; project_id?: string | null; session_id?: string | null; offset?: number; limit?: number }
  ): Promise<ConversationHistory> {
    const search = new URLSearchParams({ workspace_id: params.workspace_id });
    if (params.project_id) {
      search.set("project_id", params.project_id);
    }
    if (params.session_id) {
      search.set("session_id", params.session_id);
    }
    if (params.offset !== undefined) {
      search.set("offset", String(params.offset));
    }
    if (params.limit !== undefined) {
      search.set("limit", String(params.limit));
    }
    return normalizeEnvelope(await this.get<ConversationHistory>(
      `/api/frontend/conversations/${encodeURIComponent(conversationId)}/history?${search}`
    ));
  }

  async conversationIndex(params: {
    workspace_id: string;
    project_id?: string | null;
    session_id?: string | null;
    limit?: number;
  }): Promise<ConversationIndex> {
    const search = new URLSearchParams({ workspace_id: params.workspace_id });
    if (params.project_id) {
      search.set("project_id", params.project_id);
    }
    if (params.session_id) {
      search.set("session_id", params.session_id);
    }
    if (params.limit !== undefined) {
      search.set("limit", String(params.limit));
    }
    return normalizeEnvelope(await this.get<ConversationIndex>(`/api/frontend/conversations?${search}`));
  }

  async deleteConversation(
    conversationId: string,
    params: { workspace_id: string; project_id?: string | null; session_id?: string | null; confirmed: boolean }
  ): Promise<ConversationDeleteResult> {
    const search = new URLSearchParams({
      workspace_id: params.workspace_id,
      confirmed: String(params.confirmed)
    });
    if (params.project_id) {
      search.set("project_id", params.project_id);
    }
    if (params.session_id) {
      search.set("session_id", params.session_id);
    }
    return normalizeEnvelope(await this.delete<ConversationDeleteResult>(
      `/api/frontend/conversations/${encodeURIComponent(conversationId)}?${search}`
    ));
  }

  async clearConversationHistory(params: {
    workspace_id: string;
    project_id?: string | null;
    session_id?: string | null;
    confirmed: boolean;
  }): Promise<ConversationClearHistoryResult> {
    const search = new URLSearchParams({
      workspace_id: params.workspace_id,
      confirmed: String(params.confirmed)
    });
    if (params.project_id) {
      search.set("project_id", params.project_id);
    }
    if (params.session_id) {
      search.set("session_id", params.session_id);
    }
    return normalizeEnvelope(await this.delete<ConversationClearHistoryResult>(`/api/frontend/conversations?${search}`));
  }

  async cancelTextTurn(
    conversationId: string,
    payload: { workspace_id: string; project_id?: string | null; session_id?: string | null; idempotency_key: string }
  ): Promise<CancelTurnResult> {
    return this.post<CancelTurnResult>(
      `/api/frontend/conversations/${encodeURIComponent(conversationId)}/turns/cancel`,
      payload
    );
  }

  async stageAttachment(conversationId: string, payload: AttachmentStageRequest): Promise<AttachmentStageResult> {
    return this.post<AttachmentStageResult>(
      `/api/frontend/conversations/${encodeURIComponent(conversationId)}/attachments/stage`,
      payload
    );
  }

  async commandCatalog(): Promise<CommandDiscoveryCatalog> {
    return this.get<CommandDiscoveryCatalog>("/api/tools/catalog");
  }

  async projects(): Promise<ProjectListResult> {
    return this.get<ProjectListResult>("/api/projects");
  }

  async project(projectId: string): Promise<ProjectManifestSummary> {
    return this.get<ProjectManifestSummary>(`/api/projects/${encodeURIComponent(projectId)}`);
  }

  async transcribeVoice(payload: VoiceTranscriptionRequest): Promise<VoiceTranscriptionResult> {
    return this.post<VoiceTranscriptionResult>("/api/frontend/voice/transcriptions", payload);
  }

  async voiceConversationTurn(payload: VoiceConversationTurnRequest): Promise<VoiceConversationTurnResult> {
    return this.post<VoiceConversationTurnResult>("/api/frontend/voice/conversation-turn", payload);
  }

  async activitySnapshot(projectId: string): Promise<ProjectActivitySnapshot> {
    const path = projectId.startsWith("conversation:") ? `/api/activity/scopes/${encodeURIComponent(projectId)}` : `/api/projects/${encodeURIComponent(projectId)}/activity`;
    return normalizeActivitySnapshot(await this.get<ProjectActivitySnapshot>(path));
  }

  async activityEvents(projectId: string, cursor?: string | null): Promise<ActivityEventsResult> {
    const search = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
    return this.get<ActivityEventsResult>(`/api/projects/${encodeURIComponent(projectId)}/activity/events${search}`);
  }

  async insightReport(): Promise<InsightReport> {
    return this.get<InsightReport>("/api/insight/report");
  }

  async settingsSnapshot(): Promise<SettingsSnapshot> {
    const [
      defaults,
      catalog,
      providers,
      providerSettings,
      voiceSettings,
      voiceProviders,
      voicePacks,
      ttsVoices
    ] = await Promise.all([
      this.modelDefaults(),
      this.modelCatalog(),
      this.modelProviders(),
      this.providerSettings(),
      this.voiceSettings(),
      this.voiceProviders(),
      this.voicePacks(),
      this.ttsVoices()
    ]);
    return {
      models: {
        defaults,
        catalog,
        providers,
        provider_settings: providerSettings
      },
      voice: {
        settings: voiceSettings,
        providers: voiceProviders,
        packs: voicePacks,
        voices: ttsVoices
      }
    };
  }

  async modelDefaults(): Promise<ModelHubDefaults> {
    return this.get<ModelHubDefaults>("/api/models/default");
  }

  async updateModelDefaults(payload: UpdateModelDefaultsRequest): Promise<ModelHubDefaults> {
    return this.post<ModelHubDefaults>("/api/models/default", payload);
  }

  async modelCatalog(): Promise<ModelCatalogEntry[]> {
    return this.get<ModelCatalogEntry[]>("/api/models/catalog");
  }

  async modelProviders(): Promise<ModelProviderInfo[]> {
    return this.get<ModelProviderInfo[]>("/api/models/providers");
  }

  async providerSettings(): Promise<ProviderSetting[]> {
    return this.get<ProviderSetting[]>("/api/provider-settings");
  }

  async updateProviderSetting(providerId: string, payload: UpdateProviderSettingRequest): Promise<ProviderSetting> {
    return this.patch<ProviderSetting>(`/api/provider-settings/${encodeURIComponent(providerId)}`, payload);
  }

  async voiceSettings(): Promise<VoiceSettings> {
    return this.get<VoiceSettings>("/api/voice/settings");
  }

  async updateVoiceSettings(payload: UpdateVoiceSettingsRequest): Promise<VoiceSettings> {
    return this.patch<VoiceSettings>("/api/voice/settings", payload);
  }

  async voiceProviders(): Promise<VoiceProviderSummary[]> {
    return this.get<VoiceProviderSummary[]>("/api/voice/providers");
  }

  async voicePacks(): Promise<VoicePackManifest[]> {
    return this.get<VoicePackManifest[]>("/api/voice/packs");
  }

  async ttsVoices(): Promise<VoicePackEntry[]> {
    return this.get<VoicePackEntry[]>("/api/voice/voices");
  }

  async notifications(): Promise<NotificationRecord[]> {
    return this.get<NotificationRecord[]>("/api/notifications");
  }

  async markNotificationRead(notificationId: string): Promise<NotificationRecord> {
    return this.post<NotificationRecord>(`/api/notifications/${encodeURIComponent(notificationId)}/read`, {});
  }

  async dismissNotification(notificationId: string): Promise<{ deleted: true; id: string }> {
    return this.delete<{ deleted: true; id: string }>(`/api/notifications/${encodeURIComponent(notificationId)}`);
  }

  activityStreamUrl(projectId: string, cursor?: string | null): string {
    const search = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
    const path = projectId.startsWith("conversation:") ? `/api/activity/scopes/${encodeURIComponent(projectId)}/stream` : `/api/projects/${encodeURIComponent(projectId)}/activity/stream`;
    return this.url(`${path}${search}`);
  }

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(this.url(path), { method: "GET" });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return (await response.json()) as T;
  }

  private async post<T>(path: string, payload: unknown): Promise<T> {
    const response = await fetch(this.url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return (await response.json()) as T;
  }

  private async patch<T>(path: string, payload: unknown): Promise<T> {
    const response = await fetch(this.url(path), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return (await response.json()) as T;
  }

  private async delete<T>(path: string): Promise<T> {
    const response = await fetch(this.url(path), { method: "DELETE" });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return (await response.json()) as T;
  }

  private url(path: string): string {
    return new URL(path, this.baseUrl).toString();
  }

  private async errorFrom(response: Response): Promise<SynapseClientError> {
    let details: unknown = null;
    try {
      details = await response.json();
    } catch {
      details = await response.text();
    }
    return new SynapseClientError(safeBackendErrorMessage(response.status, details), response.status, details);
  }
}

export interface ActivityStreamHandlers {
  onSnapshot(snapshot: ProjectActivitySnapshot, cursor: string | null): void;
  onActivity(event: OperationalFact, cursor: string | null): void;
  onResync(snapshot: ProjectActivitySnapshot, cursor: string | null): void;
  onError(error: Event): void;
}

export function openActivityStream(url: string, handlers: ActivityStreamHandlers): EventSource {
  const stream = new EventSource(url);
  stream.addEventListener("snapshot", (event) => {
    handlers.onSnapshot(normalizeActivitySnapshot(JSON.parse(event.data)), event.lastEventId || null);
  });
  stream.addEventListener("activity", (event) => {
    handlers.onActivity(JSON.parse(event.data) as OperationalFact, event.lastEventId || null);
  });
  stream.addEventListener("resync", (event) => {
    handlers.onResync(normalizeActivitySnapshot(JSON.parse(event.data)), event.lastEventId || null);
  });
  stream.addEventListener("error", (event) => handlers.onError(event));
  return stream;
}

function normalizeActivitySnapshot(value: ProjectActivitySnapshot): ProjectActivitySnapshot {
  return {
    ...value,
    entities: Array.isArray(value.entities) ? value.entities : [],
    relations: Array.isArray(value.relations) ? value.relations : [],
    degradationReasons: Array.isArray(value.degradationReasons) ? value.degradationReasons : []
  };
}

function safeBackendErrorMessage(status: number, details: unknown): string {
  if (typeof details === "object" && details !== null && "detail" in details) {
    const detail = (details as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return `Synapse backend returned ${status}.`;
}

export function consumeNdjson(
  input: string,
  onEvent: (event: TextStreamEvent) => void,
  flush = false
): string {
  const lines = input.split(/\r?\n/);
  const remainder = flush ? "" : (lines.pop() ?? "");
  for (const line of lines) {
    if (line.trim()) {
      onEvent(JSON.parse(line) as TextStreamEvent);
    }
  }
  if (flush && remainder.trim()) {
    onEvent(JSON.parse(remainder) as TextStreamEvent);
  }
  return remainder;
}
