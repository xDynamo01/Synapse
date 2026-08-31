from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from factories.agents import seed_test_agent
from synapse.core.app import create_runtime
from synapse.core.config import Settings


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
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        create_runtime(settings)
    seed_test_agent(
        settings.data_dir,
        "artemis",
        name="Artemis",
        role="orchestrator",
        can_delegate=True,
        capabilities=["conversation", "voice"],
    )
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Speech Pipeline Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = create_runtime(settings)
    return directory, settings, runtime


def create_pipeline(runtime):
    multimodal = runtime.multimodal.create_session(["user", "artemis"], ["text", "voice", "audio"])
    audio = runtime.audio.create_session(
        multimodal_session_id=multimodal.session_id,
        agent_id="artemis",
    )
    voice = runtime.voice.create_session("artemis")
    pipeline = runtime.speech_pipeline.create_session(
        audio_session_id=audio.session_id,
        voice_session_id=voice.session_id,
        multimodal_session_id=multimodal.session_id,
        agent_id="artemis",
    )
    return multimodal, audio, voice, pipeline


class SpeechPipelineRuntimeTests(unittest.TestCase):
    def test_create_session(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        _, audio, voice, pipeline = create_pipeline(runtime)

        self.assertEqual(pipeline.audio_session_id, audio.session_id)
        self.assertEqual(pipeline.voice_session_id, voice.session_id)
        self.assertEqual(pipeline.status, "idle")

    def test_pause_resume_close_session(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        *_, pipeline = create_pipeline(runtime)

        paused = runtime.speech_pipeline.pause_session(pipeline.pipeline_session_id)
        resumed = runtime.speech_pipeline.resume_session(pipeline.pipeline_session_id)
        closed = runtime.speech_pipeline.close_session(pipeline.pipeline_session_id)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(resumed.status, "idle")
        self.assertEqual(closed.status, "closed")

    def test_process_mock_input_creates_turn_signal_and_multimodal_event(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal, *_rest, pipeline = create_pipeline(runtime)

        turn = runtime.speech_pipeline.process_mock_input(
            pipeline.pipeline_session_id,
            "hello input",
        )

        self.assertEqual(turn.transcript, "hello input")
        self.assertIsNotNone(turn.perception_signal_id)
        signals = runtime.perception.list_signals_by_session(pipeline.audio_session_id)
        self.assertEqual(signals[-1].signal_type, "speech")
        events = runtime.multimodal.list_session_events(multimodal.session_id)
        event_types = [event.event_type for event in events]
        self.assertIn("perception.signal", event_types)
        self.assertIn("speech_pipeline.input.processed", event_types)

    def test_process_mock_output_creates_utterance_output_and_completed_state(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        _, _, voice, pipeline = create_pipeline(runtime)

        turn = runtime.speech_pipeline.process_mock_output(
            pipeline.pipeline_session_id,
            "hello output",
        )

        self.assertEqual(turn.text, "hello output")
        self.assertTrue(turn.output_ref.startswith("mock://tts/"))
        utterances = runtime.voice.list_utterances(voice.session_id)
        self.assertEqual(utterances[0].utterance_id, turn.utterance_id)
        self.assertEqual(utterances[0].state, "completed")

    def test_process_mock_output_preserves_voice_completion(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        _multimodal, _audio, voice, pipeline = create_pipeline(runtime)

        runtime.speech_pipeline.process_mock_output(pipeline.pipeline_session_id, "hello")

        self.assertEqual(runtime.voice.get_session(voice.session_id).status, "idle")

    def test_summary(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        *_, pipeline = create_pipeline(runtime)

        runtime.speech_pipeline.process_mock_input(pipeline.pipeline_session_id, "input")
        runtime.speech_pipeline.process_mock_output(pipeline.pipeline_session_id, "output")
        summary = runtime.speech_pipeline.summarize_session(pipeline.pipeline_session_id)

        self.assertEqual(summary.input_turn_count, 1)
        self.assertEqual(summary.output_turn_count, 1)
        self.assertEqual(summary.latest_input.transcript, "input")
        self.assertEqual(summary.latest_output.text, "output")

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        *_, pipeline = create_pipeline(runtime)

        sessions = runtime.commands.execute(runtime.context(), "/speech-sessions")
        detail = runtime.commands.execute(
            runtime.context(),
            f"/speech-session {pipeline.pipeline_session_id}",
        )
        summary = runtime.commands.execute(
            runtime.context(),
            f"/speech-summary {pipeline.pipeline_session_id}",
        )

        self.assertEqual(sessions.status, "ok")
        self.assertEqual(detail.data["session"]["pipeline_session_id"], pipeline.pipeline_session_id)
        self.assertEqual(summary.data["summary"]["input_turn_count"], 0)

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        audio = runtime.audio.create_session(agent_id="artemis")
        voice = runtime.voice.create_session("artemis")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post(
            "/api/speech/sessions",
            json={"audio_session_id": audio.session_id, "voice_session_id": voice.session_id},
        )
        session_id = created.json()["pipeline_session_id"]

        self.assertEqual(created.status_code, 200)
        self.assertEqual(client.get("/api/speech/sessions").status_code, 200)
        self.assertEqual(client.get(f"/api/speech/sessions/{session_id}").status_code, 200)
        self.assertEqual(client.post(f"/api/speech/sessions/{session_id}/pause").json()["status"], "paused")
        self.assertEqual(client.post(f"/api/speech/sessions/{session_id}/resume").json()["status"], "idle")
        self.assertEqual(
            client.post(f"/api/speech/sessions/{session_id}/input/mock").status_code,
            404,
        )
        self.assertEqual(
            client.post(f"/api/speech/sessions/{session_id}/output/mock").status_code,
            404,
        )
        self.assertEqual(client.get(f"/api/speech/sessions/{session_id}/summary").status_code, 200)
        self.assertEqual(client.post(f"/api/speech/sessions/{session_id}/close").json()["status"], "closed")

    def test_health_and_readiness_include_speech_pipeline(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        create_pipeline(runtime)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.speech_pipeline_runtime_available)
        self.assertEqual(health.speech_pipeline_sessions_count, 1)
        self.assertIn("speech_pipeline.ready", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
