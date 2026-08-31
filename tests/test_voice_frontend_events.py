from __future__ import annotations

from dataclasses import replace

import pytest

from synapse.core.exceptions import ValidationError
from synapse.voice.frontend_events import (
    VOICE_FRONTEND_EVENT_V1,
    VoiceFrontendEventStream,
    VoiceFrontendEventType,
    VoicePresentationState,
    make_voice_frontend_event,
)


def _event(revision: int, event_type: VoiceFrontendEventType):
    return make_voice_frontend_event(
        voice_session_id="voice-1",
        event_type=event_type,
        correlation_reference="voice-session://voice-1",
        revision=revision,
        causal_revision=revision,
        utterance_id="utterance-1",
        conversation_turn_reference="turn-1",
        metadata={"phase": event_type.value},
    )


def test_projection_is_rebuildable_and_versioned() -> None:
    stream = VoiceFrontendEventStream("voice-1", "voice-session://voice-1")
    for event in (
        _event(1, VoiceFrontendEventType.IDLE),
        _event(2, VoiceFrontendEventType.LISTENING),
        _event(3, VoiceFrontendEventType.SPEECH_STARTED),
        _event(4, VoiceFrontendEventType.SPEECH_ENDED),
        _event(5, VoiceFrontendEventType.PROCESSING),
        _event(6, VoiceFrontendEventType.SPEAKING_STARTED),
        _event(7, VoiceFrontendEventType.SPEAKING_ENDED),
    ):
        assert event.format_version == VOICE_FRONTEND_EVENT_V1
        stream.publish(event)
    snapshot = stream.snapshot()
    assert snapshot.state is VoicePresentationState.LISTENING
    assert snapshot.revision == 7
    assert len(stream.events_after(4)) == 3


def test_duplicate_is_idempotent_but_contradiction_stale_and_wrong_session_are_rejected() -> None:
    stream = VoiceFrontendEventStream("voice-1", "voice-session://voice-1")
    event = _event(1, VoiceFrontendEventType.LISTENING)
    stream.publish(event)
    stream.publish(event)
    assert len(stream.events_after(0)) == 1
    with pytest.raises(ValidationError, match="Contradictory"):
        stream.publish(replace(event, event_type=VoiceFrontendEventType.ERROR))
    with pytest.raises(ValidationError, match="Stale"):
        stream.publish(_event(1, VoiceFrontendEventType.PROCESSING))
    with pytest.raises(ValidationError, match="session mismatch"):
        stream.publish(replace(_event(2, VoiceFrontendEventType.IDLE), voice_session_id="wrong"))
    with pytest.raises(ValidationError, match="correlation mismatch"):
        stream.publish(
            replace(
                _event(2, VoiceFrontendEventType.IDLE),
                correlation_reference="voice-session://wrong",
            )
        )


@pytest.mark.parametrize(
    "field_name",
    ["transcript", "pcm", "waveform", "amplitude", "thinking", "reasoning", "avatar"],
)
def test_sensitive_and_visual_metadata_is_rejected(field_name: str) -> None:
    stream = VoiceFrontendEventStream("voice-1", "voice-session://voice-1")
    with pytest.raises(ValidationError, match="forbidden"):
        stream.publish(replace(_event(1, VoiceFrontendEventType.IDLE), metadata={field_name: "x"}))


def test_synthesis_processing_is_not_speaking_without_playback_evidence() -> None:
    stream = VoiceFrontendEventStream("voice-1", "voice-session://voice-1")
    stream.publish(_event(1, VoiceFrontendEventType.PROCESSING))
    assert stream.snapshot().state is VoicePresentationState.PROCESSING
    stream.publish(_event(2, VoiceFrontendEventType.SPEAKING_STARTED))
    assert stream.snapshot().state is VoicePresentationState.SPEAKING


def test_interruption_detection_does_not_imply_stop_confirmation() -> None:
    stream = VoiceFrontendEventStream("voice-1", "voice-session://voice-1")
    stream.publish(_event(1, VoiceFrontendEventType.INTERRUPTION_DETECTED))
    assert stream.snapshot().state is VoicePresentationState.INTERRUPTED
    assert [event.event_type for event in stream.events_after(0)] == [
        VoiceFrontendEventType.INTERRUPTION_DETECTED
    ]


@pytest.mark.parametrize(
    ("event_type", "state"),
    [
        (VoiceFrontendEventType.PAUSED, VoicePresentationState.PAUSED),
        (VoiceFrontendEventType.CANCELLING, VoicePresentationState.INTERRUPTED),
        (VoiceFrontendEventType.CANCELLED, VoicePresentationState.IDLE),
        (VoiceFrontendEventType.UNAVAILABLE, VoicePresentationState.UNAVAILABLE),
        (VoiceFrontendEventType.ERROR, VoicePresentationState.ERROR),
    ],
)
def test_operational_terminal_and_availability_projection(
    event_type: VoiceFrontendEventType, state: VoicePresentationState
) -> None:
    stream = VoiceFrontendEventStream("voice-1", "voice-session://voice-1")
    stream.publish(_event(1, event_type))
    assert stream.snapshot().state is state
