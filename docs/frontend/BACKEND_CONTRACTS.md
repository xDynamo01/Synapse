# Synapse Frontend V2 — Backend Contracts

Status: `FRONTEND V2 SLICE 12 COMMAND INTENT ROUTING READY`

This document maps the existing backend to the required frontend V2 experience. `PROPOSED` entries are not implemented by this task.

## Status vocabulary

- `READY`: backend contract exists and evidence supports the required frontend need.
- `PARTIAL`: backend has usable pieces but at least one required frontend path is missing or incomplete.
- `MISSING`: no adequate backend contract was identified.
- `NOT REQUIRED BACKEND-SIDE`: the requirement belongs to frontend state, visuals, or layout.
- `FRONTEND REQUIREMENT GAP`: the backend may remain ready in its historical roadmap, but frontend V2 needs an additional contract or adaptation.

## Contract inventory

| Contract | Purpose | Backend owner | Existing contract | Transport/event | Frontend consumption | Project scope | Session scope | Failure states | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| First-run status | Decide whether onboarding or workspace opens. | Frontend V2 boundary over Primary Agent + Agents + Models. | `GET /api/frontend/bootstrap`. | HTTP. | Shell boot gate. | `workspace_id`, optional `project_id` and `session_id`. | App startup. | no primary, corrupt primary ref, no providers/models, degraded state. | `READY` — Slice 1 closes the consolidated first-run boundary. |
| Agent creation | Create first/default agent and normal agents. | Agents runtime/provisioning. | `POST /api/agents`, `POST /api/agents/preview`, validation/patch/lifecycle routes. | HTTP. | Onboarding form and agent management. | Can bind later to workspace/project context. | User-initiated. | validation error, provider/model invalid, policy failure. | `READY`. |
| Primary/default agent | Establish and restore the usable main agent. | Primary Agent runtime. | `/api/primary-agent`, `/api/primary-agent/replace`, primary interaction routes. | HTTP. | Shell boot, composer target, Conversation Log default. | Workspace-aware via runtime state/context where present. | Startup/resume. | `primary_agent_required`, selection required, corrupt/missing reference. | `READY`. |
| Provider/model inventory | Show only real provider/model options. | Model Hub + System Insight. | `/api/providers`, `/api/providers/health`, `/api/models/*`, `/api/models/resolve`, `/api/models/default`. | HTTP. | First-run model selector, Insight, composer model display. | Global/local runtime scope. | Startup and refresh. | unavailable, invalid model, health degraded. | `READY`. |
| Settings — models/providers | Configure default model/provider and provider runtime settings. | Model Hub + Provider Settings. | `GET/POST /api/models/default`, `GET /api/models/catalog`, `GET /api/models/providers`, `GET/PATCH /api/provider-settings/{id}`. | HTTP. | Settings panel. | Global/local runtime. | Explicit Save. | unknown provider, unavailable model, invalid endpoint, backend failure. | `READY` for Slice 10. |
| Text conversation turn | Submit user text and receive assistant result. | Frontend V2 boundary over Conversations + Chat runtime. | `POST /api/frontend/conversations/{id}/turns`. | HTTP. | Composer submit. | `workspace_id`, optional `project_id` and `session_id`; rejects metadata scope mismatch. | Turn lifecycle. | validation, provider failure, cancellation, backend unavailable. | `READY` for text. |
| Streamed conversation turn | Stream assistant lifecycle and response. | Frontend V2 boundary over Conversations + Chat runtime. | `POST /api/frontend/conversations/{id}/turns/stream`, `POST /api/frontend/conversations/{id}/turns/cancel`. | NDJSON stream + HTTP cancel. | Live assistant response in Conversation Log/Presence. | `workspace_id`, optional `project_id` and `session_id`; rejects metadata scope mismatch. | Turn stream. | stream error event, validation error event, cancellation, partial response. | `READY` for text cancellation boundary; provider-level mid-call interruption is not claimed for `single_complete_chunk`. |
| Conversational Swarm request | Let the Primary Agent classify a natural-language Swarm request, request one confirmation only when details are ambiguous, and create the real mission, Swarm and temporary workforce after acceptance. | Chat runtime + Swarm interaction runtime through the Frontend V2 boundary. | Stream events `confirmation_required` and `swarm_started`; `POST /api/frontend/swarm/confirmations/{request_id}` resolves `accept_recommendation`, `keep_requested` or `cancel`. | NDJSON stream + scoped HTTP decision. | Shared confirmation card in Conversation Log and Workspace CLI; an accepted or explicit request opens the factual Swarm workspace. | `workspace_id`, optional `project_id` and `session_id`, `actor_id`; all supplied scopes must match the persisted interaction. | Interaction is persisted before side effects and is idempotent per conversation/request. | invalid or stale request, scope mismatch, explicit-model under-provisioning, resource/capacity failure, workforce awaiting workers. | `READY` for bounded conversational creation; it does not claim autonomous mission discovery or background execution beyond the existing Swarm runtime. |
| Conversation history/log | Persist and restore conversation timeline. | Frontend V2 boundary over Conversations runtime. | `POST /api/frontend/conversations/open`, `GET /api/frontend/conversations/{id}/history`. | HTTP. | Conversation Log, restart restore, pagination. | `workspace_id`, optional `project_id` and `session_id`; boundary-created conversations carry scope metadata. | Durable. | not found, revision conflict, delete confirmation, scope mismatch. | `READY` for bounded text pagination and summary read; voice transcript enters history only after the user sends it as normal text. |
| Voice devices/providers | Show voice availability. | Voice runtime. | `/api/voice/devices`, `/api/voice/providers`, settings routes. | HTTP. | Voice controls and degraded state. | Global/local runtime. | Startup/refresh. | no device, no provider, health degraded. | `READY`. |
| Settings — voice | Configure real voice settings only. | Voice runtime. | `GET/PATCH /api/voice/settings`, `GET /api/voice/providers`, `GET /api/voice/packs`, `GET /api/voice/voices`. | HTTP. | Settings panel. | Global/local runtime. | Explicit Save. | unsupported provider/model, invalid setting, backend failure, missing/corrupt voice asset. | `READY` for factual settings/discovery and the v0.01 packaged default pack; degraded states remain explicit. |
| Transcription | Convert audio into text. | Frontend V2 boundary over Voice/audio/speech. | `POST /api/frontend/voice/transcriptions`, Voice recording completion runtime. | HTTP. | Explicit mic input and editable composer transcript. | `workspace_id`, optional `project_id`, `session_id` and `conversation_id`; rejects metadata scope mismatch when a conversation is supplied. | Recording/transcription only; user must send transcript manually. | unsupported format, empty recording, provider unavailable, transcription failure, scope mismatch. | `READY` for explicit recording → STT → text composer; not a full Voice Conversation Mode claim. |
| TTS synthesis | Convert text into audio. | Voice/audio/speech. | `/api/audio/synthesize`, `POST /api/frontend/voice/conversation-turn`. | HTTP. | Spoken response playback. | Global/local runtime; frontend V2 voice turn binds to the active conversation. | Turn playback. | provider unavailable, synthesis failure, playback failure. | `READY` for standalone synthesis and frontend V2 voice-turn audio return. |
| Voice conversation | Speech to same conversation to agent response to TTS. | Frontend V2 boundary over Voice + Conversations + Chat + Speech adapters. | `POST /api/frontend/voice/conversation-turn`; legacy `/api/voice/conversation/turn` remains separate. | HTTP. | Conversation Mode. | `workspace_id`, optional `project_id`, `session_id`, required `conversation_id`, optional `voice_session_id`. | Continuous user-controlled frontend loop. | empty recording, STT failure, agent failure, TTS failure, backend unavailable, scope mismatch. | `READY` for frontend V2 continuous turn loop with integrated TTS; not a full duplex/provider-cancel claim. |
| Continuous voice/interruption | Full duplex conversation mode and interruption. | Voice + frontend capture/playback boundary. | Frontend playback stop plus existing cancellation primitives. | HTTP + browser playback. | Conversation Mode controls. | Conversation-bound once active. | Long-lived frontend loop. | device lost, cancellation, interruption, provider unavailable. | `PARTIAL` — playback interruption is supported frontend-side; provider-level generation cancellation remains limited by current stream/provider semantics. |
| Default Voice Pack | Discover installed TTS voices from governed backend assets. | Voice runtime. | `GET /api/voice/packs`, `GET /api/voice/voices`; `PATCH /api/voice/settings` persists `default_tts_voice`. | HTTP. | Settings Voice selector. | Global/local runtime. | Startup/refresh/explicit Save. | no pack, incomplete pack, missing asset, checksum mismatch, configured voice removed, TTS unavailable. | `READY` for v0.01 packaged default pack: exactly six checksum-verified redistributable voices and packaged Piper runtime; degraded states remain explicit. |
| Activity snapshot/events | Show factual project activity. | Operational Projection runtime. | `/api/projects/{project_id}/activity`, `/events`, `/stream`. | HTTP + SSE. | Activity/Constellation data source. | Project-scoped. | Cursor/resync stream. | invalid cursor, `activity_resync_required`, backend unavailable. | `READY` — Slice 8 consumes the existing backend stream through a frontend scene adapter. |
| Presence | Show assistant/voice/work state. | Frontend projection over backend facts. | No single Presence contract; facts come from primary agent, conversation stream, voice, activity, notifications. | Mixed HTTP/stream. | Main visual state. | Workspace/project where available. | Live session. | degraded/unavailable/unknown must be explicit. | `PARTIAL / FRONTEND REQUIREMENT GAP` — Presence projection boundary is `PROPOSED`. |
| Insight | Hardware, providers, diagnostics, model recommendations. | System Insight runtime. | `/api/system/insight`, `/hardware`, `/gpu`, `/cpu`, `/system/memory`, `/storage`, `/processes`, `/insight/providers`, `/models/recommendations`, diagnostics/report. | HTTP. | Insight panel and model recommendations. | Global/local runtime. | Startup/refresh/on demand. | provider unavailable, diagnostics degraded. | `READY`. |
| Commands/tools | Slash discovery, tool catalog, safe execution/intents. | Commands + Tools + Desktop Command Authority + Project Governance. | `/api/tools`, `/api/tools/catalog`, `/api/projects`, `/api/projects/{id}`, `/api/frontend/conversations/open`, `/api/tools/preview`, `/api/tools/run`, `/api/tool-intents/*`, `/api/desktop/commands`. | HTTP. | Composer slash menu, UI command routing and project-scoped conversation switching. | `/project` is project-scoped; broader tools depend on their payload. | User intent. | unknown command, unavailable command, invalid argument, missing project, approval required, rejected, authority error. | `READY` for discovery and Slice 12 governed UI/project command routing; `PARTIAL` for broad operational tool execution UX. |
| Approvals | Show and resolve pending approval decisions. | Tools/Approvals runtime. | `/api/approvals/pending`, approval routes, tool-intent approve/reject routes. | HTTP. | Notification badge, approval panel, command flow. | Depends on tool/mission/session context. | User decision. | pending, rejected, expired, invalid decision. | `READY`. |
| Notifications | Persist and present user-visible operational notices. | Platform notifications. | `/api/notifications`, `/unread`, read/delete/cleanup routes. | HTTP. | Header bell, unread badge and on-demand elevated popover. | Records may reference project/session entities. | Durable. | unavailable, action failed, cleanup failure. | `READY` for Slice 11 frontend consumption. |
| Attachments | Govern file ingestion into conversation/project context. | Frontend V2 boundary over Conversations + storage/data directory. | `POST /api/frontend/conversations/{id}/attachments/stage`, `/api/conversations/{id}/attachments` list/register with checksum/storage ref validation. | Electron allowlisted file picker + HTTP. | Composer attachment chip and next text turn refs. | `workspace_id`, optional `project_id` and `session_id`; conversation scope is enforced before staging/send. | User-selected local file staged into backend-owned storage. | invalid filename, empty/oversized/unsupported file, unreadable/changed file, invalid base64, checksum/storage mismatch, attachment scope mismatch. | `READY` for governed local staging + registration + conversation refs; no advanced browser, preview, remote upload or multimodal processing claim. |
| On-demand panels | Open/close panel presentation. | Frontend shell. | Uses feature-specific backend contracts above. | Not applicable. | UI layout state. | Frontend preference. | Renderer session. | panel unavailable if contract degraded. | `NOT REQUIRED BACKEND-SIDE`. |
| Settings — appearance | Persist frontend-owned visual preference. | Frontend V2 settings preferences. | `settingsPreferences.ts` governed local key. | local browser storage. | Settings panel, Presence/Activity reduced motion. | Current desktop user profile. | Explicit Save. | invalid preference normalizes to system. | `READY` for reduced motion only. |

