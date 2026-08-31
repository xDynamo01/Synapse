from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from factories.agents import seed_test_agent
from synapse.agents.registry import AgentRegistry
from synapse.audio.models import (
    AudioInputRequest,
    AudioOutputRequest,
    SpeechFeatures,
    TextToSpeechResult,
    TranscriptResult,
)
from synapse.audio.realtime_devices import PlaybackRequest, PlaybackResult
from synapse.conversations.runtime import ConversationRuntime
from synapse.conversations.voice_contracts import VoiceConversationRequest
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import dump_structured_file
from synapse.speech_adapters.models import SpeechAdapterHealth
from synapse.voice.frontend_events import VoiceFrontendEvent
from synapse.voice.persistence_models import VoiceRecordDraft
from synapse.voice.realtime import RealtimeVoiceState
from synapse.voice_composition import (
    CapabilityLevel,
    OperationalCompletion,
    VoicePerceptionConfiguration,
    VoicePerceptionRuntimeBuilder,
)


class InputPort:
    def __init__(self, devices: tuple[str, ...] = ("mic-1",)) -> None:
        self.devices = devices
        self.open_count = 0

    def capabilities(self) -> dict[str, object]:
        return {"streaming": True}

    def list_input_devices(self) -> tuple[str, ...]:
        return self.devices

    def open_stream(self, device_reference: str, *, sample_rate: int, frame_duration_ms: int):
        _ = device_reference, sample_rate, frame_duration_ms
        self.open_count += 1
        return InputStream()


class InputStream:
    def read_frame(self) -> bytes:
        return b"\0" * 640

    def close(self) -> None:
        return None


class OutputPort:
    def __init__(self, devices: tuple[str, ...] = ("speaker-1",)) -> None:
        self.devices = devices
        self.play_count = 0

    def capabilities(self) -> dict[str, object]:
        return {"interruption": True}

    def list_output_devices(self) -> tuple[str, ...]:
        return self.devices

    def play(self, request: PlaybackRequest) -> PlaybackResult:
        self.play_count += 1
        return PlaybackResult(request.playback_id, True, True, False)

    def request_stop(self, playback_id: str) -> PlaybackResult:
        return PlaybackResult(playback_id, True, True, False, True, True, True)


class Classifier:
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        _ = frame, sample_rate
        return False


class SequenceClassifier:
    def __init__(self) -> None:
        self._values = iter([True] * 10 + [False] * 20)

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        _ = frame, sample_rate
        return next(self._values)


class Conversation:
    def submit(self, request: VoiceConversationRequest):
        _ = request
        return None


class FrontendSink:
    def __init__(self) -> None:
        self.events: list[VoiceFrontendEvent] = []

    def publish(self, event: VoiceFrontendEvent) -> None:
        self.events.append(event)


@dataclass
class Adapter:
    provider: str
    status: str = "available"
    transcribe_count: int = 0
    synthesize_count: int = 0

    def health(self) -> SpeechAdapterHealth:
        return SpeechAdapterHealth(
            f"{self.provider}_adapter", self.provider, self.status, "2026-08-11T00:00:00+00:00"
        )

    def transcribe(self, request: AudioInputRequest):
        self.transcribe_count += 1
        raise AssertionError("STT must not run while building")

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        self.synthesize_count += 1
        raise AssertionError("TTS must not run while building")


class OperationalSTT(Adapter):
    def transcribe(self, request: AudioInputRequest) -> TranscriptResult:
        self.transcribe_count += 1
        return TranscriptResult(
            text="controlled speech",
            language="pt-BR",
            duration_ms=request.duration_ms,
            confidence=0.9,
            provider_id="faster_whisper",
            speech_features=SpeechFeatures(),
        )


class Execution:
    def execute(self, request):
        raise AssertionError("execution boundary must not run while building")


def configured(tmp_path: Path, **changes: object):
    values: dict[str, object] = {
        "input_device_reference": "mic-1",
        "output_device_reference": "speaker-1",
        "stt_model": "base",
        "tts_model": "pt_BR-female.onnx",
    }
    values.update(changes)
    (tmp_path / "voice/models/faster-whisper/base").mkdir(parents=True, exist_ok=True)
    return VoicePerceptionConfiguration(**values)


