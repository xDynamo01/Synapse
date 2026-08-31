from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from synapse.attention.contracts import WorldStateReadPort
from synapse.attention.errors import AttentionExpired, AttentionNotFound
from synapse.attention.models import (
    ATTENTION_STATUSES,
    DISPOSITIONS,
    SEVERITIES,
    AttentionEvent,
    AttentionItem,
    AttentionScoreResult,
    attention_item_from_dict,
    now_iso,
)
from synapse.core.data_dir import DataDir
from synapse.core.events import Event, EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_json, load_structured_file
from synapse.observability.redaction import redact
from synapse.world_state.models import WorldStateSnapshot


class AttentionRuntime:
    """Deterministic attention queue. This runtime never executes a disposition."""

    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        world_state: WorldStateReadPort | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.world_state = world_state
        self.root = data_dir.resolve("attention")
        self.items_root = self.root / "items"
        self.items_root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "event_ledger.json"
        self._lock = RLock()
        self.suppressed_count = 0

    def ingest_event(
        self,
        event: AttentionEvent | Event | dict[str, Any],
        world_state: WorldStateSnapshot | None = None,
    ) -> AttentionItem:
        normalized = self._normalize_event(event)
        self._validate_event(normalized)
        with self._lock:
            ledger = load_structured_file(self.ledger_path)
            event_items = dict(ledger.get("event_items", {}))
            existing_id = event_items.get(normalized.id)
            if existing_id:
                return self.get_item(existing_id)
            dedup_key = self._deduplication_key(normalized)
            existing = self._find_active_by_key(dedup_key)
            if existing:
                item = self._aggregate(
                    existing,
                    normalized,
                    self._world_state_snapshot(world_state),
                )
            else:
                score = self.score_event(
                    normalized,
                    self._world_state_snapshot(world_state),
                )
                status = "pending"
                suppression_reason = None
                if (
                    score.score < score.thresholds["record_only"]
                    and normalized.severity != "critical"
                ):
                    status = "suppressed"
                    suppression_reason = "below_relevance_threshold"
                    self.suppressed_count += 1
                item = AttentionItem(
                    type=normalized.type,
                    source_event_ids=[normalized.id],
                    entity_refs=normalized.entity_refs,
                    title=normalized.title,
                    summary=normalized.summary,
                    severity=normalized.severity,
                    urgency=_bounded(normalized.urgency),
                    relevance=score.score,
                    confidence=_bounded(normalized.confidence),
                    created_at=normalized.created_at,
                    expires_at=normalized.expires_at,
                    status=status,
                    suggested_dispositions=(
                        normalized.suggested_dispositions or [score.disposition_recommendation]
                    ),
                    policy_context={"score": asdict(score)},
                    correlation_id=normalized.correlation_id,
                    provenance=redact(normalized.provenance),
                    metadata=redact(normalized.metadata),
                    deduplication_key=dedup_key,
                    suppression_reason=suppression_reason,
                )
                self._persist(item)
                event_name = "attention.created" if status == "pending" else "attention.suppressed"
                self._emit(event_name, item)
            event_items[normalized.id] = item.id
            if len(event_items) > 20_000:
                event_items = dict(list(event_items.items())[-20_000:])
            dump_json(self.ledger_path, {"event_items": event_items})
            return item

    def score_event(
        self,
        event: AttentionEvent,
        world_state: WorldStateSnapshot | None = None,
    ) -> AttentionScoreResult:
        severity = {"informational": 0.05, "low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}[
            event.severity
        ]
        state = self._world_state_snapshot(world_state)
        active = state.active_context
        ref_values = {value for ref in event.entity_refs for value in ref.values()}
        task_relation = 1.0 if active.get("task_id") in ref_values else 0.0
        conversation_relation = 1.0 if active.get("conversation_id") in ref_values else 0.0
        mission_relation = 1.0 if active.get("mission_id") in ref_values else 0.0
        age_seconds = max(0.0, (datetime.now(UTC) - _instant(event.created_at)).total_seconds())
        recency = max(0.0, 1.0 - age_seconds / 3600.0)
        repetition = min(1.0, float(event.metadata.get("occurrence_count", 1)) / 10.0)
        user_available = 0.0 if state.user_state.get("presence") in {"away", "offline"} else 1.0
        dnd_penalty = (
            0.35 if state.user_state.get("do_not_disturb") and event.severity != "critical" else 0.0
        )
        risk = _bounded(float(event.metadata.get("risk", severity)))
        resolvable = _bounded(float(event.metadata.get("resolution_capability", 0.0)))
        preference = _bounded(float(event.metadata.get("preference", 0.5)))
        factors = {
            "severity": severity * 0.24,
            "urgency": _bounded(event.urgency) * 0.16,
            "current_task_relation": task_relation * 0.08,
            "active_conversation_relation": conversation_relation * 0.06,
            "mission_relation": mission_relation * 0.08,
            "recency": recency * 0.08,
            "confidence": _bounded(event.confidence) * 0.10,
            "repetition": repetition * 0.04,
            "preference": preference * 0.04,
            "user_availability": user_available * 0.04,
            "risk": risk * 0.05,
            "resolution_capability": resolvable * 0.03,
            "do_not_disturb_penalty": -dnd_penalty,
        }
        score = round(max(0.0, min(1.0, sum(factors.values()))), 4)
        thresholds = {"record_only": 0.18, "notify": 0.42, "suggest": 0.58, "act": 0.78}
        if event.severity == "critical":
            recommendation = "require_approval"
        elif score >= thresholds["act"]:
            recommendation = "suggest"
        elif score >= thresholds["suggest"]:
            recommendation = "suggest"
        elif score >= thresholds["notify"]:
            recommendation = "notify"
        elif score >= thresholds["record_only"]:
            recommendation = "record_only"
        else:
            recommendation = "ignore"
        warnings = []
        if dnd_penalty:
            warnings.append("do_not_disturb_active")
        if event.confidence < 0.5:
            warnings.append("low_confidence")
        return AttentionScoreResult(score, factors, thresholds, recommendation, warnings)

    def list_items(self, status: str | None = None, limit: int = 100) -> list[AttentionItem]:
        if status and status not in ATTENTION_STATUSES:
            raise ValidationError(f"Invalid attention status: {status}")
        items = [
            attention_item_from_dict(load_structured_file(path))
            for path in self.items_root.glob("*.json")
        ]
        if status:
            items = [item for item in items if item.status == status]
        items.sort(
            key=lambda item: (item.severity == "critical", item.relevance, item.created_at),
            reverse=True,
        )
        return items[: max(0, limit)]

    def get_item(self, item_id: str) -> AttentionItem:
        path = self._path(item_id)
        if not path.exists():
            raise AttentionNotFound(f"Attention item not found: {item_id}")
        return attention_item_from_dict(load_structured_file(path))

    def next_eligible(self, now: datetime | None = None) -> AttentionItem | None:
        instant = now or datetime.now(UTC)
        self.expire_items(instant)
        eligible = []
        for item in self.list_items(limit=10_000):
            if item.status == "pending":
                eligible.append(item)
            elif (
                item.status == "deferred"
                and item.deferred_until
                and _instant(item.deferred_until) <= instant
            ):
                eligible.append(self._transition(item, "pending", deferred_until=None))
        return eligible[0] if eligible else None

    def acknowledge(self, item_id: str) -> AttentionItem:
        return self._transition(self.get_item(item_id), "acknowledged")

    def defer(self, item_id: str, until: str | None = None) -> AttentionItem:
        item = self.get_item(item_id)
        self._ensure_live(item)
        deferred_until = until or (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
        return self._transition(item, "deferred", deferred_until=deferred_until)

    def suppress(self, item_id: str, reason: str) -> AttentionItem:
        item = self.get_item(item_id)
        if item.severity == "critical":
            raise ValidationError("Critical attention items cannot be suppressed")
        self.suppressed_count += 1
        return self._transition(item, "suppressed", suppression_reason=reason)

    def mark_processing(self, item_id: str) -> AttentionItem:
        return self._transition(self.get_item(item_id), "processing")

    def resolve(self, item_id: str) -> AttentionItem:
        item = self._transition(self.get_item(item_id), "resolved")
        self._emit("attention.resolved", item)
        return item

    def fail(self, item_id: str, reason: str) -> AttentionItem:
        return self._transition(
            self.get_item(item_id), "failed", metadata={"failure_reason": reason}
        )

    def expire_items(self, now: datetime | None = None) -> int:
        instant = now or datetime.now(UTC)
        count = 0
        for item in self.list_items(limit=10_000):
            if item.status in {"resolved", "expired"} or not item.expires_at:
                continue
            if _instant(item.expires_at) <= instant:
                self._transition(item, "expired")
                count += 1
        return count

    def health(self) -> dict[str, Any]:
        items = self.list_items(limit=10_000)
        return {
            "status": "healthy",
            "queue_depth": len([item for item in items if item.status in {"pending", "deferred"}]),
            "suppressed_count": len([item for item in items if item.status == "suppressed"]),
            "failed_count": len([item for item in items if item.status == "failed"]),
        }

    def _aggregate(
        self, existing: AttentionItem, event: AttentionEvent, world_state: WorldStateSnapshot | None
    ) -> AttentionItem:
        count = existing.occurrence_count + 1
        severity = _max_severity(existing.severity, event.severity)
        score = self.score_event(
            replace(
                event, severity=severity, metadata={**event.metadata, "occurrence_count": count}
            ),
            world_state,
        )
        escalated = severity != existing.severity or score.score >= existing.relevance + 0.15
        status = (
            "pending"
            if existing.status == "suppressed" and (escalated or severity == "critical")
            else existing.status
        )
        item = replace(
            existing,
            source_event_ids=[*existing.source_event_ids, event.id][-100:],
            severity=severity,
            urgency=max(existing.urgency, _bounded(event.urgency)),
            relevance=max(existing.relevance, score.score),
            confidence=max(existing.confidence, _bounded(event.confidence)),
            status=status,
            updated_at=now_iso(),
            occurrence_count=count,
            suppression_reason=None if status == "pending" else existing.suppression_reason,
            policy_context={"score": asdict(score)},
        )
        self._persist(item)
        if escalated:
            self._emit("attention.escalated", item)
        else:
            self._emit("attention.aggregated", item)
        return item

    def _transition(self, item: AttentionItem, status: str, **changes: Any) -> AttentionItem:
        if status not in ATTENTION_STATUSES:
            raise ValidationError(f"Invalid attention status: {status}")
        if status not in {"expired", "failed"}:
            self._ensure_live(item)
        metadata = changes.pop("metadata", None)
        if metadata is not None:
            changes["metadata"] = {**item.metadata, **redact(metadata)}
        updated = replace(item, status=status, updated_at=now_iso(), **changes)
        self._persist(updated)
        return updated

    @staticmethod
    def _ensure_live(item: AttentionItem) -> None:
        if item.expires_at and _instant(item.expires_at) <= datetime.now(UTC):
            raise AttentionExpired(f"Attention item expired: {item.id}")

    def _find_active_by_key(self, key: str) -> AttentionItem | None:
        for item in self.list_items(limit=10_000):
            if item.deduplication_key == key and item.status not in {
                "resolved",
                "expired",
                "failed",
            }:
                return item
        return None

    @staticmethod
    def _deduplication_key(event: AttentionEvent) -> str:
        explicit = event.metadata.get("deduplication_key")
        if explicit:
            return str(explicit)
        refs = sorted(f"{key}:{value}" for ref in event.entity_refs for key, value in ref.items())
        material = "|".join([event.type, event.source, event.title.lower().strip(), *refs])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _normalize_event(event: AttentionEvent | Event | dict[str, Any]) -> AttentionEvent:
        if isinstance(event, AttentionEvent):
            return event
        if isinstance(event, Event):
            raw = event.payload
            return AttentionEvent(
                id=event.id,
                type=event.type,
                source=event.source_module,
                title=str(raw.get("title") or event.type.replace(".", " ").title()),
                summary=str(raw.get("summary") or raw.get("message") or event.type),
                severity=_normalize_severity(raw.get("severity") or event.severity),
                urgency=float(raw.get("urgency", 0.0)),
                confidence=float(raw.get("confidence", 1.0)),
                entity_refs=list(raw.get("entity_refs", [])),
                suggested_dispositions=list(raw.get("suggested_dispositions", [])),
                expires_at=raw.get("expires_at"),
                correlation_id=event.correlation_id,
                provenance={"event_id": event.id, "source": event.source},
                metadata=dict(raw.get("metadata", {})),
                created_at=event.timestamp,
            )
        allowed = AttentionEvent.__dataclass_fields__
        raw = dict(event)
        raw["severity"] = _normalize_severity(raw.get("severity", "informational"))
        return AttentionEvent(**{key: value for key, value in raw.items() if key in allowed})

    @staticmethod
    def _validate_event(event: AttentionEvent) -> None:
        if event.severity not in SEVERITIES:
            raise ValidationError(f"Invalid attention severity: {event.severity}")
        invalid = set(event.suggested_dispositions) - DISPOSITIONS
        if invalid:
            raise ValidationError(f"Invalid suggested dispositions: {sorted(invalid)}")
        if not event.source.strip() or not event.type.strip():
            raise ValidationError("Attention event source and type are required")

    def _persist(self, item: AttentionItem) -> None:
        dump_json(self._path(item.id), asdict(item))

    def _world_state_snapshot(
        self,
        snapshot: WorldStateSnapshot | None,
    ) -> WorldStateSnapshot:
        if snapshot is not None:
            return snapshot
        if self.world_state is not None:
            return self.world_state.snapshot()
        return WorldStateSnapshot()

    def _path(self, item_id: str) -> Path:
        return self.items_root / f"{item_id}.json"

    def _emit(self, event_type: str, item: AttentionItem) -> None:
        self.event_bus.emit(
            event_type,
            "attention",
            {
                "attention_item_id": item.id,
                "type": item.type,
                "severity": item.severity,
                "status": item.status,
                "relevance": item.relevance,
                "occurrence_count": item.occurrence_count,
                "correlation_id": item.correlation_id,
            },
        )


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_severity(value: Any) -> str:
    return {"info": "informational", "warning": "medium", "error": "high"}.get(
        str(value), str(value)
    )


def _max_severity(left: str, right: str) -> str:
    order = ["informational", "low", "medium", "high", "critical"]
    return max((left, right), key=order.index)
