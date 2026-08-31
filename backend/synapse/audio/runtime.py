from __future__ import annotations

import base64
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from synapse.audio.contracts import SpeechExecutionPort
from synapse.audio.devices import DeviceRuntime
from synapse.audio.ingestion import AudioIngestionLimits, decode_base64_audio, ingest_audio
from synapse.audio.models import (
    AUDIO_DEVICE_TYPES,
    AUDIO_SESSION_STATUSES,
    AudioDevice,
    AudioInputRequest,
    AudioOutputRequest,
    AudioPayload,
    AudioSession,
    SpeechToTextResult,
    TextToSpeechResult,
    TranscriptResult,
)
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.multimodal.runtime import MultimodalCommunicationRuntime
from synapse.providers.models import CapabilityProvider
from synapse.providers.runtime import ProviderRuntime


class AudioRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        providers: ProviderRuntime,
        multimodal: MultimodalCommunicationRuntime,
        speech_adapters: SpeechExecutionPort | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.providers = providers
        self.multimodal = multimodal
        self.speech_adapters = speech_adapters
        self.devices = DeviceRuntime()
        self.dev_mode = os.getenv("SYNAPSE_DEV_MODE", "").lower() in {"1", "true", "yes"}

    def ingest(
        self,
        audio_bytes: bytes,
        mime_type: str | None = None,
        *,
        limits: AudioIngestionLimits | None = None,
    ) -> AudioPayload:
        payload = ingest_audio(audio_bytes, mime_type, limits=limits)
        self.events.emit(
            "audio.ingested",
            "audio",
            {
                "mime_type": payload.mime_type,
                "source_mime_type": payload.source_mime_type,
                "duration_ms": payload.duration_ms,
                "sample_rate": payload.sample_rate,
                "channels": payload.channels,
                "checksum": payload.checksum,
            },
        )
        return payload

    def ingest_base64(
        self,
        audio_base64: str,
        mime_type: str | None = None,
        *,
        limits: AudioIngestionLimits | None = None,
    ) -> AudioPayload:
        return self.ingest(decode_base64_audio(audio_base64), mime_type, limits=limits)

    def create_session(
        self,
        multimodal_session_id: str | None = None,
        agent_id: str | None = None,
        input_device_id: str | None = None,
        output_device_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> AudioSession:
        if multimodal_session_id:
            self.multimodal.get_session(multimodal_session_id)
        session = AudioSession(
            session_id=session_id or AudioSession().session_id,
            multimodal_session_id=multimodal_session_id,
            agent_id=agent_id,
            input_device_id=input_device_id,
            output_device_id=output_device_id,
            metadata=metadata or {},
        )
        self._write_session(session)
        self.events.emit("audio.session.created", "audio", asdict(session))
        return session

    def get_session(self, session_id: str) -> AudioSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise NotFound(f"Audio session not found: {session_id}")
        return self._read_session(session_id)

    def list_sessions(self, status: str | None = None) -> list[AudioSession]:
        if status and status not in AUDIO_SESSION_STATUSES:
            raise ValidationError(f"Invalid audio session status: {status}")
        sessions = [
            self._read_session(path.stem) for path in sorted(self._sessions_root().glob("*.yaml"))
        ]
        if status:
            sessions = [session for session in sessions if session.status == status]
        return sorted(sessions, key=lambda item: (item.updated_at, item.session_id))

    def pause_session(self, session_id: str) -> AudioSession:
        session = self._set_session_status(session_id, "paused")
        self.events.emit("audio.session.paused", "audio", asdict(session))
        return session

    def resume_session(self, session_id: str) -> AudioSession:
        session = self._set_session_status(session_id, "idle")
        self.events.emit("audio.session.resumed", "audio", asdict(session))
        return session

    def close_session(self, session_id: str) -> AudioSession:
        session = self._set_session_status(session_id, "closed")
        self.events.emit("audio.session.closed", "audio", asdict(session))
        return session

    def list_devices(self) -> list[AudioDevice]:
        return [
            AudioDevice(
                device_id=device.stable_id,
                name=device.name,
                device_type=device.direction,
                enabled=device.available,
                metadata={
                    **device.metadata,
                    "runtime_id": device.id,
                    "backend": device.backend,
                    "is_default": device.is_default,
                    "channels": device.channels,
                    "default_sample_rate": device.default_sample_rate,
                },
            )
            for device in self.devices.list_devices()
        ]

    def device_health(self) -> dict[str, Any]:
        return self.devices.health()

    def register_mock_device(
        self,
        device_id: str,
        name: str,
        device_type: str,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> AudioDevice:
        _require_dev_mode(self.dev_mode)
        if device_type not in AUDIO_DEVICE_TYPES:
            raise ValidationError(f"Invalid audio device type: {device_type}")
        device = AudioDevice(
            device_id=device_id,
            name=name,
            device_type=device_type,
            enabled=enabled,
            metadata={"mock": True, **(metadata or {})},
        )
        dump_structured_file(self._device_path(device_id), asdict(device))
        return device

    def resolve_stt_provider(self) -> CapabilityProvider:
        return self._resolve_provider("speech_to_text")

    def resolve_tts_provider(self) -> CapabilityProvider:
        return self._resolve_provider("text_to_speech")

    def transcribe_mock(self, request: AudioInputRequest, text: str) -> SpeechToTextResult:
        _require_dev_mode(self.dev_mode)
        if request.session_id is None:
            raise ValidationError("Audio input request requires a session_id")
        session = self._set_session_status(request.session_id, "listening")
        provider = self._resolve_provider("speech_to_text", request.provider_id)
        result = SpeechToTextResult(
            text=text,
            language=request.language,
            confidence=1.0,
            provider_id=provider.provider_id,
            latency_ms=0,
            metadata={"mock": True, **request.metadata},
        )
        self.events.emit(
            "audio.mock.transcribed",
            session.agent_id or "audio",
            {"session_id": session.session_id, **asdict(result)},
        )
        self._emit_multimodal_event(
            session,
            channel="voice",
            event_type="audio.mock.transcribed",
            payload=asdict(result),
            provider_id=provider.provider_id,
        )
        return result

    def transcribe(self, request: AudioInputRequest) -> TranscriptResult:
        if self.speech_adapters is None:
            raise ValidationError("Speech adapter runtime is unavailable.")
        if not request.audio_base64:
            raise ValidationError("Audio payload is required.")
        try:
            payload = self.ingest_base64(request.audio_base64, request.audio_format)
            normalized_request = replace(
                request,
                audio_base64=base64.b64encode(payload.audio_bytes).decode("ascii"),
                audio_format=payload.mime_type,
                duration_ms=payload.duration_ms,
                metadata={
                    **request.metadata,
                    "audio_checksum": payload.checksum,
                    "source_mime_type": payload.source_mime_type,
                    "sample_rate": payload.sample_rate,
                    "channels": payload.channels,
                },
            )
            result = self.speech_adapters.transcribe(normalized_request)
            self.events.emit("audio.transcribed", "audio", asdict(result))
            return result
        except Exception as exc:
            self.events.emit(
                "audio.transcription_failed",
                "audio",
                {
                    "session_id": request.session_id,
                    "provider_id": request.provider_id,
                    "error": str(exc),
                },
            )
            raise

    def synthesize_mock(self, request: AudioOutputRequest) -> TextToSpeechResult:
        _require_dev_mode(self.dev_mode)
        session = self._set_session_status(request.session_id, "speaking")
        provider = self._resolve_provider("text_to_speech", request.provider_id or "mock_tts")
        result = TextToSpeechResult(
            output_ref=f"mock://tts/{request.session_id}",
            provider_id=provider.provider_id,
            voice_id=request.voice_id,
            latency_ms=0,
            metadata={"mock": True, "text": request.text, **request.metadata},
        )
        self.events.emit(
            "audio.mock.synthesized",
            session.agent_id or "audio",
            {"session_id": session.session_id, **asdict(result)},
        )
        self._emit_multimodal_event(
            session,
            channel="audio",
            event_type="audio.mock.synthesized",
            payload=asdict(result),
            provider_id=provider.provider_id,
        )
        return result

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        if self.speech_adapters is None:
            raise ValidationError("Speech adapter runtime is unavailable.")
        if not request.text or not request.text.strip():
            raise ValidationError("Text is required.")
        try:
            result = self.speech_adapters.synthesize(request)
            self.events.emit("audio.synthesized", "audio", asdict(result))
            return result
        except Exception as exc:
            self.events.emit(
                "audio.synthesis_failed",
                "audio",
                {
                    "session_id": request.session_id,
                    "provider_id": request.provider_id,
                    "error": str(exc),
                },
            )
            raise

    def _resolve_provider(
        self,
        capability_id: str,
        provider_id: str | None = None,
    ) -> CapabilityProvider:
        try:
            if provider_id:
                provider = self.providers.get_provider(provider_id)
                if capability_id not in provider.capabilities:
                    raise ValidationError(
                        f"Provider {provider_id} does not implement {capability_id}"
                    )
                resolved = CapabilityProvider(
                    capability_id=capability_id,
                    provider_id=provider_id,
                    priority=0,
                    enabled=provider.enabled,
                    metadata={"source": "explicit"},
                )
            else:
                resolved = self.providers.resolve_provider_for_capability(capability_id)
            self.events.emit(
                "audio.provider.resolved",
                "audio",
                {"capability_id": capability_id, "provider_id": resolved.provider_id},
            )
            return resolved
        except Exception as exc:
            self.events.emit(
                "audio.provider.unavailable",
                "audio",
                {"capability_id": capability_id, "provider_id": provider_id, "error": str(exc)},
            )
            raise

    def _emit_multimodal_event(
        self,
        session: AudioSession,
        channel: str,
        event_type: str,
        payload: dict[str, Any],
        provider_id: str,
    ) -> None:
        if not session.multimodal_session_id:
            return
        self.multimodal.emit_event(
            session_id=session.multimodal_session_id,
            channel=channel,
            event_type=event_type,
            source=session.agent_id or "audio",
            payload=payload,
            metadata={"audio_session_id": session.session_id, "provider_id": provider_id},
        )

    def _set_session_status(self, session_id: str, status: str) -> AudioSession:
        if status not in AUDIO_SESSION_STATUSES:
            raise ValidationError(f"Invalid audio session status: {status}")
        session = self.get_session(session_id)
        if session.status == "closed" and status != "closed":
            raise ValidationError(f"Audio session is closed: {session_id}")
        updated = replace(session, status=status, updated_at=_now())
        self._write_session(updated)
        return updated

    def _read_session(self, session_id: str) -> AudioSession:
        raw = load_structured_file(self._session_path(session_id))
        raw.setdefault("session_id", session_id)
        raw.setdefault("multimodal_session_id", None)
        raw.setdefault("agent_id", None)
        raw.setdefault("status", "idle")
        raw.setdefault("input_device_id", None)
        raw.setdefault("output_device_id", None)
        raw.setdefault("created_at", _now())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("metadata", {})
        return AudioSession(**raw)

    def _write_session(self, session: AudioSession) -> None:
        if session.status not in AUDIO_SESSION_STATUSES:
            raise ValidationError(f"Invalid audio session status: {session.status}")
        dump_structured_file(self._session_path(session.session_id), asdict(session))

    def _read_device(self, path) -> AudioDevice:
        raw = load_structured_file(path)
        raw.setdefault("metadata", {})
        return AudioDevice(**raw)

    def _sessions_root(self):
        root = self.data_dir.resolve("audio/sessions")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _devices_root(self):
        root = self.data_dir.resolve("audio/devices")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _session_path(self, session_id: str):
        return self._sessions_root() / f"{session_id}.yaml"

    def _device_path(self, device_id: str):
        return self._devices_root() / f"{device_id}.yaml"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_dev_mode(enabled: bool) -> None:
    if not enabled:
        raise ValidationError("Development audio doubles are disabled.")
