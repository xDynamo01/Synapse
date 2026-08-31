from __future__ import annotations

import hashlib
import io
import json
import wave
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from synapse.audio.ingestion import ingest_audio
from synapse.audio.models import AudioInputRequest, AudioOutputRequest, TextToSpeechResult
from synapse.audio.realtime_devices import AudioOutputPort, MicrophoneInputPort
from synapse.conversations.runtime import ConversationRuntime
from synapse.conversations.voice_contracts import (
    ConversationResponseReference,
    VoiceConversationRequest,
)
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import load_structured_file
from synapse.perception.models import (
    PerceptionArtifactKind,
    PerceptionArtifactReference,
    PerceptionBundleStatus,
    PerceptionResultBundle,
    RetentionClass,
    VoicePerceptionRequest,
)
from synapse.perception.nonverbal import AcousticFeatureProvider, LocalDSPAcousticFeatureProvider
from synapse.speech_adapters.execution import SpeechExecutionPort
from synapse.speech_adapters.faster_whisper import FasterWhisperSpeechToTextAdapter
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest
from synapse.speech_adapters.piper_tts import PiperTextToSpeechAdapter
from synapse.voice.frontend_events import VoiceFrontendEventSink
from synapse.voice.realtime import (
    ConversationHandoffPort,
    RealtimeVoiceConfig,
    RealtimeVoiceRuntime,
    RealtimeVoiceState,
)
from synapse.voice.sqlite_persistence import SQLiteVoiceJournal
from synapse.voice.vad import FrameClassifier, VADConfig, WebRTCVADProvider
from synapse.voice_composition.conversation import (
    LocalConversationHandoff,
    conversation_wiring_health,
)


class CapabilityLevel(StrEnum):
    SUPPORTED = "supported"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"
    CORRUPT = "corrupt"
    SCHEMA_MISMATCH = "schema_mismatch"
    MIGRATION_MISMATCH = "migration_mismatch"


class OperationalCompletion(StrEnum):
    INTERNALLY_COMPLETE = "internally_complete"
    EXTERNALLY_BLOCKED = "externally_blocked"
    INTENTIONALLY_UNAVAILABLE = "intentionally_unavailable"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    level: CapabilityLevel
    facts: tuple[tuple[str, str | bool | int | None], ...] = ()

    def fact(self, name: str) -> str | bool | int | None:
        return dict(self.facts).get(name)


@dataclass(frozen=True, slots=True)
class VoicePerceptionHealthSnapshot:
    persistence: ComponentHealth
    audio_input: ComponentHealth
    vad: ComponentHealth
    stt: ComponentHealth
    conversation: ComponentHealth
    perception: ComponentHealth
    tts: ComponentHealth
    playback: ComponentHealth
    frontend_events: ComponentHealth
    voice_input: ComponentHealth
    speech_to_text: ComponentHealth
    voice_conversation: ComponentHealth
    speech_output: ComponentHealth
    full_duplex_voice: ComponentHealth
    real_time_voice: ComponentHealth
    operational_completion: tuple[tuple[str, OperationalCompletion], ...]
    checked_at: str