def build(tmp_path: Path, configuration=None, **dependencies: object):
    conversation_runtime = dependencies.pop("conversation_runtime", None)
    conversation_context = dependencies.pop("conversation_context", None)
    return VoicePerceptionRuntimeBuilder(
        data_dir=DataDir(tmp_path),
        configuration=configuration or configured(tmp_path),
        microphone=dependencies.pop("microphone", InputPort()),
        output=dependencies.pop("output", OutputPort()),
        conversation=dependencies.pop("conversation", None),
        conversation_runtime=conversation_runtime,
        conversation_context=conversation_context,
        frame_classifier=dependencies.pop("frame_classifier", Classifier()),
        stt=dependencies.pop("stt", Adapter("faster_whisper")),
        tts=dependencies.pop("tts", Adapter("piper")),
        **dependencies,
    ).build()


def real_conversation(tmp_path: Path) -> tuple[ConversationRuntime, PermissionContext]:
    seed_test_agent(tmp_path, "artemis", role="assistant")
    dump_structured_file(
        tmp_path / "config/permissions.yaml",
        {"subjects": {"local_owner": ["agents.message"]}},
    )
    events = EventBus(tmp_path)
    permissions = PermissionManager(tmp_path, events)
    runtime = ConversationRuntime(
        DataDir(tmp_path), AgentRegistry(DataDir(tmp_path)), permissions, events
    )
    return runtime, PermissionContext("local_owner")


def test_minimal_build_reports_optional_dependencies_without_false_readiness(tmp_path: Path):
    runtime = VoicePerceptionRuntimeBuilder(
        data_dir=DataDir(tmp_path),
        configuration=VoicePerceptionConfiguration(stt_model=None, perception_enabled=False),
        frame_classifier=Classifier(),
        stt=Adapter("faster_whisper"),
        tts=Adapter("piper", "unavailable"),
    ).build()
    health = runtime.health_snapshot()
    assert health.persistence.level is CapabilityLevel.SUPPORTED
    assert health.audio_input.level is CapabilityLevel.NOT_CONFIGURED
    assert health.frontend_events.level is CapabilityLevel.NOT_CONFIGURED
    assert health.perception.level is CapabilityLevel.NOT_CONFIGURED
    assert health.real_time_voice.level is CapabilityLevel.UNAVAILABLE


def test_full_local_build_is_supported_only_with_all_operational_evidence(tmp_path: Path):
    conversations, context = real_conversation(tmp_path)
    runtime = build(
        tmp_path,
        configuration=configured(tmp_path, conversation_target_agent_id="artemis"),
        conversation_runtime=conversations,
        conversation_context=context,
        tts_execution=Execution(),
        frontend_events=FrontendSink(),
    )
    health = runtime.health_snapshot()
    assert health.stt.level is CapabilityLevel.SUPPORTED
    assert health.tts.level is CapabilityLevel.SUPPORTED
    assert health.perception.level is CapabilityLevel.SUPPORTED
    assert health.frontend_events.level is CapabilityLevel.SUPPORTED
    assert health.conversation.level is CapabilityLevel.SUPPORTED
    assert health.real_time_voice.level is CapabilityLevel.SUPPORTED


@pytest.mark.parametrize(
    ("dependency", "expected"),
    [
        ({"microphone": InputPort(())}, CapabilityLevel.UNAVAILABLE),
        ({"output": OutputPort(())}, CapabilityLevel.UNAVAILABLE),
        ({"conversation": None}, CapabilityLevel.UNAVAILABLE),
    ],
)
def test_missing_operational_dependency_is_reported(
    tmp_path: Path, dependency: dict[str, object], expected: CapabilityLevel
):
    runtime = build(tmp_path, tts_execution=Execution(), **dependency)
    assert runtime.health_snapshot().real_time_voice.level is expected


def test_conversation_health_requires_runtime_permission_and_explicit_target(tmp_path: Path):
    runtime = build(tmp_path)
    health = runtime.health_snapshot().conversation
    assert health.level is CapabilityLevel.NOT_CONFIGURED
    assert health.fact("contract_available") is True
    assert health.fact("runtime_available") is False
    assert health.fact("target_configured") is False
    assert health.fact("request_path_available") is False
    assert health.fact("response_path_available") is False


def test_configured_unknown_agent_is_unavailable_and_never_reselected(tmp_path: Path):
    conversations, context = real_conversation(tmp_path)
    runtime = build(
        tmp_path,
        configuration=configured(tmp_path, conversation_target_agent_id="missing"),
        conversation_runtime=conversations,
        conversation_context=context,
    )
    health = runtime.health_snapshot().conversation
    assert health.level is CapabilityLevel.UNAVAILABLE
    assert health.fact("target_configured") is True
    assert health.fact("target_available") is False