## Required frontend-facing boundary contracts

These contracts are `PROPOSED` and must not be treated as implemented until a future slice creates and tests them.

### `READY FirstRunBoundary`

Purpose: one frontend-safe boot call that returns:

- whether onboarding is required;
- Primary Agent state;
- usable agent candidates;
- available providers/models;
- validation requirements for agent creation;
- degraded or unavailable reasons;
- active conversation/resume token when a usable Primary Agent exists.

Implemented by `GET /api/frontend/bootstrap`.

Agent creation for first-run is implemented by `POST /api/frontend/first-agent`. It validates provider/model selections against frontend-safe model options, creates a persistent agent through the existing provisioning runtime, assigns it as Primary through the existing Primary Agent runtime, and returns a deterministic bootstrap payload.

Evidence:

- `backend/synapse/api/routers/frontend_boundary.py`
- `tests/test_frontend_v2_boundary.py`
- `apps/frontend-v2/src/shared/frontendClient.ts`
- `apps/frontend-v2/tests/frontendClient.test.ts`

### `READY TextConversationBoundary`

Purpose: provide the future frontend with a narrow, typed text conversation boot contract:

- open or restore a conversation;
- bind conversation to Primary Agent;
- carry `workspace_id`, optional `project_id`, and optional `session_id`;
- submit user text through the real Chat runtime;
- consume the existing NDJSON stream through a frontend-safe wrapper;
- recover persisted history after restart;
- emit frontend-safe validation/degraded error state.

