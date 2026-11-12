# Synapse Core local protocol v1

Run `synapse-backend --state-dir PATH --workspace PATH` with an existing workspace directory. The process reads one UTF-8 JSON request per line from stdin and writes exactly one JSON response per line to stdout. A request line is limited to 65,536 bytes, excluding its line ending. Startup errors go to stderr and exit nonzero. The CLI is a local human-owned transport, not an authenticated network API.

On Windows, `--local-endpoint NAME` selects the same v1 framing over an owner-only
local named pipe. The Core stays running after the client disconnects and can
finish active jobs while no client is attached. The host admits one pipe
connection at a time. Desktop clients release it after each exchange. See the
[Windows desktop guide](../../../docs/guides/windows-native-desktop.md).

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
| `mission_plan_start` | `mission_id`, `scope`, `model_id`, `objective`, required `review_model_id` and `review_generation`; optional exact `skill` and `context` references |
| `mission_plan_get` | `mission_id`; returns job status, pinned job metadata and, on success, validated `plan` and proposed `mission` |
| `project_check_start` | `mission_id`, zero-based `check_index`, and exact planned `artifacts` of `{path, content}` |
| `project_check_get` | `check_id`; returns current status, cleanup state and completed phase receipt |
| `project_check_cancel` | `check_id`; stops a running check |
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
| `conversation_start` | `chat_id`, `model_id`, `content`; optional exact `skill` pin and `context` references; appends one user message and starts an asynchronous AI job |
| `job_get` | `job_id`; returns job state, content/error, deterministic message IDs, `skill` for guided jobs, and selected `context` metadata when references were supplied |
| `learning_get` | `source_job_id`; returns durable background status, attempts, error and pending conflict metadata |
| `job_cancel` | `job_id`; persists cancellation before terminating its worker |
| `mission_execute` | `mission_id`; starts generation and integration for an approved sealed mission |
| `mission_run_get` | `mission_id`; returns candidate digest, phase, review, pre/postcheck counts and integration intents |
| `mission_recovery_inspect` | `mission_id`; observes journaled paths in a mission requiring recovery |
| `mission_recovery_resolve` | `mission_id`, `mode` (`finalize` or `rollback`); schedules owner resolution |
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

Optional conversation `skill` has exactly `scope`, `id`, `version`, and `digest`. Core resolves that immutable registered version and requires the chat's exact project scope and complete matching digest before appending the human message. Missing versions return `not_found`; mismatched scope/digest returns `contract_conflict`. The source job snapshots the pin durably; `job_get.skill` remains unchanged after registering another version or restarting. Unguided request serialization and job response shapes omit `skill` as before. Reusing a start request ID returns its original receipt; altering the pin with that ID conflicts.

Guided conversations prepend one Core-authored system message marking Skill instructions as untrusted domain data, with a serialized JSON object containing only the pin and instructions. Skill tool/permission declarations are excluded. Guidance grants no file access, mission approval, memory approval, or executable authority; worker output has no Core-command dispatch path. Canonical memory still requires explicit references through the separate `context` field or `memory_get`. Guidance is ephemeral context, never a chat message or an automatic-learning source; learning continues to receive only the latest human source and its fixed extraction instruction. The full guidance message counts toward the same 64-message/48,000-byte context budget and the worker's 32,768-byte per-message limit; overflow rejects the start atomically. Registry limits do not guarantee a Skill fits together with a conversation. `skill_guidance` is implemented for explicit pins and requires an available model; discovery, evolution and autonomous mission execution remain unavailable.

Optional conversation `context` is a list of at most 16 unique exact `{"scope":"project:<id>","key":"<key>"}` references, with no other fields. An absent or empty list is omitted in canonical serialization and `job_get`, preserving ordinary/guided requests. Keys use the existing nonempty, NUL-free 256 UTF-8 byte memory limit; scopes use the existing exact project scope validation. Duplicate entries and malformed references return `invalid_request`. Core resolves each exact latest revision within the dispatcher transaction through the explicit memory scope gate. Missing keys return `not_found`; a latest `resolved` or `superseded` revision returns `context_inactive`, without falling back to an older active revision. Explicit cross-project reads are allowed; references do not change the source chat or learning scope, promote records, or read other keys, chats, or project transcripts.

