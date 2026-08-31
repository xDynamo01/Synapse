from __future__ import annotations

import base64
import io
import sys
import tempfile
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.audio.models import SpeechFeatures, TextToSpeechResult, TranscriptResult
from synapse.audio.realtime_devices import PlaybackRequest, PlaybackResult
from synapse.bootstrap.adapters.voice_perception import LocalVoicePerceptionAdapter
from synapse.conversations.voice_contracts import PerceptionAvailability, ResponseDisposition
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.perception.models import (
    PerceptionArtifactKind,
    PerceptionBundleStatus,
    PerceptionResultBundle,
    VoicePerceptionRequest,
)
from synapse.voice.frontend_events import (
    VoiceFrontendEventSink,
    VoiceFrontendEventStream,
    VoiceFrontendEventType,
    VoicePresentationState,
)
from synapse.voice.realtime import (
    ConversationRequest,
    ConversationResponse,
    PerceptionHandoffPort,
    RealtimeVoiceConfig,
    RealtimeVoiceRuntime,
    RealtimeVoiceState,
    VoiceIntegrationJournal,
)
from synapse.voice.sqlite_persistence import SQLiteVoiceJournal
from synapse.voice.vad import VADConfig, WebRTCVADProvider

FRAME = b"\x00\x00" * 320


class SequenceClassifier:
    def __init__(self, values: list[bool]) -> None:
        self._values = iter(values)

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        return next(self._values)


class FakeStream:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = iter(frames)
        self.closed = False

    def read_frame(self) -> bytes:
        return next(self.frames)

    def close(self) -> None:
        self.closed = True


class FakeMicrophone:
    def __init__(self, frames: list[bytes]) -> None:
        self.stream = FakeStream(frames)
        self.open_count = 0

    def capabilities(self) -> dict[str, object]:
        return {"streaming": True}

    def list_input_devices(self) -> tuple[str, ...]:
        return ("input-1",)

    def open_stream(
        self,
        device_reference: str,
        *,
        sample_rate: int,
        frame_duration_ms: int,
    ) -> FakeStream:
        assert device_reference == "input-1"
        assert sample_rate == 16_000
        assert frame_duration_ms == 20
        self.open_count += 1
        return self.stream


class FakeOutput:
    def __init__(
        self,
        *,
        completed: bool = True,
        stop_confirmed: bool = True,
        fail_playback: bool = False,
    ) -> None:
        self.completed = completed
        self.stop_confirmed = stop_confirmed
        self.fail_playback = fail_playback
        self.requests: list[PlaybackRequest] = []

    def capabilities(self) -> dict[str, object]:
        return {"interruption": True}

    def list_output_devices(self) -> tuple[str, ...]:
        return ("output-1",)

    def play(self, request: PlaybackRequest) -> PlaybackResult:
        self.requests.append(request)
        if self.fail_playback:
            return PlaybackResult(
                request.playback_id, True, False, False, error="device disconnected"
            )
        return PlaybackResult(request.playback_id, True, True, self.completed)

    def request_stop(self, playback_id: str) -> PlaybackResult:
        return PlaybackResult(
            playback_id,
            True,
            True,
            False,
            interrupted=self.stop_confirmed,
            stop_requested=True,
            stop_confirmed=self.stop_confirmed,
            error=None if self.stop_confirmed else "stop unverified",
        )


class FakeSpeech:
    def __init__(self, *, transcript: str = "hello", tts_available: bool = True) -> None:
        self.transcript = transcript
        self.tts_available = tts_available
        self.transcribe_calls = 0
        self.synthesize_calls = 0

    def adapter_health(self, adapter_id: str) -> SimpleNamespace:
        return SimpleNamespace(status="available" if self.tts_available else "degraded")

    def transcribe(self, request) -> TranscriptResult:
        self.transcribe_calls += 1
        if self.transcript == "<failure>":
            raise ValidationError("stt unavailable")
        return TranscriptResult(
            text=self.transcript,
            status="success",
            language="en",
            duration_ms=request.duration_ms,
            confidence=0.9,
            provider_id="faster_whisper",
            speech_features=SpeechFeatures(),
            metadata={"model": request.model, "local_files_only": True},
        )

    def synthesize(self, request) -> TextToSpeechResult:
        self.synthesize_calls += 1
        if not self.tts_available:
            raise ValidationError("tts execution boundary unavailable")
        return TextToSpeechResult(
            output_ref="artifact://tts/1",
            provider_id="piper",
            audio_base64=base64.b64encode(_wav()).decode(),
            audio_format="audio/wav",
        )


