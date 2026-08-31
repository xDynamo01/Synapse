from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

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
    create_runtime(settings)
    permissions = {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:artemis": ["*"],
            "agent:atlas": ["*"],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Conversation Summary Test",
            "mode": "test",
            "default_agent_id": "artemis",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    seed_test_agent(settings.data_dir, "artemis", role="orchestrator", can_delegate=True)
    seed_test_agent(settings.data_dir, "atlas", role="assistant")
    return directory, create_runtime(settings)


def send_message(runtime, body: str = "First message"):
    legacy = runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id="atlas",
        subject="Summary test",
        body=body,
    )
    return runtime.conversations.message_status(legacy.id)


def send_message_in_conversation(runtime, conversation_id: str, body: str):
    legacy = runtime.communication.send_agent_message(
        runtime.context(),
        from_agent_id="artemis",
        to_agent_id="atlas",
        subject="Summary test",
        body=body,
        conversation_id=conversation_id,
    )
    return runtime.conversations.message_status(legacy.id)


class ConversationSummaryTests(unittest.TestCase):
    def test_generate_summary_uses_configured_model(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime, "Summarize this")

        summary = runtime.chat.generate_conversation_summary(
            runtime.context(), message.conversation_id, "artemis"
        )

        self.assertTrue(summary.summary)
        self.assertEqual(summary.metadata["generated_by"], "model")
        self.assertEqual(summary.source_message_ids, [message.message_id])
        self.assertEqual(summary.model, "synapse-test")
        self.assertEqual(summary.provider, "mock")

    def test_missing_summary_returns_clear_state(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime)

        summary = runtime.conversations.get_conversation_summary(message.conversation_id)

        self.assertEqual(summary.summary, "")
        self.assertFalse(summary.metadata["exists"])
        self.assertEqual(summary.message_count, 1)

    def test_update_summary_persists_markdown_and_yaml(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime)

        summary = runtime.conversations.update_conversation_summary(
            message.conversation_id,
            "Agents agreed on the next task.",
        )
        loaded = runtime.conversations.get_conversation_summary(message.conversation_id)
        summary_md = runtime.data_dir.resolve(
            f"conversations/{message.conversation_id}/SUMMARY.md"
        )
        summary_yaml = runtime.data_dir.resolve(
            f"conversations/{message.conversation_id}/SUMMARY.yaml"
        )

        self.assertEqual(summary.summary, "Agents agreed on the next task.")
        self.assertEqual(loaded.summary, summary.summary)
        self.assertTrue(summary_md.exists())
        self.assertTrue(summary_yaml.exists())
        self.assertIn("Agents agreed", summary_md.read_text(encoding="utf-8"))

    def test_no_heuristic_summary_is_exposed_in_production(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime, "Collect the files")
        send_message_in_conversation(runtime, message.conversation_id, "Prepare the index")

        self.assertFalse(hasattr(runtime.conversations, "generate_mock_summary"))
        summary = runtime.conversations.get_conversation_summary(message.conversation_id)
        self.assertEqual(summary.summary, "")
        self.assertFalse(summary.metadata["exists"])

    def test_build_context_includes_summary_and_recent_messages(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime, "Message one")
        send_message_in_conversation(runtime, message.conversation_id, "Message two")
        runtime.conversations.update_conversation_summary(
            message.conversation_id,
            "Short summary.",
        )

        context = runtime.conversations.build_conversation_context(
            message.conversation_id,
            max_messages=1,
        )

        self.assertEqual(context["summary"]["summary"], "Short summary.")
        self.assertEqual(len(context["messages"]), 1)
        self.assertEqual(context["messages"][0]["payload"]["body"], "Message two")
        self.assertEqual(context["participants"], ["artemis", "atlas"])

    def test_commands_work(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime)

        missing = runtime.commands.execute(
            runtime.context(),
            f"/conversation-summary {message.conversation_id}",
        )
        updated = runtime.commands.execute(
            runtime.context(),
            f'/update-conversation-summary {message.conversation_id} "Command summary"',
        )
        context = runtime.commands.execute(
            runtime.context(),
            f"/build-conversation-context {message.conversation_id}",
        )

        self.assertEqual(missing.status, "ok")
        self.assertFalse(missing.data["summary"]["metadata"]["exists"])
        self.assertEqual(updated.status, "ok")
        self.assertEqual(context.status, "ok")
        self.assertEqual(context.data["context"]["summary"]["summary"], "Command summary")

    def test_api_summary_and_context_work(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        missing = client.get(f"/api/conversations/{message.conversation_id}/summary")
        updated = client.post(
            f"/api/conversations/{message.conversation_id}/summary",
            json={"summary": "API summary"},
        )
        context = client.get(f"/api/conversations/{message.conversation_id}/context")

        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.json()["metadata"]["exists"])
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.json()["summary"]["summary"], "API summary")

    def test_events_are_emitted(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = send_message(runtime)

        runtime.conversations.update_conversation_summary(message.conversation_id, "Event summary")
        runtime.conversations.build_conversation_context(message.conversation_id)

        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("conversation.summary.updated", event_types)
        self.assertIn("conversation.context.built", event_types)


if __name__ == "__main__":
    unittest.main()
