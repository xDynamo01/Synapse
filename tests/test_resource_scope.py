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
from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.core.permissions import PermissionContext
from synapse.resources import ResourceRef, ResourceScope, check_resource_access


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def runtime_in_tempdir(permissions: dict | None = None):
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    permissions = permissions or {
        "subjects": {
            "local_owner": ["*"],
            "user:local_owner": ["*"],
            "agent:worker": ["filesystem.read"],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Resource Scope Test",
            "mode": "test",
            "default_agent_id": "orchestrator",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    return directory, settings, create_runtime(settings)


class ResourceScopeTests(unittest.TestCase):
    def test_resource_ref_creation(self) -> None:
        resource = ResourceRef("file", path="memory/MEMORY.md", owner_agent_id="worker")

        self.assertEqual(resource.resource_type, "file")
        self.assertEqual(resource.path, "memory/MEMORY.md")
        self.assertEqual(resource.owner_agent_id, "worker")

    def test_resource_ref_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValidationError):
            ResourceRef("unknown", resource_id="item-1")

    def test_resource_scope_creation(self) -> None:
        resource = ResourceRef("approval", resource_id="approval-1")
        scope = ResourceScope(
            agent_id="worker",
            action="approve",
            resource_ref=resource,
            correlation_id="corr-1",
            device_id="device-1",
        )

        self.assertEqual(scope.resource_ref.resource_id, "approval-1")
        self.assertEqual(scope.action, "approve")

    def test_permission_context_accepts_optional_resource_scope(self) -> None:
        scope = ResourceScope(
            agent_id="worker",
            action="read",
            resource_ref=ResourceRef("file", path="notes.txt"),
        )
        context = PermissionContext(actor_id="worker", actor_type="agent", resource_scope=scope)

        self.assertEqual(context.resource_scope, scope)

    def test_check_resource_access_allowed(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        scope = check_resource_access(
            agent_id="worker",
            action="read",
            resource_ref=ResourceRef("file", path="notes.txt"),
            context=runtime.context(actor_id="worker", actor_type="agent"),
            permission_manager=runtime.permissions,
        )

        self.assertEqual(scope.resource_ref.path, "notes.txt")
        event = runtime.events.tail(1)[0]
        self.assertEqual(event.type, "permission.decision")
        self.assertEqual(event.payload["resource_type"], "file")
        self.assertEqual(event.payload["action"], "read")

    def test_check_resource_access_denied(self) -> None:
        permissions = {
            "subjects": {
                "local_owner": ["*"],
                "user:local_owner": ["*"],
                "agent:worker": [],
            }
        }
        directory, _, runtime = runtime_in_tempdir(permissions)
        self.addCleanup(directory.cleanup)

        with self.assertRaises(PermissionDenied):
            check_resource_access(
                agent_id="worker",
                action="read",
                resource_ref=ResourceRef("file", path="notes.txt"),
                context=runtime.context(actor_id="worker", actor_type="agent"),
                permission_manager=runtime.permissions,
            )

    def test_sensitive_operation_emits_resource_scope(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = runtime.approvals.create_request(
            context=runtime.context(actor_id="worker", actor_type="agent"),
            tool_name="write_file",
            tool_args={"path": "notes.txt"},
            risk_level="high",
            reason="test approval",
            tool_call_id="tool-call-1",
        )

        runtime.approvals.approve(runtime.context(), request.id)

        decisions = [
            event
            for event in runtime.events.tail(20)
            if event.type == "permission.decision"
            and event.payload.get("resource_type") == "approval"
        ]
        self.assertTrue(decisions)
        self.assertEqual(decisions[-1].payload["resource_id"], request.id)
        self.assertEqual(decisions[-1].payload["action"], "approve")


if __name__ == "__main__":
    unittest.main()
