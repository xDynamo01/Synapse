# Synapse Frontend V2 — Architecture

Status: `FRONTEND V2 SLICE 12 COMMAND INTENT ROUTING READY`

This document defines the target architecture for a clean frontend rebuild. It is not an implementation plan for the retired ADE frontend and does not authorize dependency installation.

## Architectural principle

```text
backend facts
↓
frontend-facing application boundary
↓
typed client
↓
application state
↓
UI / visualization adapter
↓
renderer
```

No fictitious operational state is allowed in Presence, Activity, Constellation, Conversation Log, Insight, notifications, or command surfaces.

## Frontend-facing application boundary

The target dependency direction is:

```text
Frontend
↓
Frontend-facing Application Boundary
↓
Conversation / Workspace / Activity / Voice / Insight / Commands / Notifications
↓
backend domains
```

The boundary is `PROPOSED`. It should consolidate existing backend capabilities into frontend-safe contracts without creating a second source of truth.

### Boundary responsibilities

| Boundary service | Responsibility | Backend sources |
| --- | --- | --- |
| FirstRun | Determine whether onboarding is required, list usable providers/models, create first agent, set Primary/default. | agents, agent kinds, models |
| Workspace | Project/workspace context, active project, degraded state. | project governance, primary agent, health |
| Conversation | Conversation CRUD, turns, streaming, history, cancellation, summaries, participants. | conversations/chat |
| Voice | Devices/providers, recording lifecycle, transcription, synthesis, voice conversation facts. | voice/audio/speech |
| Activity | Project activity snapshot, event cursor, SSE stream, resync requirements. | operational projection |
| Insight | Hardware, providers, diagnostics, model compatibility, recommendations. | system insight, model hub |
| Commands | Slash discovery, command explanation, command intent submission, approval-aware execution. | commands, tools, desktop command authority |
| Notifications | Notification records, unread/read state, cleanup, action-required routing. | platform notifications |
| Attachments | File staging, checksum, governed registration, conversation/project context references. | conversations, storage/data directory |

## State model

### Domain/application state

Domain/application state is typed, factual, and recoverable from backend responses or durable frontend preferences.

Examples:

- active conversation id;
- Primary Agent state;
- provider/model availability;
- current stream lifecycle;
- pending approval count;
- notification unread count;
- activity cursor and resync state;
- selected shell view;
- user preference for minimized Conversation Log.

### Visual scene state

Visual scene state exists only to render factual application state.

Examples:

- particle positions;
- node easing;
- glow intensity;
- transition progress;
- reduced-motion variant;
- viewport camera for Activity/Constellation.

The renderer must never become the authority for whether an agent exists, a model is available, a voice session is active, a tool ran, or a task completed.

## Desktop shell

The desktop shell owns:

- window lifecycle;
- secure preload bridge;
- renderer boot;
- backend process/sidecar supervision when implemented;
- local-first connectivity and degraded states;
- file picker integration through an allowlisted IPC path;
- audio device access through browser/Electron capabilities and backend contracts.

Renderer code must not receive generic filesystem, shell, process, or network authority. Every privileged action must pass through a narrow allowlist.

## Typed client

The typed client should be generated from or manually aligned with backend contracts. It must:

- treat non-2xx responses as typed failure states;
- support streaming NDJSON and SSE where the backend uses them;
- preserve cursor/resync semantics;
- expose validation, permission, degraded, unavailable, and approval-required states;
- avoid implicit fallback to fake data.

Slice 2 implements the first manually aligned typed client in `apps/frontend-v2/src/shared/frontendClient.ts`. Renderer components consume frontend-facing backend contracts through this client instead of scattered `fetch()` calls.

Slice 3 hardens the same typed client for NDJSON stream cleanup and moves conversation runtime decisions into `apps/frontend-v2/src/shared/conversationRuntime.ts`.

## Application modules

### Shell

Owns navigation, first-run gating, selected surface, degraded global state, and the minimal side rail.

### Conversation

Owns conversation list/detail, stream lifecycle, history pagination, cancellation, summaries, attachment references, and Conversation Log projection.

Slice 3 defines explicit frontend conversation states: `idle`, `restoring`, `sending`, `streaming`, `completed`, `failed` and `disconnected`. History reconciliation is deterministic by message identity, keeps partial assistant text separate from persisted history, and does not resend turns after disconnect.

