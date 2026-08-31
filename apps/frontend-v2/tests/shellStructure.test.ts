import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(__dirname, "..");

function read(path: string): string {
  return readFileSync(resolve(root, path), "utf-8");
}

describe("minimal secure desktop shell", () => {
  it("uses the canonical spatial structure from Slice 2", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("side-rail");
    expect(renderer).toContain("history-button");
    expect(renderer).toContain("HistoryPanel");
    expect(renderer).toContain("center-surface");
    expect(renderer).toContain("conversation-log");
    expect(renderer).toContain("lazy(() => import(\"./Presence\")");
    expect(renderer).toContain("lazy(() =>");
    expect(renderer).toContain("import(\"./ActivityConstellation\")");
    expect(renderer).toContain("VisualErrorBoundary");
    expect(renderer).toContain("Suspense fallback");
    expect(renderer).toContain("<Presence scene={presenceScene} theme={state.frontendSettings.theme} />");
    expect(renderer).toContain("<ActivityConstellation");
    expect(renderer).not.toContain("Presence placeholder");
    expect(renderer).toContain("composer");
    expect(css).toContain("grid-template-columns: 54px minmax(0, 1fr)");
    expect(css).toContain(".app-shell.log-minimized");
    expect(css).toContain("bottom: 46px");
    expect(css).toContain("border-radius: 999px");
  });

  it("renders Conversation Log as an elevated internal panel, not a rigid sidebar", () => {
    const css = read("src/renderer/styles.css");

    expect(css).toContain(".conversation-log");
    expect(css).toContain("position: absolute");
    expect(css).toContain("right: clamp(18px, 3vw, 36px)");
    expect(css).toContain("bottom: clamp(96px, 14vh, 126px)");
    expect(css).toContain("border-radius: 22px");
    expect(css).toContain("box-shadow:");
    expect(css).not.toContain("border-left: 1px solid rgba(142, 229, 237, 0.12)");
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
    expect(css).toContain("position: absolute");
  });

  it("keeps launch, History and New Chat separated from active conversation messages", () => {
    const renderer = read("src/renderer/main.tsx");
    const client = read("src/shared/frontendClient.ts");
    const types = read("src/shared/types.ts");

    expect(renderer).toContain("conversationIndex");
    expect(renderer).toContain("historyPanelOpen");
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

  it("keeps the elevated panel responsive and clear of the composer", () => {
    const css = read("src/renderer/styles.css");

    expect(css).toContain("top: clamp(62px, 8vh, 86px)");
    expect(css).toContain("max-width: calc(100vw - 96px)");
    expect(css).toContain("@media (max-width: 920px)");
    expect(css).toContain("bottom: 112px");
    expect(css).toContain("width: min(500px, calc(100vw - 104px))");
  });

  it("keeps only out-of-scope controls disabled instead of fake-operational", () => {
    const renderer = read("src/renderer/main.tsx");

    expect(renderer).toContain("Show Activity/Constellation");
    expect(renderer).toContain('aria-pressed={activeVisual === "activity"}');
    expect(renderer).not.toContain("Open Insight");
    expect(renderer).toContain("Open Settings");
    expect(renderer).not.toContain("Settings unavailable in this slice");
    expect(renderer).toContain("Record voice for transcription");
    expect(renderer).toContain("Start Conversation Mode");
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
    expect(renderer).toContain("Themes");
    expect(renderer).toContain("Models");
    expect(renderer).toContain("Insight");
    expect(renderer).not.toContain("Settings General");
    expect(renderer).not.toContain('Settings section General');
    expect(renderer).toContain("Personalization");
    expect(renderer).toContain("Only real settings with active owners are shown.");
    expect(renderer).toContain("validateModelSelection");
    expect(renderer).toContain("Secrets are never displayed");
    expect(renderer).not.toContain("Privacy");
    expect(client).toContain("settingsSnapshot()");
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
    expect(renderer).toContain("themeOptions");
    expect(renderer).toContain("theme-sample");
    expect(renderer).toContain("provider-facts");
    expect(renderer).toContain("voice-pack-grid");
    expect(renderer).toContain("Default Voice Pack discovery reports");
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
    expect(renderer).toContain('conversationModeState !== "inactive"');
    expect(renderer).toContain("playConversationModeAudio");
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
    expect(presence).toContain("presenceDisplayStatus");
    expect(adapter).toContain('"listening"');
    expect(adapter).toContain('"transcribing"');
    expect(adapter).toContain('"processing"');
    expect(adapter).toContain('"speaking"');
    expect(css).toContain(".presence");
    expect(css).toContain(".presence-canvas");
    expect(css).toContain(".visual-fallback");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });

  it("keeps factual Activity wired while parking the constellation graph for the next version", () => {
    const renderer = read("src/renderer/main.tsx");
    const activity = read("src/renderer/ActivityConstellation.tsx");
    const adapter = read("src/shared/activityAdapter.ts");
    const client = read("src/shared/frontendClient.ts");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("activeVisual");
    expect(renderer).toContain("activitySnapshot(projectId)");
    expect(renderer).toContain("openActivityStream");
    expect(renderer).toContain("applyActivityEvent");
    expect(renderer).toContain("deriveActivityScene");
    expect(client).toContain("/api/projects/");
    expect(client).toContain("/activity/stream");
    expect(activity).toContain("activity-preview-card");
    expect(activity).toContain("Constellation arrives in the next version");
    expect(activity).not.toContain("<svg");
    expect(activity).not.toContain("activity-node-core");
    expect(adapter).toContain("parentEntityId");
    expect(activity).toContain("activityStatus(scene)");
    expect(adapter).toContain("activityPerformanceBudget");
    expect(adapter).toContain("aggregate:overflow");
    expect(adapter).toContain("activity resync required");
    expect(css).toContain(".activity-view");
    expect(css).toContain(".activity-preview-card");
  });

  it("keeps heavy visualization modules outside the startup path", () => {
    const renderer = read("src/renderer/main.tsx");
    const presence = read("src/renderer/Presence.tsx");
    const activity = read("src/renderer/ActivityConstellation.tsx");

    expect(renderer).not.toContain('from "./Presence"');
    expect(renderer).not.toContain('from "./ActivityConstellation"');
    expect(renderer).toContain("const Presence = lazy");
    expect(renderer).toContain("const ActivityConstellation = lazy");
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
    expect(main).toContain("BrowserWindow.fromWebContents(event.sender)?.close()");
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
    const script = read("scripts/build-root-launcher.ps1");

    expect(main).toContain("assets/icons/synapse.ico");
    expect(main).toContain("icon: iconPath");
    expect(script).toContain("assets\\icons\\synapse.ico");
    expect(script).toContain("/win32icon:$iconPath");
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

  it("applies theme changes to the shell icon components immediately", () => {
    const renderer = read("src/renderer/main.tsx");
    const css = read("src/renderer/styles.css");

    expect(renderer).toContain("onPreviewFrontendSettings");
    expect(renderer).toContain("const shellIcons = assetsForTheme(state.frontendSettings.theme)");
    expect(renderer).toContain("iconVisualOffsets");
    expect(renderer).toContain('type ShellIconVisualKey = "constellation" | "history" | "settings" | "notificationsIdle" | "notificationsActive"');
    expect(renderer).toContain("shellIconStyle");
    expect(renderer).toContain("src={shellIcons.navigation.constellation}");
    expect(renderer).toContain("src={shellIcons.navigation.history}");
    expect(renderer).toContain("src={shellIcons.navigation.settings}");
    expect(renderer).toContain("shell-nav-icon-frame");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--activity");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--history");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--settings");
    expect(renderer).toContain("shell-nav-icon shell-nav-icon--notifications");
    expect(renderer).toContain("assetsForTheme(theme).notifications");
    expect(renderer).toContain('shellIconStyle(unreadNotifications > 0 ? "notificationsActive" : "notificationsIdle")');
    expect(css).toContain("--shell-nav-bg");
    expect(css).toContain("--shell-nav-bg-hover");
    expect(css).toContain("--shell-nav-bg-active");
    expect(css).toContain("--shell-nav-border");
    expect(css).toContain(".shell-nav-icon-frame");
    expect(css).toContain(".shell-nav-icon");
    expect(css).toContain("drop-shadow(1px 0 0 rgba(0, 0, 0, 0.9))");
    expect(css).toContain("transform: translate(var(--shell-icon-x, 0), var(--shell-icon-y, 0)) scale(var(--shell-icon-scale, 1))");
  });

  it("defines root executable build automation", () => {
    const packageJson = read("package.json");
    const script = read("scripts/build-root-launcher.ps1");

    expect(packageJson).toContain("build:root-exe");
    expect(script).toContain("Synapse.exe");
    expect(script).toContain("electron.exe");
    expect(script).toContain("CreateNoWindow = true");
  });
});
