import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(__dirname, "..");

function read(path: string): string {
  return readFileSync(resolve(root, path), "utf-8");
}

describe("minimal secure desktop shell", () => {
  it("keeps Presence textless and reacts to measured speech without restarting the canvas", () => {
    const presence = read("src/renderer/Presence.tsx");
    expect(presence).not.toContain("presence-identity");
    expect(presence).not.toContain("presenceDisplayStatus");
    expect(presence).toContain("presence-accessible-state");
    expect(presence).toContain('current.state === "speaking" ? current.amplitude : 0');
    expect(presence).toContain("sceneRef.current");
    expect(presence).toContain("amplitude * 0.65");
    const playback = read("src/renderer/main.tsx").split("function startPlaybackAmplitudeMeter")[1].split("function pumpAmplitude")[0];
    expect(playback).toContain("createMediaElementSource(audio)");
    expect(playback).not.toContain('"speaking", 0.42');
  });
  it("reopens the conversation with an accessible message icon", () => {
    const renderer = read("src/renderer/main.tsx");
    const button = renderer.split('className="log-reopen"')[1].split("</button>")[0];
    expect(button).toContain('onClick={onToggle}');
    expect(button).toContain('aria-label="Mostrar mensagens"');
    expect(button).toContain('title="Mostrar mensagens"');
    expect(button).toContain("<svg");
    expect(button).toContain('aria-hidden="true"');
    expect(button).not.toMatch(/>\s*Log\s*</);
  });
  it("keeps constellation framing fixed without a visible title or zoom controls", () => {
    const view = read("src/renderer/ActivityConstellation.tsx");
    expect(view).not.toContain("<h2>Constelação</h2>");
    expect(view).not.toContain("Diminuir zoom");
    expect(view).not.toContain("Aumentar zoom");
    expect(view).not.toContain("Enquadrar");
    expect(view).toContain("Fechar registro");
    expect(view).toContain("constellation-accessible-nodes");
  });
  it("offers microphone mute without stopping conversation and fences late capture", () => {
    const renderer = read("src/renderer/main.tsx");
    expect(renderer).toContain('"Ativar microfone" : "Silenciar microfone"');
    expect(renderer).toContain("aria-pressed={conversationModeRunning ? microphoneMuted : undefined}");
    expect(renderer).toContain("microphoneEpoch !== microphoneEpochRef.current");
    expect(renderer).toContain("captureEpoch !== microphoneEpochRef.current");
    expect(renderer).toContain("if (microphoneMutedRef.current) return;");
    const mute = renderer.split("function toggleMicrophoneMute(): void {")[1].split("function cleanupConversationModePlayback")[0];
    expect(mute).toContain("cancelVoiceRecording()");
    expect(mute).not.toContain("stopConversationMode(");
    expect(mute).not.toContain("cleanupConversationModePlayback()");
    expect(mute).toContain("!conversationModeRequestRef.current && !playbackRef.current");
    const recovery = renderer.split("function recoverConversationModeTurnError(error: unknown): void {")[1].split("function scheduleConversationModeListening")[0];
    expect(recovery).toContain("conversationModeRequestRef.current = null;");
  });
  it("keeps voice feedback out of the composer control grid with bounded scrolling", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");
    expect(renderer).toContain('className="composer-voice-feedback"');
    expect(renderer).toContain('className="voice-understanding"');
    const feedback = css.match(/\.composer-voice-feedback\s*\{([^}]+)\}/)?.[1];
    expect(feedback).toContain("position: absolute");
    expect(feedback).toContain("max-height:");
    expect(feedback).toContain("overflow-y: auto");
  });
  it("uses bounded theme backgrounds while preserving quiet settings surfaces", () => {
    const css = read("src/renderer/styles.css");
    const engine = read("src/renderer/themeEngine.css");
    expect(css).not.toContain('url("../../assets/media/synapse-nebula-background.png")');
    expect(css).toContain(".center-surface::before");
    expect(engine).toContain("prefers-reduced-motion: reduce");
    expect(engine).toContain("radial-gradient(ellipse at 0% 0%, #000");
    expect(engine).toContain("color-mix(in srgb, var(--app-bg-deep) 88%, #000)");
    expect(engine).toContain("linear-gradient(90deg, var(--shell-gradient-start)");
    expect(engine).toContain("linear-gradient(180deg, var(--rail-gradient-start)");
    expect(css).toContain(".settings-panel.settings-conservative {");
    expect(css).toContain("background: #22252b;");
  });
  it("uses the supplied workshop image with deterministic monitor effects", () => {
    const renderer = read("src/renderer/main.tsx");
    const atmosphere = read("src/renderer/SynapseCoreAtmosphere.tsx");
    const presence = read("src/renderer/Presence.tsx");
    const engine = read("src/renderer/themeEngine.css");

    expect(atmosphere).toContain("synapse-inventor-workshop.jpg");
    expect(atmosphere).toContain("workshopScreens");
    expect(atmosphere).toContain("drawWorkshopScreenEffects");
    expect(engine).toContain("synapse-core-atmosphere-image");
    expect(engine).toContain("pointer-events: none");
    expect(engine).toContain("opacity: 1;");
    expect(read("src/renderer/styles.css")).toContain("width: min(450px, 42vw, calc(100% - 36px), calc(100vh - 290px));");
    expect(presence).toContain("1.22");
  });
  it("places the brain toggle inside the composer control row", () => {
    const renderer = read("src/renderer/main.tsx");
    const toggle = read("src/renderer/MoMToggle.tsx");
    expect(toggle).toContain('className="brain-icon"');
    expect(toggle).toContain('aria-pressed={configuration?.resource_policy === "ECONOMICAL"}');
    expect(renderer.indexOf('<MoMToggle client=')).toBeGreaterThan(renderer.indexOf('onChange={(event) => changeText(event.target.value)}'));
    const modes = read("src/renderer/styles.css").match(/\.composer-modes\s*\{([^}]+)\}/)?.[1];
    expect(modes).not.toContain("position: absolute");
  });
  it("uses the canonical spatial structure from Slice 2", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("side-rail");
    expect(renderer).toContain("history-button");
    expect(renderer).toContain("LibraryPanel");
    expect(renderer).toContain("center-surface");
    expect(renderer).toContain("conversation-log");
    expect(renderer).toContain("lazy(() => import(\"./Presence\")");
    expect(renderer).toContain("lazy(() =>");
    expect(renderer).toContain("WorkspacePanel");
    expect(renderer).toContain("VisualErrorBoundary");
    expect(renderer).toContain("Suspense fallback");
    expect(renderer).toContain("<Presence scene={presenceScene} theme={state.frontendSettings.theme} reducedMotion={state.reducedMotion} focused={state.focused} />");
    expect(renderer).not.toContain("<ActivityConstellation");
    expect(renderer).not.toContain("Presence placeholder");
    expect(renderer).toContain("composer");
    expect(css).toContain("grid-template-columns: 54px minmax(0, 1fr)");
    expect(css).toContain(".app-shell.log-minimized");
    expect(css).toContain("bottom: 46px");
    expect(css).toContain("border-radius: 999px");
  });

  it("renders Conversation Log as floating solid bubbles over the workspace", () => {
    const css = read("src/renderer/styles.css");

    expect(css).toContain(".conversation-log");
    expect(css.match(/\.conversation-log\s*\{[^}]*z-index:\s*21;/s)?.[0]).toBeTruthy();
    expect(css).toContain("position: absolute");
    expect(css).toContain("right: 0");
    expect(css).toContain("bottom: 0");
    expect(css).toContain("background: transparent");
    expect(css).toContain(".conversation-log.is-faded");
    expect(css).toContain("background: #0a2029");
    expect(css).toContain("background: #123a43");
    expect(css).toContain("mask-image: linear-gradient");
    expect(css).not.toContain("grid-template-columns: 54px minmax(0, 1fr) 330px");
  });

  it("minimizes Conversation Log without preserving an empty right column", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("log-reopen");
    expect(renderer).toContain("messages={state.messages}");
    expect(renderer).toContain("streamText={state.streamText}");
    expect(renderer).toContain("runtimeStatus={state.conversationStatus}");
    expect(renderer).toContain("runtimeError={state.conversationError}");
    expect(css).toContain(".app-shell.log-minimized");
    expect(css).toContain("grid-template-columns: 54px minmax(0, 1fr)");
    expect(css).toContain(".log-reopen");
    expect(css.match(/\.log-reopen\s*\{[^}]*z-index:\s*9;/s)?.[0]).toBeTruthy();
    expect(css).toContain("position: absolute");
  });

  it("keeps launch, Library and New Chat separated from active conversation messages", () => {
    const renderer = read("src/renderer/main.tsx");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");

    expect(renderer).toContain("conversationIndex");
    expect(renderer).toContain("historyPanelOpen");
    expect(renderer).toContain("librarySection");
    expect(renderer).toContain("messages: []");
    expect(renderer).toContain("openNewConversation");
    expect(renderer).toContain("openConversationFromHistory");
    expect(renderer).toContain("current.conversation?.conversation_id !== conversationId");
    expect(renderer).toContain("event.conversation_id && event.conversation_id !== conversationId");
    expect(renderer).toContain("New Chat");
    expect(renderer).toContain("Persisted conversations");
    expect(client).toContain("conversationIndex");
    expect(client).toContain("/api/frontend/conversations?");
    expect(types).toContain("export interface ConversationIndex");
    expect(types).toContain("export interface ConversationIndexItem");
  });

  it("uses theme-compatible native control styling for Settings selects", () => {
    const css = read("src/renderer/styles.css");

    expect(css).toContain("color-scheme: dark");
    expect(css).toContain("--control-bg");
    expect(css).toContain("--control-disabled");
    expect(css).toContain("option:checked");
    expect(css).toContain("option:disabled");
    expect(css).toContain(".settings-card select:focus");
    expect(css).not.toContain("option {\\n  color: black;");
  });

  it("preserves auto-scroll only while the user is at the end", () => {
    const renderer = read("src/renderer/main.tsx");

    expect(renderer).toContain("autoScrollRef");
    expect(renderer).toContain("distanceFromBottom < 24");
    expect(renderer).toContain("list.scrollTop = list.scrollHeight");
    expect(renderer).toContain("onScroll={rememberScrollPosition}");
  });

  it("keeps pagination, summaries and cancellation inside the approved conversation surfaces", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("Load older messages");
    expect(renderer).toContain("summary?.summary");
    expect(renderer).toContain("canCancel");
    expect(renderer).toContain("cancelTextTurn");
    expect(css).toContain(".load-older");
    expect(css).toContain(".message.summary");
  });

  it("prevents rapid double submit and restores failed draft safely", () => {
    const renderer = read("src/renderer/main.tsx");

    expect(renderer).toContain('state.conversationStatus === "sending"');
    expect(renderer).toContain('state.conversationStatus === "streaming"');
    expect(renderer).toContain('onClick={canCancel ? () => void onCancel() : (event) => void submit(event)}');
    expect(renderer).toContain("failedDraft");
    expect(renderer).toContain("setText(\"\")");
  });

  it("keeps the attached panel responsive and shifts the composer with Presence", () => {
    const css = read("src/renderer/styles.css");

    expect(css).toContain("top: 54px");
    expect(css).toContain("max-width: calc(100vw - 96px)");
    expect(css).toContain("@media (max-width: 920px)");
    expect(css).toContain(".main-area.log-open .composer");
    expect(css).toContain("width: min(500px, calc(100vw - 104px))");
  });

  it("keeps only out-of-scope controls disabled instead of fake-operational", () => {
    const renderer = read("src/renderer/main.tsx");

    expect(renderer).toContain("workspace-button");
    expect(renderer).toContain('aria-pressed={state.workspaceOpen}');
    expect(renderer).not.toContain("Open Insight");
    expect(renderer).toContain("Open Settings");
    expect(renderer).not.toContain("Settings unavailable in this slice");
    expect(renderer).toContain("Record voice for transcription");
    expect(renderer).toContain("Start Conversation Mode");
  });

  it("keeps Workspace CLI responses in the terminal surface", () => {
    const renderer = read("src/renderer/main.tsx");

    expect(renderer).toContain('onSubmitWork={(request) => void sendMessage(request, [], "workspace")}');
    expect(renderer).toContain("workspaceCommandOutput: [...current.workspaceCommandOutput");
    expect(renderer).toContain("if (workspaceSurface)");
    expect(renderer).toContain("workspaceCommandOutput: current.workspaceCommandOutput.map");
  });

  it("keeps Insight inside Settings instead of a separate sidebar panel", () => {
    const renderer = read("src/renderer/main.tsx");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");
    const css = read("src/renderer/styles.css");

    expect(client).toContain('"/api/insight/report"');
    expect(types).toContain("export interface InsightReport");
    expect(types).toContain("export interface InsightHardwareSnapshot");
    expect(types).toContain("export interface InsightModelRecommendation");
    expect(renderer).toContain("InsightContent");
    expect(renderer).toContain('aria-label="Settings Insight"');
    expect(renderer).toContain('Settings section ${sectionLabel(section)}');
    expect(renderer).toContain("onRefreshInsight");
    expect(renderer).not.toContain("onToggleInsight");
    expect(renderer).not.toContain("Open Insight");
    expect(renderer).not.toContain("Close Insight");
    expect(renderer).toContain("Recommended");
    expect(renderer).toContain("Possible with limitations");
    expect(renderer).toContain("Not recommended locally");
    expect(renderer).toContain("Recommendations are backend decisions, not installation claims.");
    expect(renderer).toContain("recommendationSource");
    expect(renderer).toContain("No GPU reported by backend hardware discovery.");
    expect(renderer).toContain("Available models");
    expect(renderer).toContain('insightStatus: unavailable ? "unavailable" : "error"');
    expect(css).toContain(".settings-insight .insight-content");
    expect(css).toContain(".settings-tabs");
  });

  it("opens Settings as an elevated internal surface backed only by real settings contracts", () => {
    const renderer = read("src/renderer/main.tsx");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");
    const preferences = read("src/shared/settingsPreferences.ts");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("SettingsPanel");
    expect(renderer).toContain("onToggleSettings");
    expect(renderer).toContain("onCloseSettings");
    expect(renderer).toContain("onRefreshSettings");
    expect(renderer).toContain("onSaveSettings");
    expect(renderer).toContain('event.key === "Escape"');
    expect(renderer).toContain('role="dialog"');
    expect(renderer).toContain('aria-modal="false"');
    expect(renderer).toContain("Voice");
    expect(renderer).toContain("Models");
    expect(renderer).toContain("Insight");
    expect(renderer).not.toContain("Settings General");
    expect(renderer).not.toContain('Settings section General');
    expect(renderer).toContain("Personalization");
    expect(renderer).toContain("Only real settings with active owners are shown.");
    expect(renderer).toContain("validateModelSelection");
    expect(renderer).toContain("Secrets are never displayed");
    expect(renderer).not.toContain("Privacy");
    expect(client).toContain("settingsSnapshot(agentId?: string)");
    expect(renderer).toContain('update("agentName", event.target.value)');
    expect(renderer).toContain('update("personality", event.target.value)');
    expect(client).toContain('this.url("/api/audio/synthesize")');
    expect(client).toContain('"/api/models/default"');
    expect(client).toContain('"/api/models/catalog"');
    expect(client).toContain('"/api/models/providers"');
    expect(client).toContain('"/api/provider-settings"');
    expect(client).toContain('"/api/voice/settings"');
    expect(client).toContain('"/api/voice/providers"');
    expect(client).toContain("method: \"PATCH\"");
    expect(types).toContain("export interface SettingsSnapshot");
    expect(types).toContain("export interface ProviderSetting");
    expect(types).toContain("export interface VoiceSettings");
    expect(preferences).toContain("synapse.frontend-v2.settings");
    expect(preferences).toContain("effectiveReducedMotion");
    expect(preferences).toContain("normalizeTheme");
    expect(css).toContain(".settings-panel");
    expect(css).toContain("position: absolute");
    expect(css).toContain("top: clamp(66px, 10vh, 96px)");
    expect(css).toContain("bottom: clamp(82px, 12vh, 118px)");
    expect(css).toContain(".settings-tabs");
    expect(css).toContain(".settings-body");
    expect(css).toContain(".settings-content");
    expect(css).toContain("grid-template-columns: 184px minmax(0, 1fr)");
    expect(renderer).toContain("SynapseCoreAtmosphere");
    expect(renderer).toContain("provider-facts");
    expect(renderer).toContain("voice-pack-grid");
    expect(renderer).toContain('aria-label="Default Voice Pack voices"');
    expect(renderer).toContain('className="voice-card-actions"');
    expect(renderer).toContain("activeSection === \"models\" && !snapshot");
    expect(renderer).toContain("activeSection === \"voice\" && !snapshot");
  });

  it("supports explicit recording without adding a separate voice conversation surface", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("navigator.mediaDevices.getUserMedia({ audio: true })");
    expect(renderer).toContain("new MediaRecorder(stream)");
    expect(renderer).toContain("stopVoiceRecording");
    expect(renderer).toContain("cancelVoiceRecording");
    expect(renderer).toContain("mergeTranscriptionIntoDraft");
    expect(renderer).toContain("onTranscribeVoice");
    expect(css).toContain(".voice-status");
  });

  it("keeps manual transcription and Conversation Mode as distinct composer controls", () => {
    const renderer = read("src/renderer/main.tsx");

    expect(renderer).toContain("onConversationVoiceTurn");
    expect(renderer).toContain("conversationModeState");
    expect(renderer).toContain("Start Conversation Mode");
    expect(renderer).toContain("Stop Conversation Mode");
    expect(renderer).toContain("Record voice for transcription");
    expect(renderer).toContain("conversationModeCapturesMicrophone");
    expect(renderer).toContain("conversationModeMinimumVoicePeak");
    expect(renderer).toContain("conversationModeRestartDelayMs");
    expect(renderer).toContain("playConversationModeAudio");
    expect(renderer).toContain("audioBlobUrl");
    expect(renderer).toContain("URL.revokeObjectURL");
    expect(renderer).toContain("cleanupConversationModePlayback");
  });

  it("renders factual Presence through one procedural canvas layer without Pixi overlap", () => {
    const renderer = read("src/renderer/main.tsx");
    const presence = read("src/renderer/Presence.tsx");
    const adapter = read("src/shared/presenceAdapter.ts");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("derivePresenceState");
    expect(renderer).toContain("VisualLoadingFallback");
    expect(renderer).toContain("onPresenceChange={updatePresenceFacts}");
    expect(renderer).toContain("startAmplitudeMeter");
    expect(renderer).toContain("startPlaybackAmplitudeMeter");
    expect(presence).not.toContain('from "pixi.js"');
    expect(presence).not.toContain("new Application()");
    expect(presence).toContain("presence-canvas");
    expect(presence).toContain("makeParticles(340)");
    expect(presence).toContain("requestAnimationFrame");
    expect(presence).toContain("drawTechnicalRing");
    expect(presence).toContain("presence-accessible-state");
    expect(adapter).toContain('"listening"');
    expect(adapter).toContain('"transcribing"');
    expect(adapter).toContain('"processing"');
    expect(adapter).toContain('"speaking"');
    expect(css).toContain(".presence");
    expect(css).toContain(".presence-canvas");
    expect(css).toContain(".visual-fallback");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });

  it("keeps factual Activity wired to the live constellation renderer", () => {
    const renderer = read("src/renderer/main.tsx");
    const activity = read("src/renderer/ActivityConstellation.tsx");
    const adapter = read("src/shared/activityAdapter.ts");
    const client = read("src/shared/frontendClient.ts");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("activeVisual");
    expect(renderer).toContain("activitySnapshot(activityProjectId)");
    expect(renderer).toContain("openActivityStream");
    expect(renderer).toContain("applyActivityEvent");
    expect(renderer).toContain("deriveActivityScene");
    expect(client).toContain("/api/projects/");
    expect(client).toContain("/activity/stream");
    expect(activity).toContain("ConstellationCanvas");
    expect(activity).toContain("constellation-canvas");
    expect(activity).toContain("canvas.destroy()");
    expect(activity).toContain("modelSummary");
    expect(activity).toContain("activity-work-log");
    expect(activity).toContain("selectedNode.metadata.title");
    expect(activity).not.toContain("Constellation arrives in the next version");
    expect(activity).not.toContain("Graph preview paused");
    expect(adapter).toContain("parentEntityId");
    expect(adapter).toContain("withBaselineActivityState");
    expect(activity).toContain("activityStatus(scene)");
    expect(adapter).toContain("activityPerformanceBudget");
    expect(adapter).toContain("aggregate:overflow");
    expect(adapter).toContain("activity resync required");
    expect(css).toContain(".activity-view");
    expect(css).toContain(".activity-svg");
    expect(css).not.toContain(".activity-preview-card");
  });

  it("keeps heavy visualization modules outside the startup path", () => {
    const renderer = read("src/renderer/main.tsx");
    const presence = read("src/renderer/Presence.tsx");
    const activity = read("src/renderer/ActivityConstellation.tsx");

    expect(renderer).not.toContain('from "./Presence"');
    expect(renderer).not.toContain('from "./ActivityConstellation"');
    expect(renderer).toContain("const Presence = lazy");
    expect(renderer).not.toContain("const ActivityConstellation = lazy");
    expect(renderer).toContain("VisualErrorBoundary");
    expect(renderer).toContain("Suspense");
    expect(presence).not.toContain('from "pixi.js"');
    expect(activity).not.toContain('from "pixi.js"');
  });

  it("enforces Electron security settings and allowlisted IPC", () => {
    const main = read("src/main/main.ts");
    const preload = read("src/preload/preload.ts");
    const preloadWriter = read("scripts/write-preload-cjs.mjs");
    const html = read("src/renderer/index.html");

    expect(main).toContain("frame: false");
    expect(main).toContain("contextIsolation: true");
    expect(main).toContain("sandbox: true");
    expect(main).toContain("nodeIntegration: false");
    expect(main).toContain('appendSwitch("autoplay-policy", "no-user-gesture-required")');
    expect(main).toContain("../preload/preload.cjs");
    expect(preload).toContain("contextBridge.exposeInMainWorld");
    expect(preload).toContain("synapse:window:minimize");
    expect(preload).toContain("synapse:window:toggle-maximize");
    expect(preload).toContain("synapse:window:is-maximized");
    expect(preload).toContain("synapse:window:maximized-changed");
    expect(preload).toContain("synapse:attachment:pick-file");
    expect(preloadWriter).toContain("pickAttachmentFile");
    expect(preloadWriter).toContain("synapse:attachment:pick-file");
    expect(preload).not.toContain("send(");
    expect(html).toContain("Content-Security-Policy");
  });

  it("stages attachments through governed picker and backend refs without exposing local paths", () => {
    const main = read("src/main/main.ts");
    const preload = read("src/preload/preload.ts");
    const renderer = read("src/renderer/main.tsx");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");
    const css = read("src/renderer/styles.css");

    expect(main).toContain('ipcMain.handle("synapse:attachment:pick-file"');
    expect(main).toContain("dialog.showOpenDialog");
    expect(main).toContain('properties: ["openFile"]');
    expect(main).toContain('selectedPath.startsWith("\\\\\\\\")');
    expect(main).toContain("before.isSymbolicLink()");
    expect(main).toContain("File changed during selection");
    expect(preload).toContain("pickAttachmentFile");
    expect(renderer).toContain("pickAndStageAttachment");
    expect(renderer).toContain("onStageAttachment");
    expect(renderer).toContain("stageAttachment");
    expect(renderer).toContain("attachment-chip");
    expect(renderer).toContain("MessageAttachments");
    expect(renderer).toContain("attachments,");
    expect(client).toContain("/attachments/stage");
    expect(types).toContain("export interface AttachmentStageResult");
    expect(types).toContain("export interface ConversationAttachment");
    expect(css).toContain(".attachment-tray");
    expect(css).toContain(".message-attachments");
    expect(renderer).not.toContain("webkitdirectory");
  });

  it("wires custom window controls through explicit IPC and the sender BrowserWindow", () => {
    const main = read("src/main/main.ts");
    const preload = read("src/preload/preload.ts");
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");
    const packageJson = read("package.json");
    const preloadWriter = read("scripts/write-preload-cjs.mjs");

    expect(main).toContain('ipcMain.handle("synapse:window:minimize", (event)');
    expect(main).toContain("BrowserWindow.fromWebContents(event.sender)?.minimize()");
    expect(main).toContain('ipcMain.handle("synapse:window:toggle-maximize", (event)');
    expect(main).toContain("BrowserWindow.fromWebContents(event.sender)");
    expect(main).toContain("window.unmaximize()");
    expect(main).toContain("window.maximize()");
    expect(main).toContain('ipcMain.handle("synapse:window:is-maximized", (event)');
    expect(main).toContain('ipcMain.handle("synapse:window:close", (event)');
    expect(main).toContain("BrowserWindow.fromWebContents(event.sender)?.hide()");
    expect(main).toContain("new Tray(image)");
    expect(main).toContain('label: "Abrir Synapse"');
    expect(main).toContain('label: "Sair"');
    expect(main).toContain('window.on("maximize"');
    expect(main).toContain('window.on("unmaximize"');
    expect(main).toContain("synapse:window:maximized-changed");
    expect(preload).toContain("onMaximizedChange");
    expect(preload).not.toContain("execute(action");
    expect(renderer).toContain("window.synapse?.window.isMaximized()");
    expect(renderer).toContain("window.synapse?.window.onMaximizedChange");
    expect(renderer).toContain('aria-label={maximized ? "Restore" : "Maximize"}');
    expect(renderer).toContain('onDoubleClick={() => void toggleMaximize()}');
    expect(renderer).toContain("event.stopPropagation()");
    expect(css).toContain("-webkit-app-region: drag");
    expect(css).toContain("-webkit-app-region: no-drag");
    expect(packageJson).toContain("write-preload-cjs.mjs");
    expect(preloadWriter).toContain('require("electron")');
    expect(preloadWriter).toContain("contextBridge.exposeInMainWorld");
    expect(preloadWriter).toContain("synapse:window:is-maximized");
  });

  it("uses the approved icon in Electron without adding renderer authority", () => {
    const main = read("src/main/main.ts");

    expect(main).toContain("assets/icons/synapse.ico");
    expect(main).toContain("icon: iconPath");
  });

  it("keeps slash command discovery as composer-local surface", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("command-discovery");
    expect(renderer).toContain("Slash command discovery");
    expect(renderer).toContain("onKeyDown={handleKeyDown}");
    expect(renderer).toContain('event.key === "Escape"');
    expect(renderer).toContain('event.key === "ArrowDown"');
    expect(renderer).toContain('event.key === "ArrowUp"');
    expect(css).toContain(".command-discovery");
    expect(css).toContain("bottom: calc(100% + 10px)");
  });

  it("routes slash intents through typed command execution instead of the conversation log", () => {
    const renderer = read("src/renderer/main.tsx");
    const discovery = read("src/shared/commandDiscovery.ts");
    const client = read("src/shared/frontendClient.ts");
    const css = read("src/renderer/styles.css");

    expect(discovery).toContain("buildCommandRegistry");
    expect(discovery).toContain("resolveSlashIntent");
    expect(discovery).toContain('execution_kind: "ui"');
    expect(discovery).toContain('execution_kind: "project_scope"');
    expect(discovery).toContain('execution_kind: "unsupported"');
    expect(discovery).toContain("isSafeProjectId");
    expect(renderer).toContain("executeCommand");
    expect(renderer).toContain("onExecuteCommand");
    expect(renderer).toContain('command === "activity"');
    expect(renderer).toContain('command === "insight"');
    expect(renderer).toContain('command === "settings"');
    expect(renderer).toContain('command === "project"');
    expect(renderer).toContain("client.project(projectId)");
    expect(renderer).toContain("project_id: projectId");
    expect(renderer).toContain("command-status");
    expect(renderer).not.toContain("await onSend(content);\\n      setText(\"\");\\n    } finally");
    expect(client).toContain('"/api/projects"');
    expect(client).toContain("/api/projects/${encodeURIComponent(projectId)}");
    expect(css).toContain(".command-status.completed");
    expect(css).toContain(".command-status.failed");
  });

  it("renders factual notifications from backend contracts as a header popover", () => {
    const renderer = read("src/renderer/main.tsx");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("NotificationsPanel");
    expect(renderer).toContain("notification-button");
    expect(renderer).toContain("notification-badge");
    expect(renderer).toContain("notificationsOpen");
    expect(renderer).toContain('event.key === "Escape"');
    expect(renderer).toContain('event.key === "ArrowDown"');
    expect(renderer).toContain('event.key === "ArrowUp"');
    expect(renderer).toContain("Mark read");
    expect(renderer).toContain("Dismiss");
    expect(renderer).toContain("Approval required is factual here; resolving remains owned by the approvals flow.");
    expect(renderer).toContain('notificationsStatus: "degraded"');
    expect(renderer).toContain('notificationsStatus: current.notifications.length > 0 ? "degraded" : "error"');
    expect(client).toContain('"/api/notifications"');
    expect(client).toContain("/read`");
    expect(client).toContain('method: "DELETE"');
    expect(types).toContain("export interface NotificationRecord");
    expect(types).toContain(' | "approval"');
    expect(css).toContain(".notifications-panel");
    expect(css).toContain("position: absolute");
    expect(css).toContain("top: 52px");
    expect(css).toContain("right: clamp(18px, 3vw, 34px)");
    expect(css).toContain("max-height: min(560px, calc(100vh - 132px))");
    expect(css).not.toContain(".side-rail .notifications");
  });

  it("renders Project Files inside Library without running retrieval", () => {
    const renderer = read("src/renderer/main.tsx");
    const discovery = read("src/shared/commandDiscovery.ts");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");
    const css = read("src/renderer/styles.css");

    expect(discovery).toContain('tool_id: "project.files"');
    expect(discovery).toContain('opens_surface: "project_files"');
    expect(renderer).toContain("<LibraryPanel");
    expect(renderer).toContain("Histórico de chat");
    expect(renderer).toContain("Arquivos enviados");
    expect(renderer).toContain("ProjectFilesPanel");
    expect(renderer).toContain("projectFilesOpen");
    expect(renderer).toContain("state.bootstrap?.project_id, state.projectFilesOpen");
    expect(renderer).toContain("Library opened on Project Files without running retrieval.");
    expect(renderer).toContain("text.trim().length > 0 || attachments.length > 0");
    expect(renderer).toContain("Abrir/listar arquivos não executa retrieval nem gera embedding de query.");
    expect(renderer).toContain("Reindexar");
    expect(renderer).toContain("Remover");
    expect(renderer).toContain("Busca semântica local");
    expect(renderer).toContain("Fallback lexical continua disponível quando factual.");
    expect(client).toContain("projectKnowledgeDocuments(projectId");
    expect(client).toContain("/api/project-knowledge/documents?");
    expect(client).toContain("/reindex`");
    expect(client).toContain("/remove`");
    expect(client).not.toContain("/api/project-knowledge/query");
    expect(types).toContain("ProjectKnowledgeDocumentsResult");
    expect(types).toContain("ProjectKnowledgeSemanticStatus");
    expect(css).toContain(".library-tabs");
    expect(css).toContain(".project-files-panel");
    expect(css).toContain(".project-files-panel.embedded");
    expect(css).toContain(".project-files-list");
    expect(css).toContain("overflow: auto");
  });

  it("applies theme changes to the shell icon components immediately", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("onPreviewFrontendSettings");
    expect(renderer).toContain('aria-label={`Backend status: ${state}`}');
    expect(renderer).not.toContain('<div className={`backend-pill ${state}`}>{state}</div>');
    expect(renderer).toContain("const shellIcons = assetsForTheme(state.frontendSettings.theme)");
    expect(renderer).toContain("iconVisualOffsets");
    expect(renderer).toContain('type ShellIconVisualKey = "constellation" | "history" | "settings" | "notificationsIdle" | "notificationsActive"');
    expect(renderer).toContain("shellIconStyle");
    expect(renderer).toContain("workspace-button");
    expect(renderer).toContain("src={shellIcons.navigation.history}");
    expect(renderer).toContain("src={shellIcons.navigation.settings}");
    expect(renderer).toContain("shell-nav-icon-frame");
    expect(renderer).not.toContain("shell-nav-icon shell-nav-icon--activity");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--history");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--settings");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--notifications");
    expect(renderer).toContain("assetsForTheme(theme).notifications");
    expect(renderer).toContain('shellIconStyle(unreadNotifications > 0 ? "notificationsActive" : "notificationsIdle")');
    expect(css).toContain("--shell-nav-bg");
    expect(css).toContain("--shell-nav-bg-hover");
    expect(css).toContain("--shell-nav-bg-active");
    expect(css).toContain("--shell-nav-border");
    expect(css).toContain("color: var(--primary-accent)");
    expect(css).toContain("background: color-mix(in srgb, var(--shell-nav-bg) 72%, transparent)");
    expect(css).toContain(".backend-pill::before");
    expect(css).toContain("font-size: 0");
    expect(css).toContain(".backend-pill.degraded");
    expect(css).toContain(".backend-pill.connecting");
    expect(css).toContain(".shell-nav-icon-frame");
    expect(css).toContain(".shell-nav-icon");
    expect(css).toContain("drop-shadow(1px 0 0 rgba(0, 0, 0, 0.9))");
    expect(css).toContain("transform: translate(var(--shell-icon-x, 0), var(--shell-icon-y, 0)) scale(var(--shell-icon-scale, 1))");
  });

  it("keeps the root launcher synchronized with the current frontend build", () => {
    const packageJson = read("package.json");
    const launcher = read("scripts/build-root-launcher.ps1");

    expect(packageJson).toContain("build:root-exe");
    expect(launcher).toContain("apps\\frontend-v2");
    expect(launcher).toContain("dist\\main\\main\\main.js");
    expect(launcher).toContain("Synapse.exe");
    expect(launcher).toContain("electron.exe");
    expect(packageJson).not.toContain("package:win");
    expect(packageJson).not.toContain("release:artifacts");
    expect(packageJson).not.toContain("electron-builder");
    expect(packageJson).not.toContain("nsis");
    expect(packageJson).not.toContain("Synapse-Setup");
  });
});
