# Synapse Frontend V2 — Product Specification

Status: `FRONTEND V2 SLICE 12 COMMAND INTENT ROUTING READY`

This document is the canonical product specification for the clean Synapse desktop frontend rebuild. It does not restore the retired ADE frontend and does not authorize frontend implementation, dependency installation, mocks, or backend gap fixes.

## Product direction

Synapse V2 is a local-first desktop AI workspace. The primary surface is Presence: an ambient, factual visualization of the current assistant state. The persistent operational surface is the Conversation Log: text and voice share the same durable history. Workspace, Insight, commands, notifications, and attachments are available on demand without turning the main workspace into an operations dashboard.

### Planned integrated visual workspace

The product direction reserves a future sidebar surface for a deep visual-creation
workspace. This is a planned stage, not an implemented frontend requirement. It would
bring an image/document canvas into Synapse so visual work, project files and AI
interaction share one governed context instead of requiring an external editor for every
iteration.

The intended experience is closer to an AI-native creative workspace than a decorative
visual panel: the user could create or edit a document, select a region, request a
generation or transformation, review the result, and ask the Primary Agent or a Swarm
to perform project-scoped work against the artifact. Local and external providers would
remain behind the existing Model Hub, Provider Settings, permission and tool boundaries.

The initial scope is deliberately deferred until the following contracts are designed:

- durable document/layer/revision and asset-provenance models;
- canvas/rendering and large-image performance boundaries;
- explicit image-generation and region-edit capability contracts;
- project-file custody, export and recovery semantics;
- agent authority, approvals, progress, cancellation and failure handling;
- safe Electron/preload exposure for file and rendering operations.

This future surface must remain distinct from Presence (conversation/ambient state),
Workspace CLI (operational work) and project execution surfaces. Adding
the sidebar entry or implementing a canvas is outside the current frontend slices until
the dedicated architecture/product plan is approved.

The frontend must render backend facts. It must not invent agents, work, voice state, approvals, model availability, hardware compatibility, or activity.

## Core experience

### First run

Expected flow:

```text
Synapse starts
↓
frontend-facing boundary checks for a usable Primary Agent
↓
none exists
↓
provider/model inventory is loaded
↓
user configures the first agent
↓
backend validates and creates the agent
↓
agent becomes Primary/default
↓
normal workspace opens
```

The onboarding reappears if there is legitimately no usable Primary Agent. It must not rely only on a local `firstRunCompleted` flag. If providers or models are unavailable, the onboarding must show a clear recoverable state and must not create a partial agent.

Status: `READY` for the frontend/backend first-run path.

Evidence:

- Agent creation and validation exist in `backend/synapse/api/routers/agents.py`.
- Provider/model discovery and resolution exist in `backend/synapse/api/routers/models.py`.
- Primary/default agent selection and restart recovery exist in `backend/synapse/api/routers/agent_kinds.py` and `tests/test_primary_agent_runtime.py`.
- `apps/frontend-v2/src/renderer/main.tsx` consumes the first-run boundary before opening the workspace.
- `apps/frontend-v2/src/shared/frontendClient.ts` centralizes the typed client for bootstrap and first-agent creation.

### Main shell