def test_missing_stt_model_and_piper_execution_are_not_supported(tmp_path: Path):
    runtime = build(
        tmp_path,
        configuration=configured(tmp_path, stt_model="missing"),
        tts_execution=None,
    )
    health = runtime.health_snapshot()
    assert health.stt.level is CapabilityLevel.DEGRADED
    assert health.stt.fact("model_available") is False
    assert health.tts.level is CapabilityLevel.DEGRADED
    assert health.tts.fact("execution_boundary_available") is True
    assert health.tts.fact("execution_authority_available") is False
    assert health.real_time_voice.level is CapabilityLevel.UNAVAILABLE


def test_build_has_no_device_provider_perception_or_frontend_side_effects(tmp_path: Path):
    microphone, output, stt, tts, sink = (
        InputPort(),
        OutputPort(),
        Adapter("stt"),
        Adapter("tts"),
        FrontendSink(),
    )
    runtime = build(
        tmp_path,
        microphone=microphone,
        output=output,
        stt=stt,
        tts=tts,
        frontend_events=sink,
        tts_execution=Execution(),
    )
    assert runtime.session_started is False
    assert (
        microphone.open_count
        == output.play_count
        == stt.transcribe_count
        == tts.synthesize_count
        == 0
    )
    assert sink.events == []


def test_start_is_explicit_and_close_is_idempotent_and_terminal(tmp_path: Path):
    microphone = InputPort()
    runtime = build(tmp_path, microphone=microphone)
    runtime.start_session("session-1", "actor-1")
    assert runtime.session_started is True
    assert microphone.open_count == 1
    runtime.close()
    runtime.close()
    with pytest.raises(ValidationError, match="closed"):
        runtime.health_snapshot()


def test_restart_replays_without_stream_or_pending_work_execution(tmp_path: Path):
    stt, tts, microphone = Adapter("stt"), Adapter("tts"), InputPort()
    first = build(tmp_path, stt=stt, tts=tts, microphone=microphone)
    first.journal.append(
        VoiceRecordDraft("realtime:session-1", "transcription.requested", 1, {}, "pending-1")
    )
    reopened = build(tmp_path, stt=stt, tts=tts, microphone=microphone)
    reopened.restore_session("session-1", "actor-1")
    assert reopened.realtime is not None
    assert reopened.realtime.state is RealtimeVoiceState.RECONCILIATION_REQUIRED
    assert reopened.session_started is False
    assert microphone.open_count == stt.transcribe_count == tts.synthesize_count == 0


def test_invalid_migration_checksum_fails_closed(tmp_path: Path):
    runtime = build(tmp_path)
    database = runtime.journal.path
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER voice_migrations_no_update")
        connection.execute("UPDATE voice_migrations SET checksum='invalid'")
    with pytest.raises(ValidationError, match="migration mismatch"):
        build(tmp_path)


def test_existing_adapter_never_overrides_unavailable_health(tmp_path: Path):
    runtime = build(tmp_path, stt=Adapter("faster_whisper", "unavailable"))
    assert runtime.health_snapshot().stt.level is CapabilityLevel.UNAVAILABLE
    assert runtime.health_snapshot().real_time_voice.level is CapabilityLevel.UNAVAILABLE


