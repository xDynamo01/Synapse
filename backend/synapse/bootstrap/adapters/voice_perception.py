from __future__ import annotations

import io
import wave

from synapse.audio.ingestion import ingest_audio
from synapse.perception.models import (
    PerceptionBundleStatus,
    PerceptionResultBundle,
    VoicePerceptionRequest,
)
from synapse.perception.runtime import PerceptionRuntime


class LocalVoicePerceptionAdapter:
    def __init__(self, perception: PerceptionRuntime) -> None:
        self._perception = perception

    def analyze_transient(
        self, request: VoicePerceptionRequest, pcm_bytes: bytes, sample_rate: int
    ) -> PerceptionResultBundle:
        payload = ingest_audio(_pcm_wav(pcm_bytes, sample_rate))
        artifacts = self._perception.analyze_acoustic_features(
            payload,
            input_reference=request.audio_checksum_reference,
            source_identity=request.voice_session_id,
            occurrence_started_at=request.occurrence_started_at,
            occurrence_ended_at=request.occurrence_ended_at,
        )
        unavailable = tuple(
            artifact.type for artifact in artifacts if artifact.values.get("available") is False
        )
        return self._perception.create_result_bundle(
            request,
            artifacts,
            status=(
                PerceptionBundleStatus.PARTIAL if unavailable else PerceptionBundleStatus.AVAILABLE
            ),
            missing_capabilities=unavailable,
            limitations=("Raw PCM was transient and is not part of this bundle.",),
        )


def _pcm_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return output.getvalue()
