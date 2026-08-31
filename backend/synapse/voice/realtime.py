from __future__ import annotations

import base64
import hashlib
import io
import wave
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from synapse.audio.models import AudioInputRequest, AudioOutputRequest, TextToSpeechResult
from synapse.audio.realtime_devices import (
    AudioOutputPort,
    MicrophoneInputPort,
    PCMInputStream,
    PlaybackRequest,
    PlaybackResult,
)
from synapse.conversations.voice_contracts import (
    AcceptedConversationResponse,
    ConversationResponseReference,
    PerceptionAvailability,
    ResponseDisposition,
    VoiceConversationRequest,
)
from synapse.core.exceptions import ValidationError
from synapse.perception.models import PerceptionResultBundle, VoicePerceptionRequest
from synapse.voice.frontend_events import (
    VoiceFrontendEventSink,
    VoiceFrontendEventType,
    make_voice_frontend_event,
)
from synapse.voice.persistence_models import VoiceRecordDraft, VoiceReplay
from synapse.voice.vad import VADConfig, WebRTCVADProvider


class RealtimeVoiceState(StrEnum):
    WAITING = "waiting"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    UTTERANCE_FINALIZING = "utterance_finalizing"
    TRANSCRIPTION_PENDING = "transcription_pending"
    WAITING_FOR_RESPONSE = "waiting_for_response"
    SYNTHESIS_PENDING = "synthesis_pending"
    SYSTEM_SPEAKING = "system_speaking"
    INTERRUPTION_PENDING = "interruption_pending"
    CANCELLATION_PENDING = "cancellation_pending"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    ERROR = "error"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class RealtimeVoiceConfig:
    input_device_reference: str
    output_device_reference: str
    sample_rate: int = 16_000
    frame_duration_ms: int = 20
    vad_aggressiveness: int = 2
    minimum_speech_ms: int = 200
    end_silence_ms: int = 400
    language: str = "pt-BR"
    stt_provider_id: str = "faster_whisper"
    stt_model: str = "tiny"
    tts_provider_id: str = "piper"
    tts_voice_id: str | None = None
    conversation_reference: str | None = None
    purpose: str | None = None
    perception_requested: bool = True
    persist_transcript_content: bool = False
    response_timeout_ms: int = 30_000


@dataclass(frozen=True, slots=True)
class RealtimeVoiceFact:
    sequence: int
    kind: str
    state: RealtimeVoiceState
    correlation_reference: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapturedUtterance:
    utterance_id: str
    session_id: str
    correlation_reference: str
    input_device_reference: str
    started_frame: int
    ended_frame: int
    duration_ms: int
    pcm_reference: str
    pcm_checksum: str
    occurrence_started_at: str
    occurrence_ended_at: str
    pcm_bytes: bytes = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class TranscriptionFact:
    transcription_id: str
    utterance_id: str
    correlation_reference: str
    provider_id: str
    model: str
    language: str | None
    text: str
    duration_ms: int | None
    confidence: float | None
    checksum: str
    provenance: str


ConversationRequest = VoiceConversationRequest
ConversationResponse = ConversationResponseReference


class RealtimeSpeechPort(Protocol):
    def adapter_health(self, adapter_id: str): ...

    def transcribe(self, request: AudioInputRequest): ...

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult: ...


class ConversationHandoffPort(Protocol):
    def submit(self, request: ConversationRequest) -> ConversationResponse | None: ...


class PerceptionHandoffPort(Protocol):
    def analyze_transient(
        self, request: VoicePerceptionRequest, pcm_bytes: bytes, sample_rate: int
    ) -> PerceptionResultBundle: ...


class VoiceIntegrationJournal(Protocol):
    def append(
        self, draft: VoiceRecordDraft, *, expected_revision: int | None = None
    ): ...

    def replay(self, stream_id: str) -> VoiceReplay: ...


