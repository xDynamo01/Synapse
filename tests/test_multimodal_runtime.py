from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

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
    create_runtime(settings)
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Multimodal Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    return directory, create_runtime(settings)


class MultimodalRuntimeTests(unittest.TestCase):
    def test_create_session(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        session = runtime.multimodal.create_session(
            participants=["user", "agent"],
            active_channels=["text", "voice"],
            metadata={"conversation_id": "conversation-1"},
        )

        self.assertEqual(session.status, "active")
        self.assertIn("voice", session.active_channels)
        self.assertEqual(session.metadata["conversation_id"], "conversation-1")

    def test_list_sessions(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.multimodal.create_session(["one"], ["text"])
        runtime.multimodal.create_session(["two"], ["system"])

        sessions = runtime.multimodal.list_sessions()

        self.assertEqual(len(sessions), 2)

    def test_pause_resume_and_close_session(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.multimodal.create_session(["user"], ["text"])

        paused = runtime.multimodal.pause_session(session.session_id)
        resumed = runtime.multimodal.resume_session(session.session_id)
        closed = runtime.multimodal.close_session(session.session_id)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(resumed.status, "active")
        self.assertEqual(closed.status, "closed")

    def test_emit_event(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.multimodal.create_session(["user"], ["text"])

        event = runtime.multimodal.emit_event(
            session.session_id,
            channel="text",
            event_type="message",
            source="user",
            payload={"text": "hello"},
            metadata={"provider_id": "mock_stt"},
        )

        self.assertEqual(event.channel, "text")
        self.assertEqual(event.payload["text"], "hello")
        self.assertEqual(event.metadata["provider_id"], "mock_stt")

    def test_list_session_events(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.multimodal.create_session(["user"], ["text"])
        runtime.multimodal.emit_event(session.session_id, "text", "message", "user", {"n": 1})
        runtime.multimodal.emit_event(session.session_id, "text", "message", "agent", {"n": 2})

        events = runtime.multimodal.list_session_events(session.session_id)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].source, "agent")

    def test_supported_channels(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        channels = runtime.multimodal.get_supported_channels()

        self.assertIn("text", channels)
        self.assertIn("audio", channels)
        self.assertIn("vision", channels)
        self.assertNotIn("avatar", channels)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.multimodal.create_session(["user"], ["text"])

        sessions = runtime.commands.execute(runtime.context(), "/multimodal-sessions")
        detail = runtime.commands.execute(
            runtime.context(),
            f"/multimodal-session {session.session_id}",
        )
        channels = runtime.commands.execute(runtime.context(), "/multimodal-channels")

        self.assertEqual(sessions.status, "ok")
        self.assertEqual(detail.data["session"]["session_id"], session.session_id)
        self.assertIn("voice", channels.data["channels"])

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post(
            "/api/multimodal/sessions",
            json={"participants": ["user"], "active_channels": ["text"]},
        )
        session_id = created.json()["session_id"]
        runtime.multimodal.emit_event(session_id, "text", "message", "user", {"text": "hi"})

        self.assertEqual(created.status_code, 200)
        self.assertEqual(client.get("/api/multimodal/sessions").status_code, 200)
        self.assertEqual(client.get(f"/api/multimodal/sessions/{session_id}").status_code, 200)
        self.assertEqual(
            client.post(f"/api/multimodal/sessions/{session_id}/pause").json()["status"],
            "paused",
        )
        self.assertEqual(
            client.post(f"/api/multimodal/sessions/{session_id}/resume").json()["status"],
            "active",
        )
        self.assertEqual(
            client.post(f"/api/multimodal/sessions/{session_id}/close").json()["status"],
            "closed",
        )
        self.assertEqual(len(client.get(f"/api/multimodal/sessions/{session_id}/events").json()), 1)
        self.assertIn("text", client.get("/api/multimodal/channels").json())

    def test_health_and_readiness_include_multimodal(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.multimodal_runtime_available)
        self.assertIn("multimodal.ready", [check.id for check in readiness.checks])