Slice 4 extends conversation runtime with `cancelled`, bounded history pagination and read-only summary integration. Cancellation is requested through the frontend boundary by idempotency key; current backend streaming remains `single_complete_chunk`, so provider-level mid-call interruption is not claimed beyond the supported backend cancellation boundary.

Slice 13 activates composer attachments through a governed ingestion path. The renderer can only request the allowlisted Electron file picker; it receives no local path and no filesystem capability. The frontend posts selected bytes and minimal metadata to `POST /api/frontend/conversations/{conversation_id}/attachments/stage`; the backend enforces conversation scope, validates size/type/name, recalculates checksum, writes the backend-owned storage ref, registers through the existing conversation runtime, and only registered refs for the active conversation may accompany the next text turn. Conversation Log renders factual attachment metadata when history returns it; no preview or multimodal processing is claimed.

Slice 14 hardens startup and visualization lifecycle without changing product capability. Presence and Activity/Constellation are loaded through React `lazy(...)`/`Suspense` instead of static startup imports, keeping PixiJS-heavy code outside the initial renderer chunk. A local visual error boundary/fallback isolates Presence/Activity load or renderer failures from the shell. Pixi applications, ResizeObservers, document visibility listeners, Activity SSE streams, media tracks, recorders, timers and playback objects remain governed by component/effect cleanup.

### Workspace

Owns project/workspace selection and factual binding to conversation, activity, and agent contexts.

### Commands

Owns slash command discovery and intent submission. It must route through the backend command/tool authority and must never provide a generic IPC escape hatch.

Micro-slice 3.5 implements discovery only. The typed client reads the existing `/api/tools/catalog` registry, the composer opens a local elevated list for `/`, filters by typed input and supports keyboard selection. Selecting a command inserts the command token into the composer; execution semantics remain governed by future command-authority slices.

Slice 12 adds a typed frontend command registry over factual discovery. UI commands (`/activity`, `/insight`, `/settings`) execute only frontend-local surface actions. `/project <project_id>` validates a constrained argument, confirms the project through `GET /api/projects/{project_id}`, then reopens the conversation through the frontend conversation boundary with `project_id` scope. Backend tool catalog entries remain discoverable facts but are classified as unsupported for direct composer execution unless a governed route exists. Unknown slash input returns a recoverable composer-local error and does not pollute the Conversation Log.

### Panels

Owns on-demand panel state only. Panels do not own backend truth.

Slice 10 adds Settings as an elevated internal panel. It owns open/close/draft state and frontend-owned reduced-motion preference only. Backend-owned configuration remains behind typed HTTP contracts and is saved explicitly.

### Notifications

Owns notification presentation, read/unread transitions, and action routing through backend contracts.

Slice 11 implements Notifications as a header/top-surface button with a discreet unread badge and an elevated internal popover. It consumes only real platform notification records through the typed frontend client. The panel supports loading, ready, empty, degraded and error states, plus backend-owned read/delete transitions. Approval notifications are rendered as factual attention items; approval resolution remains owned by approval routes/domain UI and is not duplicated by the notification panel.

### Insight

Owns hardware/provider/model diagnostics presentation and panel state only. It consumes `GET /api/insight/report` through the typed frontend client, groups backend recommendations by factual status, shows provider/model counts from backend facts, and preserves unavailable/degraded/error states. Insight is an elevated internal surface over the workspace, not page navigation and not a second hardware discovery authority.

Slice 9 implements the sidebar Insight action, close and Escape behavior, manual refresh, loading/ready/degraded/unavailable/error states, responsive bounds, and clear distinction that backend recommendations do not imply installed local models unless backend facts say so.

### Settings

Owns configuration presentation and draft state for settings with existing owners. Model/provider defaults and provider enablement/endpoint/default model are backend-owned by Model Hub and Provider Settings. Voice enablement/provider/model/language/VAD/raw-audio retention are backend-owned by Voice settings. Appearance reduced motion is frontend-owned and persisted through `settingsPreferences.ts`.

Settings is not an operations dashboard and does not duplicate Insight recommendations. It validates provider/model choices against the backend model registry snapshot before saving and relies on backend validation for canonical rejection.

### Visualization

