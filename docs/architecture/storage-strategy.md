# Storage Strategy

The strategy is evidence-based and intentionally plural. DataDir remains the path
authority; storage technology follows data shape and operational requirements.

## Decision categories

### Keep current human-editable files

Agent CONFIG/SOUL/SKILLS/MEMORY/INBOX, policies, system configuration,
conversation Markdown summaries and similar user-owned content remain YAML or
Markdown. They require domain validation and explicit migrations, not automatic
collection conversion.

### Use FileCollection

Choose the file primitive when all are true:

- records are operational and independently replaceable;
- the collection is small or explicitly bounded, normally below 500 records;
- lookup is primarily by ID and filters are simple equalities;
- writes are low/moderate and no cross-collection transaction is required;
- full scans/recovery are operationally acceptable.

Singleton state may use the atomic writer and lock without pretending to be a
record collection.

### Future SQLite candidate

Evaluate SQLite when one or more measured conditions hold:

- the collection approaches 1,000 files or grows without a hard bound;
- sustained write rate or concurrent mutation makes file fsync dominant;
- full paginated listing/query exceeds roughly 500 ms on representative hardware;
- multi-field indexes, joins, uniqueness constraints or multi-record transactions
  are required;
- recovery must be journaled rather than record-by-record;
- startup, disk directory traversal or retention scans become material.

The 500-agent benchmark used 1,000 file records and measured 7.69 seconds for full
pagination, despite a 53 ms first page. A 2,500-record durable-write stress attempt
exceeded 184 seconds. Therefore conversations, attempts/events at modeled volume,
delegation executions, tool history, perception streams, voice/vision histories and
observability are SQLite candidates. This phase does not migrate them.

### Keep raw artifacts separate

Audio, images and downloaded models remain files. Metadata may
eventually use FileCollection or SQLite, but binary content does not enter either
record payload.

## Recommendations by current family

| Family | Recommendation |
| --- | --- |
| Human configuration/content | current files |
| Memory at current bounded alpha volume | atomic document primitive; reassess if growing |
| Workers and Notifications | FileCollection with explicit bounds/retention |
| Attempts at current pilot volume | FileCollection; SQLite when mission history grows |
| Conversations/messages, events, audit, tool execution | SQLite candidate |
| Derived caches and inboxes | rebuildable files/cache |
| Raw audio/vision/models | separate binary artifacts |

Agent count alone is never the decision. Query shape, write rate, transaction need,
concurrency, recovery, startup, listing latency and disk size are considered
together.
