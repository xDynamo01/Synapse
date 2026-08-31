from __future__ import annotations

from synapse.audio.ingestion import decode_base64_audio, ingest_audio
from synapse.audio.models import AudioInputRequest, VoiceAnalysisResult
from synapse.core.exceptions import ValidationError
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest


class LocalVoiceAnalysisAdapter:
    def __init__(self, manifest: SpeechAdapterManifest) -> None:
        self._manifest = manifest

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def capabilities(self) -> dict[str, object]:
        return {
            "duration": True,
            "rms": True,
            "peak": True,
            "silence": True,
            "pitch": False,
            "emotion": False,
            "streaming": False,
        }

    def health(self) -> SpeechAdapterHealth:
        from datetime import UTC, datetime

        return SpeechAdapterHealth(
            adapter_id=self._manifest.adapter_id,
            provider_id=self._manifest.provider_id,
            status="available",
            checked_at=datetime.now(UTC).isoformat(),
            message="Local objective acoustic analysis is available.",
            metadata={"metrics": self.capabilities()},
        )

    def analyze(self, request: AudioInputRequest) -> VoiceAnalysisResult:
        if not request.audio_base64:
            raise ValidationError("Audio payload is required for voice analysis.")
        payload = ingest_audio(
            decode_base64_audio(request.audio_base64),
            request.audio_format,
        )
        silence_ratio = payload.silence_ratio
        silence_duration_ms = (
            int(round(payload.duration_ms * silence_ratio)) if silence_ratio is not None else None
        )
        speech_duration_ms = (
            payload.duration_ms - silence_duration_ms if silence_duration_ms is not None else None
        )
        return VoiceAnalysisResult(
            provider_id=self._manifest.provider_id,
            duration_ms=payload.duration_ms,
            average_volume=payload.average_volume,
            peak_volume=payload.peak_volume,
            silence_ratio=silence_ratio,
            silence_duration_ms=silence_duration_ms,
            speech_duration_ms=speech_duration_ms,
            metadata={
                "checksum": payload.checksum,
                "sample_rate": payload.sample_rate,
                "channels": payload.channels,
                "objective_metrics_only": True,
            },
        )
