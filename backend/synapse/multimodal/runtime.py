from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.multimodal.errors import (
    MultimodalFusionFailed,
    MultimodalFusionInvalid,
    MultimodalObservationNotFound,
)
from synapse.multimodal.models import (
    COMMUNICATION_CHANNELS,
    COMMUNICATION_SESSION_STATUSES,
    CommunicationEvent,
    CommunicationSession,
    MultimodalObservation,
)
from synapse.observability.correlation import current_correlation_fields

if TYPE_CHECKING:
    from synapse.perception.runtime import PerceptionRuntime


class MultimodalCommunicationRuntime:
    def __init__(
        self, data_dir: DataDir, events: EventBus, perception: PerceptionRuntime | None = None
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.perception = perception

    def bind_perception(self, perception: PerceptionRuntime) -> None:
        self.perception = perception

    def create_session(
        self,
        participants: list[str],
        active_channels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> CommunicationSession:
        channels = active_channels or ["text"]
        self._validate_channels(channels)
        session = CommunicationSession(
            session_id=session_id or CommunicationSession().session_id,
            participants=list(participants),
            active_channels=list(dict.fromkeys(channels)),
            metadata=metadata or {},
        )
        self._write_session(session)
        self.events.emit("multimodal.session.created", "multimodal", asdict(session))
        return session

    def get_session(self, session_id: str) -> CommunicationSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise NotFound(f"Multimodal session not found: {session_id}")
        return self._read_session(session_id)

    def list_sessions(self, status: str | None = None) -> list[CommunicationSession]:
        if status and status not in COMMUNICATION_SESSION_STATUSES:
            raise ValidationError(f"Invalid multimodal session status: {status}")
        sessions = [
            self._read_session(path.stem) for path in sorted(self._sessions_root().glob("*.yaml"))
        ]
        if status:
            sessions = [session for session in sessions if session.status == status]
        return sorted(sessions, key=lambda item: (item.updated_at, item.session_id))

    def close_session(self, session_id: str) -> CommunicationSession:
        session = self._set_session_status(session_id, "closed")
        self.events.emit("multimodal.session.closed", "multimodal", asdict(session))
        return session

    def pause_session(self, session_id: str) -> CommunicationSession:
        session = self._set_session_status(session_id, "paused")
        self.events.emit("multimodal.session.paused", "multimodal", asdict(session))
        return session

    def resume_session(self, session_id: str) -> CommunicationSession:
        session = self._set_session_status(session_id, "active")
        self.events.emit("multimodal.session.resumed", "multimodal", asdict(session))
        return session

    def emit_event(
        self,
        session_id: str,
        channel: str,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        target: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> CommunicationEvent:
        session = self.get_session(session_id)
        if session.status not in {"active", "paused"}:
            raise ValidationError(f"Multimodal session is not open: {session_id}")
        self._validate_channels([channel])
        if channel not in session.active_channels:
            session = replace(
                session,
                active_channels=[*session.active_channels, channel],
                updated_at=_now(),
            )
            self._write_session(session)
        fields = current_correlation_fields()
        event = CommunicationEvent(
            channel=channel,
            event_type=event_type,
            source=source,
            target=target,
            payload=payload or {},
            correlation_id=correlation_id or fields.get("correlation_id"),
            causation_id=causation_id or fields.get("causation_id"),
            metadata=metadata or {},
        )
        self._append_event(session_id, event)
        self.events.emit(
            "multimodal.event.emitted",
            source,
            {"session_id": session_id, **asdict(event)},
        )
        return event

    def list_session_events(self, session_id: str) -> list[CommunicationEvent]:
        self.get_session(session_id)
        path = self._events_path(session_id)
        if not path.exists():
            return []
        events: list[CommunicationEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw.setdefault("target", None)
            raw.setdefault("correlation_id", None)
            raw.setdefault("causation_id", None)
            raw.setdefault("metadata", {})
            events.append(CommunicationEvent(**raw))
        return events

    def get_supported_channels(self) -> list[str]:
        return sorted(COMMUNICATION_CHANNELS)

    def fuse(
        self,
        observation_ids: list[str] | None = None,
        *,
        correlation_id: str | None = None,
        window_seconds: int = 15,
    ) -> MultimodalObservation:
        if not self.perception:
            raise MultimodalFusionInvalid("Perception runtime is not connected")
        if window_seconds < 1 or window_seconds > 3600:
            raise MultimodalFusionInvalid("Fusion window must be between 1 and 3600 seconds")
        self.events.emit(
            "perception.fusion_started",
            "multimodal",
            {"source_count": len(observation_ids or []), "correlation_id": correlation_id},
        )
        try:
            observations = (
                [self.perception.get_observation(item) for item in observation_ids]
                if observation_ids
                else self.perception.list_observations(correlation_id=correlation_id)
            )
            if not observations:
                raise MultimodalFusionInvalid("No active observations matched the fusion request")
            newest = max(_parse_time(item.timestamp) for item in observations)
            cutoff = newest - timedelta(seconds=window_seconds)
            observations = [item for item in observations if _parse_time(item.timestamp) >= cutoff]
            modalities = self._modalities(observations)
            if len(modalities) < 2:
                raise MultimodalFusionInvalid(
                    "Fusion requires observations from at least two modalities"
                )
            confidences = [
                float(item.confidence) for item in observations if item.confidence is not None
            ]
            relevances = [
                float(item.relevance) for item in observations if item.relevance is not None
            ]
            entities = _unique_dicts([entity for item in observations for entity in item.entities])
            conflicts = self._conflicts({item.id for item in observations})
            fusion = MultimodalObservation(
                source_observation_ids=[item.id for item in observations],
                time_window={
                    "start": min(item.timestamp for item in observations),
                    "end": max(item.timestamp for item in observations),
                    "seconds": window_seconds,
                },
                interpretation={
                    "type": "multimodal.correlated_observations",
                    "modalities": modalities,
                    "observation_types": [item.type for item in observations],
                },
                entities=entities,
                relations=[
                    {
                        "type": "temporally_correlated",
                        "source_ids": [item.id for item in observations],
                    }
                ],
                confidence=min(confidences) if confidences else None,
                relevance=sum(relevances) / len(relevances) if relevances else None,
                contradictions=conflicts,
                provenance=[
                    {
                        "observation_id": item.id,
                        "signal_ids": item.signal_ids,
                        "provenance": item.provenance,
                    }
                    for item in observations
                ],
                warnings=[
                    "Confidence is the conservative minimum of supplied provider confidences."
                ]
                if confidences
                else ["Source observations did not provide confidence."],
                correlation_id=correlation_id
                or next(
                    (item.correlation_id for item in observations if item.correlation_id), None
                ),
                metadata={"modalities": modalities, "source_count": len(observations)},
            )
            dump_structured_file(self._fusion_path(fusion.id), asdict(fusion))
            self.events.emit(
                "perception.fusion_completed",
                "multimodal",
                {
                    "fusion_id": fusion.id,
                    "source_count": len(observations),
                    "modalities": modalities,
                    "contradiction_count": len(conflicts),
                    "correlation_id": fusion.correlation_id,
                },
            )
            return fusion
        except Exception as exc:
            self.events.emit(
                "perception.fusion_failed",
                "multimodal",
                {"error_type": type(exc).__name__, "correlation_id": correlation_id},
            )
            if isinstance(exc, (MultimodalFusionInvalid, MultimodalObservationNotFound)):
                raise
            raise MultimodalFusionFailed("Multimodal fusion failed") from exc

    def get_fusion(self, fusion_id: str) -> MultimodalObservation:
        path = self._fusion_path(fusion_id)
        if not path.exists():
            raise MultimodalObservationNotFound(f"Multimodal observation not found: {fusion_id}")
        return MultimodalObservation(**load_structured_file(path))

    def list_fusions(self, correlation_id: str | None = None) -> list[MultimodalObservation]:
        fusions = [
            MultimodalObservation(**load_structured_file(path))
            for path in sorted(self._fusions_root().glob("*.json"))
        ]
        if correlation_id is not None:
            fusions = [item for item in fusions if item.correlation_id == correlation_id]
        return sorted(fusions, key=lambda item: (item.created_at, item.id))

    def preview_context_payload(self, fusion_id: str) -> dict[str, Any]:
        fusion = self.get_fusion(fusion_id)
        return {
            "source_type": "multimodal_observation",
            "source_id": fusion.id,
            "interpretation": fusion.interpretation,
            "confidence": fusion.confidence,
            "relevance": fusion.relevance,
            "provenance": fusion.provenance,
            "contradictions": fusion.contradictions,
            "warnings": fusion.warnings,
        }

    def _modalities(self, observations: list[Any]) -> list[str]:
        if not self.perception:
            return []
        result: set[str] = set()
        for observation in observations:
            for signal_id in observation.signal_ids:
                try:
                    result.add(self.perception.get_signal(signal_id).modality)
                except NotFound:
                    continue
        return sorted(result)

    def _conflicts(self, observation_ids: set[str]) -> list[dict[str, Any]]:
        if not self.perception:
            return []
        return [
            asdict(item)
            for item in self.perception.list_conflicts()
            if observation_ids.intersection(item.observation_ids)
        ]

    def _set_session_status(self, session_id: str, status: str) -> CommunicationSession:
        if status not in COMMUNICATION_SESSION_STATUSES:
            raise ValidationError(f"Invalid multimodal session status: {status}")
        session = self.get_session(session_id)
        updated = replace(session, status=status, updated_at=_now())
        self._write_session(updated)
        return updated

    def _read_session(self, session_id: str) -> CommunicationSession:
        raw = load_structured_file(self._session_path(session_id))
        raw.setdefault("session_id", session_id)
        raw.setdefault("participants", [])
        raw.setdefault("active_channels", [])
        raw.setdefault("status", "active")
        raw.setdefault("created_at", _now())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("metadata", {})
        return CommunicationSession(**raw)

    def _write_session(self, session: CommunicationSession) -> None:
        self._validate_channels(session.active_channels)
        if session.status not in COMMUNICATION_SESSION_STATUSES:
            raise ValidationError(f"Invalid multimodal session status: {session.status}")
        dump_structured_file(self._session_path(session.session_id), asdict(session))

    def _append_event(self, session_id: str, event: CommunicationEvent) -> None:
        path = self._events_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")

    def _validate_channels(self, channels: list[str]) -> None:
        invalid = [channel for channel in channels if channel not in COMMUNICATION_CHANNELS]
        if invalid:
            raise ValidationError(f"Invalid multimodal channel(s): {', '.join(invalid)}")

    def _sessions_root(self):
        root = self.data_dir.resolve("multimodal/sessions")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _session_path(self, session_id: str):
        return self._sessions_root() / f"{session_id}.yaml"

    def _events_path(self, session_id: str):
        return self._sessions_root() / f"{session_id}.events.jsonl"

    def _fusions_root(self) -> Path:
        root = self.data_dir.resolve("multimodal/fusions")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _fusion_path(self, fusion_id: str) -> Path:
        return self._fusions_root() / f"{fusion_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _unique_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
