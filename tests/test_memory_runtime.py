from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.serialization import dump_structured_file
from synapse.memory.errors import MemoryError


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(project_root=PROJECT_ROOT, data_dir=Path(directory.name) / "data", host="127.0.0.1", port=8717, default_actor_id="local_owner")
    create_runtime(settings)
    dump_structured_file(
        settings.data_dir / "config" / "permissions.yaml",
        {
            "subjects": {
                "local_owner": ["*"],
                "agent:researcher": ["filesystem.read"],
                "guest": ["filesystem.read"],
            }
        },
    )
    return directory, settings, create_runtime(settings)


class MemoryRuntimeTests(unittest.TestCase):
    def test_crud_revision_restart_and_soft_delete(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        item = runtime.memory.create(runtime.context(), scope="user", owner_id="local_owner", source="explicit", content="Prefers concise answers", tags=["preference"], importance=80)
        restarted = create_runtime(settings)
        self.assertEqual(restarted.memory.get(restarted.context(), item.id).content, item.content)
        updated = restarted.memory.update(restarted.context(), item.id, expected_revision=1, content="Prefers very concise answers")
        self.assertEqual(updated.revision, 2)
        with self.assertRaisesRegex(MemoryError, "revision"):
            restarted.memory.update(restarted.context(), item.id, expected_revision=1, content="stale")
        deleted = restarted.memory.delete(restarted.context(), item.id, expected_revision=2)
        self.assertEqual(deleted.status, "deleted")
        self.assertEqual(deleted.content, "")

    def test_working_memory_requires_expiry_and_cleans_up(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        with self.assertRaisesRegex(MemoryError, "expires_at"):
            runtime.memory.create(runtime.context(), scope="session", owner_id="s1", source="turn", content="temporary")
        item = runtime.memory.create(runtime.context(), scope="session", owner_id="s1", source="turn", content="temporary", expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
        self.assertEqual(runtime.memory.cleanup(runtime.context()), 1)
        self.assertEqual(runtime.memory.get(runtime.context(), item.id).status, "expired")

    def test_retrieval_is_deterministic_and_budgeted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.memory.create(runtime.context(), scope="knowledge", owner_id="local_owner", source="manual", content="Python supports dataclasses", tags=["python"], importance=90)
        runtime.memory.create(runtime.context(), scope="knowledge", owner_id="local_owner", source="manual", content="Rust supports traits", tags=["rust"], importance=80)
        result = runtime.memory.retrieve_memory(runtime.context(), "Python", ["knowledge"], filters={"tags": ["python"]}, budget=20)
        self.assertEqual([item.content for item in result.records], ["Python supports dataclasses"])
        self.assertEqual(result.strategy, "text_tags_recency_importance")

    def test_agent_scope_is_isolated_and_sensitive_memory_denied(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        item = runtime.memory.create(runtime.context(), scope="agent", owner_id="artemis", source="manual", content="private")
        with self.assertRaisesRegex(MemoryError, "denied"):
            runtime.memory.get(runtime.context(actor_id="researcher", actor_type="agent"), item.id)
        sensitive = runtime.memory.create(runtime.context(), scope="user", owner_id="local_owner", source="manual", content="secret", metadata={"sensitive": True})
        with self.assertRaisesRegex(MemoryError, "denied"):
            runtime.memory.get(runtime.context(actor_id="guest"), sensitive.id)

    def test_corrupt_storage_fails_explicitly(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        path = runtime.data_dir.resolve("memory/records.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(MemoryError, "corrupt"):
            runtime.memory.list(runtime.context())

    def test_import_export_and_deduplication(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        first = runtime.memory.create(runtime.context(), scope="system", owner_id="local_owner", source="manual", content="constraint")
        duplicate = runtime.memory.create(runtime.context(), scope="system", owner_id="local_owner", source="manual", content="constraint")
        self.assertEqual(first.id, duplicate.id)
        payload = runtime.memory.export_records(runtime.context(), scopes=["system"])
        self.assertEqual(len(runtime.memory.import_records(runtime.context(), payload)), 1)

    def test_context_fusion_budget_provenance_and_deduplication(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        runtime.memory.create(runtime.context(), scope="session", owner_id="s1", source="turn", content="same content", expires_at=expires)
        result = runtime.context_fusion.build_context(session_id="s1", incoming_message="current input", options={"budget": 100, "response_reserve": 10}, permission_context=runtime.context(), persist_snapshot=False)
        self.assertEqual(result.items[0].source_type, "incoming_message")
        self.assertTrue(result.trace_id)
        self.assertLessEqual(result.total_estimated_tokens, 90)
        self.assertIn("[incoming_message:current]", result.rendered_context)

    def test_api_and_commands_use_canonical_runtime(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")
        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        command = runtime.commands.execute(runtime.context(), "/remember explicit fact")
        self.assertEqual(command.status, "ok")
        self.assertEqual(runtime.commands.execute(runtime.context(), "/memory").data["memory"][0]["content"], "explicit fact")
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)
        created = client.post("/api/memory", json={"scope": "knowledge", "owner_id": "local_owner", "content": "API fact"})
        self.assertEqual(created.status_code, 200)
        memory_id = created.json()["id"]
        self.assertEqual(client.get(f"/api/memory/{memory_id}").status_code, 200)
        searched = client.post("/api/memory/search", json={"query": "API", "scopes": ["knowledge"]})
        self.assertEqual(searched.json()["records"][0]["id"], memory_id)
        preview = client.post("/api/context/preview", json={"incoming_message": "hello", "options": {"budget": 100}})
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["trace_id"])

    def test_chat_does_not_heuristically_write_memory(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        self.assertFalse(hasattr(runtime.chat, "_extract_memory_facts"))


if __name__ == "__main__":
    unittest.main()
