# Primary MoM — routing and settings

Updated: 2026-09-07

## Current status — optional specialists and default generalist

When MoM is enabled, the Primary chat uses a local deterministic intent policy
to select one saved operation route before inference. No extra LLM is called to
make this choice. Models settings exposes the default generalist and saves it
through the existing model-defaults endpoint. Settings > MoM configures four
specialists: coding, reasoning, review and summary. Ordinary conversation stays
on the generalist even when MoM is enabled, without an extra inference call.
Existing conversation routes are retained for compatibility with explicit MoM
API operations; ordinary chat no longer selects that route.

The composer has a persisted MoM toggle independent of Swarm. It reads current
configuration and uses revision-checked saves, blocks activation without a
specialist and requires readback after uncertain saves. Settings saves refresh
the toggle. The admitted model route is fixed before inference: switching off
during generation applies to subsequent selections, not the running inference.
No models are downloaded, loaded or unloaded by toggling the mode.

The initial `local-intent-v1` policy recognizes explicit Portuguese/English terms
in the leading request (up to 1,000 characters, before a fenced code block or
blank-line document body). Precedence is summary, review, coding, reasoning,
then conversation. This is a keyword classifier, not general semantic
understanding: mixed intents and implicit follow-ups may need clearer wording.
It selects one model per turn, not a multi-step parallel ensemble.

A missing specialist route, stale Primary binding or invalid provider fails
visibly instead of silently substituting the generalist. Conversation is the
category for unmatched ordinary messages, not an availability fallback.
The same model may serve several roles.
Disabled/absent MoM preserves the legacy runtime path and existing saved data;
this delivery does not enable MoM or edit the user's actual settings automatically.

Chat owns the routing port; a bootstrap adapter connects it to MoM. Chat does
not import the MoM domain. Existing Primary context loading, response preferences,
history, project context and tool permissions are preserved. Swarm and secondary
agents retain their assigned model paths. Slash commands keep their command path.
Selection events include operation, provider/model and revision; chat results
retain operation/revision. No new stream schema or telemetry display is implied.

Earlier routing delivery verification (historical): 24 focused MoM/boundary tests passed, including frontend turns and
streaming after runtime recreation, with mocked inference. Mypy passed all 800
source files; Ruff and diff check passed. Frontend: 113 tests, isolated Electron
settings QA and build passed. ESLint retains the existing voice callback warning.
Architecture: 267 passed, four existing failures remain (API helper/runtime
allowlists, composition line ceiling and OpenAPI count). Related chat/Primary/
local-pool/Swarm regression: 37 passed and four existing legacy local-chat/LM Studio
tests failed. Global backend is NOT READY; real LLM quality, latency and intent
classification accuracy have not been established by fixtures.

## Optional-mode verification — 2026-09-07

- Executed: 26 MoM/boundary tests passed, including saved default generalist
  through the frontend API after restart, one inference per conversation turn,
  specialist selection, and disable-during-inference affecting only the next turn.
- Executed: 113 frontend tests passed; isolated Electron QA passed four specialist
  selectors, persisted toggle, uncertain-save readback and bounded scrolling.
  This uses fake transport and inference, not the user's configured models.
- Executed: Ruff passed; global Mypy passed 800 source files; ESLint has no errors
  and retains the existing voice callback dependency warning; diff check passed.
- Executed: architecture 267 passed / 4 failed at the unchanged helper/runtime
  allowlists, composition line ceiling and frozen OpenAPI count listed above.
- Executed: Model Hub/frontend boundary regression 32 passed / 11 failed:
  provider count (9 versus 8), model-hub health, and nine conversation fixtures
  reaching unavailable LM Studio instead of their intended mock provider.
  These absent-MoM fixtures retain the unchanged legacy path; no test was weakened.
- Failed: standalone renderer type check retains the pre-existing
  ConversationRecord.updated_at error. Production Vite/main builds passed.
- Executed: current frontend and backend sidecar rebuilt for root Synapse.exe;
  runnable hygiene found no stale artifacts to retire. No user settings/model
  files were changed and no real-model performance/quality test was performed.

The current mode uses deterministic routing, not autonomous model-to-model
consultation or answer synthesis. Swarm, tool authority and model residency policy
are unchanged. Broad regression is not green; global backend remains NOT READY.

## Earlier slices

## Product boundary

MoM (Mixture of Models) is operation-level model routing for the current Primary
Agent. It does not create agents. The Primary keeps its identity and may use
different models for different operations. Swarm remains separate: each worker
keeps its assigned model. No Swarm execution path imports or invokes MoM.

The first slice implements explicit configuration and inference operations through
the backend API. A subsequent Settings slice adds the MoM tab with five model
selectors, persistent saves, explicit enable/disable, and reload after uncertain
saves. At that stage it did not change ordinary chat or classify requests.
The chat integration above now selects routes; dedicated constellation
presentation remains outside this delivery.
It starts disabled and does not alter existing user settings or model files.

## Implemented contract

- Operations: `conversation`, `coding`, `reasoning`, `review`, `summary`.
- One exact provider/model route per configured operation; no silent fallback.
- Routes are workspace-scoped and bound to the Primary identity at save time.
- Only a user may configure routes. Execution admits the current active Primary
  or a user acting through it; other agents are rejected.
