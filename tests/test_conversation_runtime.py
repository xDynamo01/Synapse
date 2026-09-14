from __future__ import annotations

import hashlib
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
            "name": "Synapse V2 Conversation Test",
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


class ConversationRuntimeTests(unittest.TestCase):
    def test_update_revision_participants_and_conflict(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(), ["artemis"], title="Initial"
        )
        updated = runtime.conversations.update_conversation(
            runtime.context(),
            conversation.conversation_id,
            title="Updated",
            expected_revision=conversation.revision,
        )
        joined = runtime.conversations.add_participant(
            runtime.context(), updated.conversation_id, "atlas"
        )

        self.assertEqual(updated.revision, conversation.revision + 1)
        self.assertIn("atlas", joined.participants)
        with self.assertRaisesRegex(Exception, "revision mismatch"):
            runtime.conversations.update_conversation(
                runtime.context(), conversation.conversation_id, expected_revision=1
            )

    def test_messages_are_idempotent_paginated_and_cancellable(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(), ["artemis", "atlas"]
        )
        first = runtime.conversations.send_message(
            runtime.context(),
            "artemis",
            "atlas",
            {"body": "one"},
            conversation.conversation_id,
            idempotency_key="turn-1",
        )
        duplicate = runtime.conversations.send_message(
            runtime.context(),
            "artemis",
            "atlas",
            {"body": "one"},
            conversation.conversation_id,
            idempotency_key="turn-1",
        )
        runtime.conversations.send_message(
            runtime.context(), "atlas", "artemis", {"body": "two"}, conversation.conversation_id
        )

        self.assertEqual(first.message_id, duplicate.message_id)
        self.assertEqual(
            runtime.conversations.list_conversation_messages(
                conversation.conversation_id, offset=1, limit=1
            )[0].payload["body"],
            "two",
        )
        self.assertEqual(
            runtime.conversations.cancel_message(runtime.context(), first.message_id).status,
            "cancelled",
        )

    def test_attachment_metadata_is_validated_and_persisted(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(runtime.context(), ["artemis"])
        source = runtime.data_dir.resolve("attachments/note.txt")
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("note", encoding="utf-8")
        attachment = runtime.conversations.register_attachment(
            runtime.context(),
            conversation.conversation_id,
            filename="note.txt",
            mime_type="text/plain",
            size=4,
            storage_ref="attachments/note.txt",
            checksum=hashlib.sha256(b"note").hexdigest(),
            owner_id="local_owner",
        )

        self.assertEqual(attachment.filename, "note.txt")
        self.assertEqual(len(runtime.conversations.list_attachments(conversation.conversation_id)), 1)
        with self.assertRaisesRegex(Exception, "attachment_invalid"):
            runtime.conversations.register_attachment(
                runtime.context(),
                conversation.conversation_id,
                filename="../escape.txt",
                mime_type="text/plain",
                size=1,
                storage_ref="attachments/note.txt",
                checksum="x",
                owner_id="local_owner",
            )

        with self.assertRaisesRegex(Exception, "checksum does not match"):
            runtime.conversations.register_attachment(
                runtime.context(),
                conversation.conversation_id,
                filename="note.txt",
                mime_type="text/plain",
                size=4,
                storage_ref="attachments/note.txt",
                checksum="0" * 64,
                owner_id="local_owner",
            )

    def test_delete_requires_explicit_confirmation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(runtime.context(), ["artemis"])

        with self.assertRaisesRegex(Exception, "explicit confirmation"):
            runtime.conversations.delete_conversation(
                runtime.context(), conversation.conversation_id
            )
        runtime.conversations.delete_conversation(
            runtime.context(), conversation.conversation_id, confirmed=True
        )

    def test_canonical_agent_turn_persists_both_messages(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(), ["local_chat", "atlas"]
        )

        runtime.chat.submit_turn(
            runtime.context(),
            conversation_id=conversation.conversation_id,
            content="hello",
            target_agent_id="atlas",
        )

        messages = runtime.conversations.list_conversation_messages(conversation.conversation_id)
        self.assertEqual([item.role for item in messages], ["user", "assistant"])
        self.assertEqual([item.status for item in messages], ["completed", "completed"])

    def test_stream_contract_uses_real_complete_response_chunk(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(), ["local_chat", "atlas"]
        )

        events = list(
            runtime.chat.stream_turn(
                runtime.context(),
                conversation_id=conversation.conversation_id,
                content="hello",
                target_agent_id="atlas",
            )
        )

        self.assertEqual(
            [event["type"] for event in events],
            ["turn_started", "generation_started", "chunk_received", "generation_completed"],
        )
        self.assertEqual(events[2]["streaming_mode"], "progressive")

    def test_create_and_list_conversation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        conversation = runtime.conversations.create_conversation(
            runtime.context(),
            ["artemis", "atlas"],
            title="Planning",
        )
        conversations = runtime.conversations.list_conversations()

        self.assertEqual(conversation.status, "active")
        self.assertIn(conversation.conversation_id, {item.conversation_id for item in conversations})
        self.assertTrue(
            runtime.data_dir.resolve(
                f"conversations/{conversation.conversation_id}/CONVERSATION.yaml"
            ).exists()
        )

    def test_send_message_starts_pending(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="atlas",
            subject="Hello",
            body="Hello Atlas",
        )
        conversation_message = runtime.conversations.message_status(message.id)

        self.assertEqual(conversation_message.status, "pending")
        self.assertEqual(conversation_message.payload["body"], "Hello Atlas")

    def test_delivered_and_acknowledged_statuses(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="atlas",
            subject="Status",
            body="Track me",
        )

        delivered = runtime.communication.mark_read(runtime.context(), "atlas", message.id)
        conversation_delivered = runtime.conversations.message_status(message.id)
        acknowledged = runtime.communication.mark_processed(runtime.context(), "atlas", message.id)
        conversation_acknowledged = runtime.conversations.message_status(message.id)

        self.assertEqual(delivered.status, "read")
        self.assertEqual(conversation_delivered.status, "delivered")
        self.assertEqual(acknowledged.status, "processed")
        self.assertEqual(conversation_acknowledged.status, "acknowledged")

    def test_failed_status(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="atlas",
            subject="Failure",
            body="Fail me",
        )

        runtime.communication.mark_failed(runtime.context(), "atlas", message.id)
        conversation_message = runtime.conversations.message_status(message.id)

        self.assertEqual(conversation_message.status, "failed")

    def test_archived_agent_does_not_receive_message(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.archive_agent("atlas", runtime.context(), _skip_policy=True)

        with self.assertRaisesRegex(Exception, "archived"):
            runtime.communication.send_agent_message(
                runtime.context(),
                from_agent_id="artemis",
                to_agent_id="atlas",
                body="Blocked",
            )

    def test_deactivated_agent_does_not_receive_message(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.admin.deactivate_agent("atlas", runtime.context(), _skip_policy=True)

        with self.assertRaisesRegex(Exception, "not active"):
            runtime.communication.send_agent_message(
                runtime.context(),
                from_agent_id="artemis",
                to_agent_id="atlas",
                body="Blocked",
            )

    def test_correlation_id_is_preserved(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with correlation_scope(new_correlation("test", correlation_id="corr-conversation")):
            message = runtime.communication.send_agent_message(
                runtime.context(),
                from_agent_id="artemis",
                to_agent_id="atlas",
                body="Trace me",
            )

        conversation_message = runtime.conversations.message_status(message.id)

        self.assertEqual(conversation_message.correlation_id, "corr-conversation")

    def test_events_are_emitted(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        message = runtime.communication.send_agent_message(
            runtime.context(),
            from_agent_id="artemis",
            to_agent_id="atlas",
            body="Events",
        )
        runtime.communication.mark_read(runtime.context(), "atlas", message.id)
        runtime.communication.mark_processed(runtime.context(), "atlas", message.id)
        runtime.communication.mark_failed(runtime.context(), "atlas", message.id)

        event_types = [event.type for event in runtime.events.tail(limit=100)]
        self.assertIn("conversation.created", event_types)
        self.assertIn("message.sent", event_types)
        self.assertIn("message.delivered", event_types)
        self.assertIn("message.acknowledged", event_types)
        self.assertIn("message.failed", event_types)

    def test_commands_work(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        sent = runtime.commands.execute(
            runtime.context(),
            '/send-agent-message artemis atlas "hello from command"',
        )
        listed = runtime.commands.execute(runtime.context(), "/conversations")
        conversation_id = sent.data["conversation_message"]["conversation_id"]
        detail = runtime.commands.execute(runtime.context(), f"/conversation {conversation_id}")
        messages = runtime.commands.execute(
            runtime.context(),
            f"/conversation-messages {conversation_id}",
        )

        self.assertEqual(sent.status, "ok")
        self.assertEqual(listed.status, "ok")
        self.assertEqual(detail.status, "ok")
        self.assertEqual(messages.status, "ok")
        self.assertEqual(len(messages.data["messages"]), 1)

    def test_api_works(self) -> None:
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
            "/api/conversations",
            json={"participants": ["artemis", "atlas"], "title": "API"},
        )
        sent = client.post(
            "/api/messages/send",
            json={
                "sender_agent_id": "artemis",
                "receiver_agent_id": "atlas",
                "conversation_id": created.json()["conversation_id"],
                "subject": "API",
                "body": "API message",
            },
        )
        ack = client.post(f"/api/messages/{sent.json()['message_id']}/ack")
        messages = client.get(f"/api/conversations/{created.json()['conversation_id']}/messages")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(ack.status_code, 200)
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(messages.json()[0]["status"], "acknowledged")


if __name__ == "__main__":
    unittest.main()
