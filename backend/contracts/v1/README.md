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
| `learning_get` | `source_job_id`; returns durable background status, attempts, error and pending conflict metadata |
| `job_cancel` | `job_id`; persists cancellation before terminating its worker |
| `mission_execute` | `mission_id`; returns `capability_unavailable` in this version |
| `tool_execute` | `mission_id`, `operation`: `list`/`read` with `path`, `create`/`replace` with `path` and UTF-8 `content` |
| `tool_recovery` | `intent_id`, `mode` (`inspect`, `finalize`, `restore`, `safe_abandon`); optional `expected_current_hash` for restore |

Scopes use exact `project:<id>` strings. Memory reads require an explicit `context_reference` equal to the stored scope. `memory_put` requires a current `expected_revision` (zero for a new key), `kind` of `constraint`, `decision`, `fact`, `reproduced_issue`, `root_cause`, or `recovery`, `status` of `active`, `resolved`, or `superseded`, and a provenance object containing `source_type`, `source_id`, and `evidence`. Each update creates a new revision.

`chat_get` returns `messages`, `next_cursor`, and `has_more`; `memory_get` returns `revisions`, `next_revision`, and `has_more`. Supply the returned cursor with a new request ID while `has_more` is true. Pages stop at the requested count or a 220,000-byte record budget, whichever comes first. Responses have a 240,000-byte result budget; oversized results fail with `response_too_large`. A repeated request ID returns its original page snapshot even if new records have since arrived.

A mission contract has `version:1`, `scope`, `objective`, nonempty `actions` and `resources`, and `rollback`. Optional `artifact_digests` and `artifact_previous_digests` map exact resource paths to lowercase SHA-256 content digests. Optional `skill` pins `scope`, `id`, `version` and `digest`. These fields default to absent for existing requests. `mission_propose` returns its SHA-256 `contract_digest`. Approval requires the exact digest. Only a proposed mission can be approved; approved missions can be revoked; proposed or approved missions can be cancelled. Terminal states cannot transition.

On Windows, `tool_execute` supports bounded `workspace_list`, `workspace_read`, `artifact_create`, and `artifact_replace` operations against exact resource paths in an approved mission. Create requires its digest and rollback `manual removal`. Replace requires the exact old and new digests and rollback `verified backup`; it holds an exclusive handle, persists and checks its backup and identity before an in-place write, flushes and reads back through that handle. This is not an atomic publication. Files are bounded to 32,768 UTF-8 bytes; list is limited to 128 entries. Paths use relative ASCII components; traversal, streams, reparse points, hard-linked files, Core state and unsupported types are denied. A pinned Skill must match its immutable registered digest, declare the selected tool and permission, and have declarations contained in mission actions. Its instructions are not executable authority. Only local fixed NTFS volumes are supported; other volumes and platforms return `capability_unavailable`. Delete remains unavailable.

Create and replace commit an intent before touching the file. A completed receipt and observed SHA-256 are committed with its event. A repeated identical request returns the original receipt, and an altered request ID conflicts. A prepared intent is never automatically replayed. `inspect` reads journal metadata; `finalize` verifies a prepared replacement against its identity, approved digest and backup; `restore` verifies those and the current content (replacement digest by default, or the explicitly supplied expected SHA-256), commits a separate restore intent and writes the verified backup. `safe_abandon` releases an absent prepared create or a prepared restore whose original snapshot is still present; for the latter, `intent_id` is the restore request ID. Mutation requires the original mission to remain approved. Ambiguity, unexpected contents and corrupted backups return `recovery_required`. This boundary is not a sandbox against another process running as the OS owner.

```json
{"version":1,"request_id":"inspect-1","command":{"type":"tool_recovery","intent_id":"replace-1","mode":"inspect"}}
{"version":1,"request_id":"restore-1","command":{"type":"tool_recovery","intent_id":"replace-1","mode":"restore"}}
```

A model manifest has `id`, `provider`, `endpoint`, `capabilities`, and `memory_bytes`. Registration is catalog data; it does not load a model or prove operation. Inference requires `provider:"lm_studio"`, a `chat` capability, an explicit registered model ID, and a numeric loopback HTTP endpoint such as `http://127.0.0.1:1234` (optionally ending in `/v1`). Set `SYNAPSE_PYTHON_EXECUTABLE` to an existing Python 3.14 executable before starting the CLI. A missing executable or provider becomes a typed failed job. There is no cloud or synthetic production fallback. LM Studio's `/v1/models` may advertise downloaded but unloaded models; a request may trigger its JIT load. A Skill manifest has `id`, `version`, `scope`, `provenance`, `tools`, `permissions`, and `instructions`. Each registered version is immutable; registration does not grant tool authority.

