# API Specification

Intelligence Boundary exposes status/profile, metadata-only InformationAsset,
egress preview/decision/manifest/history and administrative trust,
classification and ledger-report surfaces. There is no force allow, bypass,
trust-all, bulk public marking, payload-to-provider or ledger mutation route.
The current contract is 494 paths, 550 unique operation IDs and 128 schemas.

Project Governance exposes controlled `/projects` project/context, RFC review
and gate, implementation-plan and evidence/acceptance resources. Status cannot
be mutated arbitrarily: there is no force approval, direct implemented, gate
bypass or arbitrary project-file endpoint.

Skills Phase 1 adds public discovery/resolution, assignment/lease reads,
administrative inspect/validate/install/status transitions/uninstall, and
diagnostic status/conflict/invalid/lease endpoints. Administrative mutations
require the existing admin/system transport context.

## Agent-kind surfaces

Primary exposes get/set/replace, interaction bootstrap/conversation and explicit
pause/resume. Ephemeral exposes mission list, instance/result reads, workforce-plan
read, reconcile, cleanup and authorized cancel. There is no arbitrary ephemeral
spawn endpoint. Persistent creation/update continues through canonical
AgentProvisioning DTOs; legacy Creator-only embodiment/default fields were removed.

## Router ownership

The API contract is implemented by 13 bounded-context routers and registered at
one point in `synapse.api.router_registry`. The legacy `api.routes` module is a
handler-free compatibility import. Transport DTOs live in their owning router;
shared header/error/Pydantic translation remains in `api.common`. The route
matrix and exact before/after OpenAPI snapshots are linked from
`docs/validation/architecture-stabilization-api-decomposition.md`.

The current frozen OpenAPI has no tags. Tags were deliberately not introduced
during structural decomposition because they would change the baseline.

## Desktop Automation + Application Control

Canonical discovery endpoints are `GET /applications`, `/windows`,
`/desktop/state`, `/automation/tree`, and `/automation/element`. Governed plan
operations are `POST /automation/plan`, `/automation/preview`,
`/automation/execute`, `/automation/cancel`, `/automation/verify`, and
`/automation/clipboard`. There is no application-specific route.

Commands are `/list-apps`, `/list-windows`, `/automation-plan`,
`/automation-preview`, `/automation-execute`, `/automation-verify`,
`/automation-cancel`, `/clipboard-get`, and `/clipboard-set`. Clipboard reads
return metadata only. All writes become normal governed plans; no command bypasses
Policy, Approval, verification, or audit.

## Insight + System Runtime

Read-only operational views are exposed at `/system`, `/hardware`, `/gpu`,
`/cpu`, `/system/memory`, `/storage`, `/processes`, `/insight/providers`,
`/models/recommendations`, `/insight/diagnostics`, and `/insight/report`.
`/system/memory`, `/insight/providers`, and `/insight/diagnostics` avoid collisions
with the frozen Memory, Provider, and Health contracts. `/system/insight` remains
the established compatibility projection. Process output is bounded and report
persistence excludes process lists.

Operational slash commands are `/system-info`, `/hardware-info`, `/gpu-info`,
`/memory-info`, `/disk-info`, `/insight-diagnostics`, `/insight-report`, and
`/model-recommendations`. All are queries and have no destructive variant.

## World State, Attention, and Agent Loop

Controlled client operations are exposed under `/world-state`, `/attention`,
`/agent-loop`, and `/agent-events`. Snapshot/entity/history reads, attention
inbox transitions, loop lifecycle/status/cycles, pending approvals, persistent
notifications, and a redacted event stream are client-facing. Reconciliation,
run-once, suppression, and proactive-mode mutation require an administrative
actor header. Direct state mutation, raw decision execution, lock internals,
and arbitrary action injection have no route.

The event stream allowlists only World State, Attention, Decision, and Loop
lifecycle summaries. Source payloads remain redacted by `EventBus` and the
stream adapter.

## Platform Governance

Canonical policy endpoints live under `/policies`; telemetry under `/events`,
`/trace`, and `/observability`; structured operational state under `/health`,
`/readiness`, and `/diagnostics`; safe foundation checks under `/foundation`
and `/security/redaction-test`. Routes are thin adapters over the same runtimes
used by commands. Policy mutations use revisions, telemetry is redacted, and no
diagnostic returns secret values or absolute paths.

## Voice, Audio and Speech

The frozen voice API exposes settings, real device discovery, provider health,
recording lifecycle, Voice Message completion, session lifecycle, conversation
turns, synthesis through canonical runtimes, and retention cleanup. No
Voice/Audio/Speech mock path exists in OpenAPI. The authoritative operation
matrix is in `docs/validation/voice-audio-speech-finalization.md`.

## Purpose

The Synapse API exposes backend runtime capabilities to trusted local clients.
It is an adapter over domain runtimes, not an independent business-logic layer.

