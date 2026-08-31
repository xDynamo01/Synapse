from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_json, load_structured_file
from synapse.observability.redaction import redact
from synapse.world_state.errors import InvalidStateUpdate, WorldStateConflict, WorldStateNotFound
from synapse.world_state.models import (
    COLLECTION_ENTITY_TYPES,
    STATE_ENTITY_TYPES,
    STATE_OPERATIONS,
    ReconciliationResult,
    StateHistoryEntry,
    WorldStateSnapshot,
    WorldStateUpdate,
    now_iso,
    snapshot_from_dict,
    update_from_dict,
)

Reconciler = Callable[[WorldStateSnapshot], list[WorldStateUpdate]]


class WorldStateRuntime:
    """Durable current-state projection. It intentionally never selects actions."""

    def __init__(self, data_dir: DataDir, event_bus: EventBus) -> None:
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.root = data_dir.resolve("world_state")
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.root / "snapshot.json"
        self.ledger_path = self.root / "update_ledger.json"
        self.expirations_path = self.root / "expirations.json"
        self.history_path = self.root / "history.jsonl"
        self._lock = RLock()
        self._reconcilers: dict[str, Reconciler] = {}
        if not self.snapshot_path.exists():
            dump_json(self.snapshot_path, asdict(WorldStateSnapshot()))

    def snapshot(self) -> WorldStateSnapshot:
        with self._lock:
            return snapshot_from_dict(load_structured_file(self.snapshot_path))

    def get_entity(self, entity_type: str, entity_id: str | None = None) -> Any:
        if entity_type not in STATE_ENTITY_TYPES:
            raise WorldStateNotFound(f"Unknown world state entity type: {entity_type}")
        value = getattr(self.snapshot(), entity_type)
        if entity_id is None:
            return value
        if not isinstance(value, dict) or entity_id not in value:
            raise WorldStateNotFound(f"World state entity not found: {entity_type}/{entity_id}")
        return value[entity_id]

    def apply_state_update(self, update: WorldStateUpdate | dict[str, Any]) -> WorldStateSnapshot:
        item = update_from_dict(update) if isinstance(update, dict) else update
        self._validate(item)
        with self._lock:
            snapshot = self.snapshot()
            ledger = load_structured_file(self.ledger_path)
            applied = dict(ledger.get("applied", {}))
            temporal = dict(ledger.get("temporal", {}))
            if item.id in applied:
                return snapshot
            if item.expected_revision is not None and item.expected_revision != snapshot.revision:
                raise WorldStateConflict(
                    f"Expected revision {item.expected_revision}, current revision is {snapshot.revision}"
                )
            key = self._entity_key(item)
            previous_timestamp = temporal.get(key)
            if previous_timestamp and self._instant(item.timestamp) < self._instant(
                previous_timestamp
            ):
                raise WorldStateConflict(f"Out-of-order update for {key}")

            raw = asdict(snapshot)
            current = raw[item.entity_type]
            if item.entity_type in COLLECTION_ENTITY_TYPES:
                current = dict(current)
                self._apply_to_collection(current, item)
            else:
                current = self._apply_to_value(current, item)
            raw[item.entity_type] = current
            raw["revision"] = snapshot.revision + 1
            raw["updated_at"] = now_iso()
            updated = snapshot_from_dict(raw)
            dump_json(self.snapshot_path, asdict(updated))

            applied[item.id] = {"revision": updated.revision, "timestamp": item.timestamp}
            temporal[key] = item.timestamp
            if len(applied) > 10_000:
                applied = dict(list(applied.items())[-10_000:])
            dump_json(self.ledger_path, {"applied": applied, "temporal": temporal})
            self._record_expiration(item)
            self._append_history(item, updated.revision)
            self.event_bus.emit(
                "world_state.updated",
                item.source,
                {
                    "update_id": item.id,
                    "revision": updated.revision,
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "operation": item.operation,
                    "correlation_id": item.correlation_id,
                },
            )
            return updated

    def expire_state(self, now: datetime | str | None = None) -> WorldStateSnapshot:
        instant = self._instant(now or datetime.now(UTC))
        with self._lock:
            raw = load_structured_file(self.expirations_path)
            entries = dict(raw.get("entries", {}))
        for key, entry in list(entries.items()):
            if self._instant(entry["expires_at"]) > instant:
                continue
            update = WorldStateUpdate(
                id=f"expire:{entry['update_id']}",
                source="world_state.expiration",
                entity_type=entry["entity_type"],
                entity_id=entry.get("entity_id"),
                operation="expire",
                timestamp=instant.isoformat(),
                provenance={"expired_update_id": entry["update_id"]},
            )
            self.apply_state_update(update)
            entries.pop(key, None)
        dump_json(self.expirations_path, {"entries": entries})
        return self.snapshot()

    def register_reconciler(self, source: str, reconciler: Reconciler) -> None:
        if not source.strip():
            raise InvalidStateUpdate("Reconciler source is required")
        self._reconcilers[source] = reconciler

    def reconcile_state(self) -> ReconciliationResult:
        checked: list[str] = []
        unavailable: list[str] = []
        inconsistencies: list[dict[str, Any]] = []
        applied = 0
        self.expire_state()
        for source, reconciler in sorted(self._reconcilers.items()):
            checked.append(source)
            try:
                updates = reconciler(self.snapshot())
                for update in updates:
                    before = self.snapshot().revision
                    after = self.apply_state_update(update).revision
                    if after != before:
                        applied += 1
                        inconsistencies.append(
                            {
                                "source": source,
                                "entity_type": update.entity_type,
                                "entity_id": update.entity_id,
                                "corrected": True,
                            }
                        )
            except Exception as exc:
                unavailable.append(source)
                self.event_bus.emit(
                    "world_state.reconciliation_source_failed",
                    "world_state",
                    {"source": source, "error_type": type(exc).__name__},
                )
        result = ReconciliationResult(
            checked_sources=checked,
            applied_updates=applied,
            inconsistencies=inconsistencies,
            unavailable_sources=unavailable,
            revision=self.snapshot().revision,
        )
        self.event_bus.emit("world_state.reconciled", "world_state", asdict(result))
        return result

    def history(self, limit: int = 100) -> list[StateHistoryEntry]:
        if not self.history_path.exists():
            return []
        rows = self.history_path.read_text(encoding="utf-8").splitlines()[-max(0, limit) :]
        return [StateHistoryEntry(**json.loads(row)) for row in rows if row.strip()]

    def health(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "status": "healthy" if self.snapshot_path.exists() else "failed",
            "revision": snapshot.revision,
            "reconcilers": sorted(self._reconcilers),
            "history_entries": len(self.history(limit=10_000)),
        }

    @staticmethod
    def _apply_to_collection(current: dict[str, Any], item: WorldStateUpdate) -> None:
        if not item.entity_id:
            raise InvalidStateUpdate(f"entity_id is required for {item.entity_type}")
        if item.operation in {"remove", "expire"}:
            current.pop(item.entity_id, None)
            return
        existing = current.get(item.entity_id, {})
        current[item.entity_id] = (
            _deep_merge(existing, item.values) if item.operation == "merge" else dict(item.values)
        )

    @staticmethod
    def _apply_to_value(current: Any, item: WorldStateUpdate) -> Any:
        if item.operation in {"remove", "expire"}:
            if item.entity_id and isinstance(current, dict):
                result = dict(current)
                result.pop(item.entity_id, None)
                return result
            return {}
        if item.operation == "increment":
            if not item.entity_id or not isinstance(current, dict):
                raise InvalidStateUpdate("increment requires a scalar field entity_id")
            amount = item.values.get("amount", 1)
            old = current.get(item.entity_id, 0)
            if not isinstance(old, (int, float)) or not isinstance(amount, (int, float)):
                raise InvalidStateUpdate("increment target and amount must be numeric")
            result = dict(current)
            result[item.entity_id] = old + amount
            return result
        if item.entity_id:
            result = dict(current) if isinstance(current, dict) else {}
            old = result.get(item.entity_id, {})
            result[item.entity_id] = (
                _deep_merge(old, item.values) if item.operation == "merge" else dict(item.values)
            )
            return result
        return _deep_merge(current, item.values) if item.operation == "merge" else dict(item.values)

    def _record_expiration(self, item: WorldStateUpdate) -> None:
        raw = load_structured_file(self.expirations_path)
        entries = dict(raw.get("entries", {}))
        key = self._entity_key(item)
        if item.expires_at:
            entries[key] = {
                "update_id": item.id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "expires_at": item.expires_at,
            }
        else:
            entries.pop(key, None)
        dump_json(self.expirations_path, {"entries": entries})

    def _append_history(self, item: WorldStateUpdate, revision: int) -> None:
        entry = StateHistoryEntry(
            update_id=item.id,
            revision=revision,
            source=item.source,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            operation=item.operation,
            timestamp=item.timestamp,
            correlation_id=item.correlation_id,
            provenance=redact(item.provenance),
            sensitivity=item.sensitivity,
        )
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")

    @staticmethod
    def _validate(item: WorldStateUpdate) -> None:
        if not item.source.strip():
            raise InvalidStateUpdate("source is required")
        if item.entity_type not in STATE_ENTITY_TYPES:
            raise InvalidStateUpdate(f"Invalid entity_type: {item.entity_type}")
        if item.operation not in STATE_OPERATIONS:
            raise InvalidStateUpdate(f"Invalid operation: {item.operation}")
        if item.sensitivity not in {"public", "internal", "sensitive", "restricted"}:
            raise InvalidStateUpdate(f"Invalid sensitivity: {item.sensitivity}")
        WorldStateRuntime._instant(item.timestamp)
        if item.expires_at:
            expires = WorldStateRuntime._instant(item.expires_at)
            if expires <= WorldStateRuntime._instant(item.timestamp):
                raise InvalidStateUpdate("expires_at must be after timestamp")
        if item.operation not in {"remove", "expire"} and not isinstance(item.values, dict):
            raise InvalidStateUpdate("values must be an object")

    @staticmethod
    def _entity_key(item: WorldStateUpdate) -> str:
        return f"{item.entity_type}:{item.entity_id or '*'}"

    @staticmethod
    def _instant(value: datetime | str) -> datetime:
        try:
            instant = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise InvalidStateUpdate(f"Invalid timestamp: {value}") from exc
        return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def _deep_merge(current: Any, update: Any) -> Any:
    if not isinstance(current, dict) or not isinstance(update, dict):
        return update
    merged = dict(current)
    for key in sorted(update):
        merged[key] = _deep_merge(merged.get(key), update[key])
    return merged
