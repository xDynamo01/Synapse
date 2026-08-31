from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from factories.agents import seed_delegation_pair
from synapse.core.app import create_runtime
from synapse.core.config import Settings

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
            "name": "Synapse V2 Delegation Completion Test",
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
    seed_delegation_pair(
        settings.data_dir,
        delegator_extra={"permissions": DEFAULT_PERMISSIONS},
        delegate_extra={"permissions": DEFAULT_PERMISSIONS},
    )
    return directory, create_runtime(settings)


def agent_context(runtime, agent_id: str):
    return runtime.context(actor_id=agent_id, actor_type="agent")


def create_task(runtime, description: str = "Prepare result.", conversation_id: str | None = None):
    task = runtime.delegation.create_task(
        context=agent_context(runtime, "artemis"),
        title="Delegated work",
        description=description,
        requester_agent_id="artemis",
        assignee_agent_id="researcher",
        conversation_id=conversation_id,
    )
    runtime.delegation.accept_task(runtime.context(), task.task_id)
    return runtime.delegation.start_task(runtime.context(), task.task_id)


class DelegationCompletionSignalTests(unittest.TestCase):
    def test_canonical_agent_result_path_has_no_removed_domain_dependency(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(),
            ["artemis", "researcher"],
            title="Canonical delegation result",
        )
        task = create_task(runtime, conversation_id=conversation.conversation_id)

        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "completed",
            "Research completed through the canonical path.",
            result="Canonical result",
        )
        completed = runtime.delegation.apply_completion_signal(runtime.context(), task.task_id)
        messages = runtime.conversations.list_conversation_messages(conversation.conversation_id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.metadata["result"], "Canonical result")
        self.assertTrue(
            any(message.payload.get("subject") == "Delegation completion submitted" for message in messages)
        )
        self.assertIsNone(importlib.util.find_spec("synapse.communication"))
        self.assertIsNone(importlib.util.find_spec("synapse.email"))

    def test_agent_registry_infers_required_identity_fields_from_fixture(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        identity = runtime.identities.load_identity("artemis")

        self.assertEqual(identity.id, "artemis")
        self.assertEqual(identity.role, "orchestrator")
        self.assertTrue(identity.can_delegate)

    def test_submit_completion_completed(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        signal = runtime.delegation.submit_completion_signal(
            context=agent_context(runtime, "researcher"),
            task_id=task.task_id,
            status="completed",
            summary="Work is complete.",
            result="Final result",
        )

        self.assertEqual(signal.status, "completed")
        self.assertTrue(runtime.data_dir.resolve(f"delegation/{task.task_id}.completion.yaml").exists())
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_apply_completed_changes_status(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "completed",
            "Done.",
            result="Result",
        )

        updated = runtime.delegation.apply_completion_signal(runtime.context(), task.task_id)

        self.assertEqual(updated.status, "completed")
        self.assertEqual(updated.metadata["result"], "Result")

    def test_submit_failed_and_apply_failed(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "failed",
            "Could not finish.",
            failure_reason="Missing source material",
        )

        updated = runtime.delegation.apply_completion_signal(runtime.context(), task.task_id)

        self.assertEqual(updated.status, "failed")
        self.assertEqual(updated.metadata["reason"], "Missing source material")

    def test_needs_followup_does_not_complete(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "needs_followup",
            "Need more detail.",
            followup_message="Please clarify scope.",
        )

        updated = runtime.delegation.apply_completion_signal(runtime.context(), task.task_id)

        self.assertEqual(updated.status, "in_progress")
        self.assertEqual(updated.metadata["followup_message"], "Please clarify scope.")

    def test_non_assignee_cannot_submit_completion(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)

        with self.assertRaisesRegex(Exception, "Only the delegation assignee"):
            runtime.delegation.submit_completion_signal(
                agent_context(runtime, "artemis"),
                task.task_id,
                "completed",
                "Done.",
            )

    def test_finalized_task_rejects_new_signal(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.delegation.complete_task(runtime.context(), task.task_id, result="Done")

        with self.assertRaisesRegex(Exception, "finalized delegation"):
            runtime.delegation.submit_completion_signal(
                agent_context(runtime, "researcher"),
                task.task_id,
                "completed",
                "Done again.",
            )

    def test_worker_recognizes_structured_completion_signal(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(
            runtime,
            json.dumps(
                {
                    "delegation_completion": {
                        "status": "completed",
                        "summary": "Structured completion.",
                        "result": "Structured result",
                    }
                }
            ),
        )

        results = runtime.worker.process_delegations(runtime.context(), "researcher")
        signal = runtime.delegation.get_completion_signal(task.task_id)

        self.assertEqual(results[0].action, "responded")
        self.assertIsNotNone(results[0].completion_signal)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.status, "completed")
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_free_text_response_does_not_complete_delegation(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime, "Plain text delegation work.")

        results = runtime.worker.process_delegations(runtime.context(), "researcher")

        self.assertEqual(results[0].action, "responded")
        self.assertIsNone(results[0].completion_signal)
        self.assertIsNone(runtime.delegation.get_completion_signal(task.task_id))
        self.assertEqual(runtime.delegation.get_task(task.task_id).status, "in_progress")

    def test_conversation_receives_completion_message(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        conversation = runtime.conversations.create_conversation(
            runtime.context(),
            ["artemis", "researcher"],
            title="Completion conversation",
        )
        task = create_task(runtime, conversation_id=conversation.conversation_id)

        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "completed",
            "Conversation summary.",
            result="Result",
        )
        messages = runtime.conversations.list_conversation_messages(conversation.conversation_id)

        self.assertTrue(
            any(
                message.payload.get("subject") == "Delegation completion submitted"
                for message in messages
            )
        )

    def test_commands(self) -> None:
        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        runtime.delegation.submit_completion_signal(
            agent_context(runtime, "researcher"),
            task.task_id,
            "completed",
            "Done.",
        )

        detail = runtime.commands.execute(runtime.context(), f"/delegation-completion {task.task_id}")
        applied = runtime.commands.execute(
            runtime.context(),
            f"/apply-delegation-completion {task.task_id}",
        )

        self.assertEqual(detail.status, "ok")
        self.assertEqual(detail.data["completion"]["status"], "completed")
        self.assertEqual(applied.status, "ok")
        self.assertEqual(applied.data["delegation"]["status"], "completed")

    def test_api_endpoints(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        task = create_task(runtime)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        submitted = client.post(
            f"/api/delegations/{task.task_id}/completion",
            json={
                "status": "completed",
                "summary": "API completion.",
                "created_by_agent_id": "researcher",
            },
        )
        detail = client.get(f"/api/delegations/{task.task_id}/completion")
        applied = client.post(f"/api/delegations/{task.task_id}/completion/apply")

        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["completion"]["status"], "completed")
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