class FakeConversation:
    def __init__(self, *, immediate: bool = False) -> None:
        self.immediate = immediate
        self.requests: list[ConversationRequest] = []

    def submit(self, request: ConversationRequest) -> ConversationResponse | None:
        self.requests.append(request)
        if not self.immediate:
            return None
        return _response(request)


class PendingPerception:
    def analyze_transient(
        self, request: VoicePerceptionRequest, pcm_bytes: bytes, sample_rate: int
    ) -> PerceptionResultBundle:
        assert pcm_bytes
        assert sample_rate == 16_000
        return PerceptionResultBundle(
            bundle_id=f"pending-{request.utterance_id}",
            fingerprint=f"fingerprint-{request.utterance_id}",
            status=PerceptionBundleStatus.PENDING,
            voice_session_id=request.voice_session_id,
            utterance_id=request.utterance_id,
            transcription_id=request.transcription_id,
            correlation_reference=request.correlation_reference,
            artifact_references=(),
            provenance=request.provenance,
            sensitivity="sensitive",
        )


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(FRAME)
    return output.getvalue()


def _response(request: ConversationRequest, text: str = "world") -> ConversationResponse:
    return ConversationResponse(
        response_id=f"response-{request.request_id[-8:]}",
        response_reference="response://1",
        request_id=request.request_id,
        conversation_turn_id=request.conversation_turn_id,
        voice_session_id=request.voice_session_id,
        utterance_id=request.utterance_id,
        transcription_id=request.transcription_id,
        correlation_reference=request.correlation_reference,
        text=text,
        provenance=("fake-conversation",),
    )


def _bundle(request: ConversationRequest) -> PerceptionResultBundle:
    return PerceptionResultBundle(
        bundle_id=f"bundle-{request.utterance_id}",
        fingerprint=f"fingerprint-{request.utterance_id}",
        status=PerceptionBundleStatus.AVAILABLE,
        voice_session_id=request.voice_session_id,
        utterance_id=request.utterance_id,
        transcription_id=request.transcription_id,
        correlation_reference=request.correlation_reference,
        artifact_references=(),
        provenance=("test-perception",),
        sensitivity="sensitive",
    )


def _runtime(
    speech_flags: list[bool],
    *,
    conversation: FakeConversation | None = None,
    output: FakeOutput | None = None,
    speech: FakeSpeech | None = None,
    perception: PerceptionHandoffPort | None = None,
    journal: VoiceIntegrationJournal | None = None,
    frontend_events: VoiceFrontendEventSink | None = None,
) -> tuple[RealtimeVoiceRuntime, FakeMicrophone, FakeConversation, FakeOutput, FakeSpeech]:
    microphone = FakeMicrophone([FRAME] * len(speech_flags))
    active_conversation = conversation or FakeConversation()
    active_output = output or FakeOutput()
    active_speech = speech or FakeSpeech()
    runtime = RealtimeVoiceRuntime(
        microphone=microphone,
        output=active_output,
        speech=active_speech,
        conversation=active_conversation,
        perception=perception,
        journal=journal,
        frontend_events=frontend_events,
        vad=WebRTCVADProvider(
            VADConfig(
                frame_duration_ms=20,
                min_speech_duration_ms=20,
                min_silence_duration_ms=40,
            ),
            SequenceClassifier(speech_flags),
        ),
    )
    return runtime, microphone, active_conversation, active_output, active_speech


def _start(runtime: RealtimeVoiceRuntime) -> None:
    runtime.start(
        "session-1",
        "actor://local-user",
        RealtimeVoiceConfig("input-1", "output-1", minimum_speech_ms=20, end_silence_ms=40),
    )


def test_construction_does_not_open_microphone_and_capabilities_are_factual() -> None:
    runtime, microphone, _, _, _ = _runtime([False])
    assert microphone.open_count == 0
    assert runtime.capability_report()["real_time_voice"] == "supported"
    assert microphone.open_count == 0


def test_invalid_explicit_device_never_falls_back_to_default() -> None:
    runtime, microphone, _, _, _ = _runtime([False])
    with pytest.raises(ValidationError, match="Configured microphone"):
        runtime.start(
            "session-1",
            "actor://user",
            RealtimeVoiceConfig("missing", "output-1"),
        )
    assert microphone.open_count == 0


def test_silence_does_not_create_utterance_or_transcription() -> None:
    runtime, _, conversation, _, speech = _runtime([False, False])
    _start(runtime)
    assert runtime.process_next_frame() is None
    assert runtime.process_next_frame() is None
    assert conversation.requests == []
    assert speech.transcribe_calls == 0


