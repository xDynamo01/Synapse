# Operational Storage Primitives

Status: implemented for a controlled four-store pilot; backend remains **NOT READY**.

## Boundary

`synapse.storage` is neutral infrastructure for small local operational
collections. It receives paths already resolved by DataDir and never imports
DataDir, domains, API, Commands or bootstrap. It is not an ORM, a universal
repository or a database abstraction.

The package contains:

- canonical internal DTOs for records, queries/pages, writes/deletes, recovery and
  retention;
- one same-directory atomic writer with flush, fsync, permission preservation,
  optional backup, atomic replace and temporary cleanup;
- one collection-grained process/file lock with timeout, owner metadata, stale
  policy, explicit reentrancy and exception-safe release;
- explicit sequential migration registration;
- `FileCollection` for deterministic record discovery, optimistic revision checks,
  checksums, bounded cursor pagination, recovery and retention.

Domain DTOs and public responses are not replaced by storage DTOs. FileCollection
wraps current record payloads internally and preserves the owner file shapes.

## Atomicity and concurrency

Writes serialize before touching the destination. Bytes are written to a unique
same-directory temporary file, flushed, fsynced where supported, assigned the prior
mode when replacing, and committed with `os.replace`. An optional `.bak` is created
before a mutable replacement. Failed writes remove the temporary and leave the
prior destination intact.

Locks are per collection, never global. A process-local `RLock` coordinates threads
and an exclusive file records PID, thread and acquisition time for cross-process
coordination. Timeout and stale thresholds are explicit. No Scheduler lock is
reused.

Optimistic revision is optional. Domains that already own revision (`Worker` and
`TaskAttempt`) project it to the collection. Notifications preserve their current
non-revisioned contract. A conflict never writes and exposes only expected/actual
revision metadata.

## Schema, migration and recovery

Every FileCollection declares an ID, current schema, validator and migration
registry. Migrations are sequential, explicit, backed up before commit and never
silently skip a version. Human-editable files are outside this mechanism.

Recovery policy is selected per collection: fail closed, quarantine, restore from
backup, or skip with warning. Quarantine is a hidden child of the resolved
collection root. Payload content and absolute paths are excluded from errors and
neutral events.

## Pagination and retention

Cursor pagination uses stable record ID ordering by default, an opaque versioned
cursor and a maximum page size of 500. Other stable timestamp orders are supported
without a general query language. Equality filters cover the pilot needs. Filename
ordered pages skip records before the cursor rather than reparsing them.

Retention accepts age/count/bytes plus owner callbacks for active and referenced
records. Dry-run is the default. The primitive never decides domain meaning and
does not delete recovery artifacts implicitly.

## Pilot stores

| Pilot | Adoption | Preserved behavior |
| --- | --- | --- |
| MemoryStorage | canonical atomic writer and collection lock | existing JSON envelope, schema 1, dedup, revisions, soft delete, corruption error |
| WorkerRegistry | FileCollection | YAML shape, duplicate error, list order, heartbeat/stale behavior, revision fields |
| TaskAttemptRuntime | nested FileCollection per mission | YAML shape, idempotency, transitions, AttemptConflict, restart |
| LocalNotificationProvider | FileCollection | YAML shape, CRUD/unread/restart and domain retention |

No second write path remains in these pilots. Existing core serialization remains
for non-pilot domains and is documented debt, not silently redirected.

## Observability and lifecycle

Collections may emit `collection.read`, `collection.write`, `collection.conflict`,
`collection.migration`, `collection.recovery` and `collection.cleanup` through the
existing EventBus-shaped port. Events contain collection ID, redacted/hashed record
ID when configured, schema, revision, duration, byte count, status and error code;
never payloads. Storage owns no active lifecycle resource.