Implemented by:

- `POST /api/frontend/conversations/open`
- `POST /api/frontend/conversations/{conversation_id}/turns`
- `POST /api/frontend/conversations/{conversation_id}/turns/stream`
- `POST /api/frontend/conversations/{conversation_id}/turns/cancel`
- `GET /api/frontend/conversations/{conversation_id}/history`

Evidence:

- `backend/synapse/api/routers/frontend_boundary.py`
- `tests/test_frontend_v2_boundary.py`
- Existing backing contracts remain in `backend/synapse/api/routers/conversations.py` and `backend/synapse/chat/runtime.py`.
- `apps/frontend-v2/src/shared/frontendClient.ts`
- `apps/frontend-v2/src/renderer/main.tsx`
- `apps/frontend-v2/src/shared/conversationRuntime.ts`
- `apps/frontend-v2/tests/conversationRuntime.test.ts`

Slice 3 does not add backend contracts. It hardens frontend consumption of the existing boundary: stream events remain ordered, completion is explicit, interrupted streams stay incomplete, history refresh is deduplicated by message identity, and reconnect recovery reconciles from history instead of resending the last turn.

Slice 4 adds bounded pagination metadata and cancellation to the same frontend boundary. Conversation summaries are read from the existing `ConversationSummary` runtime record; no frontend-generated summary or second memory engine is introduced.