def test_single_utterance_is_transient_and_handed_off_without_reasoning() -> None:
    runtime, _, conversation, _, speech = _runtime([True, True, False, False])
    _start(runtime)
    results = [runtime.process_next_frame() for _ in range(4)]
    utterance = next(item for item in results if item is not None)
    assert utterance.pcm_reference.startswith("transient://")
    assert utterance.pcm_bytes
    assert speech.transcribe_calls == 1
    request = conversation.requests[0]
    assert request.utterance_id == utterance.utterance_id
    assert request.provenance == ("voice.realtime", "stt:faster_whisper")
    assert request.transcript_reference.startswith("voice-transcript://")
    assert request.transcript_content is None
    assert request.perception_status is PerceptionAvailability.UNAVAILABLE
    assert runtime.state is RealtimeVoiceState.WAITING_FOR_RESPONSE


def test_micro_pause_does_not_split_utterance() -> None:
    flags = [True, True, False, True, True, False, False]
    runtime, _, conversation, _, _ = _runtime(flags)
    _start(runtime)
    results = [runtime.process_next_frame() for _ in flags]
    assert len([item for item in results if item is not None]) == 1
    assert len(conversation.requests) == 1


def test_multiple_utterances_are_separate_after_explicit_silence_policy() -> None:
    flags = [True, False, False, True, False, False]
    runtime, _, conversation, _, _ = _runtime(flags)
    _start(runtime)
    results = [runtime.process_next_frame() for _ in flags]
    assert len([item for item in results if item is not None]) == 2
    assert len(conversation.requests) == 2


def test_stt_failure_preserves_finalized_utterance_fact() -> None:
    runtime, _, _, _, _ = _runtime([True, False, False], speech=FakeSpeech(transcript="<failure>"))
    _start(runtime)
    runtime.process_next_frame()
    runtime.process_next_frame()
    with pytest.raises(ValidationError, match="stt unavailable"):
        runtime.process_next_frame()
    assert any(fact.kind == "utterance.finalized" for fact in runtime.facts())
    assert runtime.state is RealtimeVoiceState.ERROR


def test_stale_response_is_rejected_and_tts_unavailable_does_not_fallback() -> None:
    runtime, _, conversation, _, _ = _runtime([True, False, False])
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    request = conversation.requests[0]
    stale = replace(_response(request, "ignored"), request_id="wrong")
    with pytest.raises(ValidationError, match="correspondence"):
        runtime.receive_response(stale)

    unavailable, _, unavailable_conversation, _, _ = _runtime(
        [True, False, False], speech=FakeSpeech(tts_available=False)
    )
    _start(unavailable)
    for _ in range(3):
        unavailable.process_next_frame()
    with pytest.raises(ValidationError, match="execution boundary unavailable"):
        accepted = unavailable.receive_response(_response(unavailable_conversation.requests[0]))
        unavailable.synthesize_response(accepted.response.response_id)


def test_playback_completion_is_separate_from_response_and_synthesis() -> None:
    output = FakeOutput(completed=False)
    runtime, _, conversation, _, speech = _runtime([True, False, False], output=output)
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    assert output.requests == []
    accepted = runtime.receive_response(_response(conversation.requests[0]))
    assert output.requests == []
    playback = runtime.synthesize_response(accepted.response.response_id)
    assert speech.synthesize_calls == 1
    assert playback.started and not playback.completed
    assert runtime.state is RealtimeVoiceState.SYSTEM_SPEAKING
    runtime.complete_playback(playback.playback_id)
    assert runtime.state is RealtimeVoiceState.LISTENING


def test_output_device_failure_is_factual_and_does_not_crash_the_runtime() -> None:
    output = FakeOutput(fail_playback=True)
    runtime, _, conversation, _, _ = _runtime([True, False, False], output=output)
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    accepted = runtime.receive_response(_response(conversation.requests[0]))
    playback = runtime.synthesize_response(accepted.response.response_id)
    assert playback.started is False
    assert playback.error == "device disconnected"
    assert runtime.state is RealtimeVoiceState.ERROR
    assert any(fact.kind == "playback.failed" for fact in runtime.facts())


