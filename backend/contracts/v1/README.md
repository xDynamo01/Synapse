# Synapse Core local protocol v1

Run `synapse-backend --state-dir PATH --workspace PATH` with an existing workspace directory. The process reads one UTF-8 JSON request per line from stdin and writes exactly one JSON response per line to stdout. A request line is limited to 65,536 bytes, excluding its line ending. Startup errors go to stderr and exit nonzero. The CLI is a local human-owned transport, not an authenticated network API.

Every request has exactly `version`, `request_id`, and `command`. `version` is `1`; `request_id` is a nonempty string of at most 128 bytes. Unknown fields and protocol versions are rejected. Commands use a `type` tag in snake case. Every response has `version`, `request_id` (null if parsing failed), `ok`, `event_cursor`, `result`, and `error` with stable `code` and human-readable `message`.

Example:

```json
{"version":1,"request_id":"health-1","command":{"type":"health"}}
```

The available command shapes are:

| Type | Additional fields |
| --- | --- |
| `health` | none |
| `events_read` | `after` (cursor), `limit` (1–200) |
| `chat_create` | `chat_id`, `title`, `scope` |
| `chat_get` | `chat_id`; optional `after` (message sequence cursor, default 0), `limit` (1–100, default 50) |
| `message_append` | `chat_id`, `message_id`, `role` (`user`, `assistant`, `system`), `content` |
| `memory_put` | `scope`, `key`, `kind`, `content`, `expected_revision`, `provenance`, `status` |
| `memory_get` | `scope`, `context_reference`, `key`; optional `after_revision` (default 0), `limit` (1–100, default 50) |
| `mission_propose` | `mission_id`, `contract` |
| `mission_approve` | `mission_id`, `contract_digest` |
| `mission_cancel`, `mission_revoke` | `mission_id`, `reason` |
| `mission_get` | `mission_id` |
| `model_register` | `model` |
| `models_list` | optional `after` (opaque registry cursor, default 0), `limit` (1–100, default 50) |
| `model_get` | `model_id` |
| `skill_register` | `skill` |
| `skills_list` | `scope`; optional `after` (opaque registry cursor, default 0), `limit` (1–100, default 50) |
| `skill_get` | `scope`, `skill_id`, `version` |
| `capabilities_list` | none |
| `inference` | `model_id`, `prompt`; starts an asynchronous AI job and returns `job_id`, `status:running` |
| `conversation_start` | `chat_id`, `model_id`, `content`; appends one user message and starts an asynchronous AI job |
| `job_get` | `job_id`; returns job state, content/error and deterministic message IDs |
| `job_cancel` | `job_id`; persists cancellation before terminating its worker |
| `mission_execute` | `mission_id`; returns `capability_unavailable` in this version |

Scopes use exact `project:<id>` strings. Memory reads require an explicit `context_reference` equal to the stored scope. `memory_put` requires a current `expected_revision` (zero for a new key), `kind` of `constraint`, `decision`, `fact`, `reproduced_issue`, `root_cause`, or `recovery`, `status` of `active`, `resolved`, or `superseded`, and a provenance object containing `source_type`, `source_id`, and `evidence`. Each update creates a new revision.

`chat_get` returns `messages`, `next_cursor`, and `has_more`; `memory_get` returns `revisions`, `next_revision`, and `has_more`. Supply the returned cursor with a new request ID while `has_more` is true. Pages stop at the requested count or a 220,000-byte record budget, whichever comes first. Responses have a 240,000-byte result budget; oversized results fail with `response_too_large`. A repeated request ID returns its original page snapshot even if new records have since arrived.

A mission contract has `version:1`, `scope`, `objective`, nonempty `actions` and `resources`, and `rollback`. `mission_propose` returns its SHA-256 `contract_digest`. Approval requires the exact digest. Only a proposed mission can be approved; approved missions can be revoked; proposed or approved missions can be cancelled. Terminal states cannot transition. This version does not execute effects.

A model manifest has `id`, `provider`, `endpoint`, `capabilities`, and `memory_bytes`. Registration is catalog data; it does not load a model or prove operation. Inference requires `provider:"lm_studio"`, a `chat` capability, an explicit registered model ID, and a numeric loopback HTTP endpoint such as `http://127.0.0.1:1234` (optionally ending in `/v1`). Set `SYNAPSE_PYTHON_EXECUTABLE` to an existing Python 3.14 executable before starting the CLI. A missing executable or provider becomes a typed failed job. There is no cloud or synthetic production fallback. LM Studio's `/v1/models` may advertise downloaded but unloaded models; a request may trigger its JIT load. A Skill manifest has `id`, `version`, `scope`, `provenance`, `tools`, `permissions`, and `instructions`. Each registered version is immutable; registration does not grant tool authority.

The initial AI integration admits one active job at a time. Start returns immediately so `job_cancel`, mission revocation and other Core commands remain available. Poll with `job_get` using a fresh request ID each time; replaying a poll request ID returns its original snapshot. Job states are `running`, `succeeded`, `failed`, `cancelled` and `interrupted`. On restart, unfinished jobs become `interrupted` and are not automatically rerun. A repeated start request ID returns its original start receipt without another user message. Successful conversation jobs append one assistant message; other outcomes do not. Events contain job IDs/status/error codes, not prompts or answers. Provider errors include `model_unavailable`, `provider_unavailable`, `provider_timeout`, `provider_malformed`, `provider_redirect` and `invalid_endpoint`. Worker setup/protocol errors include `worker_unavailable` and `worker_protocol`. Cancellation suppresses late results. Canonical memory extraction is not integrated.

Conversation requests send the complete stored message history of the selected chat in order, including `system`, `user` and `assistant` messages and the new user message once. Other chats are excluded. The history survives restart. The context is limited to 64 messages and 48,000 bytes of compact UTF-8 JSON; an over-limit start returns `invalid_request` and does not append the new message or create a job. Standalone inference sends one user message under the same byte limit. The limits do not imply a model-specific token capacity.

Registry lists return bounded metadata pages with `next_cursor` and `has_more`; repeat with a new request ID and the returned `after` cursor until `has_more` is false. `models_list` entries contain `id`, `provider`, `capabilities`, `memory_bytes`, and `operational`; `skills_list` entries contain `id`, `version`, `scope`, `digest`, and `operational`. `model_get` and `skill_get` return complete registered manifests. Cursors are opaque append-order positions; do not infer IDs or ordering from them. List pages stop at the count or 220,000-byte record budget.

Storage schema version 2 adds durable AI jobs and migrates version 1 on open.

State uses one SQLite Core connection with WAL and FULL synchronous transactions. A process-held exclusive lock on the canonical state directory refuses a second live Core process with `state_in_use` and releases on process exit. Domain state, events, and the request receipt commit together. A repeated request ID with the same payload returns its original response, including after restart. A changed payload with that ID returns `idempotency_conflict`. `events_read` supports ordered replay by cursor. The state directory is bound to the canonical workspace path and rejects a different workspace.
