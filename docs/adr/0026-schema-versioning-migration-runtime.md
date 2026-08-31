# ADR 0026: Schema Versioning and Migration Runtime

## Status

Accepted

## Context

Synapse persists long-lived local records in `DATA_DIR`. Many of those records are structured YAML/JSON files. Without schema versioning, future runtime changes could silently break old local records or require ad hoc migrations scattered across runtimes.

The migration foundation must be local-first, explicit, and conservative. It must not run destructive migrations automatically during bootstrap.

## Decision

Add `backend/synapse/migrations/` with:

- `models.py`
- `registry.py`
- `runtime.py`
- `__init__.py`

Add `MigrationRegistry` to register migrations by:

- `record_type`
- `from_version`
- `to_version`
- migration function

Add `MigrationRuntime` with:

- `get_record_version(record)`
- `migrate_record(record_type, record)`
- `migrate_file(path, record_type)`
- `check_file(path, record_type)`
- `list_migrations()`
- `migration_status()`

Migration state is persisted in:

```text
DATA_DIR/migrations/history.jsonl
DATA_DIR/migrations/status.yaml
```

History records include timestamp, record type, path, from version, to version, status, and error when present.

Initial versioned record types:

- `job`
- `notification`
- `approval`

Each can carry:

- `schema_version`
- `record_type`
- `created_at`
- `updated_at`

Older records without schema metadata remain readable and are treated as version `1`.

## Consequences

Future schema changes can be implemented through registered migration paths instead of ad hoc reader patches.

`migrate_file()` preserves the original file if migration fails and records the failure in history/status.

The first implementation provides command/API visibility through:

- `/migrations`
- `GET /migrations`

## Non-Goals

- Bulk DATA_DIR migration runner
- Automatic migration during app bootstrap
- Schema migration for Markdown files
- Resource Runtime
- Capability Runtime
- UI or admin migration panel
- Database migration framework