@dataclass(frozen=True, slots=True)
class VoicePerceptionConfiguration:
    persistence_relative_path: str = "voice/voice-journal-v1.sqlite3"
    input_device_reference: str | None = None
    output_device_reference: str | None = None
    sample_rate: int = 16_000
    frame_duration_ms: int = 20
    vad_aggressiveness: int = 2
    stt_provider: str = "faster_whisper"
    stt_model: str | None = "tiny"
    tts_provider: str = "piper"
    tts_model: str | None = None
    default_voice: str | None = "female"
    perception_enabled: bool = True
    retention_policy_reference: str | None = None
    voice_policy_reference: str | None = None
    conversation_target_agent_id: str | None = None

    @classmethod
    def from_voice_settings(
        cls,
        data_dir: DataDir,
        *,
        input_device_reference: str | None = None,
        output_device_reference: str | None = None,
    ) -> VoicePerceptionConfiguration:
        settings = load_structured_file(data_dir.resolve("voice/settings.yaml"))
        return cls(
            input_device_reference=input_device_reference,
            output_device_reference=output_device_reference,
            stt_provider=str(settings.get("stt_provider_id", "faster_whisper")),
            stt_model=str(settings.get("stt_model", "tiny")),
            tts_provider=str(settings.get("tts_provider_id", "piper")),
            tts_model=(
                str(settings["tts_model"]) if settings.get("tts_model") is not None else None
            ),
            default_voice=str(settings.get("preferred_voice_gender", "female")),
            voice_policy_reference=str(settings.get("policy_version", "voice-configuration-v1")),
        )

    def validate(self) -> None:
        if Path(self.persistence_relative_path).is_absolute():
            raise ValidationError("Voice persistence path must be relative to the data directory.")
        if self.sample_rate not in {8_000, 16_000, 32_000, 48_000}:
            raise ValidationError("Unsupported Voice sample rate.")
        if self.frame_duration_ms not in {10, 20, 30}:
            raise ValidationError("Unsupported Voice frame duration.")
        if self.vad_aggressiveness not in {0, 1, 2, 3}:
            raise ValidationError("Unsupported Voice VAD aggressiveness.")
        if self.stt_provider != "faster_whisper":
            raise ValidationError("Unsupported local Voice STT provider.")
        if self.tts_provider != "piper":
            raise ValidationError("Unsupported local Voice TTS provider.")
        for reference in (self.retention_policy_reference, self.voice_policy_reference):
            if reference is not None and not reference.strip():
                raise ValidationError("Voice policy references cannot be blank.")


class SpeechToTextPort(Protocol):
    def health(self) -> SpeechAdapterHealth: ...
    def transcribe(self, request: AudioInputRequest): ...


class TextToSpeechPort(Protocol):
    def health(self) -> SpeechAdapterHealth: ...
    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult: ...


class _LocalSpeechBoundary:
    def __init__(self, stt: SpeechToTextPort, tts: TextToSpeechPort) -> None:
        self._stt = stt
        self._tts = tts

    def adapter_health(self, adapter_id: str) -> SpeechAdapterHealth:
        if adapter_id == "piper_tts_adapter":
            return self._tts.health()
        if adapter_id == "faster_whisper_adapter":
            return self._stt.health()
        raise ValidationError("Speech adapter is outside this local composition.")

    def transcribe(self, request: AudioInputRequest):
        return self._stt.transcribe(request)

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        return self._tts.synthesize(request)


class _UnavailableConversation(ConversationHandoffPort):
    def submit(self, request: VoiceConversationRequest) -> ConversationResponseReference | None:
        _ = request
        raise ValidationError("Conversation integration is unavailable.")