@pytest.mark.parametrize("stop_confirmed", [True, False])
def test_barge_in_separates_detection_stop_request_and_confirmation(
    stop_confirmed: bool,
) -> None:
    output = FakeOutput(completed=False, stop_confirmed=stop_confirmed)
    conversation = FakeConversation(immediate=True)
    runtime, _, _, _, _ = _runtime(
        [True, False, False, True], conversation=conversation, output=output
    )
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    response = _response(conversation.requests[0])
    runtime.synthesize_response(response.response_id)
    assert runtime.state is RealtimeVoiceState.SYSTEM_SPEAKING
    runtime.process_next_frame()
    facts = runtime.facts()
    assert any(fact.kind == "barge_in.detected" for fact in facts)
    stop_fact = next(fact for fact in facts if fact.kind == "playback.stop_observed")
    assert stop_fact.metadata["stop_confirmed"] is stop_confirmed
    expected = (
        RealtimeVoiceState.USER_SPEAKING
        if stop_confirmed
        else RealtimeVoiceState.INTERRUPTION_PENDING
    )
    assert runtime.state is expected


def test_cancel_request_is_not_completion_and_restart_requires_reconciliation() -> None:
    runtime, microphone, _, _, _ = _runtime([False])
    _start(runtime)
    runtime.request_cancel()
    assert runtime.state is RealtimeVoiceState.CANCELLATION_PENDING
    assert microphone.stream.closed is False
    runtime.restart_observed()
    assert runtime.state is RealtimeVoiceState.RECONCILIATION_REQUIRED
    assert any(fact.kind == "restart.external_state_unknown" for fact in runtime.facts())
    assert microphone.open_count == 1


def test_invalid_late_response_cannot_reopen_closed_session() -> None:
    runtime, _, conversation, _, _ = _runtime([True, False, False])
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    response = _response(conversation.requests[0])
    runtime.request_cancel()
    with pytest.raises(ValidationError, match="cannot reopen"):
        runtime.receive_response(response)


def test_real_acoustic_perception_bundle_reaches_conversation_by_reference() -> None:
    directory = tempfile.TemporaryDirectory()
    try:
        app = create_runtime(
            Settings(PROJECT_ROOT, Path(directory.name) / "data", "127.0.0.1", 8717, "local_owner")
        )
        runtime, _, conversation, output, speech = _runtime(
            [True, False, False], perception=LocalVoicePerceptionAdapter(app.perception)
        )
        _start(runtime)
        for _ in range(3):
            runtime.process_next_frame()
        request = conversation.requests[0]
        assert request.perception_status in {
            PerceptionAvailability.AVAILABLE,
            PerceptionAvailability.PARTIAL,
        }
        assert request.perception_bundle_reference is not None
        bundle_id = request.perception_bundle_reference.removeprefix("perception-bundle://")
        bundle = app.perception.get_result_bundle(bundle_id)
        assert bundle.utterance_id == request.utterance_id
        assert bundle.transcription_id == request.transcription_id
        assert all(
            item.artifact_kind == PerceptionArtifactKind.DERIVED_FEATURE
            for item in bundle.artifact_references
        )
        assert all(item.lineage for item in bundle.artifact_references)
        durable = "".join(
            path.read_text(encoding="utf-8")
            for path in (app.settings.data_dir / "perception").rglob("*.json")
        )
        assert "pcm_bytes" not in durable
        assert "audio_base64" not in durable
        assert "intent" not in durable
        accepted = runtime.receive_response(_response(request))
        assert accepted.response.utterance_id == request.utterance_id
        assert accepted.response.correlation_reference == request.correlation_reference
        assert speech.synthesize_calls == 0
        assert output.requests == []
    finally:
        directory.cleanup()


def test_response_acceptance_is_idempotent_and_does_not_synthesize() -> None:
    runtime, _, conversation, output, speech = _runtime([True, False, False])
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    response = _response(conversation.requests[0])
    accepted = runtime.receive_response(response)
    duplicate = runtime.receive_response(response)
    assert accepted.disposition is ResponseDisposition.ACCEPTED
    assert duplicate.disposition is ResponseDisposition.DUPLICATE
    assert speech.synthesize_calls == 0
    assert output.requests == []
    with pytest.raises(ValidationError, match="Contradictory"):
        runtime.receive_response(replace(response, text="different"))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("voice_session_id", "wrong-session"),
        ("utterance_id", "wrong-utterance"),
        ("conversation_turn_id", "wrong-turn"),
        ("correlation_reference", "wrong-correlation"),
    ],
)
def test_response_correspondence_rejects_wrong_identity(field_name: str, value: str) -> None:
    runtime, _, conversation, _, _ = _runtime([True, False, False])
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    response = replace(_response(conversation.requests[0]), **{field_name: value})
    with pytest.raises(ValidationError, match="correspondence"):
        runtime.receive_response(response)


