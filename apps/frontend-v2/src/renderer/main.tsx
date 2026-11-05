import React, { FormEvent, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { createRoot } from "react-dom/client";
import { MoMSettings } from "./MoMSettings";
import { createPresencePublicationGate } from "./presencePublication";
import { MoMToggle } from "./MoMToggle";
import { SwarmConfirmationCard } from "./SwarmConfirmationCard";
import type { SwarmConfirmationAction } from "./SwarmConfirmationCard";
import { WorkspacePanel } from "./WorkspacePanel";
import {
  applyActivityEvent,
  applyActivitySnapshot,
  createEmptyActivityState,
  createBaselineActivityState,
  deriveActivityScene,
  markActivityDisconnected,
  withBaselineActivityState
} from "../shared/activityAdapter";
import type { ActivityGraphState } from "../shared/activityAdapter";
import {
  applyStreamEvent,
  beginTurn,
  interruptedStream,
  markCancelled,
  prependOlderHistory,
  reconcileHistory,
  restoreFailed
} from "../shared/conversationRuntime";
import {
  applyCommandSelection,
  buildCommandRegistry,
  commandName,
  filterCommands,
  isSlashDiscoveryInput,
  moveCommandSelection,
  resolveSlashIntent
} from "../shared/commandDiscovery";
import { openActivityStream, SynapseClientError, SynapseFrontendClient } from "../shared/frontendClient";
import { derivePresenceState } from "../shared/presenceAdapter";
import type { PresenceSceneState } from "../shared/presenceAdapter";
import {
  effectiveReducedMotion,
  loadFrontendSettingsPreferences,
  normalizeTheme,
  saveFrontendSettingsPreferences
} from "../shared/settingsPreferences";
import type { FrontendSettingsPreferences, FrontendThemePreference } from "../shared/settingsPreferences";
import { pendingSwarmConfirmation } from "../shared/swarmInteraction";
import { assetsForTheme } from "../shared/themeAssets";
import { applyTheme } from "../shared/themeEngine";
import {
  conversationModeCapturesMicrophone,
  conversationModeStatusLabel,
  defaultConversationVadConfig,
  isEmptyRecording,
  isLikelyConversationModeEcho,
  mergeTranscriptionIntoDraft,
  normalizeVoiceError,
  releaseAudioTracks,
  updateConversationVad,
  voiceStatusLabel
} from "../shared/voiceCapture";
import type { ConversationVadSnapshot } from "../shared/voiceCapture";
import type {
  BackendConnectionState,
  AttachmentStageState,
  CommandDiscoveryItem,
  ConversationAttachment,
  ConversationIndexItem,
  ConversationMessage,
  ConversationPagination,
  ConversationRuntimeState,
  ConversationRecord,
  ConversationSummary,
  FirstAgentRequest,
  FrontendConversationError,
  FrontendBootstrap,
  InsightReport,
  NotificationRecord,
  ProjectKnowledgeDocumentRecord,
  ProjectKnowledgeDocumentsResult,
  SettingsSnapshot,
  SwarmInteractionRequest,
  ProviderModelOption,
  PrimaryAgentSummary,
  TextStreamEvent,
  ConversationModeState,
  LMStudioTelemetryEntry,
  UpdateProviderSettingRequest,
  UpdateVoiceSettingsRequest,
  VoiceConversationTurnRequest,
  VoiceConversationTurnResult,
  VoiceCaptureState,
  VoiceTranscriptionRequest
} from "../shared/types";
import "./styles.css";
import "./themeEngine.css";

const workspaceId = "default";
const historyPageSize = 50;
const conversationModeMinimumVoicePeak = 0.025;
const conversationModeListenWindowMs = 6200;
const conversationModeRestartDelayMs = 850;
const conversationModePostSpeechCooldownMs = 2200;
const conversationModeMaxCaptureMs = 12_000;
const conversationLogFadeDelayMs = 8_000;
const Presence = lazy(() => import("./Presence").then((module) => ({ default: module.Presence })));
const SynapseCoreAtmosphere = lazy(() => import("./SynapseCoreAtmosphere").then((module) => ({ default: module.SynapseCoreAtmosphere })));

type ShellIconVisualKey = "constellation" | "history" | "settings" | "notificationsIdle" | "notificationsActive";

const iconVisualOffsets: Record<ShellIconVisualKey, { x: number; y: number; scale: number }> = {
  constellation: { x: 0, y: 0, scale: 3.9 },
  history: { x: 0, y: 0, scale: 4.05 },
  settings: { x: 0, y: 0, scale: 2.1 },
  notificationsIdle: { x: 0, y: 0, scale: 3.1 },
  notificationsActive: { x: 0, y: 0, scale: 3.1 }
};

function shellIconStyle(key: ShellIconVisualKey): CSSProperties {
  const visual = iconVisualOffsets[key];
  return {
    "--shell-icon-x": `${visual.x}px`,
    "--shell-icon-y": `${visual.y}px`,
    "--shell-icon-scale": String(visual.scale)
  } as CSSProperties;
}

type SettingsSection = "personalization" | "voice" | "models" | "swarm" | "insight";
type LibrarySection = "history" | "files";

interface AppState {
  backendState: BackendConnectionState;
  bootstrap: FrontendBootstrap | null;
  conversation: ConversationRecord | null;
  messages: ConversationMessage[];
  pagination: ConversationPagination | null;
  summary: ConversationSummary | null;
  conversationStatus: ConversationRuntimeState;
  conversationError: FrontendConversationError | null;
  conversationIndex: ConversationIndexItem[];
  historyPanelOpen: boolean;
  librarySection: LibrarySection;
  historyStatus: "idle" | "loading" | "ready" | "empty" | "error";
  historyError: string | null;
  commands: CommandDiscoveryItem[];
  commandError: string | null;
  lastDraft: string;
  logMinimized: boolean;
  streamText: string;
  activeTurnKey: string | null;
  manualVoiceState: VoiceCaptureState;
  conversationModeState: ConversationModeState;
  presenceAmplitude: number;
  systemReducedMotion: boolean;
  reducedMotion: boolean;
  frontendSettings: FrontendSettingsPreferences;
  focused: boolean;
  activeVisual: "presence" | "activity";
  activityGraph: ActivityGraphState;
  modelTelemetry: string[];
  selectedActivityNodeId: string | null;
  insightStatus: "idle" | "loading" | "ready" | "degraded" | "unavailable" | "error";
  insightReport: InsightReport | null;
  insightError: string | null;
  settingsOpen: boolean;
  settingsSection: SettingsSection;
  settingsStatus: "idle" | "loading" | "ready" | "saving" | "error";
  settingsSnapshot: SettingsSnapshot | null;
  settingsError: string | null;
  notificationsOpen: boolean;
  notificationsStatus: "idle" | "loading" | "ready" | "empty" | "degraded" | "error";
  notifications: NotificationRecord[];
  notificationError: string | null;
  selectedNotificationIndex: number;
  projectFilesOpen: boolean;
  projectFilesStatus: "idle" | "loading" | "ready" | "empty" | "degraded" | "error";
  projectFiles: ProjectKnowledgeDocumentsResult | null;
  projectFilesError: string | null;
  projectFilesBusyDocumentId: string | null;
  workspaceOpen: boolean;
  workspaceStatus: "idle" | "loading" | "ready" | "error";
  workspaceProjects: import("../shared/types").ProjectManifestSummary[];
  workspaceSwarms: Array<Record<string, unknown>>;
  workspaceError: string | null;
  workspaceShowProjects: boolean;
  workspaceDemoActive: boolean;
  workspaceCommandOutput: Array<{ input: string; output: string }>;
  selectedSwarmId: string | null;
  swarmDetail: Record<string, unknown> | null;
  swarmTrace: Record<string, unknown> | null;
  swarmAgents: Array<Record<string, unknown>>;
  swarmTools: Record<string, string[]>;
  swarmResult: Record<string, unknown> | null;
  swarmConfirmation: SwarmInteractionRequest | null;
  swarmConfirmationBusy: boolean;
  error: string | null;
}

interface VisualErrorBoundaryProps {
  surface: "presence" | "activity";
  children: React.ReactNode;
}

interface VisualErrorBoundaryState {
  failedSurface: "presence" | "activity" | null;
  message: string | null;
}

class VisualErrorBoundary extends React.Component<VisualErrorBoundaryProps, VisualErrorBoundaryState> {
  state: VisualErrorBoundaryState = { failedSurface: null, message: null };

  static getDerivedStateFromError(error: unknown): VisualErrorBoundaryState {
    return {
      failedSurface: "presence",
      message: error instanceof Error ? error.message : String(error)
    };
  }

  componentDidCatch(error: unknown): void {
    this.setState({
      failedSurface: this.props.surface,
      message: error instanceof Error ? error.message : String(error)
    });
  }

  componentDidUpdate(previous: VisualErrorBoundaryProps): void {
    if (previous.surface !== this.props.surface && this.state.failedSurface !== null) {
      this.setState({ failedSurface: null, message: null });
    }
  }

  render(): React.ReactNode {
    if (this.state.failedSurface) {
      return <VisualLoadingFallback label={`${this.state.failedSurface} unavailable${this.state.message ? `: ${this.state.message}` : ""}`} failed />;
    }
    return this.props.children;
  }
}

interface ShellErrorBoundaryState {
  message: string | null;
  stack: string | null;
  componentStack: string | null;
}

class ShellErrorBoundary extends React.Component<{ children: React.ReactNode }, ShellErrorBoundaryState> {
  state: ShellErrorBoundaryState = { message: null, stack: null, componentStack: null };

  static getDerivedStateFromError(error: unknown): ShellErrorBoundaryState {
    return {
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack ?? null : null,
      componentStack: null
    };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo): void {
    this.setState({
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack ?? null : null,
      componentStack: info.componentStack ?? null
    });
  }

  render(): React.ReactNode {
    if (this.state.message) {
      return (
        <main className="fatal-renderer-error" role="alert">
          <h1>Synapse renderer unavailable</h1>
          <p>{this.state.message}</p>
          {this.state.stack ? <pre>{this.state.stack}</pre> : null}
          {this.state.componentStack ? <pre>{this.state.componentStack}</pre> : null}
        </main>
      );
    }
    return this.props.children;
  }
}

function VisualLoadingFallback({ label, failed = false }: { label: string; failed?: boolean }): React.ReactElement {
  return (
    <section className={`visual-fallback ${failed ? "failed" : "loading"}`} role="status" aria-live="polite">
      <span>{label}</span>
    </section>
  );
}

interface SettingsChanges {
  agentName: string;
  personality: string;
  defaultProvider: string;
  defaultModel: string;
  providerEnabled: boolean;
  providerEndpoint: string;
  voiceEnabled: boolean;
  sttProvider: string;
  sttModel: string;
  language: string;
  ttsProvider: string;
  defaultTtsVoice: string;
  preferredVoiceGender: string;
  vadEnabled: boolean;
  storeRawAudio: boolean;
  reducedMotion: FrontendSettingsPreferences["reducedMotion"];
  theme: FrontendThemePreference;
}

interface CommandExecutionResult {
  status: "completed" | "failed";
  message: string;
}

function App(): React.ReactElement {
  const [client, setClient] = useState<SynapseFrontendClient | null>(null);
  const initialPreferences = loadFrontendSettingsPreferences();
  const [state, setState] = useState<AppState>({
    backendState: "connecting",
    bootstrap: null,
    conversation: null,
    messages: [],
    pagination: null,
    summary: null,
    conversationStatus: "restoring",
    conversationError: null,
    conversationIndex: [],
    historyPanelOpen: false,
    librarySection: "history",
    historyStatus: "idle",
    historyError: null,
    commands: [],
    commandError: null,
    lastDraft: "",
    logMinimized: false,
    streamText: "",
    activeTurnKey: null,
    manualVoiceState: "idle",
    conversationModeState: "inactive",
    presenceAmplitude: 0,
    systemReducedMotion: false,
    reducedMotion: effectiveReducedMotion(initialPreferences.reducedMotion, false),
    frontendSettings: initialPreferences,
    focused: true,
    activeVisual: "presence",
    activityGraph: createEmptyActivityState(null),
    modelTelemetry: [],
    selectedActivityNodeId: null,
    insightStatus: "idle",
    insightReport: null,
    insightError: null,
    settingsOpen: false,
    settingsSection: "personalization",
    settingsStatus: "idle",
    settingsSnapshot: null,
    settingsError: null,
    notificationsOpen: false,
    notificationsStatus: "idle",
    notifications: [],
    notificationError: null,
    selectedNotificationIndex: 0,
    projectFilesOpen: false,
    projectFilesStatus: "idle",
    projectFiles: null,
    projectFilesError: null,
    projectFilesBusyDocumentId: null,
    workspaceOpen: false,
    workspaceStatus: "idle",
    workspaceProjects: [],
    workspaceSwarms: [],
    workspaceError: null,
    workspaceShowProjects: false,
    workspaceDemoActive: false,
    workspaceCommandOutput: [],
    selectedSwarmId: null,
    swarmDetail: null,
    swarmTrace: null,
    swarmAgents: [],
    swarmTools: {},
    swarmResult: null,
    swarmConfirmation: null,
    swarmConfirmationBusy: false,
    error: null
  });

  useEffect(() => {
    if (!window.matchMedia) {
      return;
    }
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = (): void => {
      setState((current) => ({
        ...current,
        systemReducedMotion: media.matches,
        reducedMotion: effectiveReducedMotion(current.frontendSettings.reducedMotion, media.matches)
      }));
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    applyTheme(document.documentElement, state.frontendSettings.theme, state.reducedMotion, state.focused);
  }, [state.frontendSettings.theme, state.reducedMotion, state.focused]);

  useEffect(() => {
    const update = (): void => {
      setState((current) => ({ ...current, focused: document.hasFocus() && !document.hidden }));
    };
    window.addEventListener("focus", update);
    window.addEventListener("blur", update);
    document.addEventListener("visibilitychange", update);
    update();
    return () => {
      window.removeEventListener("focus", update);
      window.removeEventListener("blur", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function connect(): Promise<void> {
      try {
        if (!window.synapse) {
          throw new Error("Synapse desktop bridge is unavailable.");
        }
        const baseUrl = await window.synapse.backendBaseUrl();
        const nextClient = new SynapseFrontendClient(baseUrl);
        if (cancelled) {
          return;
        }
        setClient(nextClient);
        const bootstrap = await nextClient.bootstrap();
        if (cancelled) {
          return;
        }
        setState((current) => ({
          ...current,
          backendState: bootstrap.degraded.length > 0 ? "degraded" : "ready",
          bootstrap,
          conversation: bootstrap.conversation,
          activityGraph: createBaselineActivityState(
            bootstrap.project_id,
            bootstrap.primary_agent,
            primaryModelOption(bootstrap.provider_model_options)
          ),
          error: null
        }));
        await window.synapse.reportBootstrap(bootstrap.onboarding_required ? "onboarding" : (bootstrap.degraded.length > 0 ? "degraded" : "ready"));
        if (!bootstrap.onboarding_required) {
          const opened = await nextClient.openConversation({ workspace_id: workspaceId, history_limit: historyPageSize });
          const index = await nextClient.conversationIndex({ workspace_id: workspaceId, limit: historyPageSize });
          let notifications: NotificationRecord[] = [];
          let notificationsStatus: AppState["notificationsStatus"] = "idle";
          let notificationError: string | null = null;
          try {
            notifications = await nextClient.notifications();
            notificationsStatus = notifications.length > 0 ? "ready" : "empty";
          } catch (notificationFailure) {
            notificationsStatus = "degraded";
            notificationError = readableError(notificationFailure);
          }
          if (!cancelled) {
            setState((current) => ({
              ...current,
              conversation: opened.conversation,
              messages: [],
              pagination: opened.pagination,
              summary: opened.summary,
              conversationStatus: "idle",
              conversationError: null,
              conversationIndex: index.conversations,
              historyStatus: index.conversations.length > 0 ? "ready" : "empty",
              historyError: null,
              commands: [],
              commandError: null,
              streamText: "",
              notifications,
              notificationsStatus,
              notificationError,
              backendState: opened.degraded.length > 0 ? "degraded" : "ready"
            }));
          }
        }
      } catch (error) {
        if (!cancelled) {
          void window.synapse?.reportBootstrap("failed");
          setState((current) => ({
            ...current,
            backendState: error instanceof SynapseClientError ? "error" : "disconnected",
            conversationStatus: "disconnected",
            error: readableError(error)
          }));
        }
      }
    }
    void connect();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshAfterOnboarding = useCallback(
    async (request: FirstAgentRequest) => {
      if (!client) {
        return;
      }
      setState((current) => ({ ...current, backendState: "connecting", error: null }));
      await client.createFirstAgent(request);
      const bootstrap = await client.bootstrap();
      const opened = await client.openConversation({ workspace_id: workspaceId, history_limit: historyPageSize });
      const index = await client.conversationIndex({ workspace_id: workspaceId, limit: historyPageSize });
      setState((current) => ({
        ...current,
        backendState: "ready",
        bootstrap,
        conversation: opened.conversation,
        messages: [],
        pagination: opened.pagination,
        summary: opened.summary,
        conversationStatus: "idle",
        conversationError: null,
        conversationIndex: index.conversations,
        historyStatus: index.conversations.length > 0 ? "ready" : "empty",
        historyError: null,
        commands: [],
        commandError: null,
        streamText: "",
        error: null
      }));
      await window.synapse?.reportBootstrap(bootstrap.degraded.length > 0 ? "degraded" : "ready");
    },
    [client]
  );

  if (state.backendState === "connecting" && !state.bootstrap) {
    return (
      <Frame
        state={state}
         activeVisual={state.activeVisual}
         onToggleActivity={() => undefined}
         onRefreshInsight={() => undefined}
         onToggleSettings={() => undefined}
         onCloseSettings={() => undefined}
         onSelectSettingsSection={() => undefined}
         onRefreshSettings={() => undefined}
        onSaveSettings={() => undefined}
        onPreviewFrontendSettings={() => undefined}
        onToggleLog={() => undefined}
        onLoadOlderHistory={() => undefined}
        onRecoverConversation={() => undefined}
        main={<CenteredStatus title="Connecting" detail="Checking backend bootstrap state." />}
      />
    );
  }

  if (!client) {
    return (
      <Frame
        state={state}
         activeVisual={state.activeVisual}
         onToggleActivity={() => undefined}
         onRefreshInsight={() => undefined}
         onToggleSettings={() => undefined}
         onCloseSettings={() => undefined}
         onSelectSettingsSection={() => undefined}
         onRefreshSettings={() => undefined}
        onSaveSettings={() => undefined}
        onPreviewFrontendSettings={() => undefined}
        onToggleLog={() => setState((current) => ({ ...current, logMinimized: !current.logMinimized }))}
        onLoadOlderHistory={() => undefined}
        onRecoverConversation={() => undefined}
        main={<CenteredStatus title="Disconnected" detail={state.error ?? "Backend is not reachable."} />}
      />
    );
  }

  if (state.bootstrap?.onboarding_required) {
    return (
      <Frame
        state={state}
         activeVisual={state.activeVisual}
         onToggleActivity={() => undefined}
         onRefreshInsight={() => undefined}
         onToggleSettings={() => undefined}
         onCloseSettings={() => undefined}
         onSelectSettingsSection={() => undefined}
         onRefreshSettings={() => undefined}
        onSaveSettings={() => undefined}
        onPreviewFrontendSettings={() => undefined}
        onToggleLog={() => setState((current) => ({ ...current, logMinimized: !current.logMinimized }))}
        onLoadOlderHistory={() => undefined}
        onRecoverConversation={() => undefined}
        main={<Onboarding bootstrap={state.bootstrap} onCreate={refreshAfterOnboarding} />}
      />
    );
  }

  return (
    <Workspace
      state={state}
      client={client}
      setState={setState}
    />
  );
}

function Workspace({
  state,
  client,
  setState
}: {
  state: AppState;
  client: SynapseFrontendClient;
  setState: React.Dispatch<React.SetStateAction<AppState>>;
}): React.ReactElement {
  const activityCursorRef = useRef<string | null>(null);
  const refreshConversationIndex = useCallback(
    async () => {
      setState((current) => ({ ...current, historyStatus: "loading", historyError: null }));
      try {
        const index = await client.conversationIndex({
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          limit: historyPageSize
        });
        setState((current) => ({
          ...current,
          conversationIndex: index.conversations,
          historyStatus: index.conversations.length > 0 ? "ready" : "empty",
          historyError: null
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          historyStatus: "error",
          historyError: readableError(error)
        }));
      }
    },
    [client, setState, state.bootstrap?.project_id, state.bootstrap?.session_id]
  );

  const sendMessage = useCallback(
    async (
      content: string,
      attachments: ConversationAttachment[] = [],
      surface: "conversation" | "workspace" = "conversation"
    ) => {
      if (!state.conversation) {
        return;
      }
      const workspaceSurface = surface === "workspace";
      const conversationId = state.conversation.conversation_id;
      const abort = new AbortController();
      const idempotencyKey = crypto.randomUUID();
      const optimistic: ConversationMessage = {
        message_id: `pending-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        conversation_id: conversationId,
        sender_agent_id: "local_chat",
        receiver_agent_id: state.bootstrap?.primary_agent?.agent_id ?? "primary",
        role: "user",
        status: "completed",
        payload: { body: content, role: "user" },
        attachments,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      if (workspaceSurface) {
        setState((current) => ({
          ...current,
          workspaceOpen: true,
          workspaceError: null,
          workspaceCommandOutput: [...current.workspaceCommandOutput, { input: content, output: "" }].slice(-100)
        }));
      } else {
        setState((current) => ({
          ...current,
          backendState: "ready",
          activeTurnKey: idempotencyKey,
          ...toReactConversationState(beginTurn(
            {
              status: current.conversationStatus,
              messages: current.messages,
              partialAssistant: current.streamText,
              error: current.conversationError,
              lastDraft: current.lastDraft
            },
            optimistic,
            content
          )),
          error: null
        }));
      }
      let completed = false;
      let startedSwarmId: string | null = null;
      try {
        await client.streamTextTurn(
          conversationId,
          {
            content,
            workspace_id: workspaceId,
            project_id: state.bootstrap?.project_id ?? null,
            session_id: state.bootstrap?.session_id ?? null,
            attachments,
            idempotency_key: idempotencyKey
          },
          (event: TextStreamEvent) => {
            if (event.conversation_id && event.conversation_id !== conversationId) {
              return;
            }
            if (event.type === "generation_completed") {
              completed = true;
            }
            if (event.type === "swarm_started") {
              startedSwarmId = event.data?.request.swarm_id ?? null;
            }
            if (workspaceSurface) {
              setState((current) => {
                const outputIndex = current.workspaceCommandOutput.length - 1;
                if (outputIndex < 0) return current;
                const entry = current.workspaceCommandOutput[outputIndex];
                const output = event.type === "chunk_received"
                  ? `${entry.output}${event.content ?? ""}`
                  : event.type === "generation_failed"
                    ? `${entry.output}\n[erro] ${event.error?.message ?? "Falha na execução."}`
                    : entry.output;
                return {
                  ...current,
                  workspaceCommandOutput: current.workspaceCommandOutput.map((item, index) =>
                    index === outputIndex ? { ...item, output } : item
                  ),
                  swarmConfirmation: event.type === "confirmation_required"
                    ? event.data?.request ?? current.swarmConfirmation
                    : event.type === "swarm_started" ? null : current.swarmConfirmation,
                  swarmConfirmationBusy: false,
                  workspaceStatus: event.type === "swarm_started" ? "idle" : current.workspaceStatus
                };
              });
              return;
            }
            setState((current) => {
              if (current.conversation?.conversation_id !== conversationId) {
                return current;
              }
              const next = applyStreamEvent(
                {
                  status: current.conversationStatus,
                  messages: current.messages,
                  partialAssistant: current.streamText,
                  error: current.conversationError,
                  lastDraft: current.lastDraft
                },
                event
              );
              return {
                ...current,
                conversationStatus: next.status,
                messages: next.messages,
                streamText: next.partialAssistant,
                conversationError: next.error,
                activeTurnKey: next.status === "completed" || next.status === "cancelled" || next.status === "failed" ? null : current.activeTurnKey,
                backendState: next.status === "failed" ? "error" : current.backendState,
                error: next.error?.message ?? current.error,
                swarmConfirmation: event.type === "confirmation_required"
                  ? event.data?.request ?? current.swarmConfirmation
                  : event.type === "swarm_started" ? null : current.swarmConfirmation,
                swarmConfirmationBusy: false,
                workspaceOpen: event.type === "swarm_started" ? true : current.workspaceOpen,
                workspaceStatus: event.type === "swarm_started" ? "idle" : current.workspaceStatus
              };
            });
          },
          abort.signal
        );
        if (workspaceSurface) {
          if (startedSwarmId) {
            setState((current) => ({
              ...current,
              workspaceOpen: true,
              selectedSwarmId: startedSwarmId
            }));
          }
          return;
        }
        const history = await client.history(conversationId, {
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          limit: historyPageSize
        });
        setState((current) => {
          if (current.conversation?.conversation_id !== conversationId) {
            return current;
          }
          return {
            ...current,
            conversation: history.conversation,
            pagination: history.pagination,
            summary: history.summary,
            ...toReactConversationState(reconcileHistory(
              {
                status: current.conversationStatus,
                messages: current.messages,
                partialAssistant: current.streamText,
                error: current.conversationError,
                lastDraft: current.lastDraft
              },
              history.messages,
              { completed }
            )),
            activeTurnKey: null,
            swarmConfirmation: pendingSwarmConfirmation(history.messages),
            swarmConfirmationBusy: false,
            backendState: history.degraded.length > 0 ? "degraded" : "ready"
          };
        });
        await refreshConversationIndex();
        if (startedSwarmId) {
          setState((current) => ({
            ...current,
            workspaceOpen: true,
            selectedSwarmId: startedSwarmId
          }));
        }
      } catch (error) {
        abort.abort();
        if (workspaceSurface) {
          setState((current) => {
            const outputIndex = current.workspaceCommandOutput.length - 1;
            if (outputIndex < 0) return current;
            const entry = current.workspaceCommandOutput[outputIndex];
            return {
              ...current,
              workspaceCommandOutput: current.workspaceCommandOutput.map((item, index) =>
                index === outputIndex
                  ? { ...item, output: `${entry.output}\n[erro] ${readableError(error)}` }
                  : item
              ),
              workspaceError: null
            };
          });
          return;
        }
        setState((current) => {
          const next = interruptedStream(
            {
              status: current.conversationStatus,
              messages: current.messages,
              partialAssistant: current.streamText,
              error: current.conversationError,
              lastDraft: current.lastDraft
            },
            error
          );
          return {
            ...current,
            ...toReactConversationState(next),
            activeTurnKey: null,
            backendState: next.status === "disconnected" ? "disconnected" : "error",
            error: next.error?.message ?? "Conversation stream failed."
          };
        });
      }
    },
    [client, refreshConversationIndex, setState, state.bootstrap?.primary_agent?.agent_id, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation]
  );

  const loadProjectFiles = useCallback(
    async () => {
      const projectId = state.bootstrap?.project_id;
      if (!projectId) {
        setState((current) => ({
          ...current,
          projectFilesStatus: "empty",
          projectFiles: null,
          projectFilesError: "No active project selected."
        }));
        return;
      }
      setState((current) => ({
        ...current,
        projectFilesStatus: "loading",
        projectFilesError: null
      }));
      try {
        const result = await client.projectKnowledgeDocuments(projectId, workspaceId);
        setState((current) => ({
          ...current,
          projectFiles: result,
          projectFilesStatus: result.documents.length > 0 ? "ready" : "empty",
          projectFilesError: null
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          projectFilesStatus: current.projectFiles ? "degraded" : "error",
          projectFilesError: readableError(error)
        }));
      }
    },
    [client, setState, state.bootstrap?.project_id]
  );

  const loadWorkspace = useCallback(async () => {
    setState((current) => ({
      ...current,
      workspaceStatus: "loading",
      workspaceError: null,
      workspaceDemoActive: false,
      swarmDetail: null,
      swarmTrace: null,
      swarmAgents: [],
      swarmResult: null
    }));
    try {
      const [projects, swarms] = await Promise.all([client.projects(), client.swarms()]);
      setState((current) => ({
        ...current,
        workspaceProjects: projects.projects,
        workspaceSwarms: swarms,
        workspaceStatus: "ready",
        workspaceError: null
      }));
    } catch (error) {
      setState((current) => ({ ...current, workspaceStatus: "error", workspaceError: readableError(error) }));
    }
  }, [client, setState]);

  useEffect(() => {
    if (state.workspaceOpen && state.workspaceStatus === "idle") {
      void loadWorkspace();
    }
  }, [loadWorkspace, state.workspaceOpen, state.workspaceStatus]);

  const selectWorkspaceSwarm = useCallback(async (swarmId: string) => {
    setState((current) => ({ ...current, selectedSwarmId: swarmId, swarmDetail: null, swarmTrace: null, swarmResult: null, workspaceError: null }));
    try {
      const [detail, trace, members] = await Promise.all([client.swarm(swarmId), client.swarmTrace(swarmId), client.swarmMembers(swarmId)]);
      const memberIds = Array.isArray(members.member_agent_ids) ? members.member_agent_ids.map(String) : [];
      const agents = await Promise.all(memberIds.map((id) => client.agentProfile(id).catch(() => ({ agent_id: id }))));
      const tools = Object.fromEntries(await Promise.all(memberIds.map(async (id) => {
        const catalog = await client.agentTools(id).catch(() => ({}));
        const items = Array.isArray(catalog.tools) ? catalog.tools.map(String) : Array.isArray(catalog.available_tools) ? catalog.available_tools.map(String) : [];
        return [id, items] as const;
      })));
      let result: Record<string, unknown> | null = null;
      if (["completed", "failed", "cancelled"].includes(String(detail.status))) {
        result = await client.swarmResult(swarmId).catch(() => null);
      }
      setState((current) => ({ ...current, selectedSwarmId: swarmId, swarmDetail: detail, swarmTrace: trace, swarmResult: result, swarmAgents: agents, swarmTools: tools }));
    } catch (error) {
      setState((current) => ({ ...current, workspaceError: readableError(error) }));
    }
  }, [client, setState]);

  useEffect(() => {
    if (!state.workspaceOpen || state.workspaceDemoActive || state.workspaceStatus !== "ready" || state.selectedSwarmId) return;
    const running = state.workspaceSwarms.find((swarm) => ["running", "paused"].includes(String(swarm.status)));
    if (running?.swarm_id) void selectWorkspaceSwarm(String(running.swarm_id));
  }, [selectWorkspaceSwarm, state.selectedSwarmId, state.workspaceDemoActive, state.workspaceOpen, state.workspaceStatus, state.workspaceSwarms]);

  useEffect(() => {
    if (!state.workspaceOpen || state.workspaceDemoActive || state.workspaceStatus !== "ready" || !state.selectedSwarmId || state.swarmDetail) return;
    void selectWorkspaceSwarm(state.selectedSwarmId);
  }, [selectWorkspaceSwarm, state.selectedSwarmId, state.swarmDetail, state.workspaceDemoActive, state.workspaceOpen, state.workspaceStatus]);

  useEffect(() => {
    if (!state.workspaceOpen || state.workspaceDemoActive || !state.selectedSwarmId) return;
    const swarmId = state.selectedSwarmId;
    const timer = window.setInterval(() => {
      void Promise.all([client.swarm(swarmId), client.swarmTrace(swarmId)]).then(async ([detail, trace]) => {
        const result = ["completed", "failed", "cancelled"].includes(String(detail.status))
          ? await client.swarmResult(swarmId).catch(() => null)
          : null;
        setState((current) => current.selectedSwarmId === swarmId ? ({ ...current, swarmDetail: detail, swarmTrace: trace, swarmResult: result }) : current);
      }).catch(() => undefined);
    }, 2200);
    return () => window.clearInterval(timer);
  }, [client, setState, state.selectedSwarmId, state.workspaceDemoActive, state.workspaceOpen]);

  const stageAttachment = useCallback(
    async (file: { filename: string; mime_type: string; size: number; content_base64: string }) => {
      if (!state.conversation) {
        throw new Error("Conversation is unavailable.");
      }
      const result = await client.stageAttachment(state.conversation.conversation_id, {
        ...file,
        workspace_id: workspaceId,
        project_id: state.bootstrap?.project_id ?? null,
        session_id: state.bootstrap?.session_id ?? null
      });
      if (state.bootstrap?.project_id) {
        void loadProjectFiles();
      }
      return result.attachment;
    },
    [client, loadProjectFiles, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation]
  );

  const transcribeVoice = useCallback(
    async (payload: Pick<VoiceTranscriptionRequest, "audio_base64" | "audio_format" | "duration_ms">) => {
      if (!state.conversation) {
        throw new Error("Conversation is unavailable.");
      }
      const result = await client.transcribeVoice({
        ...payload,
        workspace_id: workspaceId,
        project_id: state.bootstrap?.project_id ?? null,
        session_id: state.bootstrap?.session_id ?? null,
        conversation_id: state.conversation.conversation_id
      });
      return result.transcript;
    },
    [client, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation]
  );

  const runVoiceConversationTurn = useCallback(
    async (
      payload: Pick<VoiceConversationTurnRequest, "audio_base64" | "audio_format" | "voice_session_id" | "idempotency_key">,
      onGenerating?: () => void,
      signal?: AbortSignal
    ): Promise<VoiceConversationTurnResult> => {
      if (!state.conversation) {
        throw new Error("Conversation is unavailable.");
      }
      const voiceConversationId = state.conversation.conversation_id;
      setState((current) => ({ ...current, streamText: "" }));
      const result = await client.voiceConversationTurn({
        ...payload,
        workspace_id: workspaceId,
        project_id: state.bootstrap?.project_id ?? null,
        session_id: state.bootstrap?.session_id ?? null,
        conversation_id: state.conversation.conversation_id,
        language: state.settingsSnapshot?.voice.settings.language ?? "pt-BR"
      }, (delta) => {
        onGenerating?.();
        setState((current) => current.conversation?.conversation_id === voiceConversationId
          ? { ...current, streamText: current.streamText + delta, conversationStatus: "streaming" }
          : current);
      }, signal);
      if (signal?.aborted) throw new DOMException("Voice turn cancelled", "AbortError");
      const updatedConversation = { ...state.conversation, conversation_id: result.conversation_id };
      setState((current) => current.conversation?.conversation_id !== voiceConversationId ? current : ({
        ...current,
        conversation: current.conversation
          ? { ...current.conversation, conversation_id: result.conversation_id }
          : updatedConversation,
        messages: result.messages,
        pagination: result.pagination,
        summary: result.summary,
        conversationStatus: "completed",
        conversationError: null,
        streamText: "",
        backendState: result.degraded.length > 0 ? "degraded" : "ready"
      }));
      return result;
    },
    [client, setState, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation, state.settingsSnapshot?.voice.settings.language]
  );

  const loadCommands = useCallback(
    async () => {
      try {
        const catalog = await client.commandCatalog();
        setState((current) => ({ ...current, commands: buildCommandRegistry(catalog.tools), commandError: null }));
      } catch (error) {
        setState((current) => ({
          ...current,
          commands: [],
          commandError: readableError(error)
        }));
      }
    },
    [client, setState]
  );

  const openNewConversation = useCallback(
    async () => {
      setState((current) => ({
        ...current,
        conversationStatus: "restoring",
        conversationError: null,
        streamText: "",
        activeTurnKey: null,
        messages: [],
        summary: null,
        swarmConfirmation: null,
        swarmConfirmationBusy: false
      }));
      const opened = await client.openConversation({
        workspace_id: workspaceId,
        project_id: state.bootstrap?.project_id ?? null,
        session_id: state.bootstrap?.session_id ?? null,
        history_limit: historyPageSize
      });
      setState((current) => ({
        ...current,
        conversation: opened.conversation,
        messages: [],
        pagination: opened.pagination,
        summary: opened.summary,
        conversationStatus: "idle",
        conversationError: null,
        streamText: "",
        activeTurnKey: null,
        swarmConfirmation: null,
        swarmConfirmationBusy: false,
        backendState: opened.degraded.length > 0 ? "degraded" : "ready"
      }));
      await refreshConversationIndex();
    },
    [client, refreshConversationIndex, setState, state.bootstrap?.project_id, state.bootstrap?.session_id]
  );

  const openConversationFromHistory = useCallback(
    async (conversationId: string) => {
      setState((current) => ({
        ...current,
        conversationStatus: "restoring",
        conversationError: null,
        streamText: "",
        activeTurnKey: null,
        messages: [],
        summary: null
      }));
      try {
        const opened = await client.openConversation({
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          conversation_id: conversationId,
          history_limit: historyPageSize
        });
        setState((current) => ({
          ...current,
          conversation: opened.conversation,
          messages: opened.messages,
          pagination: opened.pagination,
          summary: opened.summary,
          conversationStatus: "idle",
          conversationError: null,
          streamText: "",
          activeTurnKey: null,
          historyPanelOpen: false,
          swarmConfirmation: pendingSwarmConfirmation(opened.messages),
          swarmConfirmationBusy: false,
          backendState: opened.degraded.length > 0 ? "degraded" : "ready"
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          conversationStatus: "failed",
          conversationError: {
            code: "history_restore_failure",
            message: readableError(error),
            retryable: true
          },
          backendState: "error"
        }));
      }
    },
    [client, setState, state.bootstrap?.project_id, state.bootstrap?.session_id]
  );

  const deleteConversationFromHistory = useCallback(
    async (conversationId: string) => {
      const confirmed = window.confirm("Delete this conversation history? This cannot be undone.");
      if (!confirmed) {
        return;
      }
      setState((current) => ({ ...current, historyStatus: "loading", historyError: null }));
      try {
        await client.deleteConversation(conversationId, {
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          confirmed: true
        });
        await refreshConversationIndex();
        if (state.conversation?.conversation_id === conversationId) {
          await openNewConversation();
        }
      } catch (error) {
        setState((current) => ({
          ...current,
          historyStatus: "error",
          historyError: readableError(error)
        }));
      }
    },
    [client, openNewConversation, refreshConversationIndex, setState, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation?.conversation_id]
  );

  const clearConversationHistory = useCallback(
    async () => {
      const visibleCount = state.conversationIndex.filter((item) => item.message_count > 0).length;
      if (visibleCount === 0) {
        return;
      }
      const confirmed = window.confirm(`Delete ${visibleCount} conversation${visibleCount === 1 ? "" : "s"} from history? This cannot be undone.`);
      if (!confirmed) {
        return;
      }
      setState((current) => ({ ...current, historyStatus: "loading", historyError: null }));
      try {
        await client.clearConversationHistory({
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          confirmed: true
        });
        await refreshConversationIndex();
        if (state.conversation && state.messages.length > 0) {
          await openNewConversation();
        }
      } catch (error) {
        setState((current) => ({
          ...current,
          historyStatus: "error",
          historyError: readableError(error)
        }));
      }
    },
    [client, openNewConversation, refreshConversationIndex, setState, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation, state.conversationIndex, state.messages.length]
  );

  const loadOlderHistory = useCallback(
    async () => {
      if (!state.conversation || !state.pagination?.has_older || state.pagination.previous_offset === null) {
        return;
      }
      const previousOffset = state.pagination.previous_offset;
      setState((current) => ({ ...current, conversationStatus: "restoring", conversationError: null }));
      try {
        const history = await client.history(state.conversation.conversation_id, {
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          offset: previousOffset,
          limit: historyPageSize
        });
        setState((current) => ({
          ...current,
          conversation: history.conversation,
          pagination: history.pagination,
          summary: history.summary,
          ...toReactConversationState(prependOlderHistory(
            {
              status: "idle",
              messages: current.messages,
              partialAssistant: current.streamText,
              error: current.conversationError,
              lastDraft: current.lastDraft
            },
            history.messages
          )),
          backendState: history.degraded.length > 0 ? "degraded" : "ready"
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          ...toReactConversationState(restoreFailed(
            {
              status: current.conversationStatus,
              messages: current.messages,
              partialAssistant: current.streamText,
              error: current.conversationError,
              lastDraft: current.lastDraft
            },
            error
          )),
          backendState: "error"
        }));
      }
    },
    [client, setState, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation, state.pagination]
  );

  const cancelTurn = useCallback(
    async () => {
      if (!state.conversation || !state.activeTurnKey) {
        return;
      }
      try {
        await client.cancelTextTurn(state.conversation.conversation_id, {
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          idempotency_key: state.activeTurnKey
        });
        setState((current) => ({
          ...current,
          ...toReactConversationState(markCancelled({
            status: current.conversationStatus,
            messages: current.messages,
            partialAssistant: current.streamText,
            error: current.conversationError,
            lastDraft: current.lastDraft
          })),
          activeTurnKey: null
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          conversationStatus: "failed",
          conversationError: {
            code: "cancel_failed",
            message: readableError(error),
            retryable: true
          },
          error: readableError(error)
        }));
      }
    },
    [client, setState, state.activeTurnKey, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation]
  );

  const recoverConversation = useCallback(
    async () => {
      if (!state.conversation) {
        return;
      }
      setState((current) => ({ ...current, conversationStatus: "restoring", conversationError: null }));
      try {
        const history = await client.history(state.conversation.conversation_id, {
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null,
          limit: historyPageSize
        });
        setState((current) => ({
          ...current,
          conversation: history.conversation,
          pagination: history.pagination,
          summary: history.summary,
          ...toReactConversationState(reconcileHistory(
            {
              status: current.conversationStatus,
              messages: current.messages,
              partialAssistant: current.streamText,
              error: current.conversationError,
              lastDraft: current.lastDraft
            },
            history.messages,
            { completed: true }
          )),
          swarmConfirmation: pendingSwarmConfirmation(history.messages),
          swarmConfirmationBusy: false,
          backendState: history.degraded.length > 0 ? "degraded" : "ready"
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          ...toReactConversationState(restoreFailed(
            {
              status: current.conversationStatus,
              messages: current.messages,
              partialAssistant: current.streamText,
              error: current.conversationError,
              lastDraft: current.lastDraft
            },
            error
          )),
          backendState: "error"
        }));
      }
    },
    [client, setState, state.bootstrap?.project_id, state.bootstrap?.session_id, state.conversation]
  );

  const resolveSwarmConfirmation = useCallback(
    async (action: SwarmConfirmationAction) => {
      const pending = state.swarmConfirmation;
      if (!pending || state.swarmConfirmationBusy) {
        return;
      }
      setState((current) => ({
        ...current,
        swarmConfirmationBusy: true,
        workspaceError: null,
        error: null
      }));
      try {
        const result = await client.resolveSwarmConfirmation(pending.request_id, action, {
          workspace_id: workspaceId,
          project_id: state.bootstrap?.project_id ?? null,
          session_id: state.bootstrap?.session_id ?? null
        });
        setState((current) => ({
          ...current,
          swarmConfirmation: null,
          swarmConfirmationBusy: false,
          workspaceOpen: action === "cancel" ? current.workspaceOpen : true,
          selectedSwarmId: result.request.swarm_id ?? current.selectedSwarmId,
          workspaceStatus: action === "cancel" ? current.workspaceStatus : "idle"
        }));
        await recoverConversation();
      } catch (error) {
        setState((current) => ({
          ...current,
          swarmConfirmationBusy: false,
          workspaceError: readableError(error),
          error: readableError(error)
        }));
      }
    },
    [client, recoverConversation, setState, state.bootstrap?.project_id, state.bootstrap?.session_id, state.swarmConfirmation, state.swarmConfirmationBusy]
  );

  const presencePublicationRef = useRef(createPresencePublicationGate());
  const updatePresenceFacts = useCallback(
    (manualVoiceState: VoiceCaptureState, conversationModeState: ConversationModeState, amplitude: number) => {
      if (!presencePublicationRef.current(`${manualVoiceState}:${conversationModeState}`, amplitude, performance.now())) return;
      setState((current) => ({
        ...current,
        manualVoiceState,
        conversationModeState,
        presenceAmplitude: amplitude
      }));
    },
    [setState]
  );

  const loadInsight = useCallback(
    async () => {
      setState((current) => ({
        ...current,
        insightStatus: "loading",
        insightError: null
      }));
      try {
        const report = await client.insightReport();
        const degraded = report.limitations.length > 0 || report.diagnostics.status !== "ok";
        setState((current) => ({
          ...current,
          insightReport: report,
          insightStatus: degraded ? "degraded" : "ready",
          insightError: null
        }));
      } catch (error) {
        const unavailable = error instanceof SynapseClientError && (error.status === 404 || error.status === 503);
        setState((current) => ({
          ...current,
          insightStatus: unavailable ? "unavailable" : "error",
          insightError: readableError(error)
        }));
      }
    },
    [client, setState]
  );

  const loadSettings = useCallback(
    async () => {
      setState((current) => ({
        ...current,
        settingsStatus: "loading",
        settingsError: null
      }));
      try {
        const snapshot = await client.settingsSnapshot(state.bootstrap?.primary_agent?.agent_id);
        setState((current) => ({
          ...current,
          settingsSnapshot: snapshot,
          settingsStatus: "ready",
          settingsError: null
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          settingsStatus: "error",
          settingsError: readableError(error)
        }));
      }
    },
    [client, setState, state.bootstrap?.primary_agent?.agent_id]
  );

  const toggleSettings = useCallback(
    () => {
      setState((current) => ({ ...current, settingsOpen: !current.settingsOpen }));
      if (!state.settingsOpen && state.settingsSnapshot === null) {
        void loadSettings();
      }
      if (!state.settingsOpen && state.insightReport === null) {
        void loadInsight();
      }
    },
    [loadInsight, loadSettings, setState, state.insightReport, state.settingsOpen, state.settingsSnapshot]
  );

  const saveSettings = useCallback(
    async (changes: SettingsChanges) => {
      setState((current) => ({ ...current, settingsStatus: "saving", settingsError: null }));
      try {
        const current = state.settingsSnapshot;
        if (!current) {
          const preferences = saveFrontendSettingsPreferences({
            reducedMotion: changes.reducedMotion,
            theme: "synapse"
          });
          setState((stateAfterSave) => ({
            ...stateAfterSave,
            frontendSettings: preferences,
            reducedMotion: effectiveReducedMotion(preferences.reducedMotion, stateAfterSave.systemReducedMotion),
            settingsStatus: "ready",
            settingsError: null
          }));
          return;
        }
        const selectedProvider = changes.defaultProvider || null;
        if (current.personalization && (
          changes.agentName !== current.personalization.display_name ||
          changes.personality !== current.personalization.system_prompt
        )) {
          if (!changes.agentName.trim()) throw new Error("Agent name is required.");
          await client.updatePersonality(current.personalization.agent_id, changes.agentName, changes.personality);
        }
        const providerPayload: UpdateProviderSettingRequest = {
          enabled: changes.providerEnabled,
          endpoint: changes.providerEndpoint
        };
        const voicePayload: UpdateVoiceSettingsRequest = {
          enabled: changes.voiceEnabled,
          stt_provider_id: changes.sttProvider,
          stt_model: changes.sttModel,
          language: changes.language,
          tts_provider_id: changes.ttsProvider,
          default_tts_voice: changes.defaultTtsVoice,
          preferred_voice_gender: changes.preferredVoiceGender,
          vad_enabled: changes.vadEnabled,
          store_raw_audio: changes.storeRawAudio
        };
        if (selectedProvider) {
          await client.updateProviderSetting(selectedProvider, providerPayload);
        }
        if (changes.defaultProvider !== current.models.defaults.default_provider ||
            changes.defaultModel !== current.models.defaults.default_chat_model) {
          await client.updateModelDefaults({ default_provider: selectedProvider,
            default_chat_model: changes.defaultModel || null });
        }
        await client.updateVoiceSettings(voicePayload);
        const preferences = saveFrontendSettingsPreferences({
          reducedMotion: changes.reducedMotion,
          theme: "synapse"
        });
        const snapshot = await client.settingsSnapshot(current.personalization?.agent_id);
        const bootstrap = await client.bootstrap();
        setState((stateAfterSave) => ({
          ...stateAfterSave,
          frontendSettings: preferences,
          reducedMotion: effectiveReducedMotion(preferences.reducedMotion, stateAfterSave.systemReducedMotion),
          backendState: bootstrap.degraded.length > 0 ? "degraded" : "ready",
          bootstrap,
          conversation: bootstrap.conversation ?? stateAfterSave.conversation,
          activityGraph: createBaselineActivityState(
            bootstrap.project_id,
            bootstrap.primary_agent,
            primaryModelOption(bootstrap.provider_model_options)
          ),
          selectedActivityNodeId: null,
          modelTelemetry: [],
          settingsSnapshot: snapshot,
          settingsStatus: "ready",
          settingsError: null
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          settingsStatus: "error",
          settingsError: readableError(error)
        }));
      }
    },
    [client, setState, state.settingsSnapshot]
  );

  const previewFrontendSettings = useCallback(
    (preferences: FrontendSettingsPreferences) => {
      setState((current) => ({
        ...current,
        frontendSettings: {
          reducedMotion: preferences.reducedMotion,
          theme: "synapse"
        },
        reducedMotion: effectiveReducedMotion(preferences.reducedMotion, current.systemReducedMotion)
      }));
    },
    [setState]
  );

  useEffect(() => {
    if (!state.settingsOpen) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setState((current) => ({ ...current, settingsOpen: false }));
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [setState, state.settingsOpen]);

  const executeCommand = useCallback(
    async (input: string): Promise<CommandExecutionResult> => {
      const commands = state.commands.length > 0 ? state.commands : buildCommandRegistry([]);
      const resolution = resolveSlashIntent(input, commands);
      if (resolution.kind === "plain_text") {
        return { status: "failed", message: "Plain text belongs to the conversation, not command routing." };
      }
      if (resolution.kind !== "ready") {
        return { status: "failed", message: resolution.message };
      }
      const command = commandName(resolution.command);
      if (command === "ajuda") {
        return { status: "completed", message: "Comandos: /ajuda · /projetos · /project <id> · /project.files · /settings · /insight · /activity" };
      }
      if (command === "activity") {
        setState((current) => ({
          ...current,
          activeVisual: current.activeVisual === "activity" ? "presence" : "activity"
        }));
        return { status: "completed", message: "Activity surface toggled." };
      }
      if (command === "insight") {
        setState((current) => ({ ...current, settingsOpen: true, settingsSection: "insight" }));
        if (state.insightReport === null) {
          void loadInsight();
        }
        if (state.settingsSnapshot === null) {
          void loadSettings();
        }
        return { status: "completed", message: "Settings Insight opened." };
      }
      if (command === "settings") {
        setState((current) => ({ ...current, settingsOpen: true }));
        if (state.settingsSnapshot === null) {
          void loadSettings();
        }
        return { status: "completed", message: "Settings opened." };
      }
      if (command === "project.files") {
        setState((current) => ({
          ...current,
          historyPanelOpen: true,
          librarySection: "files",
          projectFilesOpen: true
        }));
        void loadProjectFiles();
        return { status: "completed", message: "Library opened on Project Files without running retrieval." };
      }
      if (command === "projects") {
        setState((current) => ({ ...current, workspaceOpen: true, workspaceShowProjects: true }));
        if (state.workspaceStatus !== "ready") void loadWorkspace();
        return { status: "completed", message: "Projects listed in Workspace." };
      }
      if (command === "project") {
        const projectId = resolution.args.project_id;
        await client.project(projectId);
        const opened = await client.openConversation({
          workspace_id: workspaceId,
          project_id: projectId,
          session_id: state.bootstrap?.session_id ?? null,
          history_limit: historyPageSize
        });
        setState((current) => ({
          ...current,
          bootstrap: current.bootstrap ? { ...current.bootstrap, project_id: projectId } : current.bootstrap,
          conversation: opened.conversation,
          messages: opened.messages,
          pagination: opened.pagination,
          summary: opened.summary,
          conversationStatus: "idle",
          conversationError: null,
          streamText: "",
          activityGraph: createEmptyActivityState(projectId),
          selectedActivityNodeId: null,
          projectFiles: null,
          projectFilesStatus: current.projectFilesOpen ? "idle" : current.projectFilesStatus,
          backendState: opened.degraded.length > 0 ? "degraded" : "ready"
        }));
        return { status: "completed", message: `Project switched to ${projectId}.` };
      }
      return { status: "failed", message: `/${command} is not executable from this surface.` };
    },
    [
      client,
      loadInsight,
      loadProjectFiles,
      loadSettings,
      loadWorkspace,
      setState,
      state.bootstrap?.session_id,
      state.commands,
      state.insightReport,
      state.settingsSnapshot,
      state.workspaceStatus
    ]
  );

  const launchSwarmDemo = useCallback(() => {
    const names = ["Artemis", "Orion", "Nyx", "Gaia", "Helios", "Echo"];
    const demoAgents = names.slice(1).map((name, index) => ({
      agent_id: `demo-agent-${index + 2}`,
      display_name: name,
      preferred_model: "modelo simulado"
    }));
    const events = demoAgents.flatMap((agent, index) => [
      { agent_id: agent.agent_id, event_type: "task.started", timestamp: new Date().toISOString(), status: "running" },
      { agent_id: agent.agent_id, event_type: ["research.started", "analysis.started", "validation.started", "tests.started", "documentation.started"][index], timestamp: new Date().toISOString(), status: "running" }
    ]);
    setState((current) => ({
      ...current,
      settingsOpen: false,
      workspaceOpen: true,
      workspaceDemoActive: true,
      workspaceSwarms: [{ swarm_id: "demo-swarm", mission_id: "workspace-demo", status: "running", strategy: "simulação" }],
      selectedSwarmId: "demo-swarm",
      swarmDetail: { swarm_id: "demo-swarm", status: "running", member_agent_ids: demoAgents.map((agent) => agent.agent_id) },
      swarmAgents: demoAgents,
      swarmTrace: { events },
      swarmResult: null,
      workspaceStatus: "ready",
      workspaceError: null
    }));
  }, [setState]);

  const reindexProjectFile = useCallback(
    async (documentId: string) => {
      setState((current) => ({ ...current, projectFilesBusyDocumentId: documentId, projectFilesError: null }));
      try {
        await client.reindexProjectKnowledgeDocument(documentId, workspaceId);
        await loadProjectFiles();
      } catch (error) {
        setState((current) => ({
          ...current,
          projectFilesStatus: current.projectFiles ? "degraded" : "error",
          projectFilesError: readableError(error)
        }));
      } finally {
        setState((current) => ({ ...current, projectFilesBusyDocumentId: null }));
      }
    },
    [client, loadProjectFiles, setState]
  );

  const removeProjectFile = useCallback(
    async (documentId: string, displayName: string) => {
      const confirmed = window.confirm(`Remove "${displayName}" from project retrieval?`);
      if (!confirmed) {
        return;
      }
      setState((current) => ({ ...current, projectFilesBusyDocumentId: documentId, projectFilesError: null }));
      try {
        await client.removeProjectKnowledgeDocument(documentId, workspaceId);
        await loadProjectFiles();
      } catch (error) {
        setState((current) => ({
          ...current,
          projectFilesStatus: current.projectFiles ? "degraded" : "error",
          projectFilesError: readableError(error)
        }));
      } finally {
        setState((current) => ({ ...current, projectFilesBusyDocumentId: null }));
      }
    },
    [client, loadProjectFiles, setState]
  );

  useEffect(() => {
    if (state.projectFilesOpen) {
      void loadProjectFiles();
    }
  }, [loadProjectFiles, state.bootstrap?.project_id, state.projectFilesOpen]);

  const loadNotifications = useCallback(
    async () => {
      setState((current) => ({
        ...current,
        notificationsStatus: "loading",
        notificationError: null
      }));
      try {
        const notifications = await client.notifications();
        setState((current) => ({
          ...current,
          notifications,
          notificationsStatus: notifications.length > 0 ? "ready" : "empty",
          notificationError: null,
          selectedNotificationIndex: Math.min(current.selectedNotificationIndex, Math.max(0, notifications.length - 1))
        }));
      } catch (error) {
        setState((current) => ({
          ...current,
          notificationsStatus: current.notifications.length > 0 ? "degraded" : "error",
          notificationError: readableError(error)
        }));
      }
    },
    [client, setState]
  );

  const toggleNotifications = useCallback(
    () => {
      setState((current) => ({ ...current, notificationsOpen: !current.notificationsOpen }));
      if (!state.notificationsOpen && state.notificationsStatus === "idle") {
        void loadNotifications();
      }
    },
    [loadNotifications, setState, state.notificationsOpen, state.notificationsStatus]
  );

  const markNotificationRead = useCallback(
    async (notificationId: string) => {
      try {
        const notification = await client.markNotificationRead(notificationId);
        setState((current) => ({
          ...current,
          notifications: current.notifications.map((item) => item.id === notification.id ? notification : item),
          notificationError: null
        }));
      } catch (error) {
        setState((current) => ({ ...current, notificationsStatus: "degraded", notificationError: readableError(error) }));
      }
    },
    [client, setState]
  );

  const dismissNotification = useCallback(
    async (notificationId: string) => {
      try {
        await client.dismissNotification(notificationId);
        setState((current) => {
          const notifications = current.notifications.filter((item) => item.id !== notificationId);
          return {
            ...current,
            notifications,
            notificationsStatus: notifications.length > 0 ? "ready" : "empty",
            selectedNotificationIndex: Math.min(current.selectedNotificationIndex, Math.max(0, notifications.length - 1)),
            notificationError: null
          };
        });
      } catch (error) {
        setState((current) => ({ ...current, notificationsStatus: "degraded", notificationError: readableError(error) }));
      }
    },
    [client, setState]
  );

  const moveNotificationSelection = useCallback(
    (delta: number) => {
      setState((current) => {
        if (current.notifications.length === 0) {
          return current;
        }
        const next = (current.selectedNotificationIndex + delta + current.notifications.length) % current.notifications.length;
        return { ...current, selectedNotificationIndex: next };
      });
    },
    [setState]
  );

  useEffect(() => {
    if (!state.notificationsOpen) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setState((current) => ({ ...current, notificationsOpen: false }));
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [setState, state.notificationsOpen]);

  useEffect(() => {
    activityCursorRef.current = state.activityGraph.cursor;
  }, [state.activityGraph.cursor]);

  useEffect(() => {
    if (state.activeVisual !== "activity") {
      return;
    }
    // Conversation activity is the authoritative scope for the active turn;
    // project scope may contain no runtime entities and hides the live graph.
    const projectId = state.conversation?.conversation_id
      ? `conversation:${state.conversation.conversation_id}`
      : state.bootstrap?.project_id ?? null;
    if (!projectId) {
      setState((current) => ({ ...current, activityGraph: createEmptyActivityState(null) }));
      return;
    }
    const activityProjectId = projectId;
    let cancelled = false;
    let stream: EventSource | null = null;
    async function connectActivity(): Promise<void> {
      try {
        const snapshot = await client.activitySnapshot(activityProjectId);
        if (cancelled) return;
        setState((current) => ({
          ...current,
          activityGraph: applyActivitySnapshot(current.activityGraph, snapshot, current.activityGraph.cursor)
        }));
        stream = openActivityStream(client.activityStreamUrl(activityProjectId, null), {
          onSnapshot: (nextSnapshot, cursor) => {
            setState((current) => ({
              ...current,
              activityGraph: applyActivitySnapshot(current.activityGraph, nextSnapshot, cursor)
            }));
          },
          onActivity: (event, cursor) => {
            setState((current) => ({
              ...current,
              activityGraph: applyActivityEvent(current.activityGraph, event, cursor)
            }));
          },
          onResync: (nextSnapshot, cursor) => {
            setState((current) => ({
              ...current,
              activityGraph: applyActivitySnapshot(current.activityGraph, nextSnapshot, cursor, true)
            }));
          },
          onError: () => {
            setState((current) => ({
              ...current,
              activityGraph: markActivityDisconnected(current.activityGraph)
            }));
          }
        });
      } catch (error) {
        setState((current) => ({
          ...current,
          activityGraph: markActivityDisconnected(current.activityGraph),
          error: readableError(error)
        }));
      }
    }
    void connectActivity();
    return () => {
      cancelled = true;
      stream?.close();
    };
  }, [client, setState, state.activeVisual, state.bootstrap?.project_id, state.conversation?.conversation_id]);

  useEffect(() => {
    if (state.activeVisual !== "activity") {
      return;
    }
    let cancelled = false;
    let timer: number | null = null;
    async function refreshModelTelemetry(): Promise<void> {
      try {
        const model = primaryModelOption(state.bootstrap?.provider_model_options ?? []);
        const status = model?.provider_id === "synapse_local"
          ? await client.synapseLocalStatus(model.model_id)
          : await client.lmstudioStatus();
        if (cancelled) return;
        setState((current) => ({
          ...current,
          modelTelemetry: formatModelTelemetry(status.telemetry?.recent ?? [])
        }));
      } catch (error) {
        if (!cancelled) {
          setState((current) => ({
            ...current,
            modelTelemetry: [`Unable to read model log: ${readableError(error)}`]
          }));
        }
      }
    }
    void refreshModelTelemetry();
    timer = window.setInterval(() => void refreshModelTelemetry(), 1600);
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [client, setState, state.activeVisual, state.bootstrap?.provider_model_options]);

  const presenceScene = derivePresenceState({
    backendState: state.backendState,
    conversationStatus: state.conversationStatus,
    manualVoiceState: state.manualVoiceState,
    conversationModeState: state.conversationModeState,
    audioAmplitude: state.presenceAmplitude,
    reducedMotion: state.reducedMotion,
    focused: state.focused
  });
  const activityScene = deriveActivityScene(withBaselineActivityState(
    state.activityGraph,
    state.bootstrap?.primary_agent ?? null,
    primaryModelOption(state.bootstrap?.provider_model_options ?? [])
  ), {
    selectedNodeId: state.selectedActivityNodeId,
    reducedMotion: state.reducedMotion,
    focused: state.focused,
    modelTelemetry: state.modelTelemetry
  });

  return (
    <Frame
      settingsClient={client}
      state={state}
      presenceScene={presenceScene}
      activeVisual={state.activeVisual}
      onToggleActivity={() => setState((current) => ({
        ...current,
        activeVisual: current.activeVisual === "activity" ? "presence" : "activity"
      }))}
      onToggleWorkspace={() => {
        setState((current) => ({ ...current, workspaceOpen: !current.workspaceOpen }));
        if (!state.workspaceOpen) void loadWorkspace();
      }}
      onCloseWorkspace={() => setState((current) => ({ ...current, workspaceOpen: false }))}
      onRefreshWorkspace={() => void loadWorkspace()}
      onSelectWorkspaceProject={(projectId) => void executeCommand(`/project ${projectId}`)}
      onOpenWorkspaceFiles={() => {
        setState((current) => ({ ...current, historyPanelOpen: true, librarySection: "files", projectFilesOpen: true }));
        void loadProjectFiles();
      }}
      onSubmitWork={(request) => void sendMessage(request, [], "workspace")}
      onResolveSwarmConfirmation={(action) => void resolveSwarmConfirmation(action)}
      onExecuteWorkspaceCommand={async (request) => {
        const result = await executeCommand(request);
        setState((current) => ({
          ...current,
          workspaceCommandOutput: [...current.workspaceCommandOutput, { input: request, output: result.message ?? result.status }].slice(-100)
        }));
        return result;
      }}
      onLaunchSwarmDemo={launchSwarmDemo}
      onSwarmAction={async (swarmId, action) => {
        try {
          await client.swarmAction(swarmId, action);
          await loadWorkspace();
        } catch (error) {
          setState((current) => ({ ...current, workspaceError: readableError(error) }));
        }
      }}
      selectedSwarmId={state.selectedSwarmId}
      swarmDetail={state.swarmDetail}
      swarmTrace={state.swarmTrace}
      onSelectSwarm={(swarmId) => void selectWorkspaceSwarm(swarmId)}
      swarmAgents={state.swarmAgents}
      swarmTools={state.swarmTools}
      swarmResult={state.swarmResult}
      onRefreshInsight={() => void loadInsight()}
      onToggleSettings={toggleSettings}
      onToggleHistory={() => {
        setState((current) => ({
          ...current,
          historyPanelOpen: !current.historyPanelOpen,
          librarySection: "history"
        }));
        if (!state.historyPanelOpen) {
          void refreshConversationIndex();
        }
      }}
      onCloseHistory={() => setState((current) => ({ ...current, historyPanelOpen: false, projectFilesOpen: false }))}
      onSelectLibrarySection={(section) => {
        setState((current) => ({
          ...current,
          historyPanelOpen: true,
          librarySection: section,
          projectFilesOpen: section === "files"
        }));
        if (section === "history") {
          void refreshConversationIndex();
        }
        if (section === "files") {
          void loadProjectFiles();
        }
      }}
      onRefreshHistory={() => void refreshConversationIndex()}
      onOpenConversation={(conversationId) => void openConversationFromHistory(conversationId)}
      onDeleteConversation={(conversationId) => void deleteConversationFromHistory(conversationId)}
      onClearConversationHistory={() => void clearConversationHistory()}
      onNewConversation={() => void openNewConversation()}
      onCloseSettings={() => setState((current) => ({ ...current, settingsOpen: false }))}
      onSelectSettingsSection={(section) => setState((current) => ({ ...current, settingsSection: section }))}
      onRefreshSettings={() => void loadSettings()}
      onSaveSettings={(changes) => void saveSettings(changes)}
      onPreviewFrontendSettings={previewFrontendSettings}
      onToggleNotifications={toggleNotifications}
      onCloseNotifications={() => setState((current) => ({ ...current, notificationsOpen: false }))}
      onRefreshNotifications={() => void loadNotifications()}
      onMarkNotificationRead={(notificationId) => void markNotificationRead(notificationId)}
      onDismissNotification={(notificationId) => void dismissNotification(notificationId)}
      onMoveNotificationSelection={moveNotificationSelection}
      onRefreshProjectFiles={() => void loadProjectFiles()}
      onReindexProjectFile={(documentId) => void reindexProjectFile(documentId)}
      onRemoveProjectFile={(documentId, displayName) => void removeProjectFile(documentId, displayName)}
      onToggleLog={() => setState((current) => ({ ...current, logMinimized: !current.logMinimized }))}
      onLoadOlderHistory={() => void loadOlderHistory()}
      onRecoverConversation={() => void recoverConversation()}
      main={
        <main className={`main-area ${state.logMinimized ? "log-closed" : "log-open"}`} aria-label="Main area">
          <div className={`visual-stage ${state.activeVisual} ${state.logMinimized ? "log-closed" : "log-open"}`}>
            <VisualErrorBoundary surface={state.activeVisual}>
              <Suspense fallback={<VisualLoadingFallback label={`Loading ${state.activeVisual}`} />}>
                <Presence scene={presenceScene} theme={state.frontendSettings.theme} reducedMotion={state.reducedMotion} focused={state.focused} />
              </Suspense>
            </VisualErrorBoundary>
          </div>
          <Composer
            client={client}
            onSend={sendMessage}
            onCancel={cancelTurn}
            commands={state.commands}
            commandError={state.commandError}
            onDiscoverCommands={loadCommands}
            onExecuteCommand={executeCommand}
            onStageAttachment={stageAttachment}
            onTranscribeVoice={transcribeVoice}
            onConversationVoiceTurn={runVoiceConversationTurn}
            onPresenceChange={updatePresenceFacts}
            disabled={
              !state.conversation ||
              state.backendState === "disconnected" ||
              state.conversationStatus === "sending" ||
              state.conversationStatus === "streaming"
            }
            canCancel={Boolean(state.activeTurnKey) && state.conversationStatus === "streaming"}
            failedDraft={state.conversationError?.retryable && state.conversationError.code !== "generation_failed" ? state.lastDraft : ""}
          />
        </main>
      }
    />
  );
}

function Frame({
  settingsClient,
  state,
  presenceScene,
  main,
  activeVisual,
  onToggleActivity,
  onToggleWorkspace,
  onCloseWorkspace,
  onRefreshWorkspace,
  onSelectWorkspaceProject,
  onOpenWorkspaceFiles,
  onSubmitWork,
  onResolveSwarmConfirmation,
  onExecuteWorkspaceCommand,
  onLaunchSwarmDemo,
  onSwarmAction,
  selectedSwarmId,
  swarmDetail,
  swarmTrace,
  onSelectSwarm,
  swarmAgents,
  swarmTools,
  swarmResult,
  onRefreshInsight,
  onToggleSettings,
  onToggleHistory = () => undefined,
  onCloseHistory = () => undefined,
  onSelectLibrarySection = () => undefined,
  onRefreshHistory = () => undefined,
  onOpenConversation = () => undefined,
  onDeleteConversation = () => undefined,
  onClearConversationHistory = () => undefined,
  onNewConversation = () => undefined,
  onCloseSettings,
  onSelectSettingsSection,
  onRefreshSettings,
  onSaveSettings,
  onPreviewFrontendSettings,
  onToggleNotifications = () => undefined,
  onCloseNotifications = () => undefined,
  onRefreshNotifications = () => undefined,
  onMarkNotificationRead = () => undefined,
  onDismissNotification = () => undefined,
  onMoveNotificationSelection = () => undefined,
  onRefreshProjectFiles = () => undefined,
  onReindexProjectFile = () => undefined,
  onRemoveProjectFile = () => undefined,
  onToggleLog,
  onLoadOlderHistory,
  onRecoverConversation
}: {
  settingsClient?: SynapseFrontendClient;
  state: AppState;
    presenceScene?: PresenceSceneState;
  main: React.ReactNode;
  activeVisual: "presence" | "activity";
  onToggleActivity: () => void;
  onToggleWorkspace: () => void;
  onCloseWorkspace: () => void;
  onRefreshWorkspace: () => void;
  onSelectWorkspaceProject: (projectId: string) => void;
  onOpenWorkspaceFiles: () => void;
  onSubmitWork: (request: string) => void;
  onResolveSwarmConfirmation: (action: SwarmConfirmationAction) => void;
  onExecuteWorkspaceCommand: (request: string) => Promise<{ status: string; message?: string }>;
  onLaunchSwarmDemo: () => void;
  onSwarmAction: (swarmId: string, action: "start" | "pause" | "resume" | "cancel") => void;
  selectedSwarmId: string | null;
  swarmDetail: Record<string, unknown> | null;
  swarmTrace: Record<string, unknown> | null;
  onSelectSwarm: (swarmId: string) => void;
  swarmAgents: Array<Record<string, unknown>>;
  swarmTools: Record<string, string[]>;
  swarmResult: Record<string, unknown> | null;
  onRefreshInsight: () => void;
  onToggleSettings: () => void;
  onToggleHistory?: () => void;
  onCloseHistory?: () => void;
  onSelectLibrarySection?: (section: LibrarySection) => void;
  onRefreshHistory?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onDeleteConversation?: (conversationId: string) => void;
  onClearConversationHistory?: () => void;
  onNewConversation?: () => void;
  onCloseSettings: () => void;
  onSelectSettingsSection: (section: SettingsSection) => void;
  onRefreshSettings: () => void;
  onSaveSettings: (changes: SettingsChanges) => void;
  onPreviewFrontendSettings: (preferences: FrontendSettingsPreferences) => void;
  onToggleNotifications?: () => void;
  onCloseNotifications?: () => void;
  onRefreshNotifications?: () => void;
  onMarkNotificationRead?: (notificationId: string) => void;
  onDismissNotification?: (notificationId: string) => void;
  onMoveNotificationSelection?: (delta: number) => void;
  onRefreshProjectFiles?: () => void;
  onReindexProjectFile?: (documentId: string) => void;
  onRemoveProjectFile?: (documentId: string, displayName: string) => void;
  onToggleLog: () => void;
  onLoadOlderHistory: () => void;
  onRecoverConversation: () => void;
}): React.ReactElement {
  const resolvedPresenceScene = presenceScene ?? derivePresenceState({
    backendState: state.backendState,
    conversationStatus: state.conversationStatus,
    manualVoiceState: state.manualVoiceState,
    conversationModeState: state.conversationModeState,
    audioAmplitude: state.presenceAmplitude,
    reducedMotion: state.reducedMotion,
    focused: state.focused
  });
  const shellIcons = assetsForTheme(state.frontendSettings.theme);
  return (
    <div className={`app-shell ${state.logMinimized ? "log-minimized" : ""}`}>
      <TitleBar
        state={state.backendState}
        theme={state.frontendSettings.theme}
        notificationsOpen={state.notificationsOpen}
        unreadNotifications={state.notifications.filter((notification) => !notification.read).length}
        onToggleNotifications={onToggleNotifications}
      />
      <aside className="side-rail" aria-label="Primary navigation">
        <button
          className={`shell-nav-button workspace-button ${state.workspaceOpen ? "active" : ""}`}
          title={state.workspaceOpen ? "Fechar Workspace" : "Abrir Workspace"}
          aria-pressed={state.workspaceOpen}
          onClick={onToggleWorkspace}
        >
          <span className="shell-nav-icon-frame workspace-nav-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" role="img">
              <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
              <path d="M3.5 8.5h17M7 12l2 2-2 2M11.5 16H17" />
            </svg>
          </span>
        </button>
        <button
          className={`shell-nav-button history-button ${state.historyPanelOpen ? "active" : ""}`}
          title={state.historyPanelOpen ? "Close Library" : "Open Library"}
          aria-pressed={state.historyPanelOpen}
          onClick={onToggleHistory}
        >
          <span className="shell-nav-icon-frame" aria-hidden="true">
            <img
              className="shell-nav-icon shell-nav-icon--history"
              src={shellIcons.navigation.history}
              alt=""
              style={shellIconStyle("history")}
            />
          </span>
        </button>
        <button
          className={`shell-nav-button settings-button ${state.settingsOpen ? "active" : ""}`}
          title={state.settingsOpen ? "Close Settings" : "Open Settings"}
          aria-pressed={state.settingsOpen}
          onClick={onToggleSettings}
        >
          <span className="shell-nav-icon-frame" aria-hidden="true">
            <img
              className="shell-nav-icon shell-nav-icon--settings"
              src={shellIcons.navigation.settings}
              alt=""
              style={shellIconStyle("settings")}
            />
          </span>
        </button>
      </aside>
      <section className="center-surface">
        {state.frontendSettings.theme === "synapse" ? (
          <Suspense fallback={null}>
            <SynapseCoreAtmosphere
              active
              reducedMotion={state.reducedMotion}
              focused={state.focused}
              state={resolvedPresenceScene.state}
              amplitude={resolvedPresenceScene.amplitude}
            />
          </Suspense>
        ) : null}
        {main}
      </section>
      <ConversationLog
        conversationId={state.conversation?.conversation_id ?? null}
        messages={state.messages}
        streamText={state.streamText}
        pagination={state.pagination}
        summary={state.summary}
        runtimeStatus={state.conversationStatus}
        runtimeError={state.conversationError}
        minimized={state.logMinimized}
        onToggle={onToggleLog}
        onLoadOlder={onLoadOlderHistory}
        onRecover={onRecoverConversation}
        onNewConversation={onNewConversation}
        primaryAgentName={state.bootstrap?.primary_agent?.name ?? "Synapse"}
        swarmConfirmation={state.swarmConfirmation}
        swarmConfirmationBusy={state.swarmConfirmationBusy}
        onResolveSwarmConfirmation={onResolveSwarmConfirmation}
      />
      {state.historyPanelOpen ? (
        <LibraryPanel
          activeSection={state.librarySection}
          historyStatus={state.historyStatus}
          conversations={state.conversationIndex}
          activeConversationId={state.conversation?.conversation_id ?? null}
          historyError={state.historyError}
          projectId={state.bootstrap?.project_id ?? null}
          projectFilesStatus={state.projectFilesStatus}
          projectFiles={state.projectFiles}
          projectFilesError={state.projectFilesError}
          projectFilesBusyDocumentId={state.projectFilesBusyDocumentId}
          onClose={onCloseHistory}
          onSelectSection={onSelectLibrarySection}
          onRefreshHistory={onRefreshHistory}
          onOpenConversation={onOpenConversation}
          onDeleteConversation={onDeleteConversation}
          onClearConversationHistory={onClearConversationHistory}
          onRefreshProjectFiles={onRefreshProjectFiles}
          onReindex={onReindexProjectFile}
          onRemove={onRemoveProjectFile}
        />
      ) : null}
      {state.workspaceOpen ? (
        <WorkspacePanel
          projects={state.workspaceProjects}
          showProjects={state.workspaceShowProjects}
          swarms={state.workspaceSwarms}
          activeProjectId={state.bootstrap?.project_id ?? null}
          loading={state.workspaceStatus === "loading"}
          error={state.workspaceError}
          onClose={onCloseWorkspace}
          onRefresh={onRefreshWorkspace}
          onSelectProject={onSelectWorkspaceProject}
          onOpenFiles={onOpenWorkspaceFiles}
          onSwarmAction={onSwarmAction}
          selectedSwarmId={selectedSwarmId}
          swarmDetail={swarmDetail}
          swarmTrace={swarmTrace}
          onSelectSwarm={onSelectSwarm}
          swarmAgents={swarmAgents}
          swarmTools={swarmTools}
          swarmResult={swarmResult}
          demoActive={state.workspaceDemoActive}
          onSubmitWork={onSubmitWork}
          onExecuteCommand={onExecuteWorkspaceCommand}
          commandOutput={state.workspaceCommandOutput}
          agentName={state.bootstrap?.primary_agent?.name ?? "Primary Agent"}
          primaryAgentId={state.bootstrap?.primary_agent?.agent_id ?? null}
          modelName={primaryModelOption(state.bootstrap?.provider_model_options ?? [])?.model_id ?? ""}
          swarmConfirmation={state.swarmConfirmation}
          swarmConfirmationBusy={state.swarmConfirmationBusy}
          onResolveSwarmConfirmation={onResolveSwarmConfirmation}
          commands={state.commands.length > 0 ? state.commands : buildCommandRegistry([])}
        />
      ) : null}
      {state.settingsOpen ? (
        <SettingsPanel
          client={settingsClient}
          status={state.settingsStatus}
          snapshot={state.settingsSnapshot}
          frontendSettings={state.frontendSettings}
          error={state.settingsError}
          activeSection={state.settingsSection}
          primaryAgent={state.bootstrap?.primary_agent ?? null}
          insightStatus={state.insightStatus}
          insightReport={state.insightReport}
          insightError={state.insightError}
          onClose={onCloseSettings}
          onSelectSection={onSelectSettingsSection}
          onRefresh={onRefreshSettings}
          onRefreshInsight={onRefreshInsight}
          onSave={onSaveSettings}
          onPreviewFrontendSettings={onPreviewFrontendSettings}
          onLaunchSwarmDemo={onLaunchSwarmDemo}
        />
      ) : null}
      {state.notificationsOpen ? (
        <NotificationsPanel
          status={state.notificationsStatus}
          notifications={state.notifications}
          error={state.notificationError}
          selectedIndex={state.selectedNotificationIndex}
          onClose={onCloseNotifications}
          onRefresh={onRefreshNotifications}
          onMarkRead={onMarkNotificationRead}
          onDismiss={onDismissNotification}
          onMoveSelection={onMoveNotificationSelection}
        />
      ) : null}
      {state.error ? <div className="state-banner" role="status">{state.error}</div> : null}
    </div>
  );
}

function InsightContent({ report }: { report: InsightReport }): React.ReactElement {
  const recommendations = report.models.recommendations;
  const grouped = groupRecommendations(recommendations);
  return (
    <div className="insight-content">
      <section className="insight-card">
        <h3>Hardware</h3>
        <dl>
          <div><dt>CPU</dt><dd>{report.hardware.cpu.model}</dd></div>
          <div><dt>Threads</dt><dd>{report.hardware.cpu.logical_threads}</dd></div>
          <div><dt>RAM</dt><dd>{formatBytes(report.hardware.memory.available_bytes)} available / {formatBytes(report.hardware.memory.total_bytes)} total</dd></div>
          <div><dt>Provider</dt><dd>{report.hardware.provider}</dd></div>
        </dl>
        {report.hardware.gpus.length > 0 ? (
          <div className="insight-list">
            {report.hardware.gpus.map((gpu) => (
              <article key={`${gpu.provider}:${gpu.name}`}>
                <strong>{gpu.name}</strong>
                <span>{gpu.vendor} · {gpu.provider}</span>
                <small>VRAM {formatBytes(gpu.memory_free_bytes)} free / {formatBytes(gpu.memory_total_bytes)} total</small>
                {gpu.capabilities.length > 0 ? <small>{gpu.capabilities.join(" · ")}</small> : null}
                {gpu.limitations.map((item) => <small key={item} className="warning">{item}</small>)}
              </article>
            ))}
          </div>
        ) : <p className="muted">No GPU reported by backend hardware discovery.</p>}
      </section>
      <section className="insight-card">
        <h3>Local AI</h3>
        <p className="muted">Recommendations are backend decisions, not installation claims. Installed/local availability is shown only when reported by provider/model facts.</p>
        <dl>
          <div><dt>Available models</dt><dd>{report.models.available_models}</dd></div>
          <div><dt>Online providers</dt><dd>{report.models.online_providers}</dd></div>
          <div><dt>Checked</dt><dd>{report.models.checked_at}</dd></div>
        </dl>
        <div className="provider-grid">
          {report.providers.map((provider, index) => (
            <span key={providerKey(provider, index)}>{providerLabel(provider)}</span>
          ))}
        </div>
      </section>
      <RecommendationGroup title="Recommended" items={grouped.recommended} />
      <RecommendationGroup title="Possible with limitations" items={grouped.limited} />
      <RecommendationGroup title="Not recommended locally" items={grouped.notRecommended} />
      {report.diagnostics.findings.length > 0 ? (
        <section className="insight-card diagnostics">
          <h3>Diagnostics</h3>
          {report.diagnostics.findings.map((finding) => (
            <article key={finding.code}>
              <strong>{finding.severity}: {finding.summary}</strong>
              {finding.recommendation ? <small>{finding.recommendation}</small> : null}
            </article>
          ))}
        </section>
      ) : null}
      {[...report.limitations, ...report.hardware.limitations, ...report.models.limitations].map((item) => (
        <p key={item} className="insight-state degraded">{item}</p>
      ))}
    </div>
  );
}

function RecommendationGroup({ title, items }: { title: string; items: InsightReport["models"]["recommendations"] }): React.ReactElement {
  return (
    <section className="insight-card recommendations">
      <h3>{title}</h3>
      {items.length === 0 ? <p className="muted">No backend recommendation in this group.</p> : null}
      {items.map((item) => (
        <article key={`${item.task}:${item.provider_id}:${item.model_id}:${item.status}`}>
          <strong>{item.model_id ?? "No model selected"}</strong>
          <span>{item.task} · {item.status}{item.provider_id ? ` · ${item.provider_id}` : ""}{recommendationSource(item)}</span>
          <p>{item.reason}</p>
          <small>{modelFootprint(item)}</small>
          {item.evidence.slice(0, 3).map((evidence) => (
            <small key={`${evidence.source}:${evidence.metric}`}>{evidence.metric}: {String(evidence.value)}{evidence.unit ? ` ${evidence.unit}` : ""}</small>
          ))}
        </article>
      ))}
    </section>
  );
}

function ProjectFilesPanel({
  projectId,
  status,
  data,
  error,
  busyDocumentId,
  onClose,
  onRefresh,
  onReindex,
  onRemove,
  embedded = false
}: {
  projectId: string | null;
  status: AppState["projectFilesStatus"];
  data: ProjectKnowledgeDocumentsResult | null;
  error: string | null;
  busyDocumentId: string | null;
  onClose: () => void;
  onRefresh: () => void;
  onReindex: (documentId: string) => void;
  onRemove: (documentId: string, displayName: string) => void;
  embedded?: boolean;
}): React.ReactElement {
  const documents = data?.documents ?? [];
  const learned = data?.capabilities.learned_semantic ?? null;
  const lexicalAvailable = data?.capabilities.lexical.available ?? false;
  const learnedStatus = learned?.status ?? "unconfigured";

  function onKeyDown(event: React.KeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  }

  return (
    <section
      className={`project-files-panel ${status} ${embedded ? "embedded" : ""}`}
      aria-label="Project Files"
      role={embedded ? "region" : "dialog"}
      aria-modal={embedded ? undefined : "false"}
      onKeyDown={onKeyDown}
      tabIndex={-1}
    >
      {!embedded ? (
        <header className="project-files-header">
          <div>
            <span>Arquivos do Projeto</span>
            <small>{projectId ? `Projeto ${projectId}` : "Nenhum projeto ativo"}</small>
          </div>
          <div className="project-files-actions">
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText("/project ")}
              title="Copiar comando /project para o chat"
            >
              /project
            </button>
            <button type="button" onClick={onRefresh} disabled={status === "loading" || !projectId}>Refresh</button>
            <button type="button" aria-label="Close Project Files" onClick={onClose}>×</button>
          </div>
        </header>
      ) : null}
      <div className="project-files-capabilities" aria-label="Project Knowledge capability status">
        <span className={lexicalAvailable ? "available" : "unavailable"}>
          Busca lexical: {lexicalAvailable ? "disponível" : "indisponível"}
        </span>
        <span className={semanticCapabilityClass(learnedStatus)}>
          Busca semântica local: {semanticStatusLabel(learnedStatus)}
        </span>
        {learnedStatus !== "available" && learnedStatus !== "ready" ? (
          <small>Fallback lexical continua disponível quando factual.</small>
        ) : null}
      </div>
      {status === "loading" ? <p className="project-files-state">Carregando fatos dos documentos…</p> : null}
      {!projectId ? <p className="project-files-state empty">Selecione um projeto com /project &lt;project_id&gt; antes de administrar arquivos.</p> : null}
      {error ? <p className="project-files-state error">{error}</p> : null}
      {status === "degraded" ? <p className="project-files-state degraded">Mostrando último estado conhecido. Refresh falhou.</p> : null}
      {projectId && documents.length === 0 && status !== "loading" ? (
        <p className="project-files-state empty">Nenhum documento indexável registrado para este projeto.</p>
      ) : null}
      {documents.length > 0 ? (
        <div className="project-files-list" role="list" aria-label="Project indexed documents">
          {documents.map((record) => (
            <ProjectFileItem
              key={record.document.document_id}
              record={record}
              busy={busyDocumentId === record.document.document_id}
              onReindex={onReindex}
              onRemove={onRemove}
            />
          ))}
        </div>
      ) : null}
      <footer className="project-files-policy">
        Abrir/listar arquivos não executa retrieval nem gera embedding de query.
      </footer>
    </section>
  );
}

function ProjectFileItem({
  record,
  busy,
  onReindex,
  onRemove
}: {
  record: ProjectKnowledgeDocumentRecord;
  busy: boolean;
  onReindex: (documentId: string) => void;
  onRemove: (documentId: string, displayName: string) => void;
}): React.ReactElement {
  const document = record.document;
  const version = record.version;
  const status = version?.status ?? document.status;
  const chunkCount = typeof record.facts.chunk_count === "number" ? record.facts.chunk_count : version?.chunk_count ?? 0;
  const indexed = record.facts.document_indexed === true;
  const updatedAt = version?.completed_at ?? version?.started_at ?? version?.queued_at ?? document.created_at;
  const failure = version?.failure_message ?? (typeof record.facts.failure_message === "string" ? record.facts.failure_message : null);
  const type = documentTypeLabel(document.display_name);
  const removable = status !== "removed";
  const activeOperation = busy || status === "queued" || status === "reading" || status === "chunking" || status === "indexing";

  return (
    <article className={`project-file-item ${status}`} role="listitem">
      <div className="project-file-main">
        <div>
          <strong>{document.display_name}</strong>
          <small>{type} · versão {version ? shortVersion(version.version_id) : "indisponível"}</small>
        </div>
        <span className={`project-file-status ${status}`}>{statusLabel(status)}</span>
      </div>
      <dl className="project-file-facts">
        <div><dt>Retrieval</dt><dd>{indexed && status === "ready" ? "disponível" : "não disponível"}</dd></div>
        <div><dt>Chunks</dt><dd>{chunkCount}</dd></div>
        <div><dt>Atualizado</dt><dd>{formatDateTime(updatedAt)}</dd></div>
      </dl>
      {failure ? <p className="project-file-error">{failure}</p> : null}
      {version?.superseded_by ? <p className="project-file-note">Versão substituída por {shortVersion(version.superseded_by)}.</p> : null}
      {status === "removed" ? <p className="project-file-note">Removido do retrieval do projeto.</p> : null}
      <div className="project-file-actions">
        <button
          type="button"
          onClick={() => onReindex(document.document_id)}
          disabled={activeOperation || status === "removed"}
        >
          {busy ? "Processando…" : "Reindexar"}
        </button>
        <button
          type="button"
          className="danger"
          onClick={() => onRemove(document.document_id, document.display_name)}
          disabled={busy || !removable}
        >
          Remover
        </button>
      </div>
    </article>
  );
}

function semanticStatusLabel(status: string): string {
  switch (status) {
    case "available":
    case "ready":
      return "pronta";
    case "loading":
      return "carregando";
    case "unavailable":
      return "indisponível";
    case "incompatible":
      return "incompatível";
    case "failed":
      return "falhou";
    case "degraded":
      return "degradada";
    default:
      return "não configurada";
  }
}

function semanticCapabilityClass(status: string): string {
  return status === "available" || status === "ready" ? "available" : status === "loading" ? "loading" : "unavailable";
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ").toUpperCase();
}

function shortVersion(versionId: string): string {
  return versionId.length > 12 ? `${versionId.slice(0, 12)}…` : versionId;
}

function documentTypeLabel(name: string): string {
  const extension = name.includes(".") ? name.split(".").pop()?.toLowerCase() : "";
  return extension ? extension : "documento";
}

function NotificationsPanel({
  status,
  notifications,
  error,
  selectedIndex,
  onClose,
  onRefresh,
  onMarkRead,
  onDismiss,
  onMoveSelection
}: {
  status: AppState["notificationsStatus"];
  notifications: NotificationRecord[];
  error: string | null;
  selectedIndex: number;
  onClose: () => void;
  onRefresh: () => void;
  onMarkRead: (notificationId: string) => void;
  onDismiss: (notificationId: string) => void;
  onMoveSelection: (delta: number) => void;
}): React.ReactElement {
  const ordered = [...notifications].sort((a, b) => b.created_at.localeCompare(a.created_at));

  function onKeyDown(event: React.KeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      onMoveSelection(1);
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      onMoveSelection(-1);
    }
  }

  return (
    <section
      className={`notifications-panel ${status}`}
      aria-label="Notifications"
      role="dialog"
      aria-modal="false"
      onKeyDown={onKeyDown}
      tabIndex={-1}
    >
      <header className="notifications-header">
        <div>
          <span>Notifications</span>
          <small>{notificationStatusLabel(status, ordered)}</small>
        </div>
        <div className="notifications-actions">
          <button type="button" onClick={onRefresh} disabled={status === "loading"}>Refresh</button>
          <button type="button" aria-label="Close notifications" onClick={onClose}>×</button>
        </div>
      </header>
      {status === "loading" ? <p className="notifications-state">Loading backend notification facts…</p> : null}
      {status === "empty" ? <p className="notifications-state empty">No notifications need attention.</p> : null}
      {error ? <p className="notifications-state error">{error}</p> : null}
      {status === "degraded" ? <p className="notifications-state degraded">Showing last known notification facts. Refresh failed.</p> : null}
      {ordered.length > 0 ? (
        <div className="notifications-list" role="listbox" aria-label="Notification items">
          {ordered.map((notification, index) => (
            <article
              key={notification.id}
              className={`notification-item ${notification.read ? "read" : "unread"} ${notification.severity}`}
              role="option"
              aria-selected={index === selectedIndex}
              tabIndex={index === selectedIndex ? 0 : -1}
            >
              <div className="notification-item-head">
                <strong>{notification.title}</strong>
                <span>{notification.read ? "read" : "unread"}</span>
              </div>
              <p>{notification.message}</p>
              <small>{notification.category} · {notification.severity} · {notification.source} · {formatDateTime(notification.created_at)}</small>
              {notification.category === "approval" ? (
                <small className="approval-note">Approval required is factual here; resolving remains owned by the approvals flow.</small>
              ) : null}
              <div className="notification-item-actions">
                {!notification.read ? (
                  <button type="button" onClick={() => onMarkRead(notification.id)}>Mark read</button>
                ) : null}
                <button type="button" onClick={() => onDismiss(notification.id)}>Dismiss</button>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function LibraryPanel({
  activeSection,
  historyStatus,
  conversations,
  activeConversationId,
  historyError,
  projectId,
  projectFilesStatus,
  projectFiles,
  projectFilesError,
  projectFilesBusyDocumentId,
  onClose,
  onSelectSection,
  onRefreshHistory,
  onRefreshProjectFiles,
  onOpenConversation,
  onDeleteConversation,
  onClearConversationHistory,
  onReindex,
  onRemove
}: {
  activeSection: LibrarySection;
  historyStatus: AppState["historyStatus"];
  conversations: ConversationIndexItem[];
  activeConversationId: string | null;
  historyError: string | null;
  projectId: string | null;
  projectFilesStatus: AppState["projectFilesStatus"];
  projectFiles: ProjectKnowledgeDocumentsResult | null;
  projectFilesError: string | null;
  projectFilesBusyDocumentId: string | null;
  onClose: () => void;
  onSelectSection: (section: LibrarySection) => void;
  onRefreshHistory: () => void;
  onRefreshProjectFiles: () => void;
  onOpenConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
  onClearConversationHistory: () => void;
  onReindex: (documentId: string) => void;
  onRemove: (documentId: string, displayName: string) => void;
}): React.ReactElement {
  const visibleConversations = conversations.filter((item) => item.message_count > 0);
  const historySelected = activeSection === "history";
  return (
    <section className={`history-panel library-panel ${activeSection}`} aria-label="Library panel" role="dialog" aria-modal="false">
      <header className="history-header">
        <div>
          <span>Library</span>
          <small>{historySelected ? historyStatusLabel(historyStatus, visibleConversations) : projectFilesStatusLabel(projectFilesStatus, projectFiles?.documents.length ?? 0, projectId)}</small>
        </div>
        <div className="history-actions">
          {historySelected ? (
            <button
              type="button"
              onClick={onClearConversationHistory}
              disabled={historyStatus === "loading" || visibleConversations.length === 0}
            >
              Clear
            </button>
          ) : null}
          <button
            type="button"
            onClick={historySelected ? onRefreshHistory : onRefreshProjectFiles}
            disabled={historySelected ? historyStatus === "loading" : projectFilesStatus === "loading"}
          >
            Refresh
          </button>
          <button type="button" aria-label="Close Library" onClick={onClose}>×</button>
        </div>
      </header>
      <nav className="library-tabs" aria-label="Library sections">
        <button
          type="button"
          className={historySelected ? "active" : ""}
          aria-pressed={historySelected}
          onClick={() => onSelectSection("history")}
        >
          Histórico de chat
        </button>
        <button
          type="button"
          className={!historySelected ? "active" : ""}
          aria-pressed={!historySelected}
          onClick={() => onSelectSection("files")}
        >
          Arquivos enviados
        </button>
      </nav>
      {historySelected ? (
        <>
          {historyStatus === "loading" ? <p className="history-state">Loading persisted conversations…</p> : null}
          {historyError ? <p className="history-state error">{historyError}</p> : null}
          {visibleConversations.length === 0 && historyStatus !== "loading" ? (
            <p className="history-state empty">No previous conversations.</p>
          ) : null}
          {visibleConversations.length > 0 ? (
            <div className="history-list" role="listbox" aria-label="Persisted conversations">
              {visibleConversations.map((item) => {
                const conversation = item.conversation;
                return (
                  <article
                    key={conversation.conversation_id}
                    className="history-item"
                    role="option"
                    aria-selected={conversation.conversation_id === activeConversationId}
                  >
                    <button
                      type="button"
                      className="history-item-open"
                      onClick={() => onOpenConversation(conversation.conversation_id)}
                    >
                      <strong>{conversation.title || "Synapse conversation"}</strong>
                      <span>{item.preview || "No text preview"}</span>
                      <small>{formatDateTime(conversation.updated_at)} · {item.message_count} messages</small>
                    </button>
                    <button
                      type="button"
                      className="history-item-delete"
                      aria-label={`Delete conversation ${conversation.title || conversation.conversation_id}`}
                      title="Delete conversation"
                      onClick={() => onDeleteConversation(conversation.conversation_id)}
                      disabled={historyStatus === "loading"}
                    >
                      <TrashIcon />
                    </button>
                  </article>
                );
              })}
            </div>
          ) : null}
        </>
      ) : (
        <ProjectFilesPanel
          projectId={projectId}
          status={projectFilesStatus}
          data={projectFiles}
          error={projectFilesError}
          busyDocumentId={projectFilesBusyDocumentId}
          onClose={onClose}
          onRefresh={onRefreshProjectFiles}
          onReindex={onReindex}
          onRemove={onRemove}
          embedded
        />
      )}
    </section>
  );
}

function TrashIcon(): React.ReactElement {
  return (
    <svg
      className="trash-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M9 4h6l1 2h4v2H4V6h4l1-2Z" />
      <path d="M7 10h10l-.7 9.2A2 2 0 0 1 14.3 21H9.7a2 2 0 0 1-2-1.8L7 10Z" />
      <path d="M10 12v6M14 12v6" />
    </svg>
  );
}

function sectionLabel(section: SettingsSection): string {
  switch (section) {
    case "personalization":
      return "Personalization";
    case "voice":
      return "Voice";
    case "models":
      return "Models";
    case "swarm":
      return "Swarm";
    case "insight":
      return "Insight";
  }
}

const settingsSections: SettingsSection[] = ["personalization", "voice", "models", "swarm", "insight"];

interface ThemedSelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

function SettingsPanel({
  client,
  status,
  snapshot,
  frontendSettings,
  error,
  activeSection,
  primaryAgent,
  insightStatus,
  insightReport,
  insightError,
  onClose,
  onSelectSection,
  onRefresh,
  onRefreshInsight,
  onSave,
  onPreviewFrontendSettings,
  onLaunchSwarmDemo
}: {
  client?: SynapseFrontendClient;
  status: AppState["settingsStatus"];
  snapshot: SettingsSnapshot | null;
  frontendSettings: FrontendSettingsPreferences;
  error: string | null;
  activeSection: SettingsSection;
  primaryAgent: PrimaryAgentSummary | null;
  insightStatus: AppState["insightStatus"];
  insightReport: InsightReport | null;
  insightError: string | null;
  onClose: () => void;
  onSelectSection: (section: SettingsSection) => void;
  onRefresh: () => void;
  onRefreshInsight: () => void;
  onSave: (changes: SettingsChanges) => void;
  onPreviewFrontendSettings: (preferences: FrontendSettingsPreferences) => void;
  onLaunchSwarmDemo: () => void;
}): React.ReactElement {
  const initial = settingsChangesFromSnapshot(snapshot, frontendSettings);
  const [draft, setDraft] = useState<SettingsChanges>(initial);
  const [modelImportStatus, setModelImportStatus] = useState<string | null>(null);
  const [voiceCloneStatus, setVoiceCloneStatus] = useState<string | null>(null);
  const [cloneName, setCloneName] = useState("");
  const [cloneFile, setCloneFile] = useState<File | null>(null);
  const [cloneBusy, setCloneBusy] = useState(false);
  const [voiceSearch, setVoiceSearch] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const previewAudio = useRef<HTMLAudioElement | null>(null);
  const previewUrl = useRef<string | null>(null);
  const previewRequest = useRef<AbortController | null>(null);
  const stopPreview = useCallback(() => {
    previewRequest.current?.abort();
    previewRequest.current = null;
    if (previewAudio.current) {
      previewAudio.current.onended = null;
      previewAudio.current.onerror = null;
      previewAudio.current.pause();
      previewAudio.current.removeAttribute("src");
      previewAudio.current.load();
      previewAudio.current = null;
    }
    if (previewUrl.current) {
      URL.revokeObjectURL(previewUrl.current);
      previewUrl.current = null;
    }
    setPreviewId(null);
    setPreviewPlaying(false);
  }, []);
  useEffect(() => stopPreview, [activeSection, stopPreview]);

  async function preview(voiceId: string, providerId?: string): Promise<void> {
    const previewKey = `${providerId}:${voiceId}`;
    const wasPlaying = previewId === previewKey;
    stopPreview();
    if (wasPlaying || !client) return;
    const controller = new AbortController();
    previewRequest.current = controller;
    setPreviewId(previewKey);
    setLocalError(null);
    try {
      const voice = snapshot?.voice.voices.find((item) => item.voice_id === voiceId && (!providerId || item.provider === providerId));
      const language = voice?.locale || (voice?.language !== "Auto" ? voice?.language : null) || draft.language;
      const result = await client.previewVoice(
        `Eu sou ${draft.agentName.trim() || primaryAgent?.name || "Synapse"}.`,
        voiceId, providerId || voice?.provider || draft.ttsProvider,
        language, controller.signal
      );
      if (controller.signal.aborted) return;
      previewUrl.current = audioBlobUrl(result.audio_base64, result.audio_format || "audio/wav");
      const audio = new Audio(previewUrl.current);
      previewAudio.current = audio;
      audio.onended = stopPreview;
      audio.onerror = () => {
        stopPreview();
        setLocalError("Unable to play this voice preview.");
      };
      await audio.play();
      if (!controller.signal.aborted) setPreviewPlaying(true);
    } catch (error) {
      if (!controller.signal.aborted) {
        stopPreview();
        setLocalError(readableError(error));
      }
    }
  }
  useEffect(() => {
    setDraft(settingsChangesFromSnapshot(snapshot, frontendSettings));
  }, [frontendSettings, snapshot]);
  const providerSetting = snapshot?.models.provider_settings.find((item) => item.provider_id === draft.defaultProvider);
  const sttProviders = snapshot?.voice.providers.filter((item) => item.adapter_type === "stt") ?? [];
  const ttsProviders = snapshot?.voice.providers.filter((item) => item.adapter_type === "tts") ?? [];
  const ttsVoices = snapshot?.voice.voices ?? [];
  const canSave = Boolean(snapshot) && status !== "loading" && status !== "saving";

  function update<K extends keyof SettingsChanges>(key: K, value: SettingsChanges[K]): void {
    let next = { ...draft, [key]: value };
    if (key === "defaultProvider") {
      const providerId = typeof value === "string" ? value : "";
      const nextProviderSetting = snapshot?.models.provider_settings.find((item) => item.provider_id === providerId);
      const nextModel = snapshot?.models.catalog.find(
        (model) => model.provider === providerId && model.chat_usable && model.status !== "unavailable"
      );
      next = {
        ...next,
        defaultModel: nextModel?.name ?? "",
        providerEnabled: nextProviderSetting?.enabled ?? Boolean(providerId),
        providerEndpoint: nextProviderSetting?.endpoint ?? ""
      };
    }
    setDraft(next);
    if (key === "theme" || key === "reducedMotion") {
      onPreviewFrontendSettings({
        reducedMotion: next.reducedMotion === "reduce" ? "reduce" : "system",
        theme: normalizeTheme(next.theme)
      });
    }
    setLocalError(null);
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    try {
      onSave(draft);
    } catch (validationError) {
      setLocalError(readableError(validationError));
    }
  }

  return (
    <section className={`settings-panel settings-conservative ${status}`} aria-label="Settings panel" role="dialog" aria-modal="false">
      <header className="settings-header">
        <div>
          <span>Configurações</span>
          <small>{status === "ready" ? "Preferências do aplicativo" : status}</small>
        </div>
        <div className="settings-actions">
          <button type="button" onClick={onRefresh} disabled={status === "loading" || status === "saving"}>Refresh</button>
          <button type="button" aria-label="Close Settings" onClick={onClose}>×</button>
        </div>
      </header>
      <div className="settings-body">
      <nav className="settings-tabs" aria-label="Settings sections">
        {settingsSections.map((section) => (
          <button
            key={section}
            type="button"
            aria-label={`Settings section ${sectionLabel(section)}`}
            aria-pressed={activeSection === section}
            className={activeSection === section ? "active" : ""}
            onClick={() => {
              onSelectSection(section);
              if (section === "insight" && insightReport === null) {
                onRefreshInsight();
              }
            }}
          >
            {sectionLabel(section)}
          </button>
        ))}
      </nav>
      <form className="settings-content" onSubmit={submit}>
        {status === "loading" ? <p className="settings-state">Loading real settings from backend contracts…</p> : null}
        {(error || localError) && activeSection !== "insight" ? (
          <p className="settings-state error">{localError ?? error}</p>
        ) : null}

          {activeSection === "personalization" ? (
          <section className="settings-card" aria-label="Settings Personalization">
            <h3>Personalization</h3>
            <p className="muted">Give your agent a name and describe how you want it to communicate.</p>
            <label>Agent name
              <input value={draft.agentName} required maxLength={80} disabled={!snapshot?.personalization}
                onChange={(event) => update("agentName", event.target.value)} placeholder={primaryAgent?.name ?? "Agent name"} />
            </label>
            <label>Personality
              <textarea value={draft.personality} rows={7} maxLength={8000} disabled={!snapshot?.personalization}
                onChange={(event) => update("personality", event.target.value)}
                placeholder="For example: Speak Brazilian Portuguese. Be curious, direct and friendly. Avoid emojis unless I ask." />
            </label>
            <ThemedSelect
              label="Reduced motion"
              value={draft.reducedMotion}
              onChange={(value) => update("reducedMotion", value === "reduce" ? "reduce" : "system")}
              options={[
                { value: "system", label: "System preference" },
                { value: "reduce", label: "Reduce motion" }
              ]}
            />
            <p className="muted">Saved changes apply to future replies. Your conversations stay here.</p>
          </section>
          ) : null}

          {activeSection === "models" && snapshot ? (
          <section className="settings-card" aria-label="Settings Models">
            <h3>Models</h3>
            <label>
              Importar modelo local
              <input type="file" accept=".gguf,.ggml,.bin,.safetensors" disabled={!client}
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file || !client) return;
                  setModelImportStatus("Importando modelo…");
                  try {
                    const result = await client.importLocalModel(file);
                    setModelImportStatus(`${result.filename} importado. Atualize o catálogo para usar o modelo.`);
                  } catch (cause) {
                    setModelImportStatus(cause instanceof Error ? cause.message : "Falha ao importar o modelo.");
                  } finally {
                    event.target.value = "";
                  }
                }} />
            </label>
            {modelImportStatus ? <p className="muted" role="status">{modelImportStatus}</p> : null}
            <div className="provider-facts" aria-label="Detected model providers">
              {snapshot.models.providers.map((provider) => {
                const setting = snapshot.models.provider_settings.find((item) => item.provider_id === provider.provider_id);
                const configured = setting?.status === "configured" || setting?.enabled === true;
                return (
                  <article key={provider.provider_id}>
                    <strong>{provider.display_name}</strong>
                    <span>{provider.provider_id}</span>
                    <p>
                      <mark>detected</mark>
                      <mark className={configured ? "ok" : "muted"}>{configured ? "configured" : "not configured"}</mark>
                      <mark className={provider.status === "available" ? "ok" : "warn"}>{provider.status}</mark>
                    </p>
                  </article>
                );
              })}
            </div>
            <ThemedSelect
              label="Provedor padrão"
              value={draft.defaultProvider}
              onChange={(value) => update("defaultProvider", value)}
              options={[
                { value: "", label: "Selecione um provedor" },
                ...snapshot.models.providers.map((provider) => ({
                  value: provider.provider_id,
                  label: `${provider.display_name} · ${provider.status}`
                }))
              ]}
            />
            <ThemedSelect label="Modelo" value={draft.defaultModel}
              onChange={(value) => update("defaultModel", value)}
              options={[{ value: "", label: "Não configurado" }, ...snapshot.models.catalog
                .filter((model) => model.provider === draft.defaultProvider && model.chat_usable)
                .map((model) => ({ value: model.name, label: `${model.name} · ${model.status}`,
                  disabled: model.status === "unavailable" }))]} />
            <p className="muted">O generalista atende conversas sem rota específica. Configure os especialistas na aba MoM; o roteamento permanece disponível.</p>
            <label>
              Provider enabled
              <input type="checkbox" checked={draft.providerEnabled} onChange={(event) => update("providerEnabled", event.target.checked)} disabled={!draft.defaultProvider} />
            </label>
            <label>
              Provider endpoint
              <input value={draft.providerEndpoint} onChange={(event) => update("providerEndpoint", event.target.value)} placeholder={providerSetting?.endpoint ?? "backend-owned endpoint"} disabled={!draft.defaultProvider} />
            </label>
            <p className="muted">Owner: backend Model Hub and Provider Settings. Secrets are never displayed; API keys remain backend-owned.</p>
            <div className="settings-subsection" aria-label="Mixture of Models settings">
              <MoMSettings client={client} snapshot={snapshot}
                primaryId={primaryAgent?.agent_id} workspaceId={workspaceId} Select={ThemedSelect} />
            </div>
          </section>
          ) : null}
          {activeSection === "models" && !snapshot ? (
          <section className="settings-card" aria-label="Settings Models">
            <h3>Models</h3>
            <p className="settings-state error">{error ?? "Model settings are unavailable."}</p>
          </section>
          ) : null}

          {activeSection === "voice" && snapshot ? (
          <section className="settings-card" aria-label="Settings Voice">
            <div className="voice-library-heading">
              <h3>Voices <small>{ttsVoices.length}</small></h3>
              <label className="voice-enabled">Ativar voz
                <input type="checkbox" checked={draft.voiceEnabled} onChange={(event) => update("voiceEnabled", event.target.checked)} />
              </label>
            </div>
            <input aria-label="Buscar vozes" placeholder="Buscar voz, idioma ou provedor" value={voiceSearch} onChange={(event) => setVoiceSearch(event.target.value)} />
            <div className="voice-pack-grid voice-library" aria-label="Default Voice Pack voices">
              {ttsVoices.filter((voice) => `${voice.display_name} ${voice.locale} ${voice.language} ${voice.provider}`.toLowerCase().includes(voiceSearch.toLowerCase())).map((voice) => {
                const selected = draft.defaultTtsVoice === voice.voice_id && draft.ttsProvider === voice.provider;
                const previewing = previewId === `${voice.provider}:${voice.voice_id}`;
                const provider = ttsProviders.find((item) => item.provider_id === voice.provider);
                const usable = voice.usable && provider?.status === "available";
                return <article key={`${voice.provider}:${voice.voice_id}`} className={`voice-choice ${selected ? "selected" : ""}`}>
                  <button type="button" className="voice-card-select" disabled={!usable} aria-pressed={selected}
                    aria-label={`Selecionar ${voice.display_name}`} onClick={() => {
                      setDraft((current) => ({ ...current, defaultTtsVoice: voice.voice_id, ttsProvider: voice.provider,
                        language: voice.locale || (voice.language !== "Auto" ? voice.language : "") || current.language }));
                      void preview(voice.voice_id, voice.provider);
                    }}>
                    <small>{selected ? "SELECIONADA" : usable ? "DISPONÍVEL" : "INDISPONÍVEL"}</small>
                    <strong>{voice.display_name}</strong>
                    <span>{voice.provider} · {voice.locale || voice.language}</span>
                  </button>
                  <div className="voice-card-actions">
                    <button type="button" disabled={!usable || !client} onClick={() => void preview(voice.voice_id, voice.provider)}>
                      {previewing ? previewPlaying ? "Parar" : "Preparando…" : "Ouvir"}
                    </button>
                    <small>{selected ? "Salvar para aplicar" : !usable ? voice.reason || "Provedor indisponível" : "Clique para selecionar"}</small>
                  </div>
                </article>;
              })}
            </div>
            {ttsVoices.length === 0 ? <p className="muted">Nenhuma voz encontrada. Atualize o catálogo.</p> : null}
            <div className="settings-subsection voice-clone-compact" aria-label="VoiceStudio clone">
              <div className="voice-library-heading"><h4>Criar voz</h4><small>VoiceStudio</small></div>
              <div className="voice-clone-fields">
                <input aria-label="Nome da voz" placeholder="Nome da voz" maxLength={80} value={cloneName} disabled={cloneBusy} onChange={(event) => setCloneName(event.target.value)} />
                <input aria-label="Áudio de referência" type="file" accept="audio/*" disabled={cloneBusy} onChange={(event) => { setCloneFile(event.target.files?.[0] ?? null); setVoiceCloneStatus(null); }} />
                <button type="button" disabled={!client || cloneBusy || !cloneName.trim() || !cloneFile || !ttsProviders.some((item) => item.provider_id === "voicestudio" && item.status === "available")}
                  onClick={async () => {
                    if (!client || !cloneFile || cloneBusy) return;
                    setCloneBusy(true); setVoiceCloneStatus("Criando voz…");
                    try {
                      if (cloneFile.size > 20 * 1024 * 1024) throw new Error("Escolha um áudio de até 20 MB.");
                      const audioBase64 = await new Promise<string>((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onerror = () => reject(new Error("Não foi possível ler o áudio."));
                        reader.onload = () => resolve(String(reader.result));
                        reader.readAsDataURL(cloneFile);
                      });
                      await client.createVoiceStudioProfile({ name: cloneName.trim(), audio_base64: audioBase64, filename: cloneFile.name, language: draft.language, ref_text: "" });
                      setVoiceCloneStatus("Voz criada. Atualize a biblioteca para selecioná-la.");
                    } catch (cause) { setVoiceCloneStatus(readableError(cause)); }
                    finally { setCloneBusy(false); }
                  }}>{cloneBusy ? "Criando…" : "Criar voz"}</button>
              </div>
              <small>{ttsProviders.some((item) => item.provider_id === "voicestudio" && item.status === "available") ? "Use um áudio seu ou autorizado." : "Abra o VoiceStudio e atualize para criar uma voz."}</small>
              {voiceCloneStatus ? <p role="status">{voiceCloneStatus}</p> : null}
            </div>
            <details className="voice-audio-options"><summary>Áudio e entrada</summary>
            <ThemedSelect label="Reconhecimento de fala" value={draft.sttProvider} onChange={(value) => update("sttProvider", value)} options={sttProviders.map((provider) => ({ value: provider.provider_id, label: `${provider.provider_id} · ${provider.status}` }))} />
            <label>Modelo de reconhecimento<input value={draft.sttModel} onChange={(event) => update("sttModel", event.target.value)} /></label>
            <label>Idioma<input value={draft.language} onChange={(event) => update("language", event.target.value)} /></label>
            <h4>Advanced</h4>
            <ThemedSelect
              label="Preferred voice gender"
              value={draft.preferredVoiceGender}
              onChange={(value) => update("preferredVoiceGender", value)}
              options={[
                { value: "", label: "Backend default" },
                { value: "female", label: "female" },
                { value: "male", label: "male" },
                { value: "neutral", label: "neutral" }
              ]}
            />
            <label>
              VAD enabled
              <input type="checkbox" checked={draft.vadEnabled} onChange={(event) => update("vadEnabled", event.target.checked)} />
            </label>
            <label>
              Store raw audio
              <input type="checkbox" checked={draft.storeRawAudio} onChange={(event) => update("storeRawAudio", event.target.checked)} />
            </label>
            </details>
          </section>
          ) : null}
          {activeSection === "voice" && !snapshot ? (
          <section className="settings-card" aria-label="Settings Voice">
            <h3>Voice</h3>
            <p className="settings-state error">{error ?? "Voice settings are unavailable."}</p>
          </section>
          ) : null}

          {activeSection === "swarm" ? (
          <section className="settings-card" aria-label="Settings Swarm">
            <h3>Swarm</h3>
            <p className="muted">Visualize a execução coordenada de agentes em janelas independentes. O teste abaixo é local e não usa modelos ou arquivos reais.</p>
            {client ? <SwarmConfiguration client={client} /> : null}
            <div className="settings-demo-card">
              <div><strong>Swarm visual demo</strong><p className="muted">Cria agentes simulados para validar o comportamento visual do workspace.</p></div>
              <button type="button" onClick={onLaunchSwarmDemo}>Abrir demonstração</button>
            </div>
          </section>
          ) : null}

          {activeSection === "insight" ? (
          <section className="settings-card settings-insight" aria-label="Settings Insight">
            <header className="settings-card-header">
              <div>
                <h3>Insight</h3>
                <small>{insightStatus}</small>
              </div>
              <button type="button" onClick={onRefreshInsight} disabled={insightStatus === "loading"}>Refresh Insight</button>
            </header>
            {insightStatus === "loading" ? <p className="insight-state">Loading backend hardware and model facts…</p> : null}
            {insightError ? <p className="insight-state error">{insightError}</p> : null}
            {insightReport ? <InsightContent report={insightReport} /> : null}
            {!insightReport && insightStatus !== "loading" && !insightError ? (
              <p className="muted">Insight is available here after backend discovery succeeds.</p>
            ) : null}
          </section>
          ) : null}

          <footer className="settings-footer">
            <span>Only real settings with active owners are shown.</span>
            <button type="submit" disabled={!canSave}>{status === "saving" ? "Saving…" : "Save"}</button>
          </footer>
        </form>
      </div>
    </section>
  );
}

function SwarmConfiguration({ client }: { client: SynapseFrontendClient }): React.ReactElement {
  const [missions, setMissions] = useState<Array<Record<string, unknown>>>([]);
  const [agents, setAgents] = useState<Array<Record<string, unknown>>>([]);
  const [missionId, setMissionId] = useState("");
  const [strategy, setStrategy] = useState("sequential");
  const [leader, setLeader] = useState("");
  const [members, setMembers] = useState<string[]>([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    Promise.all([client.missions(), client.agents()]).then(([missionItems, agentItems]) => {
      if (!active) return;
      setMissions(missionItems);
      setAgents(agentItems);
      setStatus("ready");
    }).catch((reason) => {
      if (!active) return;
      setStatus("error");
      setError(readableError(reason));
    });
    return () => { active = false; };
  }, [client]);

  async function create(): Promise<void> {
    if (!missionId || members.length === 0) {
      setError("Selecione uma missão e pelo menos um agente membro.");
      return;
    }
    setStatus("saving");
    setError(null);
    try {
      const result = await client.createSwarm({ mission_id: missionId, strategy, leader_agent_id: leader || null, member_agent_ids: members });
      setCreated(result);
      setStatus("ready");
    } catch (reason) {
      setError(readableError(reason));
      setStatus("error");
    }
  }

  return <div className="swarm-config" aria-label="Real Swarm configuration">
    <h4>Configuração real</h4>
    <p className="muted">A execução exige uma missão existente com plano ativo. O Swarm não cria modelos automaticamente.</p>
    {status === "loading" ? <p className="muted">Carregando missões e agentes…</p> : null}
    <ThemedSelect label="Missão" value={missionId} onChange={setMissionId}
      options={[{ value: "", label: missions.length ? "Selecione uma missão" : "Nenhuma missão disponível" }, ...missions.map((item) => ({ value: String(item.mission_id ?? item.id ?? ""), label: String(item.title ?? item.mission_id ?? item.id ?? "Missão") }))]} />
    <ThemedSelect label="Estratégia" value={strategy} onChange={setStrategy}
      options={["leader_worker", "parallel", "pipeline", "review_loop"].map((value) => ({ value, label: value }))} />
    <ThemedSelect label="Líder (opcional)" value={leader} onChange={setLeader}
      options={[{ value: "", label: "Sem líder definido" }, ...agents.map((item) => ({ value: String(item.agent_id ?? item.id ?? ""), label: String(item.display_name ?? item.name ?? item.agent_id ?? item.id ?? "Agente") }))]} />
    <label className="swarm-members-label">Agentes membros
      <select multiple value={members} onChange={(event) => setMembers(Array.from(event.target.selectedOptions, (option) => option.value))}>
        {agents.map((item) => { const id = String(item.agent_id ?? item.id ?? ""); return <option key={id} value={id}>{String(item.display_name ?? item.name ?? id)}</option>; })}
      </select>
    </label>
    {error ? <p className="settings-state error">{error}</p> : null}
    <button type="button" onClick={() => void create()} disabled={status === "loading" || status === "saving" || !missionId || members.length === 0}>Criar Swarm real</button>
    {created ? <p className="muted">Swarm criado: {String(created.swarm_id ?? "identificador recebido")}</p> : null}
  </div>;
}

function ThemedSelect({
  label,
  value,
  options,
  disabled = false,
  onChange
}: {
  label: string;
  value: string;
  options: ThemedSelectOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value) ?? options[0];
  const enabledOptions = options.filter((option) => !option.disabled);
  const selectedIndex = Math.max(0, enabledOptions.findIndex((option) => option.value === selected?.value));
  const listboxId = `select-${slugify(label)}-listbox`;

  function choose(option: ThemedSelectOption): void {
    if (option.disabled) {
      return;
    }
    onChange(option.value);
    setOpen(false);
  }

  function move(delta: number): void {
    if (enabledOptions.length === 0) {
      return;
    }
    const next = enabledOptions[(selectedIndex + delta + enabledOptions.length) % enabledOptions.length];
    choose(next);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen((current) => !current);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
      } else {
        move(1);
      }
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
      } else {
        move(-1);
      }
    }
  }

  return (
    <label className="themed-select">
      <span>{label}</span>
      <button
        type="button"
        className="themed-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onKeyDown}
        onBlur={(event) => {
          if (!event.currentTarget.parentElement?.contains(event.relatedTarget as Node | null)) {
            setOpen(false);
          }
        }}
      >
        {selected?.label ?? "Unavailable"}
      </button>
      {open && !disabled ? (
        <div className="themed-select-list" id={listboxId} role="listbox" aria-label={label}>
          {options.map((option) => (
            <button
              key={`${label}:${option.value}`}
              type="button"
              role="option"
              aria-selected={option.value === value}
              disabled={option.disabled}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(option)}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </label>
  );
}

function TitleBar({
  state,
  theme,
  notificationsOpen,
  unreadNotifications,
  onToggleNotifications
}: {
  state: BackendConnectionState;
  theme: FrontendThemePreference;
  notificationsOpen: boolean;
  unreadNotifications: number;
  onToggleNotifications: () => void;
}): React.ReactElement {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void window.synapse?.window.isMaximized().then((value) => {
      if (!cancelled) {
        setMaximized(value);
      }
    });
    const unsubscribe = window.synapse?.window.onMaximizedChange((value) => setMaximized(value));
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  async function toggleMaximize(): Promise<void> {
    const next = await window.synapse?.window.toggleMaximize();
    if (typeof next === "boolean") {
      setMaximized(next);
    }
  }

  return (
    <header className="title-bar" onDoubleClick={() => void toggleMaximize()}>
      <div className="brand" aria-label="Synapse">S</div>
      <div className={`backend-pill ${state}`} aria-label={`Backend status: ${state}`} title={state} />
      <button
        type="button"
        className={`notification-button ${notificationsOpen ? "active" : ""}`}
        aria-label={unreadNotifications > 0 ? `Open notifications, ${unreadNotifications} unread` : "Open notifications"}
        aria-expanded={notificationsOpen}
        onClick={onToggleNotifications}
        onDoubleClick={(event) => event.stopPropagation()}
      >
        <span className="shell-nav-icon-frame" aria-hidden="true">
          <img
            className="shell-nav-icon shell-nav-icon--notifications"
            src={assetsForTheme(theme).notifications[unreadNotifications > 0 ? "active" : "idle"]}
            alt=""
            style={shellIconStyle(unreadNotifications > 0 ? "notificationsActive" : "notificationsIdle")}
          />
        </span>
        {unreadNotifications > 0 ? <span className="notification-badge">{unreadNotifications}</span> : null}
      </button>
      <div className="window-controls" aria-label="Window controls" onDoubleClick={(event) => event.stopPropagation()}>
        <button onClick={() => void window.synapse?.window.minimize()} aria-label="Minimize">─</button>
        <button onClick={() => void toggleMaximize()} aria-label={maximized ? "Restore" : "Maximize"}>
          {maximized ? "❐" : "□"}
        </button>
        <button onClick={() => void window.synapse?.window.close()} aria-label="Close">×</button>
      </div>
    </header>
  );
}

function Onboarding({
  bootstrap,
  onCreate
}: {
  bootstrap: FrontendBootstrap;
  onCreate: (request: FirstAgentRequest) => Promise<void>;
}): React.ReactElement {
  const [agentName, setAgentName] = useState("Synapse");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submittingRef = useRef(false);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onCreate({
        agent_id: slugify(agentName),
        display_name: agentName,
        role: "primary_agent",
        workspace_id: workspaceId,
      });
    } catch (caught) {
      setError(readableError(caught));
      setBusy(false);
    }
  }

  return (
    <main className="onboarding" aria-label="Configure your Synapse">
      <form onSubmit={(event) => void submit(event)}>
        <p className="eyebrow">First run</p>
        <h1>Welcome to Synapse</h1>
        <label>
          What should I call your primary agent?
          <input value={agentName} onChange={(event) => setAgentName(event.target.value)} />
        </label>
        {bootstrap.degraded.length > 0 ? <p className="degraded-text">You can configure a model later in Settings → Models.</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
        <button type="submit" disabled={busy || !agentName.trim()}>{busy ? "Creating…" : "Continue"}</button>
      </form>
    </main>
  );
}

function ConversationLog({
  conversationId,
  messages,
  streamText,
  pagination,
  summary,
  runtimeStatus,
  runtimeError,
  minimized,
  onToggle,
  onLoadOlder,
  onRecover,
  onNewConversation,
  primaryAgentName,
  swarmConfirmation,
  swarmConfirmationBusy,
  onResolveSwarmConfirmation
}: {
  conversationId: string | null;
  messages: ConversationMessage[];
  streamText: string;
  pagination: ConversationPagination | null;
  summary: ConversationSummary | null;
  runtimeStatus: ConversationRuntimeState;
  runtimeError: FrontendConversationError | null;
  minimized: boolean;
  onToggle: () => void;
  onLoadOlder: () => void;
  onRecover: () => void;
  onNewConversation: () => void;
  primaryAgentName: string;
  swarmConfirmation: SwarmInteractionRequest | null;
  swarmConfirmationBusy: boolean;
  onResolveSwarmConfirmation: (action: SwarmConfirmationAction) => void;
}): React.ReactElement {
  const listRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);
  const fadeTimerRef = useRef<number | null>(null);
  const [faded, setFaded] = useState(false);

  const clearFadeTimer = useCallback(() => {
    if (fadeTimerRef.current !== null) {
      window.clearTimeout(fadeTimerRef.current);
      fadeTimerRef.current = null;
    }
  }, []);

  const scheduleFade = useCallback(() => {
    clearFadeTimer();
    if (minimized || (!messages.length && !streamText && !runtimeError && !swarmConfirmation && !summary?.summary)) {
      setFaded(false);
      return;
    }
    fadeTimerRef.current = window.setTimeout(() => {
      setFaded(true);
      fadeTimerRef.current = null;
    }, conversationLogFadeDelayMs);
  }, [clearFadeTimer, messages.length, minimized, runtimeError, streamText, summary?.summary, swarmConfirmation]);

  useEffect(() => () => clearFadeTimer(), [clearFadeTimer]);

  useEffect(() => {
    setFaded(false);
    scheduleFade();
  }, [messages.length, runtimeStatus, runtimeError, scheduleFade, streamText, summary?.summary, swarmConfirmation]);

  function revealMessages(): void {
    clearFadeTimer();
    setFaded(false);
  }

  useEffect(() => {
    const list = listRef.current;
    if (list && autoScrollRef.current) {
      list.scrollTop = list.scrollHeight;
    }
  }, [messages, streamText, runtimeStatus]);

  function rememberScrollPosition(): void {
    const list = listRef.current;
    if (!list) {
      return;
    }
    const distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight;
    autoScrollRef.current = distanceFromBottom < 24;
  }

  if (minimized) {
    return (
      <button type="button" className="log-reopen" onClick={onToggle}
        aria-label="Mostrar mensagens" title="Mostrar mensagens">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Z" />
          <path d="M7 9h10M7 13h7" />
        </svg>
      </button>
    );
  }
  return (
    <aside
      className={`conversation-log ${faded ? "is-faded" : ""}`}
      aria-label="Conversation Log"
      data-conversation-id={conversationId ?? ""}
      onMouseEnter={revealMessages}
      onMouseLeave={scheduleFade}
    >
      <div className="log-header">
        <div className="log-actions">
          <button className="log-new-chat-button" onClick={onNewConversation} aria-label="New Chat" title="New Chat">+</button>
          <button onClick={onToggle} aria-label="Ocultar mensagens" title="Ocultar mensagens">›</button>
        </div>
      </div>
      <div className="message-list" ref={listRef} onScroll={rememberScrollPosition}>
        {pagination?.has_older ? (
          <button className="load-older" onClick={onLoadOlder}>
            Load older messages
          </button>
        ) : null}
        {summary?.summary ? (
          <article className="message summary">
            <span>summary</span>
            <p>{summary.summary}</p>
          </article>
        ) : null}
        {messages.length === 0 && !streamText ? <p className="empty-log">No conversation yet.</p> : null}
        {messages.map((message) => (
          <article key={message.message_id} className={`message ${message.role}`}>
            <span className="message-sender">{message.role === "user" ? "Você" : primaryAgentName}</span>
            <p>{message.payload.body ?? ""}</p>
            <MessageAttachments attachments={message.attachments ?? message.payload.attachments} />
          </article>
        ))}
        {streamText ? (
          <article className="message assistant streaming">
            <span className="message-sender">{primaryAgentName}</span>
            <p>{streamText}</p>
          </article>
        ) : null}
        {swarmConfirmation ? (
          <SwarmConfirmationCard
            request={swarmConfirmation}
            busy={swarmConfirmationBusy}
            onResolve={onResolveSwarmConfirmation}
          />
        ) : null}
        {runtimeError ? (
          <article className="message error">
            <span>{runtimeError.code}</span>
            <p>{runtimeError.message}</p>
            {runtimeError.retryable ? <button onClick={onRecover}>Reconcile history</button> : null}
          </article>
        ) : null}
      </div>
    </aside>
  );
}

function Composer({
  client,
  onSend,
  onCancel,
  commands,
  commandError,
  onDiscoverCommands,
  onExecuteCommand,
  onStageAttachment,
  onTranscribeVoice,
  onConversationVoiceTurn,
  onPresenceChange,
  disabled,
  canCancel,
  failedDraft
}: {
  client: SynapseFrontendClient;
  onSend: (content: string, attachments?: ConversationAttachment[]) => Promise<void>;
  onCancel: () => Promise<void>;
  commands: CommandDiscoveryItem[];
  commandError: string | null;
  onDiscoverCommands: () => Promise<void>;
  onExecuteCommand: (input: string) => Promise<CommandExecutionResult>;
  onStageAttachment: (file: { filename: string; mime_type: string; size: number; content_base64: string }) => Promise<ConversationAttachment>;
  onTranscribeVoice: (payload: Pick<VoiceTranscriptionRequest, "audio_base64" | "audio_format" | "duration_ms">) => Promise<string>;
  onConversationVoiceTurn: (
    payload: Pick<VoiceConversationTurnRequest, "audio_base64" | "audio_format" | "voice_session_id" | "idempotency_key">,
    onGenerating?: () => void,
    signal?: AbortSignal
  ) => Promise<VoiceConversationTurnResult>;
  onPresenceChange: (manualVoiceState: VoiceCaptureState, conversationModeState: ConversationModeState, amplitude: number) => void;
  disabled: boolean;
  canCancel: boolean;
  failedDraft: string;
}): React.ReactElement {
  const [text, setText] = useState("");
  const [momPending, setMomPending] = useState(false);
  const textRef = useRef("");
  const [busy, setBusy] = useState(false);
  const submittingRef = useRef(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [selectedCommand, setSelectedCommand] = useState(0);
  const [commandExecutionState, setCommandExecutionState] = useState<"idle" | "executing" | "completed" | "failed">("idle");
  const [commandExecutionMessage, setCommandExecutionMessage] = useState<string | null>(null);
  const [attachmentState, setAttachmentState] = useState<AttachmentStageState>("ready");
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<ConversationAttachment[]>([]);
  const [voiceState, setVoiceState] = useState<VoiceCaptureState>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [conversationModeState, setConversationModeState] = useState<ConversationModeState>("inactive");
  const [conversationModeError, setConversationModeError] = useState<string | null>(null);
  const [voiceUnderstanding, setVoiceUnderstanding] = useState<string | null>(null);
  const conversationModeActiveRef = useRef(false);
  const microphoneMutedRef = useRef(false);
  const [microphoneMuted, setMicrophoneMuted] = useState(false);
  const microphoneEpochRef = useRef(0);
  const conversationModeStateRef = useRef<ConversationModeState>("inactive");
  const conversationModeSessionRef = useRef<string | null>(null);
  const conversationModeRequestRef = useRef<AbortController | null>(null);
  const playbackRef = useRef<HTMLAudioElement | null>(null);
  const playbackUrlRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const amplitudeFrameRef = useRef<number | null>(null);
  const loopTimerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef<number | null>(null);
  const recordingCancelledRef = useRef(false);
  const conversationModePeakAmplitudeRef = useRef(0);
  const conversationModeVadRef = useRef<ConversationVadSnapshot | null>(null);
  const conversationModeLastAmplitudeAtRef = useRef<number | null>(null);
  const filteredCommands = useMemo(() => filterCommands(commands, text), [commands, text]);
  const canSend = useMemo(
    () => (text.trim().length > 0 || attachments.length > 0) && !disabled && !busy && attachmentState !== "staging" && voiceState !== "recording" && voiceState !== "transcribing",
    [attachmentState, attachments.length, busy, disabled, text, voiceState]
  );
  const voiceStatus = voiceStatusLabel(voiceState, voiceError);
  const conversationModeStatus = conversationModeStatusLabel(conversationModeState, conversationModeError);
  const conversationModeCapturing = conversationModeCapturesMicrophone(conversationModeState);
  const conversationModeRunning = conversationModeState !== "inactive" && conversationModeState !== "failed" && conversationModeState !== "interrupted";

  useEffect(() => {
    if (failedDraft && !text) {
      setText(failedDraft);
    }
  }, [failedDraft, text]);

  useEffect(() => {
    return () => {
      conversationModeActiveRef.current = false;
      conversationModeRequestRef.current?.abort();
      conversationModeRequestRef.current = null;
      releaseAudioTracks(streamRef.current);
      const playback = playbackRef.current;
      if (playback) {
        playback.pause();
        playback.removeAttribute("src");
        playback.load();
      }
      playbackRef.current = null;
      cleanupConversationModePlaybackUrl();
      clearConversationModeTimer();
      stopAmplitudeMeter();
    };
  }, []);

  useEffect(() => {
    conversationModeStateRef.current = conversationModeState;
    onPresenceChange(voiceState, conversationModeState, 0);
  }, [conversationModeState, onPresenceChange, voiceState]);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    const content = textRef.current.trim();
    const canSubmitContent =
      (content.length > 0 || attachments.length > 0) &&
      !disabled &&
      !momPending &&
      !busy &&
      attachmentState !== "staging" &&
      voiceState !== "recording" &&
      voiceState !== "transcribing";
    if (content.startsWith("/") && attachments.length === 0 && shouldExecuteSlashInput(content)) {
      setCommandOpen(false);
      await executeSlashInput(content);
      return;
    }
    if (commandOpen && content.startsWith("/") && attachments.length === 0) {
      selectCommand(filteredCommands[selectedCommand]);
      return;
    }
    if (!canSubmitContent || submittingRef.current) {
      return;
    }
    const submittedAttachments = attachments;
    submittingRef.current = true;
    setBusy(true);
    textRef.current = "";
    setText("");
    setAttachments([]);
    setAttachmentError(null);
    try {
      await onSend(content, submittedAttachments);
    } catch (error) {
      textRef.current = content;
      setText(content);
      setAttachments(submittedAttachments);
      throw error;
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  }

  async function pickAndStageAttachment(): Promise<void> {
    if (disabled || busy || attachmentState === "staging") {
      return;
    }
    setAttachmentState("selecting");
    setAttachmentError(null);
    const selected = await window.synapse?.pickAttachmentFile();
    if (!selected || selected.status === "cancelled") {
      setAttachmentState("ready");
      return;
    }
    if (selected.status === "failed") {
      setAttachmentState("failed");
      setAttachmentError(selected.error ?? "Attachment selection failed.");
      return;
    }
    if (!selected.filename || !selected.mime_type || selected.size === undefined || !selected.content_base64) {
      setAttachmentState("failed");
      setAttachmentError("Attachment selection returned incomplete metadata.");
      return;
    }
    setAttachmentState("staging");
    try {
      const staged = await onStageAttachment({
        filename: selected.filename,
        mime_type: selected.mime_type,
        size: selected.size,
        content_base64: selected.content_base64
      });
      setAttachments((current) => upsertAttachment(current, staged));
      setAttachmentState("ready");
      setAttachmentError(null);
    } catch (error) {
      setAttachmentState("failed");
      setAttachmentError(readableError(error));
    }
  }

  function removeAttachment(attachmentId: string): void {
    setAttachments((current) => current.filter((item) => item.attachment_id !== attachmentId));
  }

  function changeText(value: string): void {
    textRef.current = value;
    setText(value);
    setCommandExecutionState("idle");
    setCommandExecutionMessage(null);
    if (value === "" || !isSlashDiscoveryInput(value)) {
      setCommandOpen(false);
      setSelectedCommand(0);
      return;
    }
    setCommandOpen(true);
    setSelectedCommand(0);
    void onDiscoverCommands();
  }

  function selectCommand(command: CommandDiscoveryItem | undefined): void {
    const selected = applyCommandSelection(command);
    if (!selected) {
      setCommandOpen(false);
      return;
    }
    textRef.current = selected;
    setText(selected);
    setCommandOpen(false);
  }

  function shouldExecuteSlashInput(value: string): boolean {
    const trimmed = value.trim();
    if (trimmed === "/") {
      return false;
    }
    const selected = filteredCommands[selectedCommand];
    if (!commandOpen || !selected) {
      return true;
    }
    const selectedName = `/${commandName(selected).toLowerCase()}`;
    const lower = trimmed.toLowerCase();
    return lower === selectedName || lower.startsWith(`${selectedName} `);
  }

  async function executeSlashInput(value: string): Promise<void> {
    setBusy(true);
    setCommandExecutionState("executing");
    setCommandExecutionMessage("Executing command…");
    try {
      const result = await onExecuteCommand(value);
      setCommandExecutionState(result.status);
      setCommandExecutionMessage(result.message);
      if (result.status === "completed") {
        setText("");
      }
    } catch (error) {
      setCommandExecutionState("failed");
      setCommandExecutionMessage(readableError(error));
    } finally {
      setBusy(false);
    }
  }

  async function startVoiceRecording(): Promise<void> {
    if (disabled || conversationModeActiveRef.current || conversationModeCapturing || voiceState === "recording" || voiceState === "transcribing") {
      return;
    }
    setVoiceError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        throw new Error("Microphone recording is not available in this environment.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      streamRef.current = stream;
      recorderRef.current = recorder;
      startAmplitudeMeter(stream, (amplitude) => onPresenceChange("recording", "inactive", amplitude));
      chunksRef.current = [];
      recordingCancelledRef.current = false;
      recordingStartedAtRef.current = Date.now();
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      });
      recorder.addEventListener("stop", () => {
        if (recordingCancelledRef.current) {
          recordingCancelledRef.current = false;
          return;
        }
        void finishVoiceRecording(recorder.mimeType || "audio/webm");
      }, { once: true });
      recorder.start();
      setVoiceState("recording");
    } catch (error) {
      releaseAudioTracks(streamRef.current);
      streamRef.current = null;
      recorderRef.current = null;
      stopAmplitudeMeter();
      setVoiceState("failed");
      setVoiceError(normalizeVoiceError(error));
    }
  }

  function stopVoiceRecording(): void {
    const recorder = recorderRef.current;
    if (!recorder || voiceState !== "recording") {
      return;
    }
    setVoiceState("transcribing");
    recorder.stop();
  }

  function cancelVoiceRecording(): void {
    const recorder = recorderRef.current;
    recordingCancelledRef.current = true;
    recorderRef.current = null;
    chunksRef.current = [];
    recordingStartedAtRef.current = null;
    releaseAudioTracks(streamRef.current);
    streamRef.current = null;
    stopAmplitudeMeter();
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    setVoiceError(null);
    setVoiceState("idle");
  }

  async function finishVoiceRecording(audioFormat: string): Promise<void> {
    const blob = new Blob(chunksRef.current, { type: audioFormat });
    const startedAt = recordingStartedAtRef.current;
    chunksRef.current = [];
    recordingStartedAtRef.current = null;
    recorderRef.current = null;
    releaseAudioTracks(streamRef.current);
    streamRef.current = null;
    stopAmplitudeMeter();
    try {
      if (isEmptyRecording(blob)) {
        throw new Error("Recording did not capture audio.");
      }
      const transcript = await onTranscribeVoice({
        audio_base64: await blobToBase64(blob),
        audio_format: blob.type || audioFormat,
        duration_ms: startedAt ? Date.now() - startedAt : null
      });
      setText((current) => mergeTranscriptionIntoDraft(current, transcript));
      setVoiceError(null);
      setVoiceState("idle");
    } catch (error) {
      setVoiceState("failed");
      setVoiceError(normalizeVoiceError(error));
    }
  }

  function toggleConversationMode(): void {
    if (conversationModeActiveRef.current) {
      stopConversationMode("interrupted");
      return;
    }
    if (disabled || voiceState === "recording" || voiceState === "transcribing") {
      return;
    }
    conversationModeActiveRef.current = true;
    setConversationModeError(null);
    setConversationModeState("listening");
    void startConversationModeRecording();
  }

  async function startConversationModeRecording(): Promise<void> {
    clearConversationModeTimer();
    if (!conversationModeActiveRef.current || microphoneMutedRef.current) {
      return;
    }
    const microphoneEpoch = microphoneEpochRef.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        throw new Error("Microphone recording is not available in this environment.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      if (!conversationModeActiveRef.current || microphoneMutedRef.current || microphoneEpoch !== microphoneEpochRef.current) {
        releaseAudioTracks(stream);
        return;
      }
      logConversationModeInputDevice(stream);
      const recorder = new MediaRecorder(stream, preferredAudioRecorderOptions());
      streamRef.current = stream;
      recorderRef.current = recorder;
      conversationModePeakAmplitudeRef.current = 0;
      conversationModeVadRef.current = null;
      conversationModeLastAmplitudeAtRef.current = null;
      startAmplitudeMeter(stream, (amplitude) => {
        conversationModePeakAmplitudeRef.current = Math.max(conversationModePeakAmplitudeRef.current, amplitude);
        updateConversationModeVad(amplitude);
        onPresenceChange("idle", conversationModeStateRef.current === "capturing" ? "capturing" : "listening", amplitude);
      });
      chunksRef.current = [];
      recordingCancelledRef.current = false;
      recorder.addEventListener("dataavailable", (event) => {
        if (microphoneEpoch !== microphoneEpochRef.current) return;
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      });
      recorder.addEventListener("stop", () => {
        if (microphoneEpoch !== microphoneEpochRef.current) return;
        if (recordingCancelledRef.current) {
          recordingCancelledRef.current = false;
          return;
        }
        void finishConversationModeRecording(recorder.mimeType || "audio/webm");
      }, { once: true });
      recorder.start();
      setConversationModeState("listening");
      loopTimerRef.current = window.setTimeout(() => stopConversationModeRecording("listen_timeout"), conversationModeMaxCaptureMs);
    } catch (error) {
      recoverConversationModeTurnError(error);
    }
  }

  function stopConversationModeRecording(reason: "speech_ended" | "listen_timeout" | "manual" = "manual"): void {
    clearConversationModeTimer();
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      return;
    }
    console.log("voice_capture_diag:conversation_recording_stop", {
      reason,
      peakAmplitude: conversationModePeakAmplitudeRef.current,
      vad: conversationModeVadRef.current
    });
    setConversationModeState("finalizing");
    onPresenceChange("idle", "finalizing", 0);
    recorder.stop();
  }

  function updateConversationModeVad(amplitude: number): void {
    if (!conversationModeActiveRef.current || !recorderRef.current || recorderRef.current.state !== "recording") {
      return;
    }
    const now = performance.now();
    const previousTime = conversationModeLastAmplitudeAtRef.current ?? now;
    conversationModeLastAmplitudeAtRef.current = now;
    const next = updateConversationVad(
      conversationModeVadRef.current,
      amplitude,
      now - previousTime,
      {
        ...defaultConversationVadConfig,
        maxCaptureMs: conversationModeMaxCaptureMs
      }
    );
    conversationModeVadRef.current = next;
    if (next.shouldStart && conversationModeStateRef.current === "listening") {
      setConversationModeState("capturing");
      onPresenceChange("idle", "capturing", amplitude);
    }
    if (next.shouldStop) {
      stopConversationModeRecording(next.started ? "speech_ended" : "listen_timeout");
    }
  }

  async function finishConversationModeRecording(audioFormat: string): Promise<void> {
    const blob = new Blob(chunksRef.current, { type: audioFormat });
    const vad = conversationModeVadRef.current;
    chunksRef.current = [];
    recorderRef.current = null;
    conversationModeVadRef.current = null;
    conversationModeLastAmplitudeAtRef.current = null;
    releaseAudioTracks(streamRef.current);
    streamRef.current = null;
    stopAmplitudeMeter();
    if (!conversationModeActiveRef.current) {
      return;
    }
    try {
      if (isEmptyRecording(blob)) {
        throw new Error("Recording did not capture audio.");
      }
      if (!vad?.started || conversationModePeakAmplitudeRef.current < conversationModeMinimumVoicePeak) {
        setConversationModeError(null);
        if (conversationModeActiveRef.current) {
          scheduleConversationModeListening(conversationModeRestartDelayMs);
        }
        return;
      }
      setConversationModeState("transcribing");
      onPresenceChange("idle", "transcribing", 0);
      const voiceRequest = new AbortController();
      conversationModeRequestRef.current = voiceRequest;
      const captureEpoch = microphoneEpochRef.current;
      const audioBase64 = await blobToBase64(blob);
      if (!conversationModeActiveRef.current || microphoneMutedRef.current || captureEpoch !== microphoneEpochRef.current) {
        if (conversationModeRequestRef.current === voiceRequest) conversationModeRequestRef.current = null;
        if (conversationModeActiveRef.current) scheduleConversationModeListening(conversationModeRestartDelayMs);
        return;
      }
      const result = await onConversationVoiceTurn({
        audio_base64: audioBase64,
        audio_format: blob.type || audioFormat,
        voice_session_id: conversationModeSessionRef.current,
        idempotency_key: crypto.randomUUID()
      }, () => {
        setConversationModeState("generating");
        onPresenceChange("idle", "generating", 0);
      }, voiceRequest.signal);
      if (!conversationModeActiveRef.current || voiceRequest.signal.aborted) return;
      conversationModeRequestRef.current = null;
      conversationModeSessionRef.current = result.voice_session_id;
      setVoiceUnderstanding(result.status === "needs_repetition"
        ? `Não entendi com segurança. Transcrição incerta: “${result.transcript}”. Pode repetir?`
        : `Entendi: “${result.transcript}”`);
      await waitForNextPaint();
      setConversationModeState("generating");
      if (result.status === "needs_repetition") {
        setConversationModeError(null);
        scheduleConversationModeListening(conversationModePostSpeechCooldownMs);
        return;
      }
      if (result.status === "ignored_echo" || isLikelyConversationModeEcho(result.transcript)) {
        setConversationModeError(null);
        scheduleConversationModeListening(conversationModePostSpeechCooldownMs);
        return;
      }
      if (result.tts.audio_base64) {
        try {
          setConversationModeState("synthesizing");
          await playConversationModeAudio(result.tts.audio_base64, result.tts.audio_format);
          setConversationModeError(null);
        } catch (playbackError) {
          console.error("voice_tts_diag:conversation_playback_failed", {
            name: playbackError instanceof Error ? playbackError.name : null,
            message: playbackError instanceof Error ? playbackError.message : String(playbackError),
            error: playbackError
          });
          cleanupConversationModePlayback();
          setConversationModeError(normalizeVoiceError(playbackError));
        }
      } else {
        console.error("voice_tts_diag:conversation_tts_audio_unavailable", {
          synthesisId: result.synthesis_id,
          ttsStatus: result.tts.status,
          providerId: result.tts.provider_id,
          voiceId: result.tts.voice_id,
          audioBase64State: result.tts.audio_base64 ? "populated" : "empty",
          degraded: result.degraded
        });
        setConversationModeError(result.degraded[0]?.message ?? "TTS audio is unavailable.");
      }
      if (conversationModeActiveRef.current) {
        scheduleConversationModeListening(conversationModePostSpeechCooldownMs);
      }
    } catch (error) {
      recoverConversationModeTurnError(error);
    }
  }

  async function playConversationModeAudio(audioBase64: string | null, audioFormat: string | null): Promise<void> {
    if (!audioBase64) {
      throw new Error("TTS audio is unavailable.");
    }
    cleanupConversationModePlayback();
    setConversationModeState("speaking");
    onPresenceChange("idle", "speaking", 0.18);
    const audioUrl = audioBlobUrl(audioBase64, audioFormat ?? "audio/wav");
    playbackUrlRef.current = audioUrl;
    const audio = new Audio(audioUrl);
    playbackRef.current = audio;
    startPlaybackAmplitudeMeter(audio);
    await new Promise<void>((resolve, reject) => {
      audio.addEventListener("ended", () => resolve(), { once: true });
      audio.addEventListener("error", () => {
        const mediaError = audio.error;
        console.error("voice_tts_diag:audio_element_error", {
          code: mediaError?.code ?? null,
          message: mediaError?.message ?? null,
          networkState: audio.networkState,
          readyState: audio.readyState
        });
        reject(new Error(`TTS playback failed: ${mediaError?.message ?? "HTMLAudioElement error"}`));
      }, { once: true });
      void audio.play().catch((playbackError) => {
        console.error("voice_tts_diag:audio_play_rejected", {
          name: playbackError instanceof Error ? playbackError.name : null,
          message: playbackError instanceof Error ? playbackError.message : String(playbackError),
          networkState: audio.networkState,
          readyState: audio.readyState,
          error: playbackError
        });
        reject(playbackError);
      });
    });
    cleanupConversationModePlayback();
  }

  function stopConversationMode(state: ConversationModeState = "inactive"): void {
    microphoneEpochRef.current += 1;
    conversationModeActiveRef.current = false;
    conversationModeRequestRef.current?.abort();
    conversationModeRequestRef.current = null;
    conversationModeSessionRef.current = null;
    clearConversationModeTimer();
    cancelVoiceRecording();
    cleanupConversationModePlayback();
    setConversationModeState(state === "interrupted" ? "interrupted" : "inactive");
  }

  function failConversationMode(error: unknown): void {
    conversationModeActiveRef.current = false;
    conversationModeSessionRef.current = null;
    clearConversationModeTimer();
    recorderRef.current = null;
    chunksRef.current = [];
    recordingStartedAtRef.current = null;
    conversationModeVadRef.current = null;
    conversationModeLastAmplitudeAtRef.current = null;
    recordingCancelledRef.current = false;
    releaseAudioTracks(streamRef.current);
    streamRef.current = null;
    stopAmplitudeMeter();
    cleanupConversationModePlayback();
    setConversationModeState("failed");
    setConversationModeError(normalizeVoiceError(error));
  }

  function recoverConversationModeTurnError(error: unknown): void {
    if (!conversationModeActiveRef.current) return;
    // A completed/failed request must not block unmuting and starting capture.
    conversationModeRequestRef.current = null;
    conversationModeSessionRef.current = null;
    clearConversationModeTimer();
    recorderRef.current = null;
    chunksRef.current = [];
    recordingStartedAtRef.current = null;
    conversationModeVadRef.current = null;
    conversationModeLastAmplitudeAtRef.current = null;
    recordingCancelledRef.current = false;
    releaseAudioTracks(streamRef.current);
    streamRef.current = null;
    stopAmplitudeMeter();
    cleanupConversationModePlayback();
    setConversationModeError(normalizeVoiceError(error));
    if (!conversationModeActiveRef.current) {
      setConversationModeState("failed");
      return;
    }
    scheduleConversationModeListening(conversationModePostSpeechCooldownMs);
  }

  function scheduleConversationModeListening(delayMs: number): void {
    clearConversationModeTimer();
    setConversationModeState("cooldown");
    onPresenceChange("idle", "cooldown", 0);
    if (microphoneMutedRef.current) return;
    loopTimerRef.current = window.setTimeout(() => {
      loopTimerRef.current = null;
      if (!conversationModeActiveRef.current) {
        return;
      }
      setConversationModeError(null);
      setConversationModeState("listening");
      void startConversationModeRecording();
    }, delayMs);
  }

  function toggleMicrophoneMute(): void {
    const muted = !microphoneMutedRef.current;
    microphoneMutedRef.current = muted;
    setMicrophoneMuted(muted);
    microphoneEpochRef.current += 1;
    if (muted) {
      clearConversationModeTimer();
      // Discard partial capture, but preserve any response already in progress.
      if (!conversationModeRequestRef.current && !playbackRef.current) {
        cancelVoiceRecording();
        setConversationModeState("cooldown");
        onPresenceChange("idle", "cooldown", 0);
      }
    } else if (conversationModeActiveRef.current && !conversationModeRequestRef.current && !playbackRef.current) {
      void startConversationModeRecording();
    }
  }

  function cleanupConversationModePlayback(): void {
    const playback = playbackRef.current;
    if (playback) {
      playback.pause();
      playback.removeAttribute("src");
      playback.load();
    }
    playbackRef.current = null;
    cleanupConversationModePlaybackUrl();
    stopAmplitudeMeter();
  }

  function cleanupConversationModePlaybackUrl(): void {
    if (playbackUrlRef.current) {
      URL.revokeObjectURL(playbackUrlRef.current);
      playbackUrlRef.current = null;
    }
  }

  function waitForNextPaint(): Promise<void> {
    return new Promise((resolve) => {
      requestAnimationFrame(() => resolve());
    });
  }

  function startAmplitudeMeter(stream: MediaStream, onAmplitude: (amplitude: number) => void): void {
    stopAmplitudeMeter();
    try {
      const context = new AudioContext();
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioContextRef.current = context;
      analyserRef.current = analyser;
      pumpAmplitude(onAmplitude);
    } catch {
      onAmplitude(0);
    }
  }

  function startPlaybackAmplitudeMeter(audio: HTMLAudioElement): void {
    stopAmplitudeMeter();
    try {
      const context = new AudioContext();
      const source = context.createMediaElementSource(audio);
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(context.destination);
      audioContextRef.current = context;
      analyserRef.current = analyser;
      pumpAmplitude((amplitude) => onPresenceChange("idle", "speaking", amplitude));
    } catch {
      onPresenceChange("idle", "speaking", 0);
    }
  }

  function pumpAmplitude(onAmplitude: (amplitude: number) => void): void {
    const analyser = analyserRef.current;
    if (!analyser) {
      return;
    }
    const samples = new Uint8Array(analyser.fftSize);
    const tick = (): void => {
      const activeAnalyser = analyserRef.current;
      if (!activeAnalyser) {
        return;
      }
      activeAnalyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) {
        const normalized = (sample - 128) / 128;
        sum += normalized * normalized;
      }
      onAmplitude(Math.max(0, Math.min(1, Math.sqrt(sum / samples.length) * 3.6)));
      amplitudeFrameRef.current = window.requestAnimationFrame(tick);
    };
    tick();
  }

  function stopAmplitudeMeter(): void {
    if (amplitudeFrameRef.current !== null) {
      window.cancelAnimationFrame(amplitudeFrameRef.current);
      amplitudeFrameRef.current = null;
    }
    analyserRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
  }

  function logConversationModeInputDevice(stream: MediaStream): void {
    const tracks = stream.getAudioTracks();
    const devices = tracks.map((track) => {
      const settings = track.getSettings();
      return {
        id: track.id,
        label: track.label,
        enabled: track.enabled,
        muted: track.muted,
        readyState: track.readyState,
        deviceId: settings.deviceId ?? null,
        groupId: settings.groupId ?? null,
        sampleRate: settings.sampleRate ?? null,
        channelCount: settings.channelCount ?? null,
        echoCancellation: settings.echoCancellation ?? null,
        noiseSuppression: settings.noiseSuppression ?? null,
        autoGainControl: settings.autoGainControl ?? null
      };
    });
    console.log("voice_capture_diag:conversation_input_device", { devices });
  }

  function preferredAudioRecorderOptions(): MediaRecorderOptions | undefined {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus"
    ];
    for (const mimeType of candidates) {
      if (MediaRecorder.isTypeSupported(mimeType)) {
        return { mimeType };
      }
    }
    return undefined;
  }

  function clearConversationModeTimer(): void {
    if (loopTimerRef.current !== null) {
      window.clearTimeout(loopTimerRef.current);
      loopTimerRef.current = null;
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>): void {
    if (!commandOpen) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setCommandOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedCommand((current) => moveCommandSelection(current, 1, filteredCommands.length));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedCommand((current) => moveCommandSelection(current, -1, filteredCommands.length));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      selectCommand(filteredCommands[selectedCommand]);
    }
  }

  return (
    <form className="composer" onSubmit={(event) => void submit(event)} aria-label="Message composer">
      {commandOpen ? (
        <div className="command-discovery" role="listbox" aria-label="Slash command discovery">
          {commandError ? <p className="command-empty">{commandError}</p> : null}
          {!commandError && filteredCommands.length === 0 ? <p className="command-empty">No command matches this query.</p> : null}
          {filteredCommands.map((command, index) => (
            <button
              key={command.tool_id}
              type="button"
              role="option"
              aria-selected={index === selectedCommand}
              className={index === selectedCommand ? "selected" : ""}
              onMouseDown={(event) => {
                event.preventDefault();
                selectCommand(command);
              }}
            >
              <span>/{commandName(command)}</span>
              <small>{command.description}{command.available ? "" : ` · unavailable: ${command.reason_unavailable ?? "not available"}`}</small>
            </button>
          ))}
        </div>
      ) : null}
      <div className="composer-voice-feedback">
      {voiceStatus ? <div className={`voice-status ${voiceState}`} role="status">{voiceStatus}</div> : null}
      {voiceUnderstanding ? <div className="voice-understanding" role="status" aria-live="polite">{voiceUnderstanding}</div> : null}
      {conversationModeStatus ? (
        <div className={`voice-status conversation-mode ${conversationModeState}`} role="status">
          {microphoneMuted ? "Microfone mudo — a conversa continua ativa" : conversationModeStatus}
        </div>
      ) : null}
      </div>
      {commandExecutionMessage ? (
        <div className={`command-status ${commandExecutionState}`} role="status">
          {commandExecutionMessage}
        </div>
      ) : null}
      {attachments.length > 0 || attachmentError ? (
        <div className={`attachment-tray ${attachmentState}`} role="status">
          {attachments.map((attachment) => (
            <button
              key={attachment.attachment_id}
              type="button"
              className="attachment-chip"
              title={`${attachment.filename} · ${formatAttachmentSize(attachment.size)}`}
              onClick={() => removeAttachment(attachment.attachment_id)}
            >
              <span>{attachment.filename}</span>
              <small>{formatAttachmentSize(attachment.size)} ×</small>
            </button>
          ))}
          {attachmentError ? <span className="attachment-error">{attachmentError}</span> : null}
        </div>
      ) : null}
      <button
        type="button"
        className="composer-action composer-attach"
        title="Attach file"
        disabled={disabled || busy || attachmentState === "staging"}
        onClick={() => void pickAndStageAttachment()}
      >
        {attachmentState === "staging" ? "…" : <PaperclipIcon />}
      </button>
      <input
        value={text}
        disabled={disabled}
        placeholder="chat"
        onKeyDown={handleKeyDown}
        onChange={(event) => changeText(event.target.value)}
      />
      <MoMToggle client={client} workspaceId={workspaceId} onBusy={setMomPending} />
      <button
        type="button"
        className="composer-action composer-mic"
        title={conversationModeRunning ? (microphoneMuted ? "Ativar microfone" : "Silenciar microfone") : voiceState === "recording" ? "Stop recording and transcribe" : "Record voice for transcription"}
        aria-label={conversationModeRunning ? (microphoneMuted ? "Ativar microfone" : "Silenciar microfone") : "Gravar mensagem de voz"}
        aria-pressed={conversationModeRunning ? microphoneMuted : undefined}
        disabled={!conversationModeRunning && (disabled || conversationModeCapturing || voiceState === "transcribing")}
        onClick={conversationModeRunning ? toggleMicrophoneMute : voiceState === "recording" ? stopVoiceRecording : () => void startVoiceRecording()}
      >
        {conversationModeRunning && microphoneMuted ? <span aria-hidden="true">Mudo</span> : voiceState === "recording" ? <StopIcon /> : <MicIcon />}
      </button>
      <button
        type="button"
        className={`composer-action composer-record ${conversationModeRunning ? "active" : ""}`}
        title={
          !conversationModeRunning && voiceState === "recording"
            ? "Cancel manual recording"
            : !conversationModeRunning
              ? "Start Conversation Mode"
              : "Stop Conversation Mode"
        }
        disabled={disabled && !conversationModeRunning}
        onClick={!conversationModeRunning && voiceState === "recording" ? cancelVoiceRecording : toggleConversationMode}
      >
        <RecordIcon />
      </button>
      <button
        type="submit"
        className={`composer-action composer-send ${canCancel ? "cancel" : ""}`}
        onClick={canCancel ? () => void onCancel() : (event) => void submit(event)}
        disabled={!canCancel && (!canSend || momPending)}
        title={canCancel ? "Cancel response" : "Send message"}
      >
        {canCancel ? <StopIcon /> : <SendIcon />}
      </button>
    </form>
  );
}

function MicIcon(): React.ReactElement {
  return (
    <svg className="composer-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
      <path d="M18 11a6 6 0 0 1-12 0" />
      <path d="M12 17v4" />
      <path d="M9 21h6" />
    </svg>
  );
}

function RecordIcon(): React.ReactElement {
  return (
    <svg className="composer-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2.4" />
    </svg>
  );
}

function SendIcon(): React.ReactElement {
  return (
    <svg className="composer-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 19V5" />
      <path d="m6.5 10.5 5.5-5.5 5.5 5.5" />
    </svg>
  );
}

function PaperclipIcon(): React.ReactElement {
  return (
    <svg className="composer-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m21.4 11.6-8.8 8.8a6 6 0 0 1-8.5-8.5l9.3-9.3a4 4 0 0 1 5.7 5.7l-9.3 9.3a2 2 0 0 1-2.8-2.8l8.6-8.6" />
    </svg>
  );
}

function StopIcon(): React.ReactElement {
  return (
    <svg className="composer-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="8" y="8" width="8" height="8" rx="1.4" />
    </svg>
  );
}

async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function audioBlobUrl(audioBase64: string, audioFormat: string): string {
  const binary = atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return URL.createObjectURL(new Blob([bytes], { type: audioFormat }));
}

function groupRecommendations(items: InsightReport["models"]["recommendations"]): {
  recommended: InsightReport["models"]["recommendations"];
  limited: InsightReport["models"]["recommendations"];
  notRecommended: InsightReport["models"]["recommendations"];
} {
  return {
    recommended: items.filter((item) => item.status === "recommended"),
    limited: items.filter((item) => item.status === "limited" || item.status === "available"),
    notRecommended: items.filter((item) => item.status !== "recommended" && item.status !== "limited" && item.status !== "available")
  };
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "unknown";
  }
  const gib = value / 1024 ** 3;
  return `${gib.toFixed(gib >= 10 ? 0 : 1)} GiB`;
}

function formatAttachmentSize(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KiB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function upsertAttachment(current: ConversationAttachment[], next: ConversationAttachment): ConversationAttachment[] {
  if (current.some((item) => item.attachment_id === next.attachment_id)) {
    return current;
  }
  return [...current, next];
}

function MessageAttachments({ attachments }: { attachments: unknown }): React.ReactElement | null {
  if (!Array.isArray(attachments) || attachments.length === 0) {
    return null;
  }
  return (
    <div className="message-attachments" aria-label="Message attachments">
      {attachments.map((attachment) => {
        const item = attachment as Partial<ConversationAttachment>;
        if (!item.attachment_id || !item.filename) {
          return null;
        }
        return (
          <div key={item.attachment_id} className="message-attachment">
            <span>Attachment</span>
            <strong>{item.filename}</strong>
            {typeof item.size === "number" ? <small>{formatAttachmentSize(item.size)}</small> : null}
          </div>
        );
      })}
    </div>
  );
}

function modelFootprint(item: InsightReport["models"]["recommendations"][number]): string {
  const parts = [];
  if (item.estimated_ram_gb !== null && item.estimated_ram_gb !== undefined) {
    parts.push(`${item.estimated_ram_gb} GB RAM`);
  }
  if (item.estimated_vram_gb !== null && item.estimated_vram_gb !== undefined) {
    parts.push(`${item.estimated_vram_gb} GB VRAM`);
  }
  return parts.length > 0 ? parts.join(" · ") : "No backend footprint estimate";
}

function recommendationSource(item: InsightReport["models"]["recommendations"][number]): string {
  return item.source ? ` · ${item.source}` : "";
}

function settingsChangesFromSnapshot(
  snapshot: SettingsSnapshot | null,
  frontendSettings: FrontendSettingsPreferences
): SettingsChanges {
  const defaults = snapshot?.models.defaults;
  const setting = snapshot?.models.provider_settings.find((item) => item.provider_id === defaults?.default_provider);
  const voice = snapshot?.voice.settings;
  return {
    agentName: snapshot?.personalization?.display_name ?? "",
    personality: snapshot?.personalization?.system_prompt ?? "",
    defaultProvider: defaults?.default_provider ?? "",
    defaultModel: defaults?.default_chat_model ?? "",
    providerEnabled: setting?.enabled ?? false,
    providerEndpoint: setting?.endpoint ?? "",
    voiceEnabled: voice?.enabled ?? true,
    sttProvider: voice?.stt_provider_id ?? "",
    sttModel: voice?.stt_model ?? "base",
    language: voice?.language ?? "pt-BR",
    ttsProvider: voice?.tts_provider_id ?? "",
    defaultTtsVoice: voice?.default_tts_voice ?? "",
    preferredVoiceGender: voice?.preferred_voice_gender ?? "",
    vadEnabled: voice?.vad_enabled ?? true,
    storeRawAudio: voice?.store_raw_audio ?? false,
    reducedMotion: frontendSettings.reducedMotion,
    theme: "synapse"
  };
}

function validateModelSelection(snapshot: SettingsSnapshot, providerId: string | null, modelName: string | null): void {
  if (!providerId && modelName) {
    throw new Error("Select a provider before selecting a model.");
  }
  if (providerId && !snapshot.models.providers.some((provider) => provider.provider_id === providerId)) {
    throw new Error("Selected provider is not available in the backend model registry.");
  }
  if (providerId && modelName) {
    const valid = snapshot.models.catalog.some(
      (model) => model.provider === providerId && model.name === modelName && model.status !== "unavailable"
    );
    if (!valid) {
      throw new Error("Selected model is not available for the selected provider.");
    }
  }
}

function providerKey(provider: Record<string, unknown>, index: number): string {
  const id = provider.provider_id ?? provider.id ?? provider.name;
  return typeof id === "string" ? id : `provider-${index}`;
}

function providerLabel(provider: Record<string, unknown>): string {
  const name = provider.display_name ?? provider.provider_id ?? provider.name ?? "provider";
  const status = provider.status ?? provider.availability_state ?? provider.active;
  return `${String(name)}${status === undefined ? "" : ` · ${String(status)}`}`;
}

function CenteredStatus({ title, detail }: { title: string; detail: string }): React.ReactElement {
  return (
    <main className="centered-status">
      <h1>{title}</h1>
      <p>{detail}</p>
    </main>
  );
}

function notificationStatusLabel(status: AppState["notificationsStatus"], notifications: NotificationRecord[]): string {
  if (status === "ready" || status === "degraded") {
    const unread = notifications.filter((notification) => !notification.read).length;
    return unread > 0 ? `${unread} unread` : `${notifications.length} read`;
  }
  return status;
}

function historyStatusLabel(status: AppState["historyStatus"], conversations: ConversationIndexItem[]): string {
  if (status === "ready") {
    return `${conversations.length} conversations`;
  }
  return status;
}

function projectFilesStatusLabel(
  status: AppState["projectFilesStatus"],
  documentCount: number,
  projectId: string | null
): string {
  if (!projectId) return "No active project";
  if (status === "ready") return `${documentCount} uploaded files`;
  if (status === "empty") return "No uploaded files";
  return status;
}

function formatModelTelemetry(entries: LMStudioTelemetryEntry[]): string[] {
  return entries.slice(-80).map((entry) => {
    if (entry.raw_line) return entry.raw_line;
    const timestamp = formatTelemetryTimestamp(entry.occurred_at);
    const level = entry.status === "completed" ? "INFO" : "DEBUG";
    const model = entry.model_name ? `[${entry.model_name}] ` : "";
    const parts = [];
    const phase = entry.phase ? entry.phase.replace(/_/g, " ") : null;
    const task = entry.current_task ?? entry.current_operation ?? null;
    if (phase) parts.push(phase);
    if (task) parts.push(task);
    if (typeof entry.input_count === "number" || typeof entry.output_count === "number" || typeof entry.total_count === "number") {
      parts.push(`tokens: prompt ${entry.input_count ?? "?"} | eval ${entry.output_count ?? "?"} | total ${entry.total_count ?? "?"}`);
    }
    if (typeof entry.latency_ms === "number") parts.push(`total time ${(entry.latency_ms / 1000).toFixed(2)}s`);
    if (typeof entry.first_output_ms === "number") parts.push(`first token ${entry.first_output_ms}ms`);
    if (typeof entry.output_rate === "number") parts.push(`${entry.output_rate.toFixed(2)} tokens/s`);
    return `${timestamp} [${level}] ${model}${parts.length > 0 ? parts.join(" | ") : "native telemetry event"}`;
  });
}

function formatTelemetryTimestamp(value: string | undefined): string {
  if (!value) return new Date().toISOString().replace("T", " ").slice(0, 19);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.replace("T", " ").slice(0, 19);
  return parsed.toISOString().replace("T", " ").slice(0, 19);
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function readableError(error: unknown): string {
  if (error instanceof SynapseClientError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function primaryModelOption(options: ProviderModelOption[]): ProviderModelOption | null {
  return (
    options.find((option) => option.is_default) ??
    options.find((option) => option.provider_active && option.provider_status === "ready" && option.model_status === "ready") ??
    options[0] ??
    null
  );
}

function toReactConversationState(snapshot: {
  status: ConversationRuntimeState;
  messages: ConversationMessage[];
  partialAssistant: string;
  error: FrontendConversationError | null;
  lastDraft: string;
}): Pick<AppState, "conversationStatus" | "messages" | "streamText" | "conversationError" | "lastDraft"> {
  return {
    conversationStatus: snapshot.status,
    messages: snapshot.messages,
    streamText: snapshot.partialAssistant,
    conversationError: snapshot.error,
    lastDraft: snapshot.lastDraft
  };
}

function slugify(value: string): string {
  const slug = value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return slug || "synapse";
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <ShellErrorBoundary>
    <App />
  </ShellErrorBoundary>
);
