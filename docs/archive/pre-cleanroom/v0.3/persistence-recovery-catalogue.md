# Synapse 0.3 persistence and recovery catalogue

Paths below are relative to the governed Synapse data directory. This document
does not inspect or mutate the user's real persisted records.

## SQLite stores

| Owner | Default database | Integrity/recovery evidence | Operational status |
|---|---|---|---|
| Deployment | `deployment-runtime.sqlite3` | migration/checksum and append-only journal contracts | Not replay-tested here |
| Private Evals | `private-evals-runtime.sqlite3` | versioned immutable records and SQLite composition | Not replay-tested here |
| Coding Sessions | `coding-sessions-runtime.sqlite3` | migration checksum, checkpoints and fencing | Not crash-tested here |
| Skills phase 2 | `skills-phase2-runtime.sqlite3` | migrations, integrity and restore coordinator | Not restore-tested here |
| Sandbox | `sandbox-runtime.sqlite3` | frozen identities, journal and composition | Concrete driver opt-in |
| Repository Runtime | `repository-runtime.sqlite3` | mutation journal/fingerprint and composition | Not rollback-tested here |
| Search | `search/search.sqlite3` | search adapter/composition migration | Runtime opt-in/inert |
| Project Knowledge | `project_knowledge/project_knowledge.sqlite3` | document/chunk/index persistence | Learned embeddings optional |
| Voice | `voice/voice-journal-v1.sqlite3` | WAL, migration checksum, lineage/replay validation | Real device/provider untested |

## File and journal stores

| Owner | Principal roots | Lifecycle/recovery characteristic |
|---|---|---|
| Foundation events | `logs/events.jsonl` | append journal with inspection/cleanup paths |
| Agents | `agents/*`, `agent_provisioning/*`, `agent_admin_requests/*` | staging and atomic replacement for provisioning/admin changes |
| Conversations | `conversations/*/messages.jsonl`, manifests, summaries, attachments | append messages plus atomic metadata writes |
| Delegation | `delegation/*`, `delegation_execution/*`, `delegation_inbox/*`, `dead_letter/*` | source records, rebuildable inbox indexes and explicit recovery/DLQ |
| Missions/Swarm | `missions/*`, attempts/plans, `swarms/*`, `swarm/interactions/*` | revisioned YAML/result records and mission recovery history |
| Scheduler | `jobs/*`, `scheduler/recurring/*`, `locks/scheduler.lock`, daemon status | runner identity, lock recovery and job states |
| Memory | `memory/records.json` and agent `MEMORY.md` | atomic writes, backup/index recovery |
| Policies/approvals | `policies/*`, `approvals/*`, configuration YAML | revision/history and explicit approval states |
| World/attention/loop | `world_state/*`, `attention/*`, `agent_loop/*` | event/state records and proactive ledger |
| Multimodal | `audio/*`, `voice/*`, `vision/*`, `perception/*`, `multimodal/*` | session records, raw-data retention and voice journal |
| Desktop automation | plans/results and `desktop_automation/history/transitions.jsonl` | bounded transition history and verification results |
| Product skills | `skills/assignments`, `skills/leases`, `skills/installations` | file collections with schema and skip-with-warning recovery |
| Project governance | `project_governance/*`, `projects/*` | projects, RFCs, versions, reviews, plans, evidence and ADR records |
| Intelligence boundary | `intelligence_boundary/*` | assets, profiles, decisions, manifests, approvals and ledger |
| Health/maintenance | migrations, maintenance plans/executions, diagnostics | inspection and explicit maintenance plan execution |

## Recovery classification

- `IMPLEMENTED`: atomic writes, migration checks, journals, lineage validation,
  fencing, staging, inbox rebuild and dead-letter flows exist in code.
- `INTEGRATED`: the global SQLite compositions for deployment, private evals,
  coding sessions, skills, sandbox and repository runtime are wired and active.
- `TESTED`: architecture tests verify composition and freeze constraints; scoped
  persistence suites exist but were not all rerun in this inventory mission.
- `NOT OPERATIONAL`: no current crash injection, database corruption, rollback,
  restart or reboot recovery evidence was produced.

## Required recovery validation

1. Start and cleanly close every active global binding against disposable data.
2. Restart against the same data and compare immutable IDs/checksums.
3. Interrupt one write per store and verify atomicity or explicit corruption.
4. Exercise migration checksum mismatch without modifying the database.
5. Rebuild derived indexes/inboxes and compare source-of-truth records.
6. Validate rollback/fencing for repository, coding session and deployment.
7. Run retention/cleanup in dry-run before any destructive path.