Status: the Voice/Audio/Speech surface is **Implemented / Frozen**. Other API
domains retain their own status in `docs/backend/module-status.md`.

## Base Contract

- Framework: FastAPI.
- Application object: `synapse.main:app`.
- Default prefix: `/api`.
- Default development binding: `127.0.0.1:8717`.
- Encoding: JSON for requests/responses; multipart/binary only for explicit
  media endpoints.
- OpenAPI: generated by FastAPI at runtime.

The route module currently contains a large surface. V3 should organize route
ownership by domain without changing public paths casually.

## Actor Context

Routes that perform actor-sensitive operations accept headers where defined:

```text
X-Actor-Id
X-Actor-Type
X-Device-Id
```

The adapter converts them into `PermissionContext`. Absence uses the local
runtime default only where the endpoint contract permits it. Clients must not
use headers to claim authority they do not have; the backend still evaluates
permissions, resource scope, device trust, and approval state.

Target: replace implicit local trust with a documented local authentication and
session mechanism before remote binding is allowed.

## Error Mapping

Current common mapping:

| Exception | HTTP status |
| --- | ---: |
| `PermissionDenied` | 403 |
| `NotFound` | 404 |
| `ValidationError` | 422 |
| other `SynapseError` | 400 |
| unexpected exception | 500 |

Target error envelope:

```json
{
  "error": {
    "code": "duplicate_agent_id",
    "message": "Agent already exists: analyst",
    "details": {},
    "correlation_id": "..."
  }
}
```

Not all current endpoints emit this envelope. Until migration, clients must
handle FastAPI's current `detail` response as well.

## Resource Groups

The implemented route surface includes these groups:

- system health, readiness, daemon, lifecycle, presence;
- agents, identity, provisioning, admin and audit;
- chat, conversations and summaries;
- tasks, scheduler and retention;
- delegation, completion, execution, retry, timeout, recovery and dead letter;
- missions, mission context, supervision and mission control;
- approvals, decisions and tool intents;
- capabilities, tools, discovery, MCP and execution routing;
- models, model hub, providers and provider settings;
- agent-to-agent communication and notifications;
- multimodal, audio, speech, voice, vision and perception;
- system insight and frontend-agnostic domain responses.

The generated OpenAPI document is the exhaustive path inventory. This
specification defines cross-cutting behavior and stable resource patterns.

## Agent And Provisioning API

Implemented resource patterns include:

```text
POST   /api/agents
POST   /api/agents/preview
PATCH  /api/agents/{agent_id}
POST   /api/agents/{agent_id}/validate
POST   /api/agents/{agent_id}/activate
POST   /api/agents/{agent_id}/deactivate
POST   /api/agents/{agent_id}/archive
POST   /api/agents/{agent_id}/restore
DELETE /api/agents/{agent_id}
GET    /api/agent-provisioning/status
GET    /api/agent-provisioning/policy
GET    /api/agent-provisioning/requests
GET    /api/agent-provisioning/requests/{request_id}
POST   /api/agent-provisioning/requests/{request_id}/approve
POST   /api/agent-provisioning/requests/{request_id}/reject
POST   /api/agent-provisioning/requests/{request_id}/apply
```

Preview/dry-run must not write agent files or create approval requests.
Sensitive agent creation returns a durable provisioning and approval ID;
approve and apply remain separate operations.

## Conversation And Chat API

Physical deletion requires the explicit query parameter `confirmed=true`.
Without it, the API returns the structured `confirmation_required` conflict.
Attachment registration validates the declared size and full SHA-256 checksum
against the referenced file in `DATA_DIR`.

The canonical turn endpoint is `POST /api/conversations/{id}/turns`; streaming
uses `/turns/stream` with NDJSON lifecycle events. Conversation CRUD includes
revision-checked update, archive/restore/delete, bounded message pagination,
participants, summary generation, attachments, and message cancellation.

Legacy chat endpoints delegate to the same internal turn service. They do not
own provider, context, persistence, or tool logic.

## Memory And Context API

- `GET /memory` lists authorized records by optional scope/owner.
- `POST /memory` creates an explicit record.
- `GET/PATCH/DELETE /memory/{id}` provide revision-aware CRUD.
- `POST /memory/search` performs deterministic text/tag retrieval with budget.
- `GET /memory/export/records` and `POST /memory/import` transfer validated data.
- `POST /context/preview` returns provenance, budget, and omitted items.

Stable errors include `memory_not_found`, `invalid_scope`, `access_denied`,
`invalid_memory`, `revision_mismatch`, `persistence_failed`,
`context_budget_exceeded`, `sensitive_memory_denied`, and `import_invalid`.

## Models And Providers API

## Tools, Approvals And MCP API

