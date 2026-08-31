from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PerceptionAvailability(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"


class ResponseDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class VoiceConversationRequest:
    request_id: str
    conversation_reference: str | None
    conversation_turn_id: str
    voice_session_id: str
    utterance_id: str
    transcription_id: str
    transcript_reference: str
    actor_reference: str
    correlation_reference: str
    occurrence_started_at: str
    occurrence_ended_at: str
    response_deadline_at: str
    provenance: tuple[str, ...]
    perception_status: PerceptionAvailability
    perception_bundle_reference: str | None = None
    perception_bundle_fingerprint: str | None = None
    transcript_content: str | None = None
    purpose: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationResponseReference:
    response_id: str
    response_reference: str
    request_id: str
    conversation_turn_id: str
    voice_session_id: str
    utterance_id: str
    transcription_id: str
    correlation_reference: str
    text: str
    provenance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AcceptedConversationResponse:
    response: ConversationResponseReference
    disposition: ResponseDisposition
    accepted_at: str
