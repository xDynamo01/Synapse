from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_test_agent
from synapse.agent_tool_calling.parser import parse_explicit_json_block
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.models.types import ModelResponse

TOOL_JSON = json.dumps(
    {
        "synapse_tool_intent": {
            "tool_id": "health.summary",
            "arguments": {},
            "reason": "Check system health",
        }
    }
)


class StaticAdapter:
    provider = "mock"

    def __init__(self, content: str) -> None:
        self.content = content

    def generate(self, request_payload) -> ModelResponse:
        return ModelResponse(
            content=self.content,
            provider="mock",
            model=request_payload.model,
            metadata={"static": True},
        )


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
    (settings.data_dir / "config" / "permissions.yaml").write_text(
        json.dumps(
            {
                "subjects": {
                    "local_owner": ["*"],
                    "user:local_owner": ["*"],
                    "agent:artemis": ["*"],
                }
            }
        ),
        encoding="utf-8",
    )
    seed_test_agent(
        settings.data_dir,
        "artemis",
        role="assistant",
        extra={"preferred_model": "mock/synapse-test"},
    )
    return directory, settings, create_runtime(settings)


class AgentToolCallingParserTests(unittest.TestCase):
    def test_no_tool_intent(self) -> None:
        result = parse_explicit_json_block("No tool is needed.")

        self.assertFalse(result.found)
        self.assertEqual(result.proposals, [])
        self.assertEqual(result.errors, [])

    def test_valid_tool_intent(self) -> None:
        result = parse_explicit_json_block(TOOL_JSON)

        self.assertTrue(result.found)
        self.assertEqual(result.proposals[0].tool_id, "health.summary")
        self.assertEqual(result.proposals[0].reason, "Check system health")

    def test_invalid_json(self) -> None:
        result = parse_explicit_json_block('```json\n{"synapse_tool_intent":\n```')

        self.assertFalse(result.found)
        self.assertTrue(result.errors)

    def test_multiple_tool_intents(self) -> None:
        result = parse_explicit_json_block(
            json.dumps(
                {
                    "synapse_tool_intent": [
                        {"tool_id": "health.summary", "arguments": {}},
                        {"tool_id": "readiness.summary", "arguments": {}},
                    ]
                }
            )
        )

        self.assertEqual([proposal.tool_id for proposal in result.proposals], [
            "health.summary",
            "readiness.summary",
        ])


class AgentToolCallingRuntimeTests(unittest.TestCase):
    def test_create_intent_from_output_without_execution(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.agent_tool_calling.create_intents_from_output("artemis", TOOL_JSON)

        self.assertEqual(len(result.created_intents), 1)
        self.assertEqual(runtime.tool_intents.list_intents()[0].tool_id, "health.summary")
        self.assertEqual(runtime.tool_runtime.execution_counts, {})
        self.assertEqual(runtime.approvals.list_pending(), [])

    def test_missing_tool_is_reported(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        text = json.dumps(
            {"synapse_tool_intent": {"tool_id": "missing.tool", "arguments": {}}}
        )

        result = runtime.agent_tool_calling.create_intents_from_output("artemis", text)

        self.assertEqual(result.created_intents, [])
        self.assertTrue(any("not found" in error.lower() for error in result.errors))

    def test_preview_does_not_create_intent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.agent_tool_calling.preview_tool_calling("artemis", TOOL_JSON)

        self.assertEqual(result.created_intents, [])
        self.assertEqual(result.metadata["proposal_count"], 1)
        self.assertEqual(runtime.tool_intents.list_intents(), [])

    def test_disabled_policy_keeps_agent_runtime_inert(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.models.adapters["mock"] = StaticAdapter(TOOL_JSON)

        turn = runtime.chat.send_message(runtime.context(), "artemis", "status")

        self.assertEqual(runtime.tool_intents.list_intents(), [])
        self.assertEqual(runtime.tool_runtime.execution_counts, {})
        self.assertEqual(turn.message.metadata["tool_calling_result"]["metadata"]["mode"], "disabled")

    def test_create_intent_policy_creates_but_does_not_execute(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        (settings.data_dir / "config" / "agent_tool_calling_policy.yaml").write_text(
            json.dumps({"enabled": True, "mode": "create_intent"}),
            encoding="utf-8",
        )
        runtime.models.adapters["mock"] = StaticAdapter(TOOL_JSON)

        turn = runtime.chat.send_message(runtime.context(), "artemis", "status")

        self.assertEqual(len(runtime.tool_intents.list_intents()), 1)
        self.assertEqual(runtime.tool_runtime.execution_counts, {})
        self.assertEqual(len(turn.message.metadata["tool_calling_result"]["created_intents"]), 1)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        context = runtime.context()

        preview = runtime.commands.execute(
            context,
            f"/tool-call-preview artemis '{TOOL_JSON}'",
        )
        created = runtime.commands.execute(
            context,
            f"/tool-call-create artemis '{TOOL_JSON}'",
        )

        self.assertEqual(preview.status, "ok")
        self.assertEqual(created.status, "ok")
        self.assertEqual(len(created.data["result"]["created_intents"]), 1)
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        preview = client.post(
            "/api/agents/artemis/tool-call/preview",
            json={"text": TOOL_JSON},
        )
        created = client.post(
            "/api/agents/artemis/tool-call/create",
            json={"text": TOOL_JSON},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(len(created.json()["created_intents"]), 1)
        self.assertEqual(runtime.tool_runtime.execution_counts, {})

    def test_health_and_readiness(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.agent_tool_calling_runtime_available)
        self.assertIn("agent_tool_calling.ready", {check.id for check in readiness.checks})


if __name__ == "__main__":
    unittest.main()