Canonical Slice 2 structural shell wireframe:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Synapse                                                    window controls │
├────┬───────────────────────────────────────────────┬─────────────────────┤
│ ◎  │                                               │ Conversation Log    │
│ ◌  │           Presence / Workspace view           │ real conversation   │
│    │        factual status / degraded state         │ stream + history    │
│    │                                               │ minimizable         │
│ ⚙  │             + text/commands  🎙 mode           │                     │
└─────────────────────────────────────────────────────────────────────┘
```

The main shell must stay low-noise. Presence is the default visual area. Workspace is
the operational surface for projects, CLI work, files, research and Swarm execution.
Insight opens on demand as an elevated internal panel over the workspace; it is not page
navigation and does not replace Presence or Conversation Log state.

### Minimal sidebar

The sidebar contains only durable navigation and must not become a dense control panel:

- workspace/project switcher;
- Conversation Log access;
- Workspace/CLI;
- Insight panel;
- settings access.

### Conversation Log

The Conversation Log is the canonical user-visible history for text and voice. It must support:

- persisted turns;
- streamed assistant turns;
- voice transcripts in the same conversation timeline;
- attachment references;
- failure and cancellation states;
- resume after restart.

Status: `READY` for text history and streaming in Slice 2, `PARTIAL` for integrated voice/TTS history.

Evidence:

- Conversation CRUD, messages, turns, streaming, participants, summaries, attachments, and cancellation exist in `backend/synapse/api/routers/conversations.py`.
- The voice conversation endpoint uses the packaged Piper runtime for integrated TTS in v0.01. Provider-level cancellation/full-duplex interruption remains limited and is documented as a non-blocking limitation.
- `apps/frontend-v2/src/renderer/main.tsx` renders the right-side Conversation Log, consumes real text streaming, refreshes persisted history and supports minimize/reopen.

### Single composer

The composer owns one user-intent entry point:

- text input;
- slash-command discovery;
- attachment selection;
- voice action;
- visible validation/errors.

The composer must not bypass the Command Authority Boundary. Ordinary text goes to the active conversation. Slash-prefixed input goes to command routing and is not silently converted into a chat message when unknown or invalid.

Status: `READY` for slash-command discovery and governed Slice 12 command intent routing; `PARTIAL` for attachments and broader operational command execution UX.

Evidence:

- Backend command runtime and desktop command authority exist in `backend/synapse/bootstrap/application.py`, `backend/synapse/api/routers/tools.py`, and `backend/synapse/api/routers/desktop_commands.py`.
- `apps/frontend-v2/src/shared/frontendClient.ts` consumes `/api/tools/catalog` and project scope endpoints.
- `apps/frontend-v2/src/shared/commandDiscovery.ts` provides deterministic slash filtering, typed command registry, slash intent parsing and argument validation.
- `apps/frontend-v2/src/renderer/main.tsx` routes plain text to conversation, routes `/insight` and `/settings` to existing UI surfaces, and routes `/project <id>` through real project lookup plus the frontend conversation boundary.
- Backend tool catalog entries remain factual discovery items; unless mapped to a governed command route they are marked unavailable for direct composer execution.

### Official icon

Status: `READY` for local Electron shell and root launcher.

The current official source asset is preserved at repository root:

- `synapse icon (1).png`

Derived assets are stored under `apps/frontend-v2/assets/icons/` and are consumed by the Electron window and root launcher build. The source PNG must not be overwritten by generated derivatives.

### Voice controls

The UI must distinguish:

- push-to-talk or explicit recording/transcription;
- full Conversation Mode;
- TTS playback;
- provider/device unavailable states.

Voice capture and VAD remain client-side responsibilities unless a future backend contract explicitly changes that boundary.

Status: `READY` for governed staging/registration/turn refs; `PARTIAL` for advanced file UX and multimodal processing.

Evidence:

- Voice sessions, recording lifecycle, devices, providers, transcription, and synthesis endpoints exist in `backend/synapse/api/routers/voice.py`.
- Frontend V2 Conversation Mode uses `POST /api/frontend/voice/conversation-turn` to run the existing Voice runtime path: STT, same-conversation text turn, persisted assistant response, governed TTS synthesis, and frontend playback.
- Full duplex/provider-level interruption remains limited; playback can be stopped by the frontend, but provider-level generation cancellation remains bounded by the existing text stream limitations.

### Presence

Presence is the default visual surface. It reflects factual operational states:

- idle;
- listening;
- transcribing;
- thinking/processing;
- responding;
- speaking;
- waiting for approval;
- degraded/unavailable.

Presence must be driven by frontend-facing state derived from backend facts, not animation-only assumptions.

### Retired Activity / Constellation surface

The former Activity/Constellation visualization was removed from the active product
direction. It is not a sidebar destination, command, or frontend requirement. The
operational projection contracts may remain in the backend as factual infrastructure for
Workspace and Swarm consumers, but no visual constellation is implied by their existence.

### Insight

Insight is an on-demand elevated internal panel for local hardware, runtime/provider inventory, model compatibility, and model recommendations. It must show provider absence and degraded states without implying a model can run when it cannot. A recommendation is not an installation claim; installed/local availability is shown only when backend provider/model facts report it.

Status: `READY` for backend facts and Frontend V2 panel presentation.

Evidence:

- System, hardware, GPU, CPU, memory, storage, providers, diagnostics, report, and model recommendation endpoints exist in `backend/synapse/api/routers/system.py`.
- `apps/frontend-v2/src/shared/frontendClient.ts` consumes `GET /api/insight/report` through the typed client.
- `apps/frontend-v2/src/renderer/main.tsx` renders Insight as a closeable, manually refreshable elevated internal panel with loading, ready, degraded, unavailable and error states.
- `apps/frontend-v2/tests/shellStructure.test.ts` covers the Insight panel structure, backend contract consumption, recommendation grouping, source handling, close/refresh affordances and responsive bounds.

### Settings

Settings is an on-demand elevated internal panel for configuration, not page navigation and not a replacement for Presence. It preserves workspace, conversation and Conversation Log state behind it.

Status: `READY` for real Model/Provider, Voice and frontend-owned Appearance settings.

Settings must expose only controls with a real owner:

- backend-owned Model Hub defaults through `/api/models/default`;
- backend-owned provider configuration through `/api/provider-settings`;
- backend-owned Voice settings through `/api/voice/settings`;
- frontend-owned reduced-motion preference through the governed Frontend V2 preference key.

Settings must not show fake Privacy, attachments, notifications, command execution, packaging or titlebar controls.

Evidence:

- `apps/frontend-v2/src/shared/frontendClient.ts` loads and updates settings through typed model/provider/voice contracts.
- `apps/frontend-v2/src/shared/settingsPreferences.ts` owns the single frontend preference persistence point for reduced motion.
- `apps/frontend-v2/src/renderer/main.tsx` renders Settings as a closeable elevated panel with explicit Save, safe errors and local validation for provider/model selection.

### Window controls

Status: `READY` for the custom frameless Electron shell controls.

The titlebar controls use the explicit renderer/preload/main-process path:

```text
React titlebar control
→ contextBridge allowlist
→ named Electron IPC
→ BrowserWindow.fromWebContents(event.sender)
```

The supported actions are minimize, maximize, restore and close. Maximize/restore state is synchronized from BrowserWindow events instead of being inferred only in React. The titlebar remains draggable and the buttons remain in a no-drag region.

Evidence:

- `apps/frontend-v2/src/main/main.ts` handles window IPC by resolving the sender BrowserWindow.
- `apps/frontend-v2/src/preload/preload.ts` and generated `dist/main/preload/preload.cjs` expose only explicit window methods.
- `apps/frontend-v2/src/renderer/main.tsx` syncs maximize/restore state and supports double-click titlebar maximize/restore.
- Window controls use explicit preload IPC and are covered by frontend structure tests plus runtime validation.

### Attachments

Attachments are user-selected files that enter governed project/conversation context through a backend contract. The frontend must not treat local file selection as ingestion.

Status: `PARTIAL`.

Evidence:

- Conversation attachment registration exists in `backend/synapse/api/routers/conversations.py` and validates metadata, size, checksum, and storage reference.
- Frontend V2 Slice 13 adds governed local staging through an allowlisted Electron picker and `POST /api/frontend/conversations/{conversation_id}/attachments/stage`.
- The backend recalculates identity, stores the file under conversation-owned storage, registers the attachment, and only registered refs may accompany the next text turn.
- Advanced file browsing, preview, remote upload and multimodal processing remain outside this status.

### Notifications

Notifications are factual records, not visual-only badges. The UI must show unread, read, cleanup, action-required, approval-related, degraded, and failure states.

Status: `READY` for backend records and Frontend V2 Slice 11 presentation.

Evidence:

- Notification endpoints exist in `backend/synapse/api/routers/platform.py`.
- Agent loop notification persistence exists in `backend/synapse/agent_loop/runtime.py`.
- `apps/frontend-v2/src/shared/frontendClient.ts` consumes `/api/notifications` plus read/delete routes through the typed client.
- `apps/frontend-v2/src/renderer/main.tsx` renders the header notification button, unread badge and elevated internal popover with loading, empty, degraded and error states.
- Approval notifications are displayed factually; resolving approvals remains owned by approval/domain flows.

## Requirement classification

| Requirement | Status | Reason |
| --- | --- | --- |
| First-run first agent setup | `READY` | Slice 1 backend boundary and Slice 2 Electron onboarding consume real bootstrap/provider/model/create contracts. |
| Provider/model inventory | `READY` | Model/provider routers expose catalog, discovery, health, resolve, defaults, and validation. |
| Agent creation/validation | `READY` | Agent create, preview, validate, patch, lifecycle, provisioning APIs exist. |
| Primary/default agent restore | `READY` | Primary agent runtime covers required, selection, replace, restart, and corrupt-reference handling. |
| Text conversation | `READY` | Conversation turn and persisted message APIs exist. |
| Streamed response | `READY` | Conversation stream endpoint emits NDJSON lifecycle events. |
| Conversation Log | `READY` for text, `PARTIAL` for voice | Slice 2 implements persisted text log, stream display and restore; shared voice/TTS loop is not fully ready. |
| Voice transcription | `READY` | Transcription and voice recording completion endpoints exist. |
| Voice conversation with TTS | `READY` for frontend V2 continuous turn loop, `PARTIAL` for full duplex interruption | Frontend V2 uses real backend STT + same conversation text response + governed TTS audio playback; provider-level cancellation/full duplex remains limited. |
| Continuous voice/interruption | `PARTIAL` | Sessions/lifecycle exist; complete client/backend interruption contract is not identified. |
| Presence visualization | `NOT REQUIRED BACKEND-SIDE` | Backend facts are required; visual scene state belongs to frontend. |
| Workspace operational facts | `PARTIAL` | Project, file, CLI and Swarm contracts are being consolidated; no constellation UI is part of the active product. |
| Insight hardware/model recommendations | `READY` | System Insight endpoints exist. |
| Settings elevated surface | `READY` | Slice 10 exposes only real Model/Provider, Voice and reduced-motion settings with explicit ownership. |
| Command intent routing | `READY` for mapped commands, `PARTIAL` for broad tool execution | `/insight`, `/settings` and `/project <id>` have governed routing; arbitrary tool/catalog execution remains unavailable from the composer. |
| Attachments | `READY` for governed staging/registration/turn refs, `PARTIAL` for advanced file UX/multimodal processing | Slice 13 enables the composer `+` flow through a safe picker, backend-owned checksum/storage ref and conversation-scoped refs; preview/extraction/remote uploads remain out of scope. |
| Notifications | `READY` | Notification records/endpoints exist and Slice 11 consumes them as a header popover with unread/read/dismiss semantics. |
| On-demand panels | `NOT REQUIRED BACKEND-SIDE` | Backend supplies feature facts; panel state is frontend. |

## Non-goals for this foundation

- Do not implement frontend screens.
- Do not restore the retired ADE frontend.
- Do not install Electron, React, PixiJS, or any dependency.
- Do not create mocks or simulated operational state.
- Do not change Backend Readiness because frontend gaps exist.
- Do not implement Chat lateral, Insight UI, audio controls, or visualization changes in this task.