class RealtimeVoiceRuntime:
    def __init__(
        self,
        *,
        microphone: MicrophoneInputPort,
        output: AudioOutputPort,
        speech: RealtimeSpeechPort,
        conversation: ConversationHandoffPort,
        perception: PerceptionHandoffPort | None = None,
        journal: VoiceIntegrationJournal | None = None,
        frontend_events: VoiceFrontendEventSink | None = None,
        vad: WebRTCVADProvider | None = None,
    ) -> None:
        self._microphone = microphone
        self._output = output
        self._speech = speech
        self._conversation = conversation
        self._perception = perception
        self._journal = journal
        self._frontend_events = frontend_events
        self._vad = vad
        self._stream: PCMInputStream | None = None
        self._session_id: str | None = None
        self._actor_reference: str | None = None
        self._config: RealtimeVoiceConfig | None = None
        self._state = RealtimeVoiceState.WAITING
        self._facts: list[RealtimeVoiceFact] = []
        self._frames: list[bytes] = []
        self._utterance_start_frame = 0
        self._utterance_sequence = 0
        self._frontend_revision = 0
        self._current_utterance_id: str | None = None
        self._pending_request: ConversationRequest | None = None
        self._request_history: list[ConversationRequest] = []
        self._accepted_responses: dict[str, AcceptedConversationResponse] = {}
        self._perception_bundles: dict[str, PerceptionResultBundle] = {}
        self._superseded_request_ids: set[str] = set()
        self._active_playback: PlaybackResult | None = None
        self._cancel_requested = False

    @property
    def state(self) -> RealtimeVoiceState:
        return self._state

    def facts(self) -> tuple[RealtimeVoiceFact, ...]:
        return tuple(self._facts)

    def pending_request(self) -> ConversationRequest | None:
        return self._pending_request

    def accepted_response(self, response_id: str) -> AcceptedConversationResponse | None:
        return self._accepted_responses.get(response_id)

    def publish_capability_status(self) -> dict[str, object]:
        report = self.capability_report()
        status = str(report["real_time_voice"])
        event_type = (
            VoiceFrontendEventType.UNAVAILABLE
            if status == "unavailable"
            else VoiceFrontendEventType.IDLE
        )
        unavailable = tuple(
            name
            for name in (
                "input_device_available",
                "output_device_available",
                "vad_supported",
                "tts_execution_boundary_available",
            )
            if report.get(name) is False
        )
        self._publish_frontend_event(
            event_type,
            causal_revision=len(self._facts),
            metadata={
                "capability_status": status,
                "unavailable_capabilities": unavailable,
            },
        )
        return report

    def start(
        self,
        session_id: str,
        actor_reference: str,
        config: RealtimeVoiceConfig,
    ) -> None:
        if self._stream is not None:
            raise ValidationError("Real-time Voice is already active.")
        if config.input_device_reference not in self._microphone.list_input_devices():
            raise ValidationError("Configured microphone input device is unavailable.")
        if config.output_device_reference not in self._output.list_output_devices():
            raise ValidationError("Configured audio output device is unavailable.")
        self._session_id = session_id
        self._actor_reference = actor_reference
        self._config = config
        self._vad = self._vad or WebRTCVADProvider(
            VADConfig(
                aggressiveness=config.vad_aggressiveness,
                frame_duration_ms=config.frame_duration_ms,
                min_speech_duration_ms=config.minimum_speech_ms,
                min_silence_duration_ms=config.end_silence_ms,
            )
        )
        self._stream = self._microphone.open_stream(
            config.input_device_reference,
            sample_rate=config.sample_rate,
            frame_duration_ms=config.frame_duration_ms,
        )
        self._transition(RealtimeVoiceState.LISTENING, "microphone.opened")

    def process_next_frame(self) -> CapturedUtterance | None:
        stream, config, session_id = self._active()
        vad = self._vad
        if vad is None:
            raise ValidationError("VAD is unavailable.")
        try:
            frame = stream.read_frame()
            event = vad.process_frame(frame, config.sample_rate)
        except Exception as exc:
            self._transition(RealtimeVoiceState.ERROR, "microphone.error", error=str(exc))
            self.close()
            raise
        if (
            self._active_playback
            and self._active_playback.started
            and not self._active_playback.completed
        ):
            if event.type == "speech_started":
                self._transition(
                    RealtimeVoiceState.INTERRUPTION_PENDING,
                    "barge_in.detected",
                    playback_id=self._active_playback.playback_id,
                )
                stopped = self._output.request_stop(self._active_playback.playback_id)
                self._active_playback = stopped
                self._append(
                    "playback.stop_observed",
                    stop_requested=stopped.stop_requested,
                    stop_confirmed=stopped.stop_confirmed,
                    error=stopped.error,
                )
                if not stopped.stop_confirmed:
                    return None
                self._transition(RealtimeVoiceState.USER_SPEAKING, "speech.started")
                self._frames = [frame]
                self._utterance_start_frame = event.frame_start
            return None
        if event.type == "speech_started":
            self._frames = [frame]
            self._utterance_start_frame = event.frame_start
            self._transition(RealtimeVoiceState.USER_SPEAKING, "speech.started")
        elif event.type == "speech_continued" and self._frames:
            self._frames.append(frame)
            self._append("speech.active", frame=event.frame_end)
        elif event.type in {"speech_ended", "max_duration_reached"} and self._frames:
            self._frames.append(frame)
            self._transition(RealtimeVoiceState.UTTERANCE_FINALIZING, "speech.ended")
            utterance = self._finalize_utterance(session_id, event.frame_end)
            self._dispatch_utterance(utterance)
            return utterance
        else:
            self._append("silence", frame=event.frame_end)
        return None

    def receive_response(self, response: ConversationResponse) -> AcceptedConversationResponse:
        existing = self._accepted_responses.get(response.response_id)
        if existing:
            if existing.response != response:
                raise ValidationError("Contradictory conversation response identity.")
            return replace(existing, disposition=ResponseDisposition.DUPLICATE)
        if response.request_id in self._superseded_request_ids:
            raise ValidationError("Stale conversation response cannot assume the current turn.")
        request = self._pending_request
        if request is None:
            raise ValidationError("No conversation response is pending.")
        deadline = datetime.fromisoformat(request.response_deadline_at.replace("Z", "+00:00"))
        if datetime.now(UTC) > deadline:
            raise ValidationError("Late conversation response cannot assume the current turn.")
        if self._state in {RealtimeVoiceState.CLOSED, RealtimeVoiceState.CANCELLATION_PENDING}:
            raise ValidationError("Late response cannot reopen a terminal or cancelling session.")
        if (
            response.request_id != request.request_id
            or response.voice_session_id != request.voice_session_id
            or response.utterance_id != request.utterance_id
            or response.transcription_id != request.transcription_id
            or response.conversation_turn_id != request.conversation_turn_id
            or response.correlation_reference != request.correlation_reference
        ):
            raise ValidationError("Conversation response correspondence mismatch.")
        accepted = AcceptedConversationResponse(
            response=response,
            disposition=ResponseDisposition.ACCEPTED,
            accepted_at=datetime.now(UTC).isoformat(),
        )
        self._accepted_responses[response.response_id] = accepted
        self._pending_request = None
        self._append(
            "response.accepted",
            response_id=response.response_id,
            response=asdict(response),
            accepted_at=accepted.accepted_at,
        )
        return accepted

    def restore_pending(
        self,
        session_id: str,
        actor_reference: str,
        config: RealtimeVoiceConfig,
    ) -> None:
        if self._journal is None:
            raise ValidationError("Voice integration journal is not configured.")
        replay = self._journal.replay(f"realtime:{session_id}")
        self._session_id = session_id
        self._actor_reference = actor_reference
        self._config = config
        pending: ConversationRequest | None = None
        accepted: dict[str, AcceptedConversationResponse] = {}
        history: list[ConversationRequest] = []
        for record in replay.records:
            if record.fact_type == "conversation.requested" and "request" in record.payload:
                raw = dict(record.payload["request"])
                raw["provenance"] = tuple(raw.get("provenance", []))
                raw["perception_status"] = PerceptionAvailability(raw["perception_status"])
                pending = ConversationRequest(**raw)
                history.append(pending)
            elif record.fact_type == "conversation.request_superseded":
                self._superseded_request_ids.add(str(record.payload["request_id"]))
            elif record.fact_type == "response.accepted" and "response" in record.payload:
                raw_response = dict(record.payload["response"])
                raw_response["provenance"] = tuple(raw_response.get("provenance", []))
                response = ConversationResponse(**raw_response)
                accepted[response.response_id] = AcceptedConversationResponse(
                    response,
                    ResponseDisposition.ACCEPTED,
                    str(record.payload["accepted_at"]),
                )
                if pending and pending.request_id == response.request_id:
                    pending = None
        self._pending_request = pending
        self._request_history = history
        self._accepted_responses = accepted
        self._state = RealtimeVoiceState.RECONCILIATION_REQUIRED
        self._publish_frontend_event(
            VoiceFrontendEventType.RECONCILIATION_REQUIRED,
            causal_revision=len(replay.records),
            metadata={"external_state_known": False},
        )

    def receive_perception_bundle(
        self, request_id: str, bundle: PerceptionResultBundle
    ) -> None:
        request = next((item for item in self._request_history if item.request_id == request_id), None)
        if request is None:
            raise ValidationError("Perception bundle request identity is unknown.")
        if (
            bundle.voice_session_id != request.voice_session_id
            or bundle.utterance_id != request.utterance_id
            or bundle.transcription_id != request.transcription_id
            or bundle.correlation_reference != request.correlation_reference
        ):
            raise ValidationError("Perception bundle correspondence mismatch.")
        existing = self._perception_bundles.get(request_id)
        if existing and existing.fingerprint != bundle.fingerprint:
            raise ValidationError("Contradictory perception bundle for request.")
        self._perception_bundles[request_id] = bundle
        self._append(
            "perception.bundle_received_late"
            if request is not self._pending_request
            else "perception.bundle_received",
            request_id=request_id,
            bundle_id=bundle.bundle_id,
            fingerprint=bundle.fingerprint,
        )

    def synthesize_response(self, response_id: str) -> PlaybackResult:
        accepted = self._accepted_responses.get(response_id)
        if accepted is None:
            raise ValidationError("Conversation response has not been accepted.")
        response = accepted.response
        request = next(
            (item for item in self._request_history if item.request_id == response.request_id),
            None,
        )
        if request is None:
            raise ValidationError("Accepted response request history is unavailable.")
        config = self._require_config()
        self._transition(RealtimeVoiceState.SYNTHESIS_PENDING, "synthesis.requested")
        synthesis = self._speech.synthesize(
            AudioOutputRequest(
                session_id=request.voice_session_id,
                text=response.text,
                provider_id=config.tts_provider_id,
                voice_id=config.tts_voice_id,
                language=config.language,
                metadata={"response_reference": response.response_reference},
            )
        )
        if not synthesis.audio_base64:
            self._transition(RealtimeVoiceState.ERROR, "synthesis.output_unavailable")
            raise ValidationError("Synthesis did not produce playable audio.")
        wav_bytes = base64.b64decode(synthesis.audio_base64)
        playback_id = (
            f"playback-{hashlib.sha256(response.response_reference.encode()).hexdigest()[:24]}"
        )
        playback = self._output.play(
            PlaybackRequest(
                playback_id=playback_id,
                session_id=request.voice_session_id,
                correlation_reference=request.correlation_reference,
                output_device_reference=config.output_device_reference,
                audio_reference=synthesis.output_ref,
                wav_bytes=wav_bytes,
            )
        )
        self._active_playback = playback
        if playback.error or not playback.started:
            self._transition(RealtimeVoiceState.ERROR, "playback.failed", error=playback.error)
        elif playback.completed:
            self._transition(RealtimeVoiceState.LISTENING, "playback.completed")
        else:
            self._transition(RealtimeVoiceState.SYSTEM_SPEAKING, "playback.started")
        return playback

    def complete_playback(self, playback_id: str) -> None:
        if self._active_playback is None or self._active_playback.playback_id != playback_id:
            raise ValidationError("Playback correspondence mismatch.")
        self._active_playback = replace(self._active_playback, completed=True)
        self._transition(RealtimeVoiceState.LISTENING, "playback.completed")

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self._transition(RealtimeVoiceState.CANCELLATION_PENDING, "cancellation.requested")
        if self._active_playback and self._active_playback.started:
            stopped = self._output.request_stop(self._active_playback.playback_id)
            self._active_playback = stopped
            self._append(
                "cancellation.playback_stop_observed",
                stop_confirmed=stopped.stop_confirmed,
            )

    def confirm_cancelled(self) -> None:
        if not self._cancel_requested:
            raise ValidationError("Cancellation was not requested.")
        self.close()

    def close(self) -> None:
        previous_state = self._state
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._state is not RealtimeVoiceState.CLOSED:
            self._transition(
                RealtimeVoiceState.CLOSED,
                "microphone.closed",
                closed_from=previous_state,
            )

    def restart_observed(self) -> None:
        self._stream = None
        self._active_playback = None
        self._frames.clear()
        self._transition(
            RealtimeVoiceState.RECONCILIATION_REQUIRED,
            "restart.external_state_unknown",
        )

    def capability_report(self) -> dict[str, object]:
        inputs = self._microphone.list_input_devices()
        outputs = self._output.list_output_devices()
        vad_supported = bool((self._vad or WebRTCVADProvider()).health()["status"] == "ready")
        tts_boundary = False
        try:
            tts_boundary = self._speech.adapter_health("piper_tts_adapter").status == "available"
        except Exception:
            tts_boundary = False
        overall = (
            "supported" if inputs and outputs and vad_supported and tts_boundary else "degraded"
        )
        if not inputs or not outputs or not vad_supported:
            overall = "unavailable"
        return {
            "input_device_available": bool(inputs),
            "output_device_available": bool(outputs),
            "vad_supported": vad_supported,
            "stt_configured": True,
            "stt_local_only": True,
            "tts_configured": True,
            "tts_execution_boundary_available": tts_boundary,
            "playback_supported": bool(outputs),
            "barge_in_supported": bool(self._output.capabilities().get("interruption")),
            "real_time_voice": overall,
        }

    def _finalize_utterance(self, session_id: str, ended_frame: int) -> CapturedUtterance:
        config = self._require_config()
        pcm = b"".join(self._frames)
        checksum = hashlib.sha256(pcm).hexdigest()
        self._utterance_sequence += 1
        identity = hashlib.sha256(
            f"{session_id}:{self._utterance_sequence}:{checksum}".encode()
        ).hexdigest()
        utterance_id = f"utterance-{identity[:24]}"
        ended_at = datetime.now(UTC)
        started_at = ended_at - timedelta(milliseconds=len(self._frames) * config.frame_duration_ms)
        utterance = CapturedUtterance(
            utterance_id=utterance_id,
            session_id=session_id,
            correlation_reference=f"voice-session://{session_id}",
            input_device_reference=config.input_device_reference,
            started_frame=self._utterance_start_frame,
            ended_frame=ended_frame,
            duration_ms=len(self._frames) * config.frame_duration_ms,
            pcm_reference=f"transient://voice-pcm/{utterance_id}",
            pcm_checksum=checksum,
            occurrence_started_at=started_at.isoformat(),
            occurrence_ended_at=ended_at.isoformat(),
            pcm_bytes=pcm,
        )
        self._current_utterance_id = utterance_id
        self._frames = []
        self._append(
            "utterance.finalized",
            utterance_id=utterance_id,
            duration_ms=utterance.duration_ms,
            pcm_checksum=checksum,
        )
        return utterance

    def _dispatch_utterance(self, utterance: CapturedUtterance) -> None:
        config = self._require_config()
        self._transition(RealtimeVoiceState.TRANSCRIPTION_PENDING, "transcription.requested")
        wav_bytes = _pcm_wav(utterance.pcm_bytes, config.sample_rate)
        try:
            result = self._speech.transcribe(
                AudioInputRequest(
                    session_id=utterance.session_id,
                    provider_id=config.stt_provider_id,
                    language=config.language,
                    model=config.stt_model,
                    audio_base64=base64.b64encode(wav_bytes).decode("ascii"),
                    audio_format="audio/wav",
                    duration_ms=utterance.duration_ms,
                    metadata={
                        "utterance_id": utterance.utterance_id,
                        "pcm_checksum": utterance.pcm_checksum,
                    },
                )
            )
        except Exception as exc:
            self._transition(RealtimeVoiceState.ERROR, "transcription.failed", error=str(exc))
            raise
        if not result.text.strip() or result.status != "success":
            self._transition(RealtimeVoiceState.ERROR, "transcription.no_speech")
            raise ValidationError("STT did not produce a valid transcription.")
        transcript_checksum = hashlib.sha256(result.text.encode()).hexdigest()
        transcription_id = f"transcription-{transcript_checksum[:24]}"
        self._append(
            "transcription.received",
            transcription_id=transcription_id,
            utterance_id=utterance.utterance_id,
            provider_id=result.provider_id,
            model=config.stt_model,
            checksum=transcript_checksum,
        )
        request_id = f"conversation-{hashlib.sha256((utterance.utterance_id + transcription_id).encode()).hexdigest()[:24]}"
        perception_status = (
            PerceptionAvailability.PENDING
            if config.perception_requested
            else PerceptionAvailability.NOT_REQUESTED
        )
        perception_bundle: PerceptionResultBundle | None = None
        if config.perception_requested and self._perception is not None:
            perception_request = VoicePerceptionRequest(
                request_id=f"perception-{request_id}",
                voice_session_id=utterance.session_id,
                utterance_id=utterance.utterance_id,
                transcription_id=transcription_id,
                audio_checksum_reference=f"sha256:{utterance.pcm_checksum}",
                correlation_reference=utterance.correlation_reference,
                occurrence_started_at=utterance.occurrence_started_at,
                occurrence_ended_at=utterance.occurrence_ended_at,
                actor_reference=self._actor_reference or "",
                transcript_reference=f"voice-transcript://{transcription_id}",
                provenance=("voice.realtime", f"stt:{result.provider_id or 'unknown'}"),
            )
            try:
                perception_bundle = self._perception.analyze_transient(
                    perception_request, utterance.pcm_bytes, config.sample_rate
                )
                perception_status = PerceptionAvailability(perception_bundle.status.value)
            except Exception as exc:
                perception_status = PerceptionAvailability.UNAVAILABLE
                self._append("perception.unavailable", error_type=type(exc).__name__)
        elif config.perception_requested:
            perception_status = PerceptionAvailability.UNAVAILABLE
        if self._pending_request is not None:
            self._superseded_request_ids.add(self._pending_request.request_id)
            self._append(
                "conversation.request_superseded",
                request_id=self._pending_request.request_id,
                superseded_by=request_id,
            )
        request = ConversationRequest(
            request_id=request_id,
            conversation_reference=config.conversation_reference,
            conversation_turn_id=f"voice-turn-{utterance.utterance_id}",
            voice_session_id=utterance.session_id,
            utterance_id=utterance.utterance_id,
            transcription_id=transcription_id,
            transcript_reference=f"voice-transcript://{transcription_id}",
            actor_reference=self._actor_reference or "",
            correlation_reference=utterance.correlation_reference,
            occurrence_started_at=utterance.occurrence_started_at,
            occurrence_ended_at=utterance.occurrence_ended_at,
            response_deadline_at=(
                datetime.now(UTC) + timedelta(milliseconds=config.response_timeout_ms)
            ).isoformat(),
            provenance=("voice.realtime", f"stt:{result.provider_id or 'unknown'}"),
            perception_status=perception_status,
            perception_bundle_reference=(
                f"perception-bundle://{perception_bundle.bundle_id}"
                if perception_bundle
                else None
            ),
            perception_bundle_fingerprint=(perception_bundle.fingerprint if perception_bundle else None),
            transcript_content=result.text if config.persist_transcript_content else None,
            purpose=config.purpose,
        )
        self._pending_request = request
        self._request_history.append(request)
        if perception_bundle:
            self._perception_bundles[request_id] = perception_bundle
        self._transition(
            RealtimeVoiceState.WAITING_FOR_RESPONSE,
            "conversation.requested",
            request_id=request.request_id,
            utterance_id=request.utterance_id,
            perception_status=request.perception_status,
            request=asdict(request),
        )
        response = self._conversation.submit(request)
        if response is not None:
            self.receive_response(response)

    def _active(self) -> tuple[PCMInputStream, RealtimeVoiceConfig, str]:
        if self._stream is None or self._session_id is None:
            raise ValidationError("Real-time Voice microphone is not active.")
        return self._stream, self._require_config(), self._session_id

    def _require_config(self) -> RealtimeVoiceConfig:
        if self._config is None:
            raise ValidationError("Real-time Voice is not configured.")
        return self._config

    def _transition(self, state: RealtimeVoiceState, kind: str, **metadata: object) -> None:
        self._state = state
        self._append(kind, **metadata)

    def _append(self, kind: str, **metadata: object) -> None:
        correlation = (
            f"voice-session://{self._session_id}" if self._session_id else "voice-session://unknown"
        )
        self._facts.append(
            RealtimeVoiceFact(len(self._facts) + 1, kind, self._state, correlation, metadata)
        )
        self._publish_frontend_for_fact(kind, len(self._facts), metadata)
        if self._journal is not None and self._session_id is not None:
            stream_id = f"realtime:{self._session_id}"
            replay = self._journal.replay(stream_id)
            lineage = (replay.records[-1].fingerprint,) if replay.records else ()
            revision = len(replay.records) + 1
            self._journal.append(
                VoiceRecordDraft(
                    stream_id=stream_id,
                    fact_type=kind,
                    revision=revision,
                    payload={key: value for key, value in metadata.items()},
                    idempotency_key=f"{stream_id}:{revision}:{kind}",
                    lineage=lineage,
                ),
                expected_revision=revision - 1,
            )

    def _publish_frontend_for_fact(
        self, kind: str, causal_revision: int, metadata: dict[str, object]
    ) -> None:
        direct = {
            "microphone.opened": VoiceFrontendEventType.LISTENING,
            "speech.started": VoiceFrontendEventType.SPEECH_STARTED,
            "speech.ended": VoiceFrontendEventType.SPEECH_ENDED,
            "transcription.requested": VoiceFrontendEventType.PROCESSING,
            "conversation.requested": VoiceFrontendEventType.PROCESSING,
            "response.accepted": VoiceFrontendEventType.PROCESSING,
            "synthesis.requested": VoiceFrontendEventType.PROCESSING,
            "playback.started": VoiceFrontendEventType.SPEAKING_STARTED,
            "playback.completed": VoiceFrontendEventType.SPEAKING_ENDED,
            "barge_in.detected": VoiceFrontendEventType.INTERRUPTION_DETECTED,
            "cancellation.requested": VoiceFrontendEventType.CANCELLING,
            "restart.external_state_unknown": VoiceFrontendEventType.RECONCILIATION_REQUIRED,
        }
        if kind == "playback.stop_observed":
            if metadata.get("stop_requested") is True:
                self._publish_frontend_event(
                    VoiceFrontendEventType.INTERRUPTION_REQUESTED,
                    causal_revision=causal_revision,
                    metadata={"stop_requested": True},
                )
            if metadata.get("stop_confirmed") is True:
                self._publish_frontend_event(
                    VoiceFrontendEventType.INTERRUPTION_CONFIRMED,
                    causal_revision=causal_revision,
                    metadata={"stop_confirmed": True},
                )
            return
        event_type = direct.get(kind)
        if kind == "microphone.closed":
            if self._cancel_requested:
                event_type = VoiceFrontendEventType.CANCELLED
            elif metadata.get("closed_from") == RealtimeVoiceState.ERROR:
                event_type = VoiceFrontendEventType.ERROR
            else:
                event_type = VoiceFrontendEventType.IDLE
        if event_type is None and (
            kind.endswith(".failed")
            or kind.endswith(".error")
            or kind in {"transcription.no_speech", "synthesis.output_unavailable"}
        ):
            event_type = VoiceFrontendEventType.ERROR
        if event_type is None:
            return
        safe_metadata: dict[str, object] = {"phase": kind}
        for key in ("playback_id", "error_type", "capability_status"):
            if key in metadata:
                safe_metadata[key] = metadata[key]
        self._publish_frontend_event(
            event_type,
            causal_revision=causal_revision,
            metadata=safe_metadata,
        )

    def _publish_frontend_event(
        self,
        event_type: VoiceFrontendEventType,
        *,
        causal_revision: int,
        metadata: dict[str, object],
    ) -> None:
        if self._frontend_events is None or self._session_id is None:
            return
        self._frontend_revision += 1
        event = make_voice_frontend_event(
            voice_session_id=self._session_id,
            event_type=event_type,
            correlation_reference=f"voice-session://{self._session_id}",
            revision=self._frontend_revision,
            causal_revision=causal_revision,
            utterance_id=self._current_utterance_id,
            conversation_turn_reference=(
                self._pending_request.conversation_turn_id if self._pending_request else None
            ),
            metadata=metadata,
        )
        try:
            self._frontend_events.publish(event)
        except Exception:
            return


def _pcm_wav(pcm: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()
