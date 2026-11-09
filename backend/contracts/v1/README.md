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
| `chat_get` | `chat_id` |
| `message_append` | `chat_id`, `message_id`, `role` (`user`, `assistant`, `system`), `content` |
| `memory_put` | `scope`, `key`, `kind`, `content`, `expected_revision`, `provenance`, `status` |
| `memory_get` | `scope`, `context_reference`, `key` |
| `mission_propose` | `mission_id`, `contract` |
| `mission_approve` | `mission_id`, `contract_digest` |
| `mission_cancel`, `mission_revoke` | `mission_id`, `reason` |
| `mission_get` | `mission_id` |
| `model_register` | `model` |
| `models_list` | none |
| `skill_register` | `skill` |
| `skills_list` | `scope` |
| `capabilities_list` | none |
| `inference` | `model_id`, `prompt`; returns `capability_unavailable` in this version |
| `mission_execute` | `mission_id`; returns `capability_unavailable` in this version |

Scopes use exact `project:<id>` strings. Memory reads require an explicit `context_reference` equal to the stored scope. `memory_put` requires a current `expected_revision` (zero for a new key), `kind` of `constraint`, `decision`, `fact`, `reproduced_issue`, `root_cause`, or `recovery`, `status` of `active`, `resolved`, or `superseded`, and a provenance object containing `source_type`, `source_id`, and `evidence`. Each update creates a new revision.

A mission contract has `version:1`, `scope`, `objective`, nonempty `actions` and `resources`, and `rollback`. `mission_propose` returns its SHA-256 `contract_digest`. Approval requires the exact digest. Only a proposed mission can be approved; approved missions can be revoked; proposed or approved missions can be cancelled. Terminal states cannot transition. This version does not execute effects.

A model manifest has `id`, `provider`, `endpoint`, `capabilities`, and `memory_bytes`. Registration is catalog data only: it does not activate a provider. A Skill manifest has `id`, `version`, `scope`, `provenance`, `tools`, `permissions`, and `instructions`. Each registered version is immutable; registration does not grant tool authority.

State uses one SQLite Core connection with WAL and FULL synchronous transactions. Domain state, events, and the request receipt commit together. A repeated request ID with the same payload returns its original response, including after restart. A changed payload with that ID returns `idempotency_conflict`. `events_read` supports ordered replay by cursor. The state directory is bound to the canonical workspace path and rejects a different workspace.
