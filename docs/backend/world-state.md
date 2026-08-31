# World State

Status: **Implemented / Frozen**.

`WorldStateRuntime` is the canonical current-environment projection. It owns
state, revisioning, TTL, history, and reconciliation; it never assigns
relevance, selects a disposition, or executes an action.

## Model and storage

`WorldStateSnapshot` contains `user_state`, `system_state`,
`environment_state`, `active_context`, and bounded maps of agent,
conversation, mission, device, application, and notification references. It
also carries perception and attention summaries. Full records remain in their
frozen source domains.

Storage under `DATA_DIR/world_state/` is local-first:

- `snapshot.json`: atomic current projection;
- `update_ledger.json`: deduplication and per-entity temporal ordering;
- `expirations.json`: TTL ownership by update/entity;
- `history.jsonl`: summary-only provenance and revision history.

`apply_state_update(WorldStateUpdate)` accepts `set`, `merge`, `remove`,
`expire`, and numeric `increment`. It validates entity type, sensitivity,
timestamps and expiry, checks `expected_revision`, rejects out-of-order writes,
performs deterministic deep merge, atomically replaces the snapshot, and emits
only a redacted update summary. Reapplying an update ID is idempotent.

## Events and reconciliation

The frozen `EventBus` remains the event source. `RuntimeEventStateAdapter`
uses an allowlist and writes bounded summaries for lifecycle, presence,
missions, conversations, health, scheduler, daemon, voice, and perception.
Uncertain perception and activity signals receive TTL and never become
permanent facts automatically.

`reconcile_state()` first expires state, then compares agent presence/lifecycle,
mission references, daemon status, and scheduler lock status with canonical
runtimes. It corrects stale references and emits inconsistencies; it never
replays an action.

See `world-state-attention-agent-loop-inventory.md` for the complete ownership
matrix.
