from __future__ import annotations

import base64
import logging
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, payload_dict, runtime_from
from synapse.core.exceptions import ValidationError

router = APIRouter()


logger = logging.getLogger(__name__)


class AudioSessionCreatePayload(BaseModel):
    multimodal_session_id: str | None = None
    agent_id: str | None = None
    input_device_id: str | None = None
    output_device_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class AudioSynthesizePayload(BaseModel):
    session_id: str | None = None
    agent_id: str | None = None
    text: str
    provider_id: str | None = None
    voice_id: str | None = None
    language: str | None = None
    speed: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioTranscribePayload(BaseModel):
    audio_base64: str
    audio_format: str | None = None
    language: str | None = None
    provider_id: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    session_id: str | None = None
    multimodal_session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceConversationTurnPayload(BaseModel):
    audio_base64: str
    audio_format: str = "audio/webm"
    conversation_id: str | None = None
    agent_id: str | None = None
    language: str | None = None
    auto_respond: bool = True
    provider_id: str | None = None
    model: str | None = None
    model_provider_id: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceSessionCreatePayload(BaseModel):
    agent_id: str
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class VoiceQueuePayload(BaseModel):
    text: str
    provider_id: str | None = None
    priority: int = 100
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceSettingsPayload(BaseModel):
    provider_id: str | None = None
    stt_provider_id: str | None = None
    device_id: str | None = None
    language: str | None = None
    model: str | None = None
    tts_provider_id: str | None = None
    tts_voice_id: str | None = None
    tts_model: str | None = None
    default_tts_voice: str | None = None
    preferred_voice_gender: str | None = None
    provider_configuration_references: dict[str, str] | None = None
    tts_speed: float | None = None
    stt_model: str | None = None
    stt_device: str | None = None
    stt_compute_type: str | None = None
    input_device_id: str | None = None
    output_device_id: str | None = None
    voice_analysis_provider_id: str | None = None
    vad_provider_id: str | None = None
    vad_enabled: bool | None = None
    silence_threshold: float | None = None
    min_speech_duration_ms: int | None = None
    min_silence_duration_ms: int | None = None
    max_utterance_duration_ms: int | None = None
    recording_retention: str | None = None
    store_raw_audio: bool | None = None
    conversation_mode_defaults: dict[str, Any] | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceRecordingPayload(BaseModel):
    device_id: str | None = None
    provider_id: str | None = None
    language: str | None = None
    model: str | None = None
    audio_base64: str | None = None
    audio_format: str | None = None
    duration_ms: int | None = None
    transcript: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    recording_id: str | None = None


class VoiceTranscriptionPayload(BaseModel):
    transcript: str
    provider_id: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceRecordingStartPayload(BaseModel):
    session_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    audio_format: str = "audio/webm"
    recording_id: str | None = None


class VoiceRecordingChunkPayload(BaseModel):
    chunk_base64: str
    sequence: int
    idempotency_key: str
    expected_revision: int | None = None


class VoiceRecordingTurnPayload(BaseModel):
    recording_id: str
    idempotency_key: str


class VoiceCleanupPayload(BaseModel):
    dry_run: bool = False


class VoiceStudioProfilePayload(BaseModel):
    name: str
    audio_base64: str
    filename: str = "reference.wav"
    language: str = "pt-BR"
    ref_text: str = ""


class SpeechPipelineSessionCreatePayload(BaseModel):
    audio_session_id: str
    voice_session_id: str | None = None
    multimodal_session_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    pipeline_session_id: str | None = None