### `PROPOSED PresenceProjectionBoundary`

Purpose: convert backend facts into a small frontend state machine:

- `idle`;
- `listening`;
- `transcribing`;
- `thinking`;
- `responding`;
- `speaking`;
- `waiting_for_approval`;
- `degraded`;
- `unavailable`.

It must include source evidence and unknown/degraded reasons.

### `READY SlashCommandDiscoveryAndRouting`

Purpose: expose a safe command discovery model for the single composer:

- command id/name;
- description;
- required context;
- preview requirements;
- approval requirements;
- disabled/unavailable reason.

Implemented for discovery by `GET /api/tools/catalog`.

Slice 12 routing semantics:

- ordinary text remains conversation input;
- slash-prefixed input enters command routing and unknown slash commands fail safely;
- `/activity`, `/insight` and `/settings` are frontend-local UI commands and never call backend as visual side effects;
- `/project <project_id>` validates a bounded project id, confirms the project through `GET /api/projects/{project_id}`, then calls `POST /api/frontend/conversations/open` with `project_id`;
- backend tool catalog entries remain factual discovery items but are marked unsupported for direct composer execution until a governed tool-intent or command-authority UI route is implemented.

Evidence:

- `backend/synapse/api/routers/tools.py`
- `backend/synapse/tool_discovery/runtime.py`
- `apps/frontend-v2/src/shared/frontendClient.ts`
- `apps/frontend-v2/src/shared/commandDiscovery.ts`
- `apps/frontend-v2/tests/commandDiscovery.test.ts`

Execution beyond the explicitly mapped Slice 12 commands remains governed by future command-authority UI work and must route through existing command/tool/desktop authority.

