from __future__ import annotations

import base64
import os
import time
from typing import Any, Protocol

from synapse.audio.models import AudioOutputRequest, TextToSpeechResult
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest


class VoiceStudioTransport(Protocol):
    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any: ...
    def request_bytes(self, method: str, path: str, payload: dict[str, Any]) -> bytes: ...
    def request_multipart(self, method: str, path: str, fields: dict[str, str], file_field: str, filename: str, content: bytes) -> dict[str, Any]: ...


class VoiceStudioTextToSpeechAdapter:
    """Optional bridge to a user-installed VoiceStudio desktop API."""

    def __init__(self, manifest: SpeechAdapterManifest, data_dir: DataDir, transport: VoiceStudioTransport | None = None) -> None:
        self._http = transport
        self._manifest = manifest
        self._data_dir = data_dir
        self._base_url = os.getenv("SYNAPSE_VOICESTUDIO_URL", "http://127.0.0.1:3900").rstrip("/")

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def health(self) -> SpeechAdapterHealth:
        try:
            payload = self._request("GET", "/health")
            return SpeechAdapterHealth(
                adapter_id=self._manifest.adapter_id,
                provider_id=self._manifest.provider_id,
                status="available" if payload.get("status") == "ok" else "degraded",
                checked_at=_now(),
                message="VoiceStudio local API is responding.",
                metadata={"base_url": self._base_url, **payload},
            )
        except Exception as exc:
            return SpeechAdapterHealth(
                adapter_id=self._manifest.adapter_id,
                provider_id=self._manifest.provider_id,
                status="unconfigured",
                checked_at=_now(),
                message=f"VoiceStudio is not running at {self._base_url}.",
                metadata={"error": str(exc), "base_url": self._base_url},
            )

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        if not request.text.strip():
            raise ValidationError("Text is required for VoiceStudio synthesis.")
        started = time.perf_counter()
        payload = {
            "model": "tts-1",
            "voice": request.voice_id or "default",
            "input": request.text,
            "response_format": "wav",
            "speed": request.speed or 1.0,
        }
        audio = self._request_bytes("POST", "/v1/audio/speech", payload)
        return TextToSpeechResult(
            output_ref=f"inline://tts/{request.session_id}",
            provider_id=self._manifest.provider_id,
            voice_id=request.voice_id or "default",
            audio_base64=base64.b64encode(audio).decode("ascii"),
            audio_format="audio/wav",
            latency_ms=int((time.perf_counter() - started) * 1000),
            metadata={"engine": "voicestudio", "base_url": self._base_url},
        )

    def list_voices(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/audio/voices")
        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def create_profile(
        self, *, name: str, audio: bytes, filename: str, language: str, ref_text: str = ""
    ) -> dict[str, Any]:
        if not name.strip() or not audio:
            raise ValidationError("A profile name and a non-empty reference audio file are required.")
        fields = {"name": name.strip(), "language": language or "Auto", "ref_text": ref_text, "kind": "clone"}
        return self._request_multipart("POST", "/profiles", fields, "ref_audio", filename, audio)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self._transport().request(method, path, payload)

    def _request_bytes(self, method: str, path: str, payload: dict[str, Any]) -> bytes:
        return self._transport().request_bytes(method, path, payload)

    def _request_multipart(self, method: str, path: str, fields: dict[str, str], file_field: str, filename: str, content: bytes) -> dict[str, Any]:
        return self._transport().request_multipart(method, path, fields, file_field, filename, content)

    def _transport(self) -> VoiceStudioTransport:
        if self._http is None:
            raise ValidationError("VoiceStudio transport is not configured.")
        return self._http


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()