@router.post("/voice/sessions/{session_id}/cancel")
def cancel_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.cancel_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/recordings/start")
def start_voice_recording(
    payload: VoiceRecordingStartPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.start_recording(**payload_dict(payload)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/recordings/{recording_id}/chunks")
def append_voice_recording_chunk(
    recording_id: str,
    payload: VoiceRecordingChunkPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        chunk = base64.b64decode(payload.chunk_base64, validate=True)
        return asdict(
            runtime.voice.append_recording_chunk(
                recording_id,
                chunk,
                sequence=payload.sequence,
                idempotency_key=payload.idempotency_key,
                expected_revision=payload.expected_revision,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/recordings/{recording_id}/complete")
def complete_voice_recording(recording_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.complete_recording(recording_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/recordings/{recording_id}/cancel")
def cancel_voice_recording(recording_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.cancel_recording(recording_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/voice/recordings/{recording_id}")
def delete_voice_recording(recording_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.delete_recording(recording_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/messages/{recording_id}/complete")
def complete_voice_message(recording_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.complete_voice_message(recording_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/sessions/{session_id}/conversation/turn")
def run_voice_conversation_turn(
    session_id: str,
    payload: VoiceRecordingTurnPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.voice.run_conversation_turn(
                session_id,
                payload.recording_id,
                idempotency_key=payload.idempotency_key,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/retention/cleanup")
def cleanup_voice_storage(payload: VoiceCleanupPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.cleanup_voice_storage(dry_run=payload.dry_run))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/sessions")
def list_voice_sessions(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(session) for session in runtime.voice.list_sessions()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/sessions")
def create_voice_session(payload: VoiceSessionCreatePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.voice.create_session(
                agent_id=payload.agent_id,
                conversation_id=payload.conversation_id,
                metadata=payload.metadata,
                session_id=payload.session_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/sessions/{session_id}")
def get_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.summarize_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/sessions/{session_id}/utterances")
def list_voice_utterances(session_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.voice.list_utterances(session_id)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/sessions/{session_id}/queue")
def queue_voice_utterance(
    session_id: str,
    payload: VoiceQueuePayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.voice.queue_utterance(
                session_id,
                payload.text,
                provider_id=payload.provider_id,
                priority=payload.priority,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/sessions/{session_id}/pause")
def pause_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.pause_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/sessions/{session_id}/resume")
def resume_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.resume_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/sessions/{session_id}/close")
def close_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.close_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/settings")
def get_voice_settings(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.get_settings())
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/voice/settings")
def update_voice_settings(payload: VoiceSettingsPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.voice.update_settings(
                provider_id=payload.provider_id,
                stt_provider_id=payload.stt_provider_id,
                device_id=payload.device_id,
                language=payload.language,
                model=payload.model,
                tts_provider_id=payload.tts_provider_id,
                tts_voice_id=payload.tts_voice_id,
                tts_model=payload.tts_model,
                default_tts_voice=payload.default_tts_voice,
                preferred_voice_gender=payload.preferred_voice_gender,
                provider_configuration_references=payload.provider_configuration_references,
                tts_speed=payload.tts_speed,
                stt_model=payload.stt_model,
                stt_device=payload.stt_device,
                stt_compute_type=payload.stt_compute_type,
                input_device_id=payload.input_device_id,
                output_device_id=payload.output_device_id,
                voice_analysis_provider_id=payload.voice_analysis_provider_id,
                vad_provider_id=payload.vad_provider_id,
                vad_enabled=payload.vad_enabled,
                silence_threshold=payload.silence_threshold,
                min_speech_duration_ms=payload.min_speech_duration_ms,
                min_silence_duration_ms=payload.min_silence_duration_ms,
                max_utterance_duration_ms=payload.max_utterance_duration_ms,
                recording_retention=payload.recording_retention,
                store_raw_audio=payload.store_raw_audio,
                conversation_mode_defaults=payload.conversation_mode_defaults,
                enabled=payload.enabled,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/devices")
def list_voice_devices(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(device) for device in runtime.voice.list_devices()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/devices/{device_id}/test")
def test_voice_device(device_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.voice.test_microphone(device_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/providers")
def list_voice_providers(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.voice.list_providers()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/packs")
def list_voice_packs(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.voice.list_voice_packs()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/voices")
def list_tts_voices(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.voice.list_tts_voices()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/voicestudio/profiles")
def create_voicestudio_profile(payload: VoiceStudioProfilePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        audio = base64.b64decode(payload.audio_base64.split(",", 1)[-1], validate=True)
        result = runtime.voice.create_voicestudio_profile(
            name=payload.name, audio=audio, filename=payload.filename,
            language=payload.language, ref_text=payload.ref_text,
        )
        return {"profile": result, "voices": [asdict(item) for item in runtime.voice.list_tts_voices()]}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/recordings")
def list_voice_recordings(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.voice.list_recordings()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/recordings")
def create_voice_recording(payload: VoiceRecordingPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.voice.create_recording(
                device_id=payload.device_id,
                provider_id=payload.provider_id,
                language=payload.language or "pt-BR",
                model=payload.model,
                audio_base64=payload.audio_base64,
                audio_format=payload.audio_format,
                duration_ms=payload.duration_ms,
                transcript=payload.transcript,
                metadata=payload.metadata,
                recording_id=payload.recording_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/voice/recordings/{recording_id}")
def get_voice_recording(recording_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.voice.get_recording(recording_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/recordings/{recording_id}/transcribe")
def transcribe_voice_recording(
    recording_id: str,
    payload: VoiceTranscriptionPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.voice.transcribe_recording(
                recording_id,
                transcript=payload.transcript,
                provider_id=payload.provider_id,
                language=payload.language,
                metadata=payload.metadata,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/speech/sessions")
def list_speech_sessions(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(session) for session in runtime.speech_pipeline.list_sessions()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/speech/sessions")
def create_speech_session(
    payload: SpeechPipelineSessionCreatePayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.speech_pipeline.create_session(
                audio_session_id=payload.audio_session_id,
                voice_session_id=payload.voice_session_id,
                multimodal_session_id=payload.multimodal_session_id,
                agent_id=payload.agent_id,
                metadata=payload.metadata,
                pipeline_session_id=payload.pipeline_session_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/speech/sessions/{session_id}")
def get_speech_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_pipeline.get_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/speech/sessions/{session_id}/pause")
def pause_speech_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_pipeline.pause_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/speech/sessions/{session_id}/resume")
def resume_speech_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_pipeline.resume_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/speech/sessions/{session_id}/close")
def close_speech_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_pipeline.close_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/speech/sessions/{session_id}/summary")
def speech_session_summary(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_pipeline.summarize_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/audio/sessions")
def list_audio_sessions(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(session) for session in runtime.audio.list_sessions()]


@router.post("/audio/sessions")
def create_audio_session(payload: AudioSessionCreatePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.audio.create_session(**payload_dict(payload)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/audio/sessions/{session_id}")
def get_audio_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.audio.get_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/audio/sessions/{session_id}/pause")
def pause_audio_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.audio.pause_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/audio/sessions/{session_id}/resume")
def resume_audio_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.audio.resume_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/audio/sessions/{session_id}/close")
def close_audio_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.audio.close_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/audio/devices")
def list_audio_devices(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(device) for device in runtime.audio.list_devices()]


@router.post("/audio/synthesize")
def audio_synthesize(payload: AudioSynthesizePayload, request: Request) -> dict[str, Any]:
    from synapse.audio.models import AudioOutputRequest

    runtime = runtime_from(request)
    try:
        session_id = payload.session_id or f"tts-{uuid4().hex}"
        provider_id = payload.provider_id
        voice_id = payload.voice_id
        speed = payload.speed
        language = payload.language
        if not provider_id:
            voice_settings = runtime.voice.get_settings()
            provider_id = voice_settings.tts_provider_id or None
            voice_id = voice_id or voice_settings.default_tts_voice
            speed = speed if speed is not None else voice_settings.tts_speed
            language = language or voice_settings.language
        return asdict(
            runtime.audio.synthesize(
                AudioOutputRequest(
                    session_id=session_id,
                    text=payload.text,
                    agent_id=payload.agent_id,
                    provider_id=provider_id,
                    voice_id=voice_id,
                    language=language,
                    speed=speed,
                    metadata=payload.metadata,
                )
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/audio/transcribe")
def audio_transcribe(payload: AudioTranscribePayload, request: Request) -> dict[str, Any]:
    from synapse.audio.models import AudioInputRequest

    runtime = runtime_from(request)
    try:
        voice_settings = runtime.voice.get_settings()
        if not voice_settings.enabled:
            raise ValidationError("Voice is disabled by config.")
        logger.info(
            "audio.transcribe.request provider=%s model=%s language=%s audio_chars=%s audio_format=%s session_id=%s multimodal_session_id=%s",
            payload.provider_id or voice_settings.stt_provider_id or voice_settings.provider_id,
            payload.model or voice_settings.model,
            payload.language or voice_settings.language,
            len(payload.audio_base64 or ""),
            payload.audio_format,
            payload.session_id,
            payload.multimodal_session_id,
        )
        result = runtime.audio.transcribe(
            AudioInputRequest(
                session_id=payload.session_id,
                multimodal_session_id=payload.multimodal_session_id,
                provider_id=payload.provider_id
                or voice_settings.stt_provider_id
                or voice_settings.provider_id,
                language=payload.language or voice_settings.language,
                model=runtime.voice.resolve_model_name(payload.model or voice_settings.model),
                audio_base64=payload.audio_base64,
                audio_format=payload.audio_format,
                duration_ms=payload.duration_ms,
                metadata=payload.metadata,
            )
        )
        logger.info(
            "audio.transcribe.response provider=%s text_length=%s duration_ms=%s",
            result.provider_id,
            len(result.text or ""),
            getattr(result, "duration_ms", None),
        )
        if payload.session_id or payload.multimodal_session_id:
            signal = runtime.perception.signal_from_speech_to_text(
                result,
                session_id=payload.session_id,
                multimodal_session_id=payload.multimodal_session_id,
            )
            runtime.perception.emit_signal(signal)
        return asdict(result)
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/voice/conversation/turn")
def voice_conversation_turn(
    payload: VoiceConversationTurnPayload,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Process one user-controlled conversational voice turn.

    Capture and VAD stay in the client. The server composes the existing real
    STT, perception, local-chat, persistence, memory, and context-fusion paths.
    """
    from synapse.audio.models import AudioInputRequest

    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    turn_id = str(uuid4())
    try:
        voice_settings = runtime.voice.get_settings()
        if not voice_settings.enabled:
            raise ValidationError("Voice is disabled by config.")
        logger.info(
            "voice.conversation.turn.request turn_id=%s conversation_id=%s agent_id=%s provider=%s model=%s audio_chars=%s auto_respond=%s",
            turn_id,
            payload.conversation_id,
            payload.agent_id,
            payload.provider_id or voice_settings.stt_provider_id or voice_settings.provider_id,
            payload.model or voice_settings.model,
            len(payload.audio_base64 or ""),
            payload.auto_respond,
        )
        transcript = runtime.audio.transcribe(
            AudioInputRequest(
                session_id=payload.conversation_id,
                provider_id=payload.provider_id
                or voice_settings.stt_provider_id
                or voice_settings.provider_id,
                language=payload.language or voice_settings.language,
                model=runtime.voice.resolve_model_name(payload.model or voice_settings.model),
                audio_base64=payload.audio_base64,
                audio_format=payload.audio_format,
                metadata={
                    "source": "voice-conversation-loop",
                    "turn_id": turn_id,
                    **payload.metadata,
                },
            )
        )
        signal = runtime.perception.signal_from_speech_to_text(
            transcript,
            session_id=payload.conversation_id,
            metadata={"turn_id": turn_id, "source": "voice-conversation-loop"},
        )
        runtime.perception.emit_signal(signal)
        if not transcript.text.strip():
            raise ValidationError("Nenhuma fala foi detectada no áudio.")
        logger.info(
            "voice.conversation.turn.transcript turn_id=%s transcript_length=%s",
            turn_id,
            len(transcript.text.strip()),
        )

        chat_result = None
        conversation_id = payload.conversation_id
        if payload.auto_respond:
            chat_result = runtime.chat.local_chat(
                context=context,
                message=transcript.text.strip(),
                agent_id=payload.agent_id
                if payload.agent_id not in {None, "", "local_chat"}
                else None,
                conversation_id=conversation_id,
                model_provider_id=payload.model_provider_id,
                model_name=payload.model_name,
            )
            conversation_id = chat_result.conversation_id
            logger.info(
                "voice.conversation.turn.chat turn_id=%s response_length=%s conversation_id=%s",
                turn_id,
                len(chat_result.response or ""),
                conversation_id,
            )

        fused_context_id = None
        if conversation_id:
            fused = runtime.context_fusion.build_conversation_context(conversation_id)
            fused_context_id = fused.snapshot.interaction_context.context_id

        return {
            "transcript": transcript.text.strip(),
            "response": chat_result.response if chat_result else None,
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "transcript_result": asdict(transcript),
            "context_id": fused_context_id,
            "tts": {"status": "placeholder", "text": chat_result.response if chat_result else None},
        }
    except Exception as exc:
        raise api_error(exc) from exc