### `READY AttachmentIngestionBoundary`

Purpose: stage a selected local file into governed backend storage and then register it against a conversation/project with checksum verification.

Implementation:

- Electron main process exposes only `synapse:attachment:pick-file` through preload; renderer receives no local path and no filesystem API.
- `POST /api/frontend/conversations/{conversation_id}/attachments/stage` accepts selected file bytes plus safe metadata, validates scope, filename, MIME type and size, recalculates SHA-256 in the backend, stores under the conversation data directory, and registers through `ConversationRuntime.register_attachment(...)`.
- Text turns accept only registered attachment refs; the frontend boundary rejects refs not registered for the current conversation.
- History returns persisted message attachment metadata as factual refs. Preview/extraction/multimodal processing remains out of scope.

### `READY ExplicitVoiceTranscriptionBoundary`

Purpose: convert a user-controlled microphone recording into editable composer text without creating a separate voice conversation:

- renderer captures audio with browser microphone APIs;
- `POST /api/frontend/voice/transcriptions` accepts audio bytes plus frontend scope;
- backend creates a Voice recording, appends the chunk, completes it, and runs `complete_voice_message(...)` through the configured STT adapter;
- response returns transcript and safe metadata only;
- the frontend inserts the transcript into the existing composer draft and waits for manual send.

This boundary does not implement continuous Conversation Mode, TTS playback, interruption, or automatic message send.

### `READY FrontendV2VoiceConversationBoundary`

Purpose: close the frontend V2 Conversation Mode turn loop:

- recording/transcription;
- same conversation text turn;
- persisted assistant text;
- governed TTS synthesis;
- frontend-safe audio return;
- playback completion before returning to listening;
- transcript/response persistence evidence.

Implemented by `POST /api/frontend/voice/conversation-turn`.

This boundary does not claim full duplex Voice. Playback interruption is frontend-side; provider-level generation cancellation remains bounded by existing text generation cancellation support.

### `PARTIAL GovernedDefaultVoicePackBoundary`

Purpose: expose only voices actually installed in backend-owned Voice Pack manifests:

- `GET /api/voice/packs` returns pack metadata, expected count, usable count and incomplete reasons;
- `GET /api/voice/voices` returns per-voice `voice_id`, display name, locale, profile, provider/engine, asset reference, version, checksum, license/provenance and usability;
- checksum validation is performed by the backend at discovery time;
- Settings persists `default_tts_voice` as a logical voice id, not a filename;
- Piper model resolution can map that logical id to a verified asset.

This boundary does not define an installer or release pack. Local voice asset
availability remains a backend-owned runtime fact exposed through the Voice
contracts above.

## Flow audit

### First run

Status: `READY`.

Backend evidence:

- Agent creation and validation: `backend/synapse/api/routers/agents.py`.
- Provider/model discovery: `backend/synapse/api/routers/models.py`.
- Primary/default/restart semantics: `backend/synapse/api/routers/agent_kinds.py`, `tests/test_primary_agent_runtime.py`, `tests/acceptance/test_primary_agent_initial_setup_e2e.py`.

Gap:

- closed by `GET /api/frontend/bootstrap` and `POST /api/frontend/first-agent`.

Remaining out of this slice:

- no frontend UI;
- no Electron typed client;
- no visual Presence projection.

### Text conversation

Status: `READY`.

Backend evidence:

- `backend/synapse/api/routers/conversations.py`.
- `backend/synapse/api/routers/frontend_boundary.py`.
- `docs/api.md`.

Flow:

```text
user message
→ frontend text conversation boundary
→ agent/chat runtime
→ streamed or final assistant response
→ persisted conversation
→ Conversation Log
```

### Voice

Status: `READY` for explicit recording → STT → text composer and frontend V2 Conversation Mode turn loop; `PARTIAL` for full duplex/provider-level interruption and default voice pack distribution.

Backend evidence:

- `backend/synapse/api/routers/voice.py`.
- Voice frontend/freeze tests under `tests/`.

Gap:

- explicit frontend transcription is closed by `POST /api/frontend/voice/transcriptions`;
- frontend V2 Conversation Mode is closed by `POST /api/frontend/voice/conversation-turn`;
- default voice pack discovery is closed by `GET /api/voice/packs` and `GET /api/voice/voices`, but the release asset pack remains incomplete;
- full-duplex interruption/provider-level cancellation remains incomplete.