Owns Presence and Activity/Constellation projections. It receives a visual projection computed from application state and emits UI selection events only.

## Persistence

Canonical operational persistence remains backend-owned.

Frontend persistence may include:

- window geometry;
- selected shell view;
- minimized/open panel preferences;
- local UI accessibility preferences;
- last selected project/conversation ids when backend confirms they still exist.

Frontend persistence must not include:

- independent agent records;
- independent conversation history;
- fake model/provider inventory;
- secret-bearing provider configuration;
- backend authority decisions;
- tool execution facts.

## Security model

Required constraints:

- Electron sandbox remains enabled.
- `contextIsolation` remains enabled.
- Renderer receives only an allowlisted preload API.
- No generic IPC, shell command, filesystem, process, or native module bridge.
- Command Authority Boundary remains backend-owned.
- Attachments use governed staging/registration and checksums.
- Remote or model-produced content is untrusted and must be rendered safely.
- Backend facts should be fetched through a local, explicit transport boundary.

Slice 9 does not add renderer filesystem, process, shell or generic IPC authority. Hardware and model facts remain backend-owned through System Insight and Model Hub contracts.

Slice 10 keeps the same security boundary: no renderer Node, no generic IPC, no secrets in plaintext, and provider API keys remain backend-owned.

## Degraded and error states

The UI must explicitly represent:

- backend unavailable;
- no Primary Agent;
- no provider/model available;
- provider degraded;
- stream failed or cancelled;
- voice device unavailable;
- transcription failed;
- TTS unavailable;
- activity cursor invalid/resync required;
- Insight hardware/model report degraded or unavailable;
- attachment staging or checksum failure;
- command requires approval;
- notification action failed.
- settings load or save failed.

Opening the workspace in a broken state is not acceptable when first-run prerequisites are missing.

## Testing strategy

Future implementation slices should include:

- contract tests for typed client mappings;
- first-run state tests;
- stream lifecycle tests;
- no-agent and no-provider tests;
- voice degraded-state tests;
- activity cursor/resync tests;
- command authority/IPC allowlist tests;
- renderer tests for no simulated operational state;
- visual adapter tests proving scene state is derived from application state.

## Slice 2 implementation evidence

Implemented in `apps/frontend-v2/`:

- secure Electron main/preload/renderer split;
- sandboxed, context-isolated renderer with `nodeIntegration=false`;
- narrow preload allowlist for backend base URL and custom window controls;
- minimal React shell with icon-only side rail, factual PixiJS Presence visualization, right-side minimizable Conversation Log and compact text composer;
- first-run onboarding based on backend bootstrap truth, not frontend flags;
- typed client for bootstrap, first-agent creation, conversation open, text turns, NDJSON stream and history restore;
- root `F:\Projetos\Synapse\Synapse.exe` launcher generated by `apps/frontend-v2/scripts/build-root-launcher.ps1`.

Micro-slice 10.5 hardens the custom frameless window controls. The BrowserWindow preload now resolves to a CommonJS preload artifact generated during build so the sandboxed renderer reliably receives `window.synapse`. Window IPC remains explicit and sender-scoped: minimize, toggle maximize/restore, query maximized state and close. React synchronizes maximize/restore state from BrowserWindow events, and the titlebar keeps drag/no-drag regions intact.

## Slice 3 implementation evidence

Implemented in `apps/frontend-v2/`:

- explicit conversation runtime state model in `src/shared/conversationRuntime.ts`;
- ordered NDJSON chunk handling with reader cleanup in `src/shared/frontendClient.ts`;
- deterministic message merge/reconciliation without duplicate history messages;
- interrupted stream handling that preserves partial assistant text and marks the state as disconnected or failed instead of completed;
- retry-safe recovery action based on history reconciliation, not automatic turn resend;
- composer double-submit prevention during `sending` and `streaming`;
- failed draft restoration when a retryable send path fails;
- Conversation Log auto-scroll only when the user remains near the end.

## Micro-slice 3.5 implementation evidence

Implemented in `apps/frontend-v2/`:

- official source icon copied into governed frontend assets and converted to `.ico`/256px derivatives;
- Electron `BrowserWindow` uses `assets/icons/synapse.ico`;
- root `F:\Projetos\Synapse\Synapse.exe` build embeds the same `.ico`;
- typed command catalog client consumes `/api/tools/catalog`;
- composer-local slash discovery handles `/`, filtering, ArrowUp/ArrowDown, Enter and Escape without adding renderer filesystem or Node authority.