def test_late_response_is_rejected_by_explicit_deadline() -> None:
    runtime, _, conversation, _, _ = _runtime([True, False, False])
    runtime.start(
        "session-1",
        "actor://local-user",
        RealtimeVoiceConfig(
            "input-1",
            "output-1",
            minimum_speech_ms=20,
            end_silence_ms=40,
            response_timeout_ms=-1,
        ),
    )
    for _ in range(3):
        runtime.process_next_frame()
    with pytest.raises(ValidationError, match="Late"):
        runtime.receive_response(_response(conversation.requests[0]))


def test_new_utterance_supersedes_turn_without_erasing_history() -> None:
    flags = [True, False, False, True, False, False]
    runtime, _, conversation, _, _ = _runtime(flags)
    _start(runtime)
    for _ in flags:
        runtime.process_next_frame()
    first, second = conversation.requests
    assert first.utterance_id != second.utterance_id
    assert runtime.pending_request() == second
    with pytest.raises(ValidationError, match="Stale"):
        runtime.receive_response(_response(first))
    assert runtime.pending_request() == second
    assert any(fact.kind == "conversation.request_superseded" for fact in runtime.facts())


def test_late_perception_is_recorded_without_rewriting_current_turn() -> None:
    flags = [True, False, False, True, False, False]
    runtime, _, conversation, _, _ = _runtime(flags)
    _start(runtime)
    for _ in flags:
        runtime.process_next_frame()
    first, second = conversation.requests
    runtime.receive_perception_bundle(first.request_id, _bundle(first))
    assert runtime.pending_request() == second
    fact = next(fact for fact in runtime.facts() if fact.kind == "perception.bundle_received_late")
    assert fact.metadata["request_id"] == first.request_id


def test_restart_preserves_pending_request_without_reexecution() -> None:
    directory = tempfile.TemporaryDirectory()
    try:
        journal = SQLiteVoiceJournal(Path(directory.name) / "voice.sqlite3")
        runtime, _, conversation, _, speech = _runtime(
            [True, False, False], journal=journal
        )
        _start(runtime)
        for _ in range(3):
            runtime.process_next_frame()
        pending = conversation.requests[0]
        restored, _, _, _, restored_speech = _runtime([], journal=journal)
        restored.restore_pending(
            "session-1",
            "actor://local-user",
            RealtimeVoiceConfig("input-1", "output-1"),
        )
        assert restored.state is RealtimeVoiceState.RECONCILIATION_REQUIRED
        assert restored.pending_request() == pending
        assert restored_speech.transcribe_calls == 0
        assert speech.transcribe_calls == 1
    finally:
        directory.cleanup()


def test_restart_preserves_pending_perception_as_unknown_without_recalculation() -> None:
    directory = tempfile.TemporaryDirectory()
    try:
        journal = SQLiteVoiceJournal(Path(directory.name) / "voice.sqlite3")
        runtime, _, conversation, _, speech = _runtime(
            [True, False, False], journal=journal, perception=PendingPerception()
        )
        _start(runtime)
        for _ in range(3):
            runtime.process_next_frame()
        assert conversation.requests[0].perception_status is PerceptionAvailability.PENDING
        restored, _, _, _, restored_speech = _runtime([], journal=journal)
        restored.restore_pending(
            "session-1",
            "actor://local-user",
            RealtimeVoiceConfig("input-1", "output-1"),
        )
        pending = restored.pending_request()
        assert pending is not None
        assert pending.perception_status is PerceptionAvailability.PENDING
        assert restored.state is RealtimeVoiceState.RECONCILIATION_REQUIRED
        assert restored_speech.transcribe_calls == 0
        assert speech.transcribe_calls == 1
    finally:
        directory.cleanup()


def test_restart_preserves_accepted_response_without_synthesis() -> None:
    directory = tempfile.TemporaryDirectory()
    try:
        journal = SQLiteVoiceJournal(Path(directory.name) / "voice.sqlite3")
        runtime, _, conversation, _, _ = _runtime([True, False, False], journal=journal)
        _start(runtime)
        for _ in range(3):
            runtime.process_next_frame()
        response = _response(conversation.requests[0])
        runtime.receive_response(response)
        restored, _, _, output, speech = _runtime([], journal=journal)
        restored.restore_pending(
            "session-1",
            "actor://local-user",
            RealtimeVoiceConfig("input-1", "output-1"),
        )
        assert restored.pending_request() is None
        assert restored.accepted_response(response.response_id) is not None
        assert speech.synthesize_calls == 0
        assert output.requests == []
        assert restored.state is RealtimeVoiceState.RECONCILIATION_REQUIRED
    finally:
        directory.cleanup()


