# ADR 0003 — Foundation persistence and recovery

Date 2026-11-06

Status **RETAINED EXPERIMENT EVIDENCE — product ownership/binding revalidation REQUIRED**.

2026-11-09 owner amendment PL-001/PL-006 reopens Gate 00. Original Python/SQLite
durability/recovery results remain Windows TESTED / PASS evidence. They do not
choose the authoritative Rust/Python Core owner or validate a Rust SQLite
binding. The actual single writer, linked library, admission/ACK and crash
boundary, backup and packaging must pass
[R3 revalidation](../superpowers/plans/2026-11-09-rust-python-foundation-revalidation.md).
Product acceptance is **BLOCKED**; the original decision below is conditional
on that proof and cannot independently authorize a scaffold.

## Decision

Use the SQLite library linked by the [ADR 0001 Core runtime](0001-core-runtime-and-toolchain.md)
for a single local authoritative database. Open it in write-ahead log (WAL) mode
and set `synchronous=FULL` on each connection. Require linked SQLite 3.51.3 or
later on each target because that release fixes the WAL-reset race. The tested
Windows runtime links SQLite 3.53.1. Keep the active database and its journal
sidecars together on a local filesystem owned by the Core. [SQLite WAL documentation](https://sqlite.org/wal.html)

Serialize writes within the Core and keep read transactions short. A successful
`append_record(record_id, version, payload)` starts an immediate transaction,
inserts one immutable version and returns after `COMMIT` succeeds. The pair
`(record_id, version)` is unique. A duplicate fails and preserves the original
version. If the caller loses the response, it can read the exact version to
resolve the outcome. Readers see complete committed records at their snapshot.
Checkpointing moves WAL frames into the main file independently of commit.
The experiment uses SQLite's default automatic checkpoint and exposes a
passive checkpoint that reports frame progress when readers hold snapshots.
[SQLite checkpoint and concurrency semantics](https://sqlite.org/wal.html)

Canonical records, chat history, mission metadata and event cursors may use this
transaction boundary with separate domain contracts. The experiment's one table
is a synthetic fixture with an opaque external reference and SHA-256 digest.
For future external content, stage immutable content before committing its
reference. An interruption can leave an unreferenced blob for later collection.
Garbage collection must preserve content referenced by live records and retained
backups. Vector indexes remain rebuildable external data. The vector engine and
domain schemas are deferred.

## Backup and restoration

- Use SQLite's Online Backup API to capture a consistent snapshot, including
  committed WAL contents. Stage the snapshot on the target volume, normalize it
  to a standalone DELETE-journal database, check its schema and integrity, then
  publish atomically with a same-volume hard link that fails if the destination
  exists. The application-owned local directory must support hard links.
  [SQLite Online Backup API](https://sqlite.org/backup.html)
- Back up before each schema migration and on the cadence set by the product's
  recovery objective. For production recovery, retain verified snapshots and
  their referenced immutable blobs as one set with an integrity manifest.
  Retention, destination encryption and recovery objectives belong to the
  product backup implementation.
- Open the snapshot read-only. Check its application ID, schema version,
  expected schema and `PRAGMA integrity_check`. Restore into a fresh directory
  as a WAL-mode database after the staged copy passes the same checks. Refuse
  existing destination files, stale destination journals and snapshots with
  sidecars. Reopen, validate content and verify references before switching the
  stopped Core to the restored directory. [SQLite integrity check](https://sqlite.org/pragma.html#pragma_integrity_check)

## Migration and corruption policy

Set an application ID and use an explicit `user_version` for transactional
schema migrations. The spike migrates an empty version-zero database to version
one. A foreign, modified or unsupported schema fails closed. Before future
migrations, quiesce writers and validate a pre-migration backup. On failure,
restore that backup under the previous compatible Core in a new directory.
Keep the original database and backup until recovery is verified.

After abnormal shutdown, let SQLite recover the WAL and run integrity checks
before accepting writes. On corruption, stop writes and preserve the original
database and sidecars for diagnosis. Recover from a verified backup under the
owner's authority. The resulting state is bounded by the backup's recovery
point. A digest manifest and blob readback complement SQLite's structural
checks when the product implements full backup sets.

## Encryption boundary

The experiment uses synthetic records and plaintext SQLite. Production must
keep credentials and encryption keys in the platform secure store, separately
from the database, journals, backups and blob directory. The product's
at-rest protection must cover those files, temporary staging and exported
snapshots. Define protection and key lifecycle in the foundation security
boundary before using this path with personal data. Backup access and restore
authority follow the owner authorization policy.

## Evidence and alternatives

The [Windows spike](../evidence/foundation/persistence-spike.md) met its host
budget and verified 120 forced writer terminations. All 60 acknowledged
writes survived and all 60 staged pre-commit writes stayed invisible. All 120
integrity checks passed. A 256-version snapshot restored into a separate
directory. The rollback-journal alternative would trade concurrent snapshot
reads during writes for simpler active-file management. The plan's contingency
comparison was unnecessary after WAL passed. Linux and macOS execution,
physical power interruption and production-scale recovery are **NOT RUN**.

## Decision Charter compliance

| Binding decisions | Evidence or obligation |
|---|---|
| CR-001 | New clean-room adapter and fixtures under `experiments/persistence/`. |
| CR-004 | Synthetic inputs only. Databases, journals, logs and environments stay outside tracked files. |
| ME-001, ME-002 | Shared storage semantics with distinct canonical memory, chat, mission and retrieval contracts. |
| PL-003 | One local SQLite file family within a single Core process boundary. |
| PL-004 | Windows TESTED / PASS. Linux and macOS NOT RUN. Require the same fixtures and linked SQLite version check before qualifying either platform. |
| QA-001–QA-003 | Contract, negative, concurrent reader, process-death and real restore fixtures with exact inputs and commands. Independent review and integrated regression remain Gate 00 obligations. |

Proposed deviations — none.