class _LocalPerceptionHandoff:
    def __init__(self, provider: AcousticFeatureProvider) -> None:
        self._provider = provider

    def analyze_transient(
        self, request: VoicePerceptionRequest, pcm_bytes: bytes, sample_rate: int
    ) -> PerceptionResultBundle:
        payload = ingest_audio(_pcm_wav(pcm_bytes, sample_rate))
        result = self._provider.analyze(payload)
        references = tuple(
            PerceptionArtifactReference(
                artifact_id=_feature_id(request, feature.name),
                artifact_kind=PerceptionArtifactKind.DERIVED_FEATURE,
                type=f"audio.{feature.name}",
                provider=result.provider,
                model=result.algorithm,
                model_version=result.algorithm_version,
                confidence=None,
                occurrence_started_at=request.occurrence_started_at,
                occurrence_ended_at=request.occurrence_ended_at,
                lineage=(request.audio_checksum_reference,),
                sensitivity="sensitive",
                retention_class=RetentionClass.POLICY_PERSISTABLE,
            )
            for feature in result.features
        )
        missing = tuple(
            reference.type
            for reference, feature in zip(references, result.features, strict=True)
            if not feature.available
        )
        semantic = {
            "request": asdict(request),
            "artifacts": [asdict(reference) for reference in references],
            "missing": missing,
        }
        fingerprint = hashlib.sha256(
            json.dumps(semantic, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return PerceptionResultBundle(
            bundle_id=f"perception-bundle-{fingerprint[:24]}",
            fingerprint=fingerprint,
            status=PerceptionBundleStatus.PARTIAL if missing else PerceptionBundleStatus.AVAILABLE,
            voice_session_id=request.voice_session_id,
            utterance_id=request.utterance_id,
            transcription_id=request.transcription_id,
            correlation_reference=request.correlation_reference,
            artifact_references=references,
            provenance=(*request.provenance, f"perception:{result.provider}"),
            sensitivity="sensitive",
            missing_capabilities=missing,
            limitations=("Raw PCM was transient and is not part of this bundle.",),
        )


class VoicePerceptionRuntime:
    def __init__(
        self,
        *,
        configuration: VoicePerceptionConfiguration,
        journal: SQLiteVoiceJournal,
        realtime: RealtimeVoiceRuntime | None,
        conversation_handoff: LocalConversationHandoff | None,
        health: VoicePerceptionHealthSnapshot,
    ) -> None:
        self.configuration = configuration
        self.journal = journal
        self.realtime = realtime
        self.conversation_handoff = conversation_handoff
        self._health = health
        self._closed = False
        self._session_started = False

    @property
    def session_started(self) -> bool:
        return self._session_started

    def health_snapshot(self) -> VoicePerceptionHealthSnapshot:
        self._ensure_open()
        return self._health

    def start_session(self, session_id: str, actor_reference: str) -> None:
        self._ensure_open()
        if self.realtime is None:
            raise ValidationError("Real-time Voice is unavailable in this composition.")
        config = self.configuration
        if config.input_device_reference is None or config.output_device_reference is None:
            raise ValidationError("Voice input and output devices must be configured.")
        self.realtime.start(
            session_id,
            actor_reference,
            RealtimeVoiceConfig(
                input_device_reference=config.input_device_reference,
                output_device_reference=config.output_device_reference,
                sample_rate=config.sample_rate,
                frame_duration_ms=config.frame_duration_ms,
                vad_aggressiveness=config.vad_aggressiveness,
                stt_provider_id=config.stt_provider,
                stt_model=config.stt_model or "tiny",
                tts_provider_id=config.tts_provider,
                tts_voice_id=config.tts_model,
            ),
        )
        self._session_started = True

    def restore_session(self, session_id: str, actor_reference: str) -> None:
        self._ensure_open()
        if self.realtime is None:
            raise ValidationError("Real-time Voice is unavailable in this composition.")
        config = self.configuration
        self.realtime.restore_pending(
            session_id,
            actor_reference,
            RealtimeVoiceConfig(
                input_device_reference=config.input_device_reference or "unconfigured",
                output_device_reference=config.output_device_reference or "unconfigured",
                sample_rate=config.sample_rate,
                frame_duration_ms=config.frame_duration_ms,
                stt_model=config.stt_model or "tiny",
                tts_voice_id=config.tts_model,
            ),
        )

    def close(self) -> None:
        if self._closed:
            return
        if self.realtime is not None and (
            self._session_started or self.realtime.state is not RealtimeVoiceState.WAITING
        ):
            self.realtime.close()
        self._session_started = False
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValidationError("Voice/Perception composition is closed.")


class VoicePerceptionRuntimeBuilder:
    def __init__(
        self,
        *,
        data_dir: DataDir,
        configuration: VoicePerceptionConfiguration,
        microphone: MicrophoneInputPort | None = None,
        output: AudioOutputPort | None = None,
        conversation: ConversationHandoffPort | None = None,
        conversation_runtime: ConversationRuntime | None = None,
        conversation_context: PermissionContext | None = None,
        frontend_events: VoiceFrontendEventSink | None = None,
        tts_execution: SpeechExecutionPort | None = None,
        frame_classifier: FrameClassifier | None = None,
        stt: SpeechToTextPort | None = None,
        tts: TextToSpeechPort | None = None,
        acoustic_provider: AcousticFeatureProvider | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._configuration = configuration
        self._microphone = microphone
        self._output = output
        self._conversation = conversation
        self._conversation_runtime = conversation_runtime
        self._conversation_context = conversation_context
        self._frontend_events = frontend_events
        self._tts_execution = tts_execution
        self._frame_classifier = frame_classifier
        self._stt = stt
        self._tts = tts
        self._acoustic_provider = acoustic_provider

    def build(self) -> VoicePerceptionRuntime:
        self._configuration.validate()
        if self._conversation is not None and self._conversation_runtime is not None:
            raise ValidationError("Configure one Voice Conversation integration path.")
        journal = SQLiteVoiceJournal(
            self._data_dir.resolve(self._configuration.persistence_relative_path)
        )
        try:
            stt = self._stt or FasterWhisperSpeechToTextAdapter(
                _manifest("faster_whisper_adapter", "faster_whisper", "stt"), self._data_dir
            )
            tts = self._tts or PiperTextToSpeechAdapter(
                _manifest("piper_tts_adapter", "piper", "tts"),
                self._data_dir,
                self._tts_execution,
            )
            vad = _build_vad(self._configuration, self._frame_classifier)
            acoustic = (
                self._acoustic_provider or LocalDSPAcousticFeatureProvider()
                if self._configuration.perception_enabled
                else None
            )
            health = self._derive_health(journal, stt, tts, vad, acoustic)
            conversation = self._conversation
            wiring = conversation_wiring_health(
                self._conversation_runtime,
                self._conversation_context,
                self._configuration.conversation_target_agent_id,
            )
            if wiring.supported:
                target = self._configuration.conversation_target_agent_id
                assert self._conversation_runtime is not None
                assert self._conversation_context is not None
                assert target is not None
                conversation = LocalConversationHandoff(
                    self._conversation_runtime,
                    self._conversation_context,
                    target,
                )
            realtime = None
            if self._microphone is not None and self._output is not None:
                realtime = RealtimeVoiceRuntime(
                    microphone=self._microphone,
                    output=self._output,
                    speech=_LocalSpeechBoundary(stt, tts),
                    conversation=conversation or _UnavailableConversation(),
                    perception=_LocalPerceptionHandoff(acoustic) if acoustic is not None else None,
                    journal=journal,
                    frontend_events=self._frontend_events,
                    vad=vad,
                )
            return VoicePerceptionRuntime(
                configuration=self._configuration,
                journal=journal,
                realtime=realtime,
                conversation_handoff=(
                    conversation if isinstance(conversation, LocalConversationHandoff) else None
                ),
                health=health,
            )
        except Exception:
            # SQLiteVoiceJournal owns no long-lived connection. This boundary is
            # retained so future opened resources have one deterministic unwind path.
            raise

    def _derive_health(
        self,
        journal: SQLiteVoiceJournal,
        stt: SpeechToTextPort,
        tts: TextToSpeechPort,
        vad: WebRTCVADProvider | None,
        acoustic: AcousticFeatureProvider | None,
    ) -> VoicePerceptionHealthSnapshot:
        persistence_raw = journal.health()
        persistence_levels = {
            "available": CapabilityLevel.SUPPORTED,
            "corrupt": CapabilityLevel.CORRUPT,
            "schema_mismatch": CapabilityLevel.SCHEMA_MISMATCH,
            "migration_mismatch": CapabilityLevel.MIGRATION_MISMATCH,
            "unavailable": CapabilityLevel.UNAVAILABLE,
        }
        persistence = ComponentHealth(
            persistence_levels[persistence_raw.state.value],
            (("schema_version", persistence_raw.schema_version),),
        )
        inputs = _safe_input_devices(self._microphone)
        outputs = _safe_output_devices(self._output)
        input_configured = self._configuration.input_device_reference is not None
        output_configured = self._configuration.output_device_reference is not None
        input_available = bool(
            input_configured and self._configuration.input_device_reference in inputs
        )
        output_available = bool(
            output_configured and self._configuration.output_device_reference in outputs
        )
        audio_input = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if input_available
            else (
                CapabilityLevel.UNAVAILABLE if input_configured else CapabilityLevel.NOT_CONFIGURED
            ),
            (("configured", input_configured), ("device_available", input_available)),
        )
        playback = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if output_available
            else (
                CapabilityLevel.UNAVAILABLE if output_configured else CapabilityLevel.NOT_CONFIGURED
            ),
            (("configured", output_configured), ("device_available", output_available)),
        )
        vad_supported = vad is not None and vad.health().get("status") == "ready"
        vad_health = ComponentHealth(
            CapabilityLevel.SUPPORTED if vad_supported else CapabilityLevel.UNAVAILABLE
        )
        stt_raw = stt.health()
        model_available = _stt_model_available(self._data_dir, self._configuration.stt_model)
        stt_supported = stt_raw.status == "available" and model_available
        stt_health = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if stt_supported
            else (
                CapabilityLevel.DEGRADED
                if stt_raw.status == "available"
                else CapabilityLevel.UNAVAILABLE
            ),
            (
                ("configured", self._configuration.stt_model is not None),
                ("provider_available", stt_raw.status == "available"),
                ("model_available", model_available),
            ),
        )
        tts_raw = tts.health()
        execution_available = self._tts_execution is not None
        tts_message = (tts_raw.message or "").lower()
        injected_tts_evidence = self._tts is not None and tts_raw.status in {
            "available",
            "degraded",
        }
        executable_available = injected_tts_evidence or "executable" not in tts_message
        tts_model_available = injected_tts_evidence or _tts_model_available(
            self._data_dir, self._configuration.tts_model
        )
        tts_level = (
            CapabilityLevel.SUPPORTED
            if tts_raw.status == "available" and execution_available
            else CapabilityLevel.DEGRADED
            if tts_raw.status in {"available", "degraded"}
            else CapabilityLevel.UNAVAILABLE
        )
        tts_health = ComponentHealth(
            tts_level,
            (
                ("provider_configured", self._configuration.tts_provider == "piper"),
                ("model_configured", self._configuration.tts_model is not None),
                ("executable_available", executable_available),
                ("model_available", tts_model_available),
                ("execution_boundary_available", True),
                ("execution_authority_available", execution_available),
                (
                    "operational_execution_available",
                    tts_level is CapabilityLevel.SUPPORTED,
                ),
                ("default_voice_preference", self._configuration.default_voice),
            ),
        )
        perception_supported = (
            acoustic is not None and acoustic.health().get("status") == "supported"
        )
        perception = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if perception_supported
            else (
                CapabilityLevel.UNAVAILABLE
                if self._configuration.perception_enabled
                else CapabilityLevel.NOT_CONFIGURED
            ),
            (
                ("acoustic_supported", perception_supported),
                ("pitch_supported", perception_supported),
                ("pause_analysis_supported", perception_supported),
                ("speech_rate_supported", perception_supported),
                ("visual_capabilities", "not_configured"),
            ),
        )
        frontend = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if self._frontend_events is not None
            else CapabilityLevel.NOT_CONFIGURED,
            (("contract_available", True), ("sink_connected", self._frontend_events is not None)),
        )
        wiring = conversation_wiring_health(
            self._conversation_runtime,
            self._conversation_context,
            self._configuration.conversation_target_agent_id,
        )
        conversation = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if wiring.supported
            else (
                CapabilityLevel.NOT_CONFIGURED
                if not wiring.target_configured
                else CapabilityLevel.UNAVAILABLE
            ),
            (
                ("contract_available", wiring.contract_available),
                ("runtime_available", wiring.runtime_available),
                ("target_configured", wiring.target_configured),
                ("target_available", wiring.target_available),
                ("request_path_available", wiring.request_path_available),
                ("response_path_available", wiring.response_path_available),
            ),
        )
        voice_input_supported = (
            persistence.level is CapabilityLevel.SUPPORTED and input_available and vad_supported
        )
        stt_path_supported = voice_input_supported and stt_supported
        conversation_path_supported = stt_path_supported and wiring.supported
        speech_output_supported = output_available and tts_level is CapabilityLevel.SUPPORTED
        full_duplex_level = (
            CapabilityLevel.SUPPORTED
            if conversation_path_supported and speech_output_supported
            else CapabilityLevel.DEGRADED
            if conversation_path_supported
            else CapabilityLevel.UNAVAILABLE
        )
        voice_input = ComponentHealth(
            CapabilityLevel.SUPPORTED if voice_input_supported else CapabilityLevel.UNAVAILABLE
        )
        speech_to_text = ComponentHealth(
            CapabilityLevel.SUPPORTED if stt_path_supported else CapabilityLevel.UNAVAILABLE
        )
        voice_conversation = ComponentHealth(
            CapabilityLevel.SUPPORTED
            if conversation_path_supported
            else CapabilityLevel.UNAVAILABLE
        )
        speech_output = ComponentHealth(
            CapabilityLevel.SUPPORTED if speech_output_supported else CapabilityLevel.UNAVAILABLE
        )
        tts_external_blocker = not execution_available
        completion = (
            ("voice_input", _complete_if(voice_input_supported)),
            ("speech_to_text", _complete_if(stt_path_supported)),
            (
                "acoustic_perception",
                (
                    OperationalCompletion.INTERNALLY_COMPLETE
                    if perception_supported
                    else OperationalCompletion.INTENTIONALLY_UNAVAILABLE
                    if not self._configuration.perception_enabled
                    else OperationalCompletion.INCOMPLETE
                ),
            ),
            ("voice_conversation", _complete_if(conversation_path_supported)),
            (
                "speech_output",
                (
                    OperationalCompletion.INTERNALLY_COMPLETE
                    if speech_output_supported
                    else OperationalCompletion.EXTERNALLY_BLOCKED
                    if tts_external_blocker
                    else OperationalCompletion.INCOMPLETE
                ),
            ),
            ("visual_perception", OperationalCompletion.INTENTIONALLY_UNAVAILABLE),
            (
                "full_duplex_voice",
                (
                    OperationalCompletion.INTERNALLY_COMPLETE
                    if full_duplex_level is CapabilityLevel.SUPPORTED
                    else OperationalCompletion.EXTERNALLY_BLOCKED
                    if conversation_path_supported and tts_external_blocker
                    else OperationalCompletion.INCOMPLETE
                ),
            ),
        )
        return VoicePerceptionHealthSnapshot(
            persistence,
            audio_input,
            vad_health,
            stt_health,
            conversation,
            perception,
            tts_health,
            playback,
            frontend,
            voice_input,
            speech_to_text,
            voice_conversation,
            speech_output,
            ComponentHealth(full_duplex_level),
            ComponentHealth(full_duplex_level),
            completion,
            datetime.now(UTC).isoformat(),
        )


