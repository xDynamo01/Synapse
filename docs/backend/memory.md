# Memory Runtime

Status: **Hierarchical extension implemented; global validation has outstanding failures.**

`MemoryStore` is canonical. `MemoryStorage` is the independent storage port and
`FileMemoryStorage` the current adapter. Scopes are `system`, `user`, `agent`,
`conversation`, `session`, `task`, `mission`, and `knowledge`. Records contain
owner, source, content type, timestamps, optional expiry/confidence, importance,
tags, metadata, SHA-256 checksum, revision, and status.

Session and conversation records are working memory and require expiry. Cleanup
expires elapsed records and bounds active items. Chat never promotes text into
memory automatically.

The adapter stores schema-versioned JSON at `DATA_DIR/memory/records.json` using
temporary-file atomic replacement. Corrupt/unsupported data raises
`persistence_failed`. Markdown `USER.md`, `SYSTEM.md`, `MEMORY.md`, and agent
`MEMORY.md` remain read-compatible and are not parsed by regex.

`retrieve_memory` performs authorized text/tag filtering and stable ranking by
match, importance, recency, and ID. Token cost is explicitly estimated as four
characters per token; semantic search is not simulated.

Exact scope/owner/content deduplicates by checksum. Updates and deletion require
expected revision. Deletion removes content and leaves an auditable tombstone.
Agent-private and sensitive records enforce owner isolation. Events contain IDs
and metadata, never full content.


## Hierarchical context (2026-10-23)

Persistent memory is not permanent model context. The extension reuses `MemoryStore`,
`MemoryRecord`, the existing JSON adapter, `ContextFusionRuntime`, `ContextLoader`,
and the model adapters. It does not introduce a second memory database or a new embedding dependency.

| Layer | Implementation |
| --- | --- |
| Agent Core | Configured identity/SOUL, AGENTS.md rules and skill references in `context/loader.py` and `models/adapters.py`. Retrieved experiences never become system messages. |
| Global | Existing system/user/agent scopes, filtered by relevance and authorization. Legacy Markdown remains readable; chat selects bounded matching paragraphs. |
| Workspace | Stable `workspace_id` on records, independent of Git; existing project IDs are reused. `chat/runtime.py` propagates scope through fusion and tools. |
| Episodic | `episodic` scope and `episode`, `decision`, `result`, `reference` kinds, with source, provenance and verification state. |
| Working | Expiring `working` scope owned by the individual agent; retention limits are per scope/owner/workspace. Existing session/conversation scopes remain supported. |
| Index | Derived `records.index.json`, containing record headers, lexical hashes, byte offsets and lengths. `discover`, `/api/memory/index` and `memory_index` expose authorized metadata, not record content. The agent tool lists scopes first and pages record headers in groups of 100. |

### Audit and storage decision

Previously, retrieval deserialized the complete record collection, the save lock
started after read/modify, and the final model adapter did not include selected
Context Fusion items. Legacy Markdown was loaded eagerly and memory text entered
the system role. The changes address these concrete paths rather than replacing RAG.

`FileMemoryStorage` remains schema-1 compatible and authoritative at
`memory/records.json`. New fields have defaults for old records. Writes serialize
compact JSON with byte-addressable records and atomically publish a derived index.
Missing, stale or structurally malformed derived indexes rebuild from canonical JSON.
A selected record inconsistent with its index header fails closed. A canonical
corruption is an explicit error. Index failure after a canonical commit is reported;
a retry/restart rebuilds the index and deduplication avoids a second record.
An initial legacy/index rebuild and mutations still read the complete collection;
steady-state discovery/search read index headers and only selected record bodies.
This is not a claim of constant-memory writes or a full-text database.

Transactions now cover read, expected-revision validation and write using the
existing reentrant collection lock, including independent store instances/processes.
This reuses the existing lock timeout/staleness policy; it does not introduce a
distributed lock or multi-machine transaction guarantee.

### Scope, correction and authority

Workspace records require `memory.workspace:<id>.read` / `.write` permissions
through the existing PermissionManager (the existing `*` grant still applies).
Retrieval excludes other workspaces by default, even for a wildcard owner.
Multiple selected workspaces additionally require `cross_workspace=true`.
Explicit project-document filters keep their existing RAG intent contract.

Decisions and summaries can replace an active record with `supersedes` and
`expected_revision`. The old record is retained as `superseded`; it is excluded
from normal retrieval. Updating their content produces a replacement, not an
overwrite of historical text. `invalidate` preserves evidence but excludes the
record; delete preserves the existing content-free tombstone behavior and backup
retention. Deletion is not a promise of forensic erasure of backups.

`verified=false` is the default. Stored user/model claims are not automatically
facts. Provenance and this label travel with retrieved evidence. Memory cannot
change permissions or overwrite core instructions. Role separation is enforced
at request construction; it is not a guarantee that every model resists all
natural-language injection attempts.

### Retrieval and budgets

Memory retrieval combines lexical keys, tags, authorization, workspace, active
state, importance, recency and a current-summary priority. Existing Project Knowledge
hybrid/semantic retrieval remains in its existing component and under explicit
retrieval intent. Arbitrary memory records do **not** acquire learned embeddings
in this slice; no simulated semantic score is reported.

The final `models/budget.py` allocation covers essential rules/current request,
tool schemas, recent dialogue, selected evidence/results and response reservation.
Configured per-model windows take precedence over the existing model-catalog
snapshot; unknown windows use a labeled conservative 4096 fallback. The local
llama server remains capped at its actual 4096 context. Token counts are estimates
(UTF-8 bytes / 3 plus framing), not provider-tokenizer measurements.
Essentials that cannot fit raise an explicit error. Optional items are omitted as
whole items with an omission notice. Already-budgeted LM Studio requests bypass
the legacy second truncation. Metrics contain counts and costs, never memory text.

### Selective consolidation

`MemoryConsolidator` provides a bounded 32-item background queue over the same store.
It accepts persistent kinds only when explicitly requested or verified by its
caller, discards temporary/unconfirmed automatic candidates, preserves provenance,
and uses canonical deduplication/revision checks. `consolidate_memory` returns
`queued`, never a false saved confirmation; `recall` verifies persistence.
`remember` remains synchronous for explicit save requests and supports typed
facts, decisions, summaries, episodes, results and references. Ordinary chat is
not automatically persisted as learned facts. The queue is process-local and is
drained on graceful application close; pending jobs are not a durable restart queue.
Only committed records have the restart persistence guarantee.

### Validation

See `tests/test_memory_hierarchy.py` for A-J integration coverage, including 3001
records without loading the entire canonical collection during retrieval, two
store instances racing on one revision, index recovery, prompt authority separation,
and ChatRuntime-to-provider transport. A separate live validation with the installed
Gemma model recovered the real authorized workspace path from temporary memory.
No test data was written to the production memory store.

Current command outputs and the validation report are under `artifacts/reports/`
and `docs/validation/memory-hierarchy.md`. Global pre-existing test failures are
reported separately; this extension does not make the backend globally READY.