def test_real_piper_without_local_evidence_is_not_supported(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SYNAPSE_PIPER_EXECUTABLE", raising=False)
    monkeypatch.delenv("SYNAPSE_PIPER_MODEL", raising=False)
    runtime = VoicePerceptionRuntimeBuilder(
        data_dir=DataDir(tmp_path),
        configuration=VoicePerceptionConfiguration(stt_model=None),
        frame_classifier=Classifier(),
        stt=Adapter("faster_whisper", "unavailable"),
    ).build()
    assert runtime.health_snapshot().tts.level is CapabilityLevel.UNAVAILABLE
    assert runtime.health_snapshot().tts.fact("model_configured") is False
    assert runtime.health_snapshot().tts.fact("model_available") is False
    assert runtime.health_snapshot().tts.fact("execution_boundary_available") is True
    assert runtime.health_snapshot().tts.fact("execution_authority_available") is False


def test_controlled_audio_uses_real_conversation_runtime_without_auto_synthesis(
    tmp_path: Path,
):
    conversations, context = real_conversation(tmp_path)
    microphone, output = InputPort(), OutputPort()
    stt, tts = OperationalSTT("faster_whisper"), Adapter("piper")
    runtime = build(
        tmp_path,
        configuration=configured(tmp_path, conversation_target_agent_id="artemis"),
        microphone=microphone,
        output=output,
        frame_classifier=SequenceClassifier(),
        stt=stt,
        tts=tts,
        conversation_runtime=conversations,
        conversation_context=context,
    )
    runtime.start_session("session-1", "local_owner")
    assert runtime.realtime is not None
    for _ in range(30):
        runtime.realtime.process_next_frame()
    request = runtime.realtime.pending_request()
    assert request is not None
    assert request.transcript_content is None
    handoff = runtime.conversation_handoff
    assert handoff is not None
    response = handoff.accept_authority_response(
        request,
        response_reference="conversation-response://controlled-1",
        text="explicit authority response",
        provenance=("conversation.runtime", "authority:artemis"),
    )
    duplicate = handoff.accept_authority_response(
        request,
        response_reference="conversation-response://controlled-1",
        text="explicit authority response",
        provenance=("conversation.runtime", "authority:artemis"),
    )
    assert duplicate == response
    with pytest.raises(ValidationError, match="Contradictory"):
        handoff.accept_authority_response(
            request,
            response_reference="conversation-response://controlled-1",
            text="contradictory response",
            provenance=("conversation.runtime", "authority:artemis"),
        )
    runtime.realtime.receive_response(response)
    assert runtime.realtime.accepted_response(response.response_id) is not None
    assert tts.synthesize_count == 0
    assert output.play_count == 0
    messages = conversations.list_conversation_messages(
        conversations.list_conversations()[0].conversation_id
    )
    assert [message.sender_agent_id for message in messages] == ["local_chat", "artemis"]
    assert all(message.tool_calls == [] for message in messages)


def test_capability_decomposition_marks_only_tts_as_external_blocker(tmp_path: Path):
    conversations, context = real_conversation(tmp_path)
    runtime = build(
        tmp_path,
        configuration=configured(tmp_path, conversation_target_agent_id="artemis"),
        conversation_runtime=conversations,
        conversation_context=context,
    )
    health = runtime.health_snapshot()
    assert health.voice_input.level is CapabilityLevel.SUPPORTED
    assert health.speech_to_text.level is CapabilityLevel.SUPPORTED
    assert health.voice_conversation.level is CapabilityLevel.SUPPORTED
    assert health.speech_output.level is CapabilityLevel.UNAVAILABLE
    assert health.full_duplex_voice.level is CapabilityLevel.DEGRADED
    completion = dict(health.operational_completion)
    assert completion["voice_conversation"] is OperationalCompletion.INTERNALLY_COMPLETE
    assert completion["speech_output"] is OperationalCompletion.EXTERNALLY_BLOCKED
    assert completion["full_duplex_voice"] is OperationalCompletion.EXTERNALLY_BLOCKED


def test_composition_is_not_imported_by_domains_or_global_bootstrap():
    repository = Path(__file__).parents[1]
    prohibited_roots = (
        repository / "backend/synapse/voice",
        repository / "backend/synapse/audio",
        repository / "backend/synapse/perception",
        repository / "backend/synapse/bootstrap",
    )
    offenders = [
        path
        for root in prohibited_roots
        for path in root.rglob("*.py")
        if "synapse.voice_composition" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_configuration_rejects_absolute_persistence_path(tmp_path: Path):
    with pytest.raises(ValidationError, match="relative"):
        build(
            tmp_path,
            configuration=VoicePerceptionConfiguration(
                persistence_relative_path=str(tmp_path / "voice.sqlite3")
            ),
        )


def test_configuration_reuses_existing_voice_settings(tmp_path: Path):
    settings = tmp_path / "voice/settings.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"stt_provider_id":"faster_whisper","stt_model":"tiny",'
        '"tts_provider_id":"piper","tts_model":null,'
        '"preferred_voice_gender":"female","policy_version":"voice-configuration-v1"}',
        encoding="utf-8",
    )
    configuration = VoicePerceptionConfiguration.from_voice_settings(DataDir(tmp_path))
    assert configuration.stt_model == "tiny"
    assert configuration.default_voice == "female"
    assert configuration.tts_model is None
