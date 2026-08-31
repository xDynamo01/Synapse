from __future__ import annotations

import io
import math
import struct
import tempfile
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

from synapse.audio.ingestion import ingest_audio
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.perception.models import PerceptionArtifactKind
from synapse.voice.perception import VoicePerceptionSignal

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _wav(*, frequency: float | None, duration_ms: int, silence: tuple[int, int] | None = None) -> bytes:
    sample_rate = 16_000
    frames = []
    for index in range(sample_rate * duration_ms // 1000):
        instant_ms = index * 1000 // sample_rate
        muted = silence is not None and silence[0] <= instant_ms < silence[1]
        value = 0 if frequency is None or muted else int(12_000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        frames.append(struct.pack("<h", value))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(frames))
    return output.getvalue()


def _runtime():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(PROJECT_ROOT, Path(directory.name) / "data", "127.0.0.1", 8717, "local_owner")
    return directory, create_runtime(settings)


def test_real_local_dsp_features_have_taxonomy_lineage_and_no_raw_persistence() -> None:
    directory, runtime = _runtime()
    try:
        payload = ingest_audio(_wav(frequency=200.0, duration_ms=1000, silence=(400, 700)))
        started = datetime.now(UTC)
        artifacts = runtime.perception.analyze_acoustic_features(
            payload,
            input_reference="recording:test-1",
            source_identity="microphone:test",
            session_id="voice-session-1",
            occurrence_started_at=started.isoformat(),
            occurrence_ended_at=(started + timedelta(seconds=1)).isoformat(),
        )
        by_type = {artifact.type: artifact for artifact in artifacts}
        pitch = by_type["audio.pitch_f0"]
        assert 190.0 <= float(pitch.values["value"]) <= 210.0
        assert by_type["audio.pause_count"].values["value"] == 1
        assert by_type["audio.voiced_segment_rate"].values["unit"] == "voiced_segments_per_second"
        assert pitch.artifact_kind == PerceptionArtifactKind.DERIVED_FEATURE
        assert pitch.confidence is None
        assert pitch.input_references == ["recording:test-1"]
        assert pitch.lineage == ["recording:test-1"]
        assert pitch.external_processing is False
        persisted = "".join(
            path.read_text(encoding="utf-8")
            for path in (runtime.settings.data_dir / "perception" / "signals").glob("*.json")
        )
        assert "audio_bytes" not in persisted
        assert "RIFF" not in persisted
        assert not any(
            label in persisted.lower()
            for label in ("angry", "happy", "anxious", "engaged", "bored")
        )
    finally:
        directory.cleanup()


def test_unvoiced_audio_keeps_pitch_unavailable_instead_of_zero() -> None:
    directory, runtime = _runtime()
    try:
        payload = ingest_audio(_wav(frequency=None, duration_ms=500))
        artifacts = runtime.perception.analyze_acoustic_features(
            payload,
            input_reference="recording:silence",
            source_identity="microphone:test",
        )
        pitch = next(item for item in artifacts if item.type == "audio.pitch_f0")
        assert pitch.values["available"] is False
        assert pitch.values["value"] is None
        assert pitch.confidence is None
    finally:
        directory.cleanup()


def test_capability_health_does_not_claim_missing_visual_providers() -> None:
    directory, runtime = _runtime()
    try:
        health = runtime.perception.nonverbal_capability_health()
        assert health["acoustic_features"]["status"] == "supported"
        assert health["pitch"]["provider"] == "synapse_local_dsp"
        assert health["face_detection"]["status"] == "not_configured"
        for capability in ("head_pose", "gaze", "body_pose", "gesture"):
            assert health[capability]["status"] == "unavailable"
    finally:
        directory.cleanup()


def test_voice_activity_handoff_preserves_voice_owned_identity() -> None:
    directory, runtime = _runtime()
    try:
        runtime.perception.emit(
            VoicePerceptionSignal(
                type="speech.started",
                session_id="voice-session",
                recording_id="recording-1",
                utterance_id="utterance-1",
                provenance="voice.vad",
                values={"voiced": True},
            )
        )
        artifact = runtime.perception.list_signals()[0]
        assert artifact.artifact_kind == PerceptionArtifactKind.RAW_OBSERVATION
        assert artifact.source_identity == "voice_runtime"
        assert artifact.input_references == ["recording-1", "utterance-1"]
        assert artifact.lineage == artifact.input_references
        assert "turn" not in artifact.values
    finally:
        directory.cleanup()