The AI integration admits one active model call at a time. Start returns immediately so `job_cancel`, mission revocation and other Core commands remain available. Poll with `job_get` using a fresh request ID each time; replaying a poll request ID returns its original snapshot. Job states are `running`, `succeeded`, `failed`, `cancelled` and `interrupted`. On restart, unfinished foreground jobs become `interrupted` and are not automatically rerun. A repeated start request ID returns its original start receipt without another user message. Successful conversation jobs append one assistant message; other outcomes do not. Events contain job IDs/status/error codes, not prompts or answers. Provider errors include `model_unavailable`, `provider_unavailable`, `provider_timeout`, `provider_malformed`, `provider_redirect` and `invalid_endpoint`. Worker setup/protocol errors include `worker_unavailable` and `worker_protocol`. Cancellation suppresses late results.

After a successful conversation Core queues learning from only its latest human message, using the captured model endpoint and generation settings. Foreground inference preempts learning; interrupted learning resumes on a later dispatch, with at most three failed or interrupted attempts. Query `learning_get` with a fresh request ID after each poll: statuses are `queued`, `running`, `succeeded`, and `failed`. A completed extraction may report pending `kind_conflict` or `stale_source` conflicts. Failure never changes the completed conversation. Core validates the whole structured result before writing: at most eight source quotes, each at most 512 UTF-8 bytes, with a lowercase key and a fact, constraint or decision kind. Credentials are conservatively filtered; the filter is not comprehensive. Model classification can be wrong even for exact quotes. Identical content is deduplicated; source event order prevents stale automatic output from replacing newer manual or automatic information. Memory reads continue to require an explicit matching project context.

Automatic admission is intentionally narrow: the content must equal the entire trimmed human message, which must be one short sentence and begin with a recognized first-person assertion. Quotation marks, attribution, questions and command-like text are conservatively rejected. This can reject useful statements and does not guarantee semantic correctness or identify every command or attribution. A rejected batch is reported as `invalid_candidates`; an empty result succeeds without creating memory.

Conversation requests send the complete stored message history of the selected chat in order, including `system`, `user` and `assistant` messages and the new user message once. Other chats are excluded. The history survives restart. The context is limited to 64 messages and 48,000 bytes of compact UTF-8 JSON; an over-limit start returns `invalid_request` and does not append the new message or create a job. Standalone inference sends one user message under the same byte limit. The limits do not imply a model-specific token capacity.

Model manifests may omit `generation` for legacy behavior (1024 output tokens, 10000 ms, provider default reasoning). When supplied, `generation` must contain exactly `max_output_tokens` (integer 1–4096), `timeout_ms` (integer 250–120000), and `reasoning_effort` (`provider_default`, `none`, `low`, `medium`, or `high`). Core snapshots the effective settings in the job; `job_get` returns them as `generation`, including after restart. For the local OpenAI-compatible provider, `max_output_tokens` maps to `max_tokens` and `reasoning_effort` is omitted only for `provider_default`. Provider errors remain errors; settings do not imply model support. The worker HTTP timeout uses the configured value, and Core's supervisor adds at most 5000 ms for startup and cleanup. The worker protocol is version 3; the public API remains version 1.

Registry lists return bounded metadata pages with `next_cursor` and `has_more`; repeat with a new request ID and the returned `after` cursor until `has_more` is false. `models_list` entries contain `id`, `provider`, `capabilities`, `memory_bytes`, and `operational`; `skills_list` entries contain `id`, `version`, `scope`, `digest`, and `operational`. `model_get` and `skill_get` return complete registered manifests. Cursors are opaque append-order positions; do not infer IDs or ordering from them. List pages stop at the count or 220,000-byte record budget.

Storage schema version 6 adds the learning queue, source cursors and conflict metadata and migrates earlier schemas on open.

State uses one SQLite Core connection with WAL and FULL synchronous transactions. A process-held exclusive lock on the canonical state directory refuses a second live Core process with `state_in_use` and releases on process exit. Domain state, events, and the request receipt commit together. A repeated request ID with the same payload returns its original response, including after restart. A changed payload with that ID returns `idempotency_conflict`. `events_read` supports ordered replay by cursor. The state directory is bound to the canonical workspace path and rejects a different workspace.
