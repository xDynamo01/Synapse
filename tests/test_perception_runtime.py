from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.audio.models import SpeechFeatures, SpeechToTextResult, TextToSpeechResult
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.perception.errors import PerceptionSignalInvalid
from synapse.perception.models import PerceptionArtifactKind, PerceptionSignal, RetentionClass


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Perception Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    return directory, create_runtime(settings)


class PerceptionRuntimeTests(unittest.TestCase):
    def test_create_signal(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        signal = runtime.perception.create_signal(
            signal_type="speech",
            source_runtime="audio",
            source_provider="mock_stt",
            session_id="session-1",
            confidence=0.8,
            payload={"text": "hello"},
        )

        self.assertEqual(signal.signal_type, "speech")
        self.assertEqual(signal.source_runtime, "audio")
        self.assertEqual(signal.confidence, 0.8)

    def test_create_batch(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        signal = runtime.perception.create_signal("system", "test", {"ok": True}, session_id="s1")

        batch = runtime.perception.create_batch([signal], session_id="s1")
        summary = runtime.perception.summarize_batch(batch.batch_id)

        self.assertEqual(batch.session_id, "s1")
        self.assertEqual(summary.total_signals, 1)
        self.assertEqual(summary.by_type["system"], 1)

    def test_list_signals(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.perception.create_signal("speech", "audio", {"text": "one"}, session_id="s1")
        runtime.perception.create_signal("face", "vision", {"face": "one"}, session_id="s2")

        signals = runtime.perception.list_signals()

        self.assertEqual(len(signals), 2)

    def test_list_by_session_and_type(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.perception.create_signal("speech", "audio", {"text": "one"}, session_id="s1")
        runtime.perception.create_signal("face", "vision", {"face": "one"}, session_id="s2")

        self.assertEqual(len(runtime.perception.list_signals_by_session("s1")), 1)
        self.assertEqual(len(runtime.perception.list_signals_by_type("face")), 1)

    def test_summarize_session(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.perception.create_signal("speech", "audio", {"text": "one"}, session_id="s1", confidence=0.5)
        runtime.perception.create_signal("voice", "audio", {"voice": "one"}, session_id="s1", confidence=1.0)

        summary = runtime.perception.summarize_session("s1")

        self.assertEqual(summary.total_signals, 2)
        self.assertEqual(summary.by_type["speech"], 1)
        self.assertEqual(summary.average_confidence, 0.75)
        self.assertEqual(summary.sources, ["audio"])

    def test_audio_to_signal_converters(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        speech = runtime.perception.signal_from_speech_to_text(
            SpeechToTextResult(
                text="hello",
                confidence=0.9,
                provider_id="mock_stt",
                duration_ms=1200,
                speech_features=SpeechFeatures(
                    duration_ms=1200,
                    speech_rate=120.0,
                    pause_count=0,
                    pause_duration_ms=0,
                    silence_ratio=0.0,
                    segment_count=1,
                    timestamps=[{"start": 0.0, "end": 1.2, "text": "hello"}],
                    language_confidence=0.97,
                    provider_metadata={"provider": "mock_stt"},
                ),
            ),
            session_id="audio-1",
        )
        voice = runtime.perception.signal_from_text_to_speech(
            TextToSpeechResult(output_ref="mock://tts/audio-1", provider_id="mock_tts"),
            session_id="audio-1",
        )

        self.assertEqual(speech.signal_type, "speech")
        self.assertEqual(voice.signal_type, "voice")
        self.assertEqual(speech.payload["text"], "[REDACTED]")
        self.assertEqual(speech.payload["speech_features"]["segment_count"], 1)

    def test_vision_uses_canonical_ingestion(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        signal = runtime.perception.create_signal(
            "vision.image.validated",
            "vision",
            {"dimensions": {"width": 1, "height": 1}},
            session_id="vision-1",
        )
        observations = runtime.perception.list_observations(session_id="vision-1")
        self.assertEqual(signal.modality, "vision")
        self.assertEqual(len(observations), 1)

    def test_emit_signal_to_multimodal(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        with self.assertRaises(PerceptionSignalInvalid):
            runtime.perception.create_signal(
            "face",
            "vision",
            {"emotion": "neutral"},
            multimodal_session_id=multimodal.session_id,
            )

        signal = runtime.perception.create_signal(
            "face.bounding_box",
            "vision",
            {"bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4}},
            multimodal_session_id=multimodal.session_id,
            artifact_kind=PerceptionArtifactKind.DERIVED_FEATURE,
            input_references=["frame-1"],
        )

        runtime.perception.emit_signal(signal)

        events = runtime.multimodal.list_session_events(multimodal.session_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].channel, "vision")
        self.assertEqual(events[0].payload["signal_id"], signal.signal_id)

    def test_closed_taxonomy_and_model_provenance(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        raw = runtime.perception.ingest_signal(
            PerceptionSignal(
                type="voice.activity",
                modality="audio",
                source="voice",
                values={"active": True},
                artifact_kind=PerceptionArtifactKind.RAW_OBSERVATION,
            )
        )
        feature = runtime.perception.create_signal(
            "audio.rms",
            "audio",
            {"rms": 0.25},
            artifact_kind=PerceptionArtifactKind.DERIVED_FEATURE,
            input_references=[raw.id],
        )
        inference = runtime.perception.create_signal(
            "face.smile_probability",
            "vision",
            {"score": 0.75},
            source_provider="provider-a",
            model="face-model",
            model_version="1",
            confidence=0.75,
            artifact_kind=PerceptionArtifactKind.MODEL_INFERENCE,
            input_references=["frame-1"],
        )
        self.assertEqual(raw.artifact_kind, PerceptionArtifactKind.RAW_OBSERVATION)
        self.assertEqual(feature.input_references, [raw.id])
        self.assertEqual(inference.model_version, "1")
        with self.assertRaises(PerceptionSignalInvalid):
            runtime.perception.create_signal(
                "gesture.class",
                "vision",
                {"label": "wave"},
                artifact_kind=PerceptionArtifactKind.MODEL_INFERENCE,
            )
        with self.assertRaises(PerceptionSignalInvalid):
            runtime.perception.create_signal(
                "audio.frame",
                "audio",
                {"samples": [1]},
                retention_class=RetentionClass.TRANSIENT_ONLY,
            )

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.perception.create_signal("speech", "audio", {"text": "one"}, session_id="s1")

        signals = runtime.commands.execute(runtime.context(), "/perception-signals")
        session = runtime.commands.execute(runtime.context(), "/perception-session s1")
        by_type = runtime.commands.execute(runtime.context(), "/perception-type speech")
        summary = runtime.commands.execute(runtime.context(), "/perception-summary s1")

        self.assertEqual(signals.status, "ok")
        self.assertEqual(len(session.data["signals"]), 1)
        self.assertEqual(len(by_type.data["signals"]), 1)
        self.assertEqual(summary.data["summary"]["total_signals"], 1)

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.perception.create_signal("speech", "audio", {"text": "one"}, session_id="s1")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get("/api/perception/signals").status_code, 200)
        self.assertEqual(len(client.get("/api/perception/signals/session/s1").json()), 1)
        self.assertEqual(len(client.get("/api/perception/signals/type/speech").json()), 1)
        self.assertEqual(client.get("/api/perception/summary/s1").json()["total_signals"], 1)

    def test_health_and_readiness_include_perception(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.perception.create_signal("system", "test", {"ok": True})

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.perception_runtime_available)
        self.assertEqual(health.perception_signal_count, 1)
        self.assertIn("perception.ready", [check.id for check in readiness.checks])