### Activity

Status: `READY` for backend transport and Frontend V2 Activity/Constellation visualization.

Backend evidence:

- `backend/synapse/api/routers/operational_projection.py`.
- `tests/test_operational_projection.py`.
- `tests/test_operational_projection_stream.py`.
- `tests/test_operational_projection_transport.py`.

Frontend V2 Slice 8 evidence:

- `apps/frontend-v2/src/shared/frontendClient.ts` consumes project activity snapshot and SSE stream endpoints.
- `apps/frontend-v2/src/shared/activityAdapter.ts` converts backend activity facts into frontend-owned scene state.
- The renderer does not consume backend models directly and does not create a second event stream.
- Cursor, stale event, cross-project and resync/degraded states are represented frontend-side.

### Insight

Status: `READY` for backend contract and Frontend V2 Slice 9 consumption.

Backend evidence:

- `backend/synapse/api/routers/system.py`.
- `tests/acceptance/test_insight_system_e2e.py`.

Frontend V2 Slice 9 evidence:

- `apps/frontend-v2/src/shared/frontendClient.ts` exposes `insightReport()` for `GET /api/insight/report`.
- `apps/frontend-v2/src/shared/types.ts` defines frontend-safe Insight report, hardware, GPU, provider/model recommendation, evidence and diagnostic types.
- `apps/frontend-v2/src/renderer/main.tsx` consumes the report on demand from the sidebar Insight action and renders loading, ready, degraded, unavailable and error states with manual refresh only.
- Recommendation presentation uses backend `status`, `reason`, `provider_id`, resource estimates and optional `source`; the frontend does not hardcode a model catalog and does not treat recommendations as installed models.

### Settings

Status: `READY` for Frontend V2 Slice 10.

Backend evidence:

- `backend/synapse/api/routers/models.py` exposes Model Hub defaults, catalog, providers and Provider Settings update routes.
- `backend/synapse/providers/settings.py` persists provider enablement, endpoint and default model without exposing plaintext secrets.
- `backend/synapse/api/routers/voice.py` exposes Voice settings, providers, voice packs and discovered TTS voices.

Frontend V2 Slice 10 evidence:

- `apps/frontend-v2/src/shared/frontendClient.ts` aggregates real settings through `settingsSnapshot()` and updates them through typed `POST`/`PATCH` calls.
- `apps/frontend-v2/src/renderer/main.tsx` renders the governed Settings sections Personalization, Voice, Models, Themes and Insight. The Voice selector is populated from backend-discovered voices and disables incomplete/corrupt entries.
- Provider/model save validates against the fetched backend model registry before submitting.
- Reduced motion is the only frontend-owned setting and is persisted through `apps/frontend-v2/src/shared/settingsPreferences.ts`.

### Notifications

Status: `READY` for Frontend V2 Slice 11.

Backend evidence:

- `backend/synapse/api/routers/platform.py` exposes `GET /api/notifications`, `GET /api/notifications/unread`, `POST /api/notifications/{notification_id}/read` and `DELETE /api/notifications/{notification_id}`.
- `backend/synapse/notifications/models.py` defines the durable frontend-safe notification record fields, severity set and category taxonomy.
- `backend/synapse/notifications/runtime.py` maps only selected approval, scheduler, daemon, agent, tool and worker failure events into user-visible notifications.
- `tests/test_notification_runtime.py` covers persistence, list/unread, mark-read, delete, approval-generated notifications and cleanup.

Frontend V2 Slice 11 evidence:

- `apps/frontend-v2/src/shared/types.ts` defines `NotificationRecord`, severity and category types matching the backend record.
- `apps/frontend-v2/src/shared/frontendClient.ts` consumes list, mark-read and dismiss/delete routes through typed methods.
- `apps/frontend-v2/src/renderer/main.tsx` renders Notifications as a header button plus elevated internal popover, not page navigation or sidebar.
- Read/unread is factual from backend records. Dismiss uses notification deletion only and does not resolve approvals.
- Refresh is explicit and non-polling; if refresh fails with cached records the panel is degraded, and if no records are available it enters error state.

### Attachment

Status: `PARTIAL`.

Backend evidence:

- `backend/synapse/api/routers/conversations.py`.
- `backend/synapse/conversations/runtime.py`.

Gap:

- registration of already-staged storage references exists;
- frontend-safe local file staging/upload is not identified.
