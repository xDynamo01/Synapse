# Memory Runtime

Status: **Implemented / Frozen**.

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