- Replacing the Primary invalidates execution until the user reconfigures MoM.
- Revisions reject stale saves. Storage uses the existing atomic FileCollection
  and fails closed on malformed records. This is not tamper-proof storage:
  a valid manual edit is not cryptographically authenticated.
- Provider validation checks registration and the enabled flag. It does not
  prove credentials, model availability, available RAM, or successful inference.
- The existing model router retains provider egress enforcement. No new provider
  is installed or enabled; `lmstudio_local` is rejected in favor of canonical
  `lmstudio`. Local Synapse inference uses `synapse_local`.
- Each call generates text with the Primary's loaded identity, personality,
  durable context and the calling user's stored response style where applicable.
  It does not yet inherit a chat session's history or active project context.
- Calls expose no tools and execute no generated tool calls. Returned text is
  an inference result, not evidence that code, files or external actions ran.
- Current limits: 32,000 input characters, 1,024 requested output tokens,
  180-second timeout for `synapse_local`, 60 seconds otherwise. No automatic retry.
- Events contain operation identity, route, revision and outcome, not prompt,
  answer or raw exception text. MoM does not introduce a separate transcript log.

Primary authorization is checked at admission; replacing it does not cancel an
already-running inference. Local model residency remains governed by the existing
runtime pool, including its default one-model memory limit.

## API

All routes use existing Synapse API authentication and actor context. Do not
expose this local API publicly or treat an actor header as separate authentication.

1. `GET /api/primary/mom/configuration?workspace_id=default` reads configuration.
2. `PUT /api/primary/mom/configuration` saves routes with the revision read above.
3. `POST /api/primary/mom/operations` invokes one explicitly selected operation.

Example configuration (replace model placeholders with actual catalog IDs):

```json
{
  "workspace_id": "default",
  "expected_revision": 0,
  "enabled": true,
  "routes": [
    {"operation": "coding", "provider": "synapse_local", "model": "YOUR_CODE_MODEL_ID"},
    {"operation": "review", "provider": "synapse_local", "model": "YOUR_REVIEW_MODEL_ID"}
  ]
}
```

Example operation:

```json
{
  "workspace_id": "default",
  "operation": "coding",
  "message": "Write a Python function that validates a nonempty name."
}
```

The result includes content, provider, model, operation ID, operation type,
Primary ID and configuration revision. Mismatched provider/model responses fail.
To disable, save `enabled: false` with the current revision; disabling does not
require the old providers to remain available.

## Verification and next steps

Focused tests cover independent model routing without agent identity/config
changes, persistence across runtime recreation, stale revisions, inactive or
replaced Primary, worker denial, malformed storage, metadata-only events, API
validation and model-result mismatch. Provider inference is mocked: these tests
do not establish real model quality, latency or simultaneous GPU residency.

Architecture tests assert exactly two new non-bootstrap context edges:
`api -> mom` and `mom -> core`, with unchanged cyclic components. The frozen API
surface delta is two paths, three operations and six schemas. Existing global
readiness failures must not be hidden by these intentional baseline updates.

Next bounded slices: richer intent selection and multi-step result synthesis;
operation telemetry in the constellation; real-model resource/quality evaluation.
Swarm must not acquire this routing capability through any of these slices.

### Delivery gates

- Combined MoM and architecture run: 275 passed, 4 failed. A subsequently added
  exact-delta/cycle test also passed with the two other MoM boundary tests.
- The four remaining failures are the existing API helper allowlist, startup
  handler runtime resolution, composition-root line ceiling, and OpenAPI baseline
  discrepancy. MoM increases composition length from 486 to 494 lines; the
  preexisting 480-line ceiling remains exceeded rather than being relaxed.
- Mypy: all 798 backend source files passed. Focused Ruff and diff check passed.
- Governed backend build completed; packaged MoM runtime, composition adapters
  and API modules were verified in `backend/dist/synapse_backend/synapse_backend.exe`.
  The previous generated bundle at that target was replaced by the normal build;
  model files and the backup workspace were untouched. No commit or push.
- Real inference and automatic routing are not verified or delivered by this
  backend slice. Global backend status remains NOT READY.

### Settings delivery (2026-09-06)

Settings > MoM selects conversation, coding, reasoning, review and summary models
from the existing catalog. Each choice stores both provider and model, permits
reuse across operations, and retains missing saved models visibly instead of
silently replacing them. Saving is separate from existing defaults and Swarm.
Conflicted/unconfirmed saves require reload before retry. The UI has bounded
scrolling and does not load models or perform inference when saving.

The Settings-only stage temporarily retained default controls. The 2026-09-07
integration above removes their selection from Settings and gives enabled MoM
authority over the Primary chat route.

Frontend checks: 113 Vitest tests passed. Isolated Electron QA exercised the actual
Settings panel/selects with mocked transport: five roles, empty-route validation,
exact saves, remount persistence, save failure/reload and scrolling passed.
No real user configuration was changed. Frontend build passed and refreshed the
governed launcher bundle; no stale runnable artifacts were found to remove.
ESLint has zero errors and the existing voice callback dependency warning.
Full standalone renderer TypeScript check remains failed on preexisting Node/CSS
type configuration and ConversationRecord.updated_at issues, not treated as green.