Tool APIs expose catalog, preview, dry-run, execution status, cancellation, restricted
retry, rollback and history through ToolRuntime. Approval APIs manage pending records.
MCP APIs expose servers, health and discovery; execution uses the canonical tool path.

Provider routes list manifests, health and configured status. Model routes expose
catalog, available/discovered models, provider models, defaults, explicit folders,
refresh, validation, capabilities and selection preview. `POST /models/resolve`
returns source, reason, override and fallback warnings. Direct LM Studio chat remains
a controlled legacy diagnostic endpoint; product Chat uses ModelRouter.

## Asynchronous And Approval-Gated Operations

The current API often uses synchronous HTTP calls that return durable request
records. Target behavior:

1. validate synchronously;
2. persist request before returning;
3. return 200/202 with request ID and status;
4. let clients poll or subscribe to status/events;
5. bind approval to operation, arguments, requester, and target;
6. make apply idempotent or reject duplicate application explicitly.

No endpoint should keep an HTTP connection open for human approval.

## Pagination And Filtering

Many current list endpoints return complete arrays. Target list contracts use:

```text
limit
cursor
status
created_after
created_before
sort
```

Response target:

```json
{
  "items": [],
  "next_cursor": null,
  "total": 0
}
```

Pagination must be introduced per resource with compatibility notes; do not
silently change existing array responses.

## Idempotency

Mutating endpoints should accept or derive an idempotency key for operations
that may be retried by desktop clients. Existing durable IDs provide partial
protection in approval and execution flows. Target header:

```text
Idempotency-Key: <client-generated-id>
```

The backend persists the key with request/result and rejects conflicting reuse.

## Correlation

Clients should send a correlation identifier when a user action spans multiple
operations. The backend event model already carries correlation/causation data
in several domains. Target response headers expose the effective correlation
ID for support and trace lookup.

## Versioning

Current API paths are unversioned. Until a versioning decision is implemented:

- additive fields are preferred;
- field removal or semantic changes require migration notes;
- clients ignore unknown response fields;
- backend validates unknown enum/status values conservatively;
- persisted schema versions are not the same as HTTP API versions.

Target: introduce `/api/v1` only with an explicit compatibility and deprecation
policy, not as a mechanical path prefix.

## Security

- Bind to loopback by default.
- Never expose the development API on a network without authentication, TLS,
  origin policy, and threat review.
- CORS is not authentication.
- Redact secrets from request logs, errors, events, and OpenAPI examples.
- Validate uploaded file type, size, destination, and resource scope.
- Treat model/provider output as untrusted.

See [Security](security.md).

## Client Rules

- Use one typed API layer; components do not call `fetch` directly.
- Handle offline, loading, validation, permission, approval, and partial
  readiness states separately.
- Do not infer success from HTTP 200 alone; inspect the domain status.
- Do not fabricate records when an endpoint is unavailable.
- Preserve request/correlation IDs through user workflows.

## API Completion Criteria

- domain routers and DTOs have explicit ownership;
- stable error envelope and correlation headers;
- authentication decision for desktop/local clients;
- pagination for unbounded collections;
- idempotency for retryable mutations;
- generated OpenAPI validated in CI;
- contract tests for every public endpoint;
- no mock-only endpoint in production routing;
- documentation examples generated or checked against actual schemas.

## Perception API classification

| Surface | Classification | Notes |
| --- | --- | --- |
| signal ingest/query and active observations | public client | canonical runtime adapter; policy validation applies |
| uploaded image analysis and explicit screenshot | public client | caller-triggered only; no absolute paths |
| camera open/capture/close | administrative | optional and disabled by default |
| retention cleanup and observation delete/expire | administrative | destructive mutations are explicit |
| provider health, capabilities, sources, conflicts | diagnostics | optional capability state is truthful |
| raw provider execution details and storage paths | internal-only | intentionally not routed |
| multimodal fuse/get/correlation/context preview | public client | structured evidence, not a prompt |

No mock endpoint or continuous capture endpoint is exposed.
# Missions Operational API

The Missions API exposes canonical service adapters for mission lifecycle,
versioned planning and validation, DAG/task mutation, attempts, dispatch,
progress, result, trace, recovery, workers, swarms, DLQ, scheduler and daemon
lock recovery. Mutation DTOs carry expected revision/version and retries carry
idempotency keys where applicable. Routes contain serialization and error
conversion only; state transitions remain in domain runtimes.

Task deletion and archive are not supported by design because immutable
attempt, recovery and trace records reference task IDs. Plan deletion is also
unsupported; replacement creates a new immutable version.
# Administrative maintenance

The admin-only `/api/maintenance` surface exposes status, inspection, plan
creation/read/cancel/execute, history and contributor discovery. Requests accept
bounded registered scopes and never filesystem paths. Execution requires an
exact stored checksum and revision plus explicit confirmation; high-risk plans
also require their bound approval. Generic destructive Foundation and Retention
endpoints are no longer public.
