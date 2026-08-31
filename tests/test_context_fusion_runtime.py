from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.audio.models import SpeechFeatures, SpeechToTextResult
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
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"], "agent:orchestrator": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Context Fusion Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    write_json(
        settings.data_dir / "agents" / "orchestrator" / "CONFIG.yaml",
        {
            "id": "orchestrator",
            "name": "Orchestrator",
            "role": "test_agent",
            "permissions": ["agents.message", "delegation.create"],
        },
    )
    return directory, create_runtime(settings)


def create_conversation(runtime):
    context = runtime.context()
    conversation = runtime.conversations.create_conversation(
        context,
        participants=["orchestrator"],
        title="Fusion conversation",
    )
    runtime.conversations.send_message(
        context,
        sender_agent_id="orchestrator",
        receiver_agent_id="orchestrator",
        payload={"body": "hello"},
        conversation_id=conversation.conversation_id,
    )
    return conversation


class ContextFusionRuntimeTests(unittest.TestCase):
    def test_build_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        runtime.perception.signal_from_speech_to_text(
            SpeechToTextResult(
                text="hello",
                confidence=0.9,
                provider_id="mock_stt",
                duration_ms=1200,
                speech_features=SpeechFeatures(
                    duration_ms=1200,
                    speech_rate=100.0,
                    pause_count=0,
                    pause_duration_ms=0,
                    silence_ratio=0.0,
                    segment_count=1,
                    timestamps=[{"start": 0.0, "end": 1.2, "text": "hello"}],
                    language_confidence=0.97,
                    provider_metadata={"provider": "mock_stt"},
                ),
            ),
            multimodal_session_id=multimodal.session_id,
        )

        result = runtime.context_fusion.build_context(multimodal_session_id=multimodal.session_id)

        self.assertEqual(result.snapshot.interaction_context.multimodal_session_id, multimodal.session_id)
        self.assertTrue(result.consistency.complete)
        self.assertEqual(len(result.snapshot.signal_group.speech_signals), 1)
        self.assertEqual(len(result.snapshot.speech_features), 1)

    def test_build_conversation_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)
        runtime.perception.signal_from_speech_to_text(
            SpeechToTextResult(
                text="hello",
                confidence=0.9,
                provider_id="mock_stt",
                duration_ms=1200,
                speech_features=SpeechFeatures(
                    duration_ms=1200,
                    speech_rate=100.0,
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
            metadata={"conversation_id": conversation.conversation_id},
        )

        result = runtime.context_fusion.build_conversation_context(conversation.conversation_id)

        self.assertEqual(result.snapshot.interaction_context.conversation_id, conversation.conversation_id)
        self.assertEqual(result.snapshot.interaction_context.participants, ["orchestrator"])
        self.assertEqual(len(result.snapshot.latest_messages), 1)
        self.assertTrue(result.consistency.complete)
        self.assertEqual(len(result.snapshot.speech_features), 1)

    def test_build_mission_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)
        mission = runtime.missions.create_mission(
            title="Mission",
            status="active",
            conversation_id=conversation.conversation_id,
        )

        result = runtime.context_fusion.build_mission_context(mission.mission_id)

        self.assertEqual(result.snapshot.interaction_context.mission_id, mission.mission_id)
        self.assertIsNotNone(result.snapshot.mission_summary)
        self.assertIsNotNone(result.snapshot.delegation_summary)

    def test_build_multimodal_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])

        result = runtime.context_fusion.build_multimodal_context(multimodal.session_id)

        self.assertEqual(result.snapshot.interaction_context.participants, ["user"])
        self.assertIn("signals", result.consistency.missing_sources)

    def test_validate_context_complete(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        runtime.perception.create_signal(
            "system",
            "test",
            {"ok": True},
            multimodal_session_id=multimodal.session_id,
        )
        result = runtime.context_fusion.build_multimodal_context(multimodal.session_id)

        consistency = runtime.context_fusion.validate_context(result.snapshot)

        self.assertTrue(consistency.complete)

    def test_validate_context_incomplete(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.context_fusion.build_context(persist_snapshot=False)

        self.assertFalse(result.consistency.complete)
        self.assertIn("participants", result.consistency.missing_sources)
        self.assertIn("signals", result.consistency.missing_sources)

    def test_summarize_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        runtime.perception.create_signal("speech", "audio", {"text": "hello"}, multimodal_session_id=multimodal.session_id)
        result = runtime.context_fusion.build_multimodal_context(multimodal.session_id)

        summary = runtime.context_fusion.summarize_context(result)

        self.assertEqual(summary["participants"], 1)
        self.assertEqual(summary["signals"], 1)

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)
        mission = runtime.missions.create_mission("Mission", status="active", conversation_id=conversation.conversation_id)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        runtime.perception.create_signal("speech", "audio", {"text": "hello"}, multimodal_session_id=multimodal.session_id)

        conversation_result = runtime.commands.execute(runtime.context(), f"/context-fusion {conversation.conversation_id}")
        mission_result = runtime.commands.execute(runtime.context(), f"/context-mission {mission.mission_id}")
        session_result = runtime.commands.execute(runtime.context(), f"/context-session {multimodal.session_id}")
        validate_result = runtime.commands.execute(runtime.context(), f"/context-validate {conversation.conversation_id}")

        self.assertEqual(conversation_result.status, "ok")
        self.assertEqual(mission_result.status, "ok")
        self.assertEqual(session_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)
        mission = runtime.missions.create_mission("Mission", status="active", conversation_id=conversation.conversation_id)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get(f"/api/context/conversation/{conversation.conversation_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/context/mission/{mission.mission_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/context/session/{multimodal.session_id}").status_code, 200)
        self.assertEqual(client.get(f"/api/context/validate/{conversation.conversation_id}").status_code, 200)

    def test_health_and_readiness_include_context_fusion(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.context_fusion_runtime_available)
        self.assertIn("context_fusion.ready", [check.id for check in readiness.checks])