def test_controlled_journey_emits_factual_frontend_sequence() -> None:
    stream = VoiceFrontendEventStream("session-1", "voice-session://session-1")
    output = FakeOutput(completed=False)
    runtime, _, conversation, _, _ = _runtime(
        [True, False, False], output=output, frontend_events=stream
    )
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    response = _response(conversation.requests[0])
    accepted = runtime.receive_response(response)
    assert stream.snapshot().state is VoicePresentationState.PROCESSING
    assert output.requests == []
    playback = runtime.synthesize_response(accepted.response.response_id)
    assert stream.snapshot().state is VoicePresentationState.SPEAKING
    runtime.complete_playback(playback.playback_id)
    assert stream.snapshot().state is VoicePresentationState.LISTENING
    kinds = [event.event_type for event in stream.events_after(0)]
    assert kinds == [
        VoiceFrontendEventType.LISTENING,
        VoiceFrontendEventType.SPEECH_STARTED,
        VoiceFrontendEventType.SPEECH_ENDED,
        VoiceFrontendEventType.PROCESSING,
        VoiceFrontendEventType.PROCESSING,
        VoiceFrontendEventType.PROCESSING,
        VoiceFrontendEventType.PROCESSING,
        VoiceFrontendEventType.SPEAKING_STARTED,
        VoiceFrontendEventType.SPEAKING_ENDED,
    ]
    serialized = repr(stream.events_after(0)).lower()
    for forbidden in ("pcm", "waveform", "amplitude", "thinking", "reasoning"):
        assert forbidden not in serialized
    assert all("text" not in event.metadata for event in stream.events_after(0))


def test_frontend_interruption_preserves_detected_requested_and_confirmed_facts() -> None:
    stream = VoiceFrontendEventStream("session-1", "voice-session://session-1")
    output = FakeOutput(completed=False, stop_confirmed=True)
    conversation = FakeConversation(immediate=True)
    runtime, _, _, _, _ = _runtime(
        [True, False, False, True],
        output=output,
        conversation=conversation,
        frontend_events=stream,
    )
    _start(runtime)
    for _ in range(3):
        runtime.process_next_frame()
    runtime.synthesize_response(_response(conversation.requests[0]).response_id)
    runtime.process_next_frame()
    kinds = [event.event_type for event in stream.events_after(0)]
    assert VoiceFrontendEventType.INTERRUPTION_DETECTED in kinds
    assert VoiceFrontendEventType.INTERRUPTION_REQUESTED in kinds
    assert VoiceFrontendEventType.INTERRUPTION_CONFIRMED in kinds


def test_frontend_capability_status_and_restart_snapshot_are_factual() -> None:
    stream = VoiceFrontendEventStream("session-1", "voice-session://session-1")
    runtime, _, _, _, _ = _runtime(
        [False], speech=FakeSpeech(tts_available=False), frontend_events=stream
    )
    _start(runtime)
    report = runtime.publish_capability_status()
    assert report["real_time_voice"] == "degraded"
    assert stream.snapshot().capability_status == "degraded"
    runtime.restart_observed()
    snapshot = stream.snapshot()
    assert snapshot.state is VoicePresentationState.UNAVAILABLE
    assert snapshot.external_state_known is False


def test_frontend_cancellation_and_runtime_error_are_factual() -> None:
    cancelled_stream = VoiceFrontendEventStream("session-1", "voice-session://session-1")
    cancelled, _, _, _, _ = _runtime([False], frontend_events=cancelled_stream)
    _start(cancelled)
    cancelled.request_cancel()
    cancelled.confirm_cancelled()
    assert cancelled_stream.snapshot().state is VoicePresentationState.IDLE
    kinds = [event.event_type for event in cancelled_stream.events_after(0)]
    assert VoiceFrontendEventType.CANCELLING in kinds
    assert VoiceFrontendEventType.CANCELLED in kinds

    error_stream = VoiceFrontendEventStream("session-1", "voice-session://session-1")
    failed, _, _, _, _ = _runtime([], frontend_events=error_stream)
    _start(failed)
    with pytest.raises(StopIteration):
        failed.process_next_frame()
    assert error_stream.snapshot().state is VoicePresentationState.ERROR
