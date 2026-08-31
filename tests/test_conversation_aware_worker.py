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
from synapse.observability.correlation import correlation_scope, new_correlation

DEFAULT_PERMISSIONS = [
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "filesystem.search",
    "agents.message",
    "tasks.create",
    "tasks.update",
    "web.search",
]


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
            "agent:artemis": DEFAULT_PERMISSIONS,
            "agent:researcher": DEFAULT_PERMISSIONS,
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Conversation Worker Test",
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
    seed_test_agent(
        settings.data_dir,
        "artemis",
        role="orchestrator",
        can_delegate=True,
        extra={"preferred_model": "mock/synapse-test"},
    )
    seed_test_agent(
        settings.data_dir,
        "researcher",
        role="researcher",
        extra={
            "preferred_model": "mock/synapse-test",
            "preferred_tools": ["web_search", "read_file", "send_agent_message"],
            "allowed_tools": ["web_search", "read_file", "send_agent_message"],
            "forbidden_tools": ["write_file"],
            "permissions": DEFAULT_PERMISSIONS,
        },
    )
    return directory, create_runtime(settings)


class ConversationAwareWorkerTests(unittest.TestCase):
    def test_worker_loads_conversation_context(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Context",
            body="Use the conversation context",
        )

        result = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(result[0].status, "processed")
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("worker.conversation_context_loaded", event_types)
        conversation_message = runtime.conversations.message_status(message.id)
        self.assertEqual(conversation_message.status, "acknowledged")

    def test_worker_reply_stays_in_same_conversation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Reply",
            body="Reply in the same thread",
        )
        conversation_id = runtime.conversations.message_status(message.id).conversation_id

        result = runtime.worker.process_inbox(runtime.context(), "researcher")
        messages = runtime.conversations.list_conversation_messages(conversation_id)

        self.assertEqual(result[0].status, "processed")
        self.assertIsNotNone(result[0].reply)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1].conversation_id, conversation_id)
        self.assertEqual(messages[1].causation_id, message.id)
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("worker.conversation_reply_sent", event_types)

    def test_worker_preserves_correlation_id_on_reply(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        with correlation_scope(new_correlation("test", correlation_id="corr-worker-conversation")):
            message = runtime.communication.send_agent_message(
                runtime.context(),
                from_agent_id="artemis",
                to_agent_id="researcher",
                subject="Correlation",
                body="Keep correlation",
            )
        conversation_id = runtime.conversations.message_status(message.id).conversation_id

        runtime.worker.process_inbox(runtime.context(), "researcher")
        messages = runtime.conversations.list_conversation_messages(conversation_id)

        self.assertEqual(messages[0].correlation_id, "corr-worker-conversation")
        self.assertEqual(messages[1].correlation_id, "corr-worker-conversation")

    def test_legacy_message_without_conversation_still_processes(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversations = runtime.communication.conversations
        runtime.communication.conversations = None
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Legacy",
            body="No conversation record",
        )
        runtime.communication.conversations = conversations

        result = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(result[0].status, "processed")
        self.assertEqual(result[0].message_id, message.id)

    def test_conversation_context_failure_marks_message_failed(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="researcher",
            subject="Failure",
            body="Context should fail",
        )

        def fail_context(conversation_id: str, max_messages: int = 10):
            raise RuntimeError(f"context failed for {conversation_id}")

        runtime.conversations.build_conversation_context = fail_context

        result = runtime.worker.process_inbox(runtime.context(), "researcher")

        self.assertEqual(result[0].status, "failed")
        self.assertIn("context failed", result[0].error)
        self.assertEqual(runtime.conversations.message_status(message.id).status, "failed")
        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("worker.conversation_processing_failed", event_types)


if __name__ == "__main__":
    unittest.main()