def _build_vad(
    configuration: VoicePerceptionConfiguration,
    classifier: FrameClassifier | None,
) -> WebRTCVADProvider | None:
    try:
        return WebRTCVADProvider(
            VADConfig(
                aggressiveness=configuration.vad_aggressiveness,
                frame_duration_ms=configuration.frame_duration_ms,
            ),
            classifier,
        )
    except ValidationError:
        return None


def _safe_input_devices(port: MicrophoneInputPort | None) -> tuple[str, ...]:
    if port is None:
        return ()
    try:
        return port.list_input_devices()
    except Exception:
        return ()


def _safe_output_devices(port: AudioOutputPort | None) -> tuple[str, ...]:
    if port is None:
        return ()
    try:
        return port.list_output_devices()
    except Exception:
        return ()


def _stt_model_available(data_dir: DataDir, model: str | None) -> bool:
    if model is None:
        return False
    root = data_dir.resolve("voice/models/faster-whisper")
    candidates = (
        root / model,
        root / f"faster-whisper-{model}",
        root / f"models--Systran--faster-whisper-{model}",
    )
    return any(path.exists() for path in candidates)


def _tts_model_available(data_dir: DataDir, model: str | None) -> bool:
    if model is None:
        return False
    path = Path(model).expanduser()
    if not path.is_absolute():
        path = data_dir.resolve(f"voice/models/piper/{model}")
    return path.is_file()


def _manifest(adapter_id: str, provider_id: str, adapter_type: str) -> SpeechAdapterManifest:
    return SpeechAdapterManifest(
        adapter_id=adapter_id,
        provider_id=provider_id,
        adapter_type=adapter_type,
        name=provider_id,
        description="Local Voice composition adapter.",
        version="1.0.0",
        supported_languages=["pt-BR"],
        supports_streaming=False,
        supports_file_input=adapter_type == "stt",
        supports_realtime=False,
        requires_gpu=False,
        requires_network=False,
        metadata={"mock": False},
    )


def _pcm_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return output.getvalue()


def _feature_id(request: VoicePerceptionRequest, feature_name: str) -> str:
    identity = f"{request.request_id}:{request.audio_checksum_reference}:{feature_name}"
    return f"perception-artifact-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"


def _complete_if(value: bool) -> OperationalCompletion:
    return OperationalCompletion.INTERNALLY_COMPLETE if value else OperationalCompletion.INCOMPLETE
