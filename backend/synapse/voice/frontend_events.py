from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from synapse.core.exceptions import ValidationError

VOICE_FRONTEND_EVENT_V1 = "voice-frontend-event-v1"


class VoiceFrontendEventType(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"
    PROCESSING = "processing"
    SPEAKING_STARTED = "speaking_started"
    SPEAKING_ENDED = "speaking_ended"
    INTERRUPTION_DETECTED = "interruption_detected"
    INTERRUPTION_REQUESTED = "interruption_requested"
    INTERRUPTION_CONFIRMED = "interruption_confirmed"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class VoicePresentationState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEECH_DETECTED = "speech-detected"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    PAUSED = "paused"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class VoiceFrontendEvent:
    event_id: str
    voice_session_id: str
    event_type: VoiceFrontendEventType
    occurred_at: str
    correlation_reference: str
    revision: int
    causal_revision: int
    provenance: tuple[str, ...]
    utterance_id: str | None = None
    conversation_turn_reference: str | None = None
    occurrence_started_at: str | None = None
    occurrence_ended_at: str | None = None
    capability_status_reference: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    format_version: str = VOICE_FRONTEND_EVENT_V1


@dataclass(frozen=True, slots=True)
class VoiceFrontendSnapshot:
    voice_session_id: str
    state: VoicePresentationState
    revision: int
    last_event_id: str | None
    correlation_reference: str
    external_state_known: bool
    capability_status: str | None = None


class VoiceFrontendEventSink(Protocol):
    def publish(self, event: VoiceFrontendEvent) -> None: ...


class VoiceFrontendEventStream:
    def __init__(self, voice_session_id: str, correlation_reference: str) -> None:
        self.voice_session_id = voice_session_id
        self.correlation_reference = correlation_reference
        self._events: list[VoiceFrontendEvent] = []
        self._by_id: dict[str, VoiceFrontendEvent] = {}

    def publish(self, event: VoiceFrontendEvent) -> None:
        if event.voice_session_id != self.voice_session_id:
            raise ValidationError("Voice frontend event session mismatch.")
        if event.correlation_reference != self.correlation_reference:
            raise ValidationError("Voice frontend event correlation mismatch.")
        existing = self._by_id.get(event.event_id)
        if existing is not None:
            if existing != event:
                raise ValidationError("Contradictory duplicate Voice frontend event.")
            return
        if self._events and event.revision <= self._events[-1].revision:
            raise ValidationError("Stale Voice frontend event revision.")
        if event.format_version != VOICE_FRONTEND_EVENT_V1:
            raise ValidationError("Unsupported Voice frontend event version.")
        _validate_safe_metadata(event.metadata)
        self._events.append(event)
        self._by_id[event.event_id] = event

    def events_after(self, revision: int) -> tuple[VoiceFrontendEvent, ...]:
        return tuple(event for event in self._events if event.revision > revision)

    def snapshot(self) -> VoiceFrontendSnapshot:
        return project_voice_frontend_events(
            self.voice_session_id,
            self.correlation_reference,
            tuple(self._events),
        )


def project_voice_frontend_events(
    voice_session_id: str,
    correlation_reference: str,
    events: tuple[VoiceFrontendEvent, ...],
) -> VoiceFrontendSnapshot:
    state = VoicePresentationState.IDLE
    external_state_known = True
    capability_status: str | None = None
    last_event_id: str | None = None
    revision = 0
    transitions = {
        VoiceFrontendEventType.IDLE: VoicePresentationState.IDLE,
        VoiceFrontendEventType.LISTENING: VoicePresentationState.LISTENING,
        VoiceFrontendEventType.SPEECH_STARTED: VoicePresentationState.SPEECH_DETECTED,
        VoiceFrontendEventType.SPEECH_ENDED: VoicePresentationState.PROCESSING,
        VoiceFrontendEventType.PROCESSING: VoicePresentationState.PROCESSING,
        VoiceFrontendEventType.SPEAKING_STARTED: VoicePresentationState.SPEAKING,
        VoiceFrontendEventType.SPEAKING_ENDED: VoicePresentationState.LISTENING,
        VoiceFrontendEventType.INTERRUPTION_DETECTED: VoicePresentationState.INTERRUPTED,
        VoiceFrontendEventType.INTERRUPTION_REQUESTED: VoicePresentationState.INTERRUPTED,
        VoiceFrontendEventType.INTERRUPTION_CONFIRMED: VoicePresentationState.INTERRUPTED,
        VoiceFrontendEventType.PAUSED: VoicePresentationState.PAUSED,
        VoiceFrontendEventType.CANCELLING: VoicePresentationState.INTERRUPTED,
        VoiceFrontendEventType.CANCELLED: VoicePresentationState.IDLE,
        VoiceFrontendEventType.RECONCILIATION_REQUIRED: VoicePresentationState.UNAVAILABLE,
        VoiceFrontendEventType.UNAVAILABLE: VoicePresentationState.UNAVAILABLE,
        VoiceFrontendEventType.ERROR: VoicePresentationState.ERROR,
    }
    for event in events:
        state = transitions[event.event_type]
        revision = event.revision
        last_event_id = event.event_id
        status = event.metadata.get("capability_status")
        if isinstance(status, str):
            capability_status = status
        if event.event_type is VoiceFrontendEventType.RECONCILIATION_REQUIRED:
            external_state_known = False
    return VoiceFrontendSnapshot(
        voice_session_id,
        state,
        revision,
        last_event_id,
        correlation_reference,
        external_state_known,
        capability_status,
    )


def make_voice_frontend_event(
    *,
    voice_session_id: str,
    event_type: VoiceFrontendEventType,
    correlation_reference: str,
    revision: int,
    causal_revision: int,
    utterance_id: str | None,
    conversation_turn_reference: str | None,
    metadata: dict[str, object] | None = None,
) -> VoiceFrontendEvent:
    identity = {
        "session": voice_session_id,
        "type": event_type,
        "revision": revision,
        "causal_revision": causal_revision,
        "correlation": correlation_reference,
    }
    event_id = "voice-frontend-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:24]
    return VoiceFrontendEvent(
        event_id=event_id,
        voice_session_id=voice_session_id,
        event_type=event_type,
        occurred_at=datetime.now(UTC).isoformat(),
        correlation_reference=correlation_reference,
        revision=revision,
        causal_revision=causal_revision,
        provenance=("voice.realtime",),
        utterance_id=utterance_id,
        conversation_turn_reference=conversation_turn_reference,
        metadata=dict(metadata or {}),
    )


def _validate_safe_metadata(metadata: dict[str, object]) -> None:
    forbidden = {
        "transcript",
        "text",
        "pcm",
        "audio_base64",
        "waveform",
        "amplitude",
        "frequency",
        "thinking",
        "reasoning",
        "animation",
        "avatar",
        "emotion",
        "expression",
    }
    lowered = {key.lower().replace("-", "_") for key in metadata}
    if any(any(token in key for token in forbidden) for key in lowered):
        raise ValidationError("Voice frontend event metadata contains a forbidden field.")