## Slice 4 implementation evidence

Implemented in `apps/frontend-v2/` and `backend/synapse/api/routers/frontend_boundary.py`:

- initial conversation open returns a bounded recent history page instead of unlimited history;
- history responses include pagination metadata for progressive older-page loading;
- frontend merges pages by message identity and preserves the approved elevated Conversation Log;
- real conversation summary records are read from the existing conversation summary runtime;
- cancellation is requested through `POST /api/frontend/conversations/{conversation_id}/turns/cancel`;
- cancelled streams produce a `generation_cancelled` event and preserve partial assistant text as incomplete.

## Slice 5 implementation evidence

Implemented in `apps/frontend-v2/` and `backend/synapse/api/routers/frontend_boundary.py`:

- the composer microphone button uses browser microphone capture and `MediaRecorder`;
- capture states are explicit: `idle`, `recording`, `transcribing` and `failed`;
- stop sends the captured audio to `POST /api/frontend/voice/transcriptions`;
- cancel releases microphone tracks and discards captured chunks without opening a conversation turn;
- the frontend transcription boundary reuses the Voice recording lifecycle and configured STT adapter;
- successful transcription is inserted into the current composer draft for review/editing;
- sending the transcript still uses the existing text conversation stream/history path;
- renderer authority remains browser-only for audio capture, with no Node or filesystem access.

## Slice 6 implementation evidence

Implemented in `apps/frontend-v2/` and `backend/synapse/api/routers/frontend_boundary.py`:

- the second composer voice control starts/stops Conversation Mode independently from the manual transcription mic;
- Conversation Mode cycles through factual frontend states: `inactive`, `idle`, `listening`, `transcribing`, `processing`, `speaking`, `interrupted`, and `failed`;
- each captured utterance is sent to `POST /api/frontend/voice/conversation-turn`;
- the backend reuses the Voice session/recording lifecycle and `run_conversation_turn(...)` path for STT, same-conversation text turn, persisted assistant response, and governed TTS synthesis;
- frontend playback uses returned TTS audio and then returns to listening while mode remains active;
- stopping mode releases MediaStream, MediaRecorder, playback, timers, chunks, and cancellation state;
- playback interruption is frontend-side; provider-level generation cancellation is not claimed beyond existing text cancellation limitations.

## Slice 7 implementation evidence

Implemented in `apps/frontend-v2/`:

- Presence is derived from factual application/backend state through `src/shared/presenceAdapter.ts`;
- the renderer uses PixiJS in `src/renderer/Presence.tsx` and receives scene state only, not backend internals;
- mapped states are `idle`, `listening`, `transcribing`, `processing`, `speaking`, `interrupted`, `failed`, and `disconnected`;
- manual transcription drives `listening -> transcribing -> idle/failed` and does not send automatically;
- text conversation turns drive `processing`; they do not imply `speaking` without TTS playback;
- Conversation Mode drives `listening -> transcribing -> processing -> speaking -> listening` while active;
- audio-reactive `listening` and `speaking` use browser audio analyser amplitude from captured microphone/playback streams;
- reduced-motion, unfocused frame-rate throttling, resize handling, unmount cleanup and CSS fallback are implemented without changing Electron IPC or renderer filesystem authority.

## Slice 8 implementation evidence

Implemented in `apps/frontend-v2/`:

- the side-rail Activity/Constellation button toggles only the central visual surface between Presence and Activity;
- project activity uses the existing Operational Projection endpoints: snapshot, cursor resume and SSE stream;
- `src/shared/activityAdapter.ts` is the boundary between backend activity facts and frontend-owned constellation scene state;
- the Activity renderer uses PixiJS in `src/renderer/ActivityConstellation.tsx` and includes a DOM fallback;
- stale and cross-project events are rejected by the adapter, revision gaps become explicit resync/degraded state, and stream errors become disconnected state;
- node colors are semantic function/role mapping while runtime status is represented by motion/halo;
- large graphs are deterministically aggregated and reduced-motion disables flow particles;
- Presence state and voice/text behavior remain separate from Activity and were not changed by this slice.