Each selected record becomes a Core-authored system message that marks the following serialized JSON as untrusted quoted data. Only its scope, key, revision, kind, content and `content_digest` enter that message. It grants no mission approval, tool execution, further memory access, or authority from model output. These wrappers, optional Skill guidance, history and the new human message all count within 64 messages and 48,000 bytes of compact serialized UTF-8 JSON; each message content also remains within 32,768 UTF-8 bytes. Wrappers and JSON escaping count; nothing is silently truncated. Overflow returns `invalid_request` before appending the human message or starting a job.

`job_get.context` durably returns the selected list with exactly `scope`, `key`, `revision`, `kind`, and `content_digest` (lowercase SHA-256 of the raw content's UTF-8 bytes). It excludes content and remains pinned after subsequent manual revisions, cancellation/failure, or restart. Altering references with the same start request ID conflicts; an identical replay returns the original receipt without a new selection. Injected context remains outside stored chat messages and outside automatic learning, whose sole source is still the latest human message. Natural-language name resolution and automatic memory discovery are not implemented.

Model manifests may omit `generation` for legacy behavior (1024 output tokens, 10000 ms, provider default reasoning). When supplied, `generation` must contain exactly `max_output_tokens` (integer 1–4096), `timeout_ms` (integer 250–120000), and `reasoning_effort` (`provider_default`, `none`, `low`, `medium`, or `high`). Core snapshots the effective settings in the job; `job_get` returns them as `generation`, including after restart. For the local OpenAI-compatible provider, `max_output_tokens` maps to `max_tokens` and `reasoning_effort` is omitted only for `provider_default`. Provider errors remain errors; settings do not imply model support. The worker HTTP timeout uses the configured value, and Core's supervisor adds at most 5000 ms for startup and cleanup. The worker protocol is version 4; the public API remains version 1.

Registry lists return bounded metadata pages with `next_cursor` and `has_more`; repeat with a new request ID and the returned `after` cursor until `has_more` is false. `models_list` entries contain `id`, `provider`, `capabilities`, `memory_bytes`, and `operational`; `skills_list` entries contain `id`, `version`, `scope`, `digest`, and `operational`. `model_get` and `skill_get` return complete registered manifests. Cursors are opaque append-order positions; do not infer IDs or ordering from them. List pages stop at the count or 220,000-byte record budget.

Storage schema version 9 adds durable mission plans, job linkage, captured policy snapshots and sealed proposals. Version 8 adds nullable selected context metadata on jobs and migrates earlier schemas on open. Existing jobs omit context. Version 7 introduced nullable job Skill pins. Version 6 introduced the learning queue, source cursors and conflict metadata. The public API remains version 1 and worker protocol is version 4.

State uses one SQLite Core connection with WAL and FULL synchronous transactions. A process-held exclusive lock on the canonical state directory refuses a second live Core process with `state_in_use` and releases on process exit. Domain state, events, and the request receipt commit together. A repeated request ID with the same payload returns its original response, including after restart. A changed payload with that ID returns `idempotency_conflict`. `events_read` supports ordered replay by cursor. The state directory is bound to the canonical workspace path and rejects a different workspace.


## Structured mission planning (proposal only)

`mission_plan_start` uses the existing one-worker lifecycle and returns `job_id`,
`mission_id`, and `status:running`. It preempts background learning; another
foreground call returns `worker_busy`. Use `job_get`, `job_cancel`, or
`mission_plan_get` with fresh request IDs. A mission ID is reserved at start and
cannot be retried or rebound, including after failed/cancelled/interrupted work;
use a new mission ID. Identical start receipts replay without another call.

The primary and reviewer must be registered supported chat models at numeric
loopback HTTP endpoints. The reviewer may have the same model ID. Explicit
`review_generation` uses the existing Generation shape, must validate, and must
differ from the primary's captured effective generation. Planning uses the primary
registry generation without increasing any budget. Both complete model manifests
and their SHA-256 digests are pinned; the reviewer generation is also sealed.
This does not invoke the reviewer, load a model, or claim independent weights.

The planner sees only the original objective, fixed Core instructions, optional
exact Skill guidance resolved in the mission's explicit project scope, and exact
selected context through the existing reference gate. It reads no Workspace files
or chat history. All wrappers count toward 64 messages, 48,000 serialized UTF-8
bytes and 32,768 UTF-8 bytes per message, checked before creating a running job.
Skill/context metadata remains pinned in the job. No planning output enters
canonical learning.

Worker protocol 4 adds the typed purpose `mission_plan` alongside `conversation`
and `learning`. The provider supplies a fixed strict JSON response schema. Core
independently rejects unknown fields at every depth and validates the entire
`{summary,artifacts,checks}` result atomically: summary 1..2048 UTF-8 bytes;
artifacts 1..16 `{path,purpose}` entries, purpose 1..512 UTF-8 bytes; path 1..128
ASCII bytes, a safe single Windows component with `.rs`, `.py`, `.md`, `.txt` or
`.toml` suffix, no traversal, reserved devices, separators, streams, trailing
space/dot or case-insensitive collisions. Checks are 1..8 unique `{kind,entrypoint}`
entries; `python_unittest` must name an exact `.py` artifact and `rust_test` an
exact `.rs` artifact. No content, executable, argv, environment, grant, approval,
command or Swarm fields are accepted. JSON schema bounds characters; Core enforces
UTF-8 byte limits and cross-array constraints. Invalid output produces only the
fixed `invalid_mission_plan` job error, with no raw output or partial proposal.

On success Core derives actions exactly `mission_generate`, `project_check`,
`artifact_create`, `workspace_read`, resources exactly the artifact paths, and
rollback `owned verified removal`. The original owner objective/scope are retained.
Optional `MissionContract.execution` is a strict `MissionExecutionSpec` containing
`plan_id` (the source job ID), `primary_model`, `primary_model_digest`, `review_model`,
`review_model_digest`, `review_generation`, validated `artifacts`/`checks`, and `limits`.
The limits are fixed: `per_file_bytes:8192`, `total_bytes:24576`,
`check_timeout_ms:30000`, `preparation_timeout_ms:120000`,
`max_tool_asset_bytes:2147483648`, `job_memory_bytes:536870912`,
`owned_processes:8`, `check_output_bytes:32768`, `generation_attempts:1`.
Preparation covers future trusted-asset copy/ACL setup separately from execution;
the asset byte cap does not claim a hard disk quota.

The plan, sealed complete contract, mission proposal and successful job commit in
one Core transaction. Public `mission_propose` cannot forge or alter the sealed
policy, rebind it to another mission, or take a reserved plan mission ID with a
legacy contract. `mission_plan_get` returns `plan` and `mission` only after success;
restart preserves successful proposals and marks in-flight jobs interrupted.
Absent `execution` serializes omitted, preserving legacy contract/request digests.

Planning creates the proposal and leaves source generation, checks and approval
to their own steps. An execution-policy contract uses the integrated coordinator.
Legacy `tool_execute` retains its exact-digest authorization rules.


Planner and conversation context finalization first validates all original logical
message pieces against the existing 64-message, 48,000-byte serialized UTF-8 and
32,768-byte per-message limits. It then combines only contiguous leading system
messages, preserving their content/order with explicit Core context boundaries,
for providers that require one initial system message. Later history roles/order
are preserved. The resulting wire messages are validated under the same limits,
including the merged system message; overflow fails before any human append or
running job insertion. The original logical 64-piece admission limit still applies
even when the provider receives fewer messages. Worker protocol 4 and public
request/contract serialization remain unchanged.

## Native project checks

A check starts only with an approved sealed plan, its exact candidate artifact
set and a valid recipe index. Use the start request ID as the check ID. Replaying
that ID returns the original response. Use a fresh request ID for current
status. The CLI drives the worker while input is idle. Embedded Core consumers
can call `poll_project_check` on their existing writer loop.

Windows uses a verified LPAC worker. Configure the dedicated Python executable
with `SYNAPSE_CHECK_PYTHON_EXECUTABLE` and its adjacent package manifest as
produced by `tools/runner/build_windows_python.py`. Rust uses the configured
`SYNAPSE_RUNNER_RUST_SYSROOT`, `SYNAPSE_RUNNER_VC_X64_LIB`,
`SYNAPSE_RUNNER_SDK_UM_X64_LIB` and `SYNAPSE_RUNNER_SDK_UCRT_X64_LIB`.
Optionally set `SYNAPSE_CHECK_RUST_RUN_ROOT` to a local absolute staging parent
when the linker cannot resolve its executable beneath the state directory.
Use a staging parent outside the Workspace that other principals cannot modify.
Core creates a fresh private child and leaves the parent ACL intact.
An unavailable runtime fails closed. One check may prepare, execute or clean
up at a time. Core persists the candidate, recipe and staged tool digests.
The phase receipt carries exit codes, output digests and observed token/Job
properties. Candidate files are staged privately.

Status and cleanup are independent. Cancellation or mission revocation
blocks late receipts. A graceful shutdown records observed cleanup. After an
abrupt exit, the next Core marks previously running checks interrupted and
reports unverified cleanup without replaying the check.

## Candidate generation and review

`mission_execute` starts one durable run for an approved sealed mission. The
Core stages exact candidate bytes privately and runs the approved checks
sequentially before launching the separate pinned reviewer. Only a successful
review can advance to publication. A review can reject a passing candidate.
The response exposes the digest and verdict, while candidate bytes stay in
Core storage. The CLI advances the run while idle. Use fresh request IDs to
query changing status with `mission_run_get`.

Mission cancellation or revocation stops active work. A restart marks active
runs `interrupted` before publication. The Core never replays an ambiguous
Workspace effect after restart.
The worker v4 envelope adds `mission_generate` and `mission_review` purposes
with distinct schema templates. Generation constrains the array to the
approved count and path set; the Core still validates exact occurrence and
content limits.

## Automatic mission integration

An approval for a sealed plan pins the Workspace directory identity. The
initial Windows implementation publishes flat, create-new artifacts in a
non-Git Workspace. It verifies the current approval, exact reviewed candidate,
passing prechecks and Workspace identity before applying prepared intents.
It checks the actual published bytes and repeats the approved checks using
the same tool digests. `integrated` requires final identity and byte readback.

A failed postcheck removes only files created by that run whose identity and
bytes still match, while the original approval remains active. `rolled_back`
reports verified removal. An ambiguous effect, changed target, abrupt exit or
revocation after a write leaves `recovery_required` with the relevant file
paths and intent IDs. The targets remain reserved. Ambiguous effects remain reserved until the owner can resolve them using the
evidence. See the recovery commands below.

Approvals from before Workspace identity pinning require a newly proposed
mission for automatic integration. Earlier runs already stopped at
`review_ready` are not published by migration.


## Mission recovery

Use a fresh request ID for every new observation with
`mission_recovery_inspect`. It returns the journaled paths, expected and
observed SHA-256 digests and file identities, plus an observation classification.
A repeated request ID returns the original receipt. The inspection does not
alter the Workspace or renew mission authority.

- `verified_owned` requires the recorded identity and exact reviewed bytes.
- `matching_bytes_unproven` means the bytes match but the journal lacks
  sufficient proof of file identity.
- `absent`, `changed` and `unreadable` distinguish absence, modification or
  replacement, and an observation that cannot be safely completed.

The owner can request `finalize` when every file has a confirmed identity and
every matching postcheck receipt is durable. The Core repeats guarded
readback before marking the run integrated. A `rollback` request rechecks the
current approval, reconciles absent targets and removes only confirmed
unchanged files. Changed files and ownership ambiguity keep the reservation.
The command returns a durable scheduling receipt. Query `mission_run_get`
with fresh IDs to observe the terminal outcome.

If Core stops during recovery, restart exposes `recovery_required`. A retry
of the original request ID does not restart work. Inspect again and submit
a new owner decision when the evidence permits it. Revocation prevents
subsequent resolution effects under the old approval.
