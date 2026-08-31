from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_delegation_pair
from synapse.agents.runtime import AgentRunResult
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import load_structured_file

DEFAULT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "filesystem.search",
    "agents.message",
    "delegation.create",
    "tasks.create",
    "tasks.update",
    "web.search",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_agent_config(settings: Settings, agent_id: str, **updates) -> None:
    path = settings.data_dir / "agents" / agent_id / "CONFIG.yaml"
    config = load_structured_file(path)
    config.update(updates)
    write_json(path, config)


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
    seed_delegation_pair(
        settings.data_dir,
        delegator_extra={"permissions": DEFAULT_PERMISSIONS},
        delegate_extra={
            "permissions": DEFAULT_PERMISSIONS,
            "preferred_tools": ["send_agent_message"],
            "forbidden_tools": ["write_file"],
        },
    )
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {
            "subjects": {
                "local_owner": ["*"],
                "user:local_owner": ["*"],
                "agent:artemis": DEFAULT_PERMISSIONS,
                "agent:researcher": DEFAULT_PERMISSIONS,
            }
        },
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Agent Multimodal Bridge Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    update_agent_config(
        settings,
        "artemis",
        permissions=DEFAULT_PERMISSIONS,
        capabilities={"allow": ["agent.task.delegation"], "deny": []},
    )
    update_agent_config(
        settings,
        "researcher",
        permissions=DEFAULT_PERMISSIONS,
        preferred_tools=["send_agent_message"],
        forbidden_tools=["write_file"],
    )
    return directory, settings, create_runtime(settings)


def capture_agent_context(runtime):
    captured = {}

    def fake_run(**kwargs):
        captured["loaded_context"] = kwargs["loaded_context"]
        return AgentRunResult(
            agent_id=kwargs["agent_id"],
            response="captured",
            model={"provider": "test", "model": "mock", "metadata": {}},
        )

    runtime.agent_runtime.run = fake_run
    return captured


def create_conversation(runtime, metadata: dict | None = None):
    return runtime.conversations.create_conversation(
        runtime.context(),
        ["artemis", "researcher"],
        title="Bridge conversation",
        metadata=metadata or {},
    )


class AgentMultimodalContextBridgeTests(unittest.TestCase):
    def test_loaded_context_accepts_multimodal_context(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        loaded = runtime.context_loader.load(
            runtime.context(),
            "researcher",
            multimodal_context={"snapshot": {"source": "test"}},
        )

        self.assertEqual(loaded.multimodal_context["snapshot"]["source"], "test")
        self.assertEqual(loaded.to_dict()["multimodal_context"]["snapshot"]["source"], "test")

    def test_old_context_without_multimodal_context_remains_compatible(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        loaded = runtime.context_loader.load(runtime.context(), "researcher")

        self.assertIsNone(loaded.multimodal_context)
        self.assertIn("multimodal_context", loaded.to_dict())

    def test_worker_attaches_multimodal_context_for_conversation(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        captured = capture_agent_context(runtime)
        multimodal = runtime.multimodal.create_session(["artemis", "researcher"], ["text"])
        conversation = create_conversation(runtime, {"multimodal_session_id": multimodal.session_id})
        runtime.perception.create_signal(
            "speech",
            "audio",
            {"text": "hello"},
            multimodal_session_id=multimodal.session_id,
            metadata={"conversation_id": conversation.conversation_id},
        )
        runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Bridge",
            body="Use fused context",
            conversation_id=conversation.conversation_id,
        )

        runtime.worker.process_inbox(runtime.context(), "researcher")

        loaded = captured["loaded_context"]
        self.assertIsNotNone(loaded.multimodal_context)
        self.assertEqual(
            loaded.multimodal_context["snapshot"]["interaction_context"]["conversation_id"],
            conversation.conversation_id,
        )
        self.assertEqual(
            loaded.multimodal_context["snapshot"]["interaction_context"]["multimodal_session_id"],
            multimodal.session_id,
        )
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("agent.multimodal_context.attached", event_types)

    def test_worker_attaches_multimodal_context_for_mission_delegation(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        captured = capture_agent_context(runtime)
        mission = runtime.missions.create_mission(
            "Mission",
            status="active",
            owner_agent_id="artemis",
        )
        task = runtime.delegation.create_task(
            runtime.context(actor_id="artemis", actor_type="agent"),
            title="Mission task",
            description="Handle mission work.",
            requester_agent_id="artemis",
            assignee_agent_id="researcher",
            mission_id=mission.mission_id,
        )
        runtime.delegation.accept_task(runtime.context(), task.task_id)
        runtime.delegation.start_task(runtime.context(), task.task_id)

        runtime.worker.process_delegations(runtime.context(), "researcher")

        loaded = captured["loaded_context"]
        self.assertIsNotNone(loaded.multimodal_context)
        self.assertEqual(
            loaded.multimodal_context["snapshot"]["interaction_context"]["mission_id"],
            mission.mission_id,
        )

    def test_worker_ignores_multimodal_context_when_policy_disabled(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        captured = capture_agent_context(runtime)
        write_json(
            settings.data_dir / "config" / "multimodal_context_policy.yaml",
            {"multimodal_context": {"enabled": False}},
        )
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Disabled",
            body="No multimodal context",
        )

        runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertIsNone(captured["loaded_context"].multimodal_context)
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("agent.multimodal_context.skipped", event_types)
        self.assertEqual(runtime.conversations.message_status(message.id).status, "acknowledged")

    def test_absence_of_signals_does_not_break_worker(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        captured = capture_agent_context(runtime)
        runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="No signals",
            body="Still process",
        )

        result = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(result[0].status, "processed")
        self.assertIsNotNone(captured["loaded_context"].multimodal_context)
        self.assertIn(
            "signals",
            captured["loaded_context"].multimodal_context["consistency"]["missing_sources"],
        )

    def test_context_fusion_failure_does_not_break_worker(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        captured = capture_agent_context(runtime)
        runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Failure",
            body="Context fusion fails",
        )

        def fail_build_context(**kwargs):
            raise RuntimeError("fusion unavailable")

        runtime.context_fusion.build_context = fail_build_context

        result = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(result[0].status, "processed")
        self.assertIsNone(captured["loaded_context"].multimodal_context)
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("agent.multimodal_context.failed", event_types)

    def test_command_agent_context_preview(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)

        result = runtime.commands.execute(
            runtime.context(),
            f"/agent-context-preview researcher {conversation.conversation_id}",
        )
        policy = runtime.commands.execute(runtime.context(), "/agent-multimodal-policy")

        self.assertEqual(result.status, "ok")
        self.assertIn("multimodal_context", result.data["context"])
        self.assertEqual(policy.status, "ok")
        self.assertTrue(policy.data["policy"]["enabled"])

    def test_api_context_preview(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = create_conversation(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        preview = client.get(
            f"/api/agents/researcher/context-preview/{conversation.conversation_id}"
        )
        policy = client.get("/api/agent-multimodal-policy")

        self.assertEqual(preview.status_code, 200)
        self.assertIn("multimodal_context", preview.json())
        self.assertEqual(policy.status_code, 200)
        self.assertTrue(policy.json()["enabled"])

    def test_health_and_readiness_include_agent_bridge(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.agent_multimodal_bridge_available)
        self.assertIn("agent_multimodal_bridge.ready", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
