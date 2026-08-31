from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import synapse.agents.provisioning as provisioning_module
from synapse.agents.identity import AgentIdentityRuntime
from synapse.agents.provisioning import (
    AgentCreateRequest,
    AgentProvisioningError,
    AgentUpdateRequest,
)
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file


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
            "agent:scribe": ["filesystem.read", "filesystem.list", "filesystem.search"],
            "agent:clerk": ["tasks.create"],
        }
    }
    system = {
        "system": {
            "name": "Synapse V2 Agent Provisioning Test",
            "mode": "test",
            "default_agent_id": "scribe",
        },
        "models": {
            "default_provider": "mock",
            "providers": {"mock": {"base_url": None, "model": "synapse-test"}},
        },
    }
    write_json(settings.data_dir / "config" / "permissions.yaml", permissions)
    write_json(settings.data_dir / "config" / "system.yaml", system)
    return directory, settings, create_runtime(settings)


def write_policy(settings: Settings, **updates) -> None:
    policy = {
        "agent_provisioning": {
            "default_autonomy_level": "manual",
            "max_direct_create_autonomy_level": "manual",
            "require_approval_for_high_risk_capabilities": True,
            "require_approval_for_critical_capabilities": True,
            "sensitive_capabilities": [
                "filesystem.write",
                "scheduler.run",
                "approval.review",
            ],
            "sensitive_tools": ["write_file", "delete_file", "camera_control"],
            "blocked_capabilities": [],
            "blocked_tools": [],
            "require_forbidden_tools_for_sensitive_agents": True,
            "allow_direct_create": True,
            "allow_direct_update": True,
        }
    }
    policy["agent_provisioning"].update(updates)
    write_json(settings.data_dir / "config" / "agent_provisioning_policy.yaml", policy)


def create_request(agent_id: str = "scribe") -> AgentCreateRequest:
    return AgentCreateRequest(
        agent_id=agent_id,
        display_name="Scribe",
        role="note_taker",
        description="Maintains structured local notes.",
        focus_areas=["notes", "summaries"],
        autonomy_level="manual",
        capabilities_allow=["filesystem.read"],
        capabilities_deny=["filesystem.write"],
        initial_memory="# Scribe Memory\n\nInitial notes.\n",
        metadata={"purpose": "test"},
    )


def sensitive_request(agent_id: str = "builder") -> AgentCreateRequest:
    return AgentCreateRequest(
        agent_id=agent_id,
        display_name="Builder",
        role="file_builder",
        autonomy_level="manual",
        capabilities_allow=["filesystem.write"],
        preferred_tools=["write_file"],
    )


def guest_context(runtime):
    return runtime.context(actor_id="guest")


class AgentProvisioningTests(unittest.TestCase):
    def test_create_valid_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.provisioning.create_agent(create_request())

        self.assertTrue(result.created)
        self.assertEqual(result.agent_id, "scribe")
        self.assertTrue(result.validation.valid)

    def test_prevent_overwrite_without_authorization(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        with self.assertRaises(ValidationError):
            runtime.provisioning.create_agent(create_request())

    def test_reject_unsafe_agent_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaises(ValidationError):
            runtime.provisioning.create_agent(create_request("../escape"))

    def test_unknown_capability_fails(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = create_request()
        request = AgentCreateRequest(
            **{**request.__dict__, "capabilities_allow": ["missing.capability"]}
        )

        with self.assertRaises(ValidationError):
            runtime.provisioning.create_agent(request)

    def test_creates_agent_files_and_schema_metadata(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.provisioning.create_agent(create_request())

        base = settings.data_dir / "agents" / "scribe"
        for filename in ("SOUL.md", "CONFIG.yaml", "SKILLS.md", "MEMORY.md"):
            self.assertTrue((base / filename).exists())
        config = load_structured_file(base / "CONFIG.yaml")
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["record_type"], "agent_config")
        self.assertIn("created_at", config)
        self.assertIn("updated_at", config)

    def test_created_agent_appears_in_registry(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        agent = runtime.agents.get("scribe")

        self.assertEqual(agent.id, "scribe")
        self.assertEqual(agent.role, "note_taker")

    def test_identity_runtime_loads_created_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        identity = runtime.identities.load_identity("scribe")

        self.assertEqual(identity.name, "Scribe")
        self.assertEqual(identity.role, "note_taker")

    def test_effective_policy_works_with_created_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        policy = runtime.policies.resolve(runtime.context(actor_id="scribe", actor_type="agent"), "scribe")

        self.assertIn("filesystem.read", policy.allowed_capabilities)
        self.assertIn("read_file", policy.allowed_tools)

    def test_capability_runtime_evaluates_created_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        decision = runtime.capabilities.check_agent_capability("scribe", "filesystem.read")

        self.assertTrue(decision.allowed)

    def test_create_agent_command(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(
            runtime.context(),
            '/create-agent clerk "Clerk" "task_helper"',
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(runtime.agents.get("clerk").name, "Clerk")

    def test_create_agent_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/agents",
            json={
                "agent_id": "scribe",
                "display_name": "Scribe",
                "role": "note_taker",
                "capabilities_allow": ["filesystem.read"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agent_id"], "scribe")

    def test_create_agent_api_requires_approval_for_owner_risk(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/agents",
            json={
                "agent_id": "builder",
                "display_name": "Builder",
                "role": "file_builder",
                "capabilities_allow": ["filesystem.write"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "awaiting_approval")
        self.assertFalse(response.json()["created"])
        self.assertFalse((runtime.data_dir.resolve("agents/builder")).exists())

    def test_validate_agent_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post("/api/agents/scribe/validate")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["valid"])

    def test_sensitive_agent_becomes_pending_request(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))

        self.assertEqual(result.status, "awaiting_approval")
        self.assertFalse(result.created)
        self.assertIsNotNone(result.provisioning_request_id)
        self.assertFalse((settings.data_dir / "agents" / "builder" / "CONFIG.yaml").exists())

    def test_sensitive_agent_creates_approval_request(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        request = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)
        approval = runtime.approvals.get_status(request.approval_id)

        self.assertEqual(approval.status, "pending")
        self.assertEqual(approval.tool_args["request_type"], "agent_provisioning")
        self.assertEqual(approval.tool_args["agent_id"], "builder")
        self.assertIn("filesystem.write", approval.tool_args["requested_capabilities"])
        self.assertEqual(approval.tool_args["configuration_hash"], request.configuration_hash)
        self.assertEqual(approval.tool_args["requester_id"], "guest")

    def test_identical_sensitive_request_is_idempotent_by_configuration_hash(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.provisioning.create_agent(
            sensitive_request(), context=guest_context(runtime)
        )
        second = runtime.provisioning.create_agent(
            sensitive_request(), context=guest_context(runtime)
        )

        self.assertEqual(first.provisioning_request_id, second.provisioning_request_id)
        self.assertEqual(len(runtime.approvals.list_pending()), 1)

    def test_changed_configuration_cannot_reuse_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        first = runtime.provisioning.create_agent(
            sensitive_request(), context=guest_context(runtime)
        )
        changed_request = AgentCreateRequest(
            **{**asdict(sensitive_request()), "description": "changed"}
        )
        second = runtime.provisioning.create_agent(
            changed_request, context=guest_context(runtime)
        )

        self.assertNotEqual(first.provisioning_request_id, second.provisioning_request_id)
        first_pending = runtime.provisioning.get_provisioning_request(first.provisioning_request_id)
        second_pending = runtime.provisioning.get_provisioning_request(second.provisioning_request_id)
        self.assertNotEqual(first_pending.configuration_hash, second_pending.configuration_hash)

    def test_tampered_pending_payload_invalidates_approval_binding(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(
            sensitive_request(), context=guest_context(runtime)
        )
        pending = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)
        raw = asdict(pending)
        raw["payload"]["description"] = "tampered"
        dump_structured_file(
            runtime.data_dir.resolve(f"agent_provisioning/{pending.id}.yaml"), raw
        )

        with self.assertRaises(AgentProvisioningError) as raised:
            runtime.provisioning.approve_provisioning_request(runtime.context(), pending.id)

        self.assertEqual(raised.exception.code, "approval_mismatch")

    def test_update_can_replace_identity_content_and_permissions(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        runtime.provisioning.update_agent(
            "scribe",
            AgentUpdateRequest(
                soul_content="# Custom Soul\n",
                skills_content="# Custom Skills\n",
                permissions=["agents.message"],
            ),
        )

        self.assertEqual(
            (settings.data_dir / "agents" / "scribe" / "SOUL.md").read_text(encoding="utf-8"),
            "# Custom Soul\n",
        )
        self.assertEqual(
            (settings.data_dir / "agents" / "scribe" / "SKILLS.md").read_text(encoding="utf-8"),
            "# Custom Skills\n",
        )
        config = load_structured_file(settings.data_dir / "agents" / "scribe" / "CONFIG.yaml")
        self.assertEqual(config["permissions"], ["agents.message"])

    def test_approval_does_not_apply_automatically(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))

        approved = runtime.provisioning.approve_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )

        self.assertEqual(approved.status, "approved")
        self.assertFalse((settings.data_dir / "agents" / "builder" / "CONFIG.yaml").exists())

    def test_apply_creates_agent_after_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        runtime.provisioning.approve_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )

        applied = runtime.provisioning.apply_approved_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )

        self.assertTrue(applied.created)
        self.assertEqual(runtime.agents.get("builder").id, "builder")
        request = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)
        self.assertEqual(request.status, "applied")

    def test_rejection_prevents_application(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))

        runtime.provisioning.reject_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )

        with self.assertRaises(ValidationError):
            runtime.provisioning.apply_approved_provisioning_request(
                runtime.context(),
                result.provisioning_request_id,
            )

    def test_duplicate_application_is_blocked(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        runtime.provisioning.approve_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )
        runtime.provisioning.apply_approved_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )

        with self.assertRaises(ValidationError):
            runtime.provisioning.apply_approved_provisioning_request(
                runtime.context(),
                result.provisioning_request_id,
            )

    def test_sensitive_update_requires_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())

        result = runtime.provisioning.update_agent(
            "scribe",
            AgentUpdateRequest(capabilities_allow=["filesystem.write"]),
            context=guest_context(runtime),
        )

        self.assertEqual(result.status, "awaiting_approval")
        config = load_structured_file(Path(directory.name) / "data" / "agents" / "scribe" / "CONFIG.yaml")
        self.assertNotIn("filesystem.write", config["capabilities"]["allow"])

    def test_new_provisioning_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))

        listed = runtime.commands.execute(runtime.context(), "/agent-provisioning-requests")
        approved = runtime.commands.execute(
            runtime.context(),
            f"/approve-agent-provisioning {result.provisioning_request_id}",
        )
        applied = runtime.commands.execute(
            runtime.context(),
            f"/apply-agent-provisioning {result.provisioning_request_id}",
        )

        self.assertEqual(listed.status, "ok")
        self.assertEqual(approved.status, "ok")
        self.assertEqual(applied.status, "ok")
        self.assertEqual(runtime.agents.get("builder").id, "builder")

    def test_new_provisioning_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        listed = client.get("/api/agent-provisioning/requests")
        detail = client.get(f"/api/agent-provisioning/requests/{result.provisioning_request_id}")
        approved = client.post(
            f"/api/agent-provisioning/requests/{result.provisioning_request_id}/approve"
        )
        applied = client.post(
            f"/api/agent-provisioning/requests/{result.provisioning_request_id}/apply"
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(runtime.agents.get("builder").id, "builder")

    def test_provisioning_events_are_emitted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        runtime.provisioning.approve_provisioning_request(
            runtime.context(),
            result.provisioning_request_id,
        )

        event_types = [event.type for event in runtime.events.tail(30)]

        self.assertIn("agent.provisioning.requested", event_types)
        self.assertIn("agent.provisioning.awaiting_approval", event_types)
        self.assertIn("agent.provisioning.approved", event_types)

    def test_loads_default_policy(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        policy = runtime.provisioning.current_policy()

        self.assertEqual(policy["default_autonomy_level"], "manual")
        self.assertIn("filesystem.write", policy["sensitive_capabilities"])

    def test_sensitive_capability_requires_approval_from_policy(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))

        self.assertEqual(result.status, "awaiting_approval")

    def test_blocked_capability_rejects_create_before_approval(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_policy(settings, blocked_capabilities=["filesystem.write"])
        runtime = create_runtime(settings)

        with self.assertRaises(ValidationError):
            runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))

        self.assertEqual(runtime.provisioning.list_provisioning_requests(), [])

    def test_sensitive_tool_requires_approval_from_policy(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = AgentCreateRequest(
            agent_id="toolsmith",
            display_name="Toolsmith",
            role="tool_worker",
            preferred_tools=["write_file"],
        )

        result = runtime.provisioning.create_agent(request, context=guest_context(runtime))

        self.assertEqual(result.status, "awaiting_approval")
        pending = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)
        self.assertIn("write_file", pending.risk_decision["sensitive_tools_detected"])

    def test_autonomy_above_policy_limit_requires_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = AgentCreateRequest(
            agent_id="runner",
            display_name="Runner",
            role="assistant",
            autonomy_level="autonomous",
        )

        result = runtime.provisioning.create_agent(request, context=guest_context(runtime))

        self.assertEqual(result.status, "awaiting_approval")

    def test_risk_decision_includes_reasons_and_is_persisted(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        pending = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)

        self.assertTrue(pending.risk_decision["requires_approval"])
        self.assertTrue(pending.risk_decision["reasons"])
        self.assertIn("filesystem.write", pending.risk_decision["sensitive_capabilities_detected"])

    def test_agent_provisioning_policy_command(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.commands.execute(runtime.context(), "/agent-provisioning-policy")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["policy"]["default_autonomy_level"], "manual")

    def test_agent_provisioning_policy_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).get("/api/agent-provisioning/policy")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["default_autonomy_level"], "manual")

    def test_manual_dry_run_is_deterministic_and_has_no_side_effects(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = AgentCreateRequest(**{**asdict(create_request()), "dry_run": True})

        first = runtime.provisioning.create_agent(request)
        second = runtime.provisioning.create_agent(request)

        self.assertEqual(first.status, "dry_run")
        self.assertEqual(first.preview, second.preview)
        self.assertEqual(first.preview["config"]["created_at"], "<generated>")
        self.assertFalse((settings.data_dir / "agents" / "scribe").exists())
        self.assertEqual(runtime.provisioning.list_provisioning_requests(), [])

    def test_delegation_authority_requires_approval(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = AgentCreateRequest(
            agent_id="delegator",
            display_name="Delegator",
            role="coordinator",
            can_delegate=True,
        )

        result = runtime.provisioning.create_agent(request, context=guest_context(runtime))

        self.assertEqual(result.status, "awaiting_approval")
        pending = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)
        self.assertIn("delegation authority requires approval", pending.risk_reasons)

    def test_non_boolean_can_delegate_returns_structured_error(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        request = AgentCreateRequest(
            agent_id="invalid-delegator",
            display_name="Invalid",
            role="coordinator",
            can_delegate="yes",  # type: ignore[arg-type]
        )

        with self.assertRaises(AgentProvisioningError) as raised:
            runtime.provisioning.create_agent(request)

        self.assertEqual(raised.exception.code, "invalid_request")

    def test_identity_validation_failure_rolls_back_staging(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        original = AgentIdentityRuntime.load_identity

        def fail_identity(*_args, **_kwargs):
            raise ValidationError("identity invalid")

        AgentIdentityRuntime.load_identity = fail_identity
        self.addCleanup(setattr, AgentIdentityRuntime, "load_identity", original)

        with self.assertRaises(AgentProvisioningError) as raised:
            runtime.provisioning.create_agent(create_request())

        self.assertEqual(raised.exception.code, "identity_validation_failed")
        self.assertFalse((settings.data_dir / "agents" / "scribe").exists())
        staging = settings.data_dir / "agent_provisioning_staging"
        self.assertFalse(staging.exists() and any(staging.iterdir()))

    def test_write_failure_leaves_no_partial_agent(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        original = provisioning_module.dump_structured_file

        def fail_write(*_args, **_kwargs):
            raise OSError("disk unavailable")

        provisioning_module.dump_structured_file = fail_write
        self.addCleanup(setattr, provisioning_module, "dump_structured_file", original)

        with self.assertRaises(AgentProvisioningError) as raised:
            runtime.provisioning.create_agent(create_request())

        self.assertEqual(raised.exception.code, "provisioning_failed")
        self.assertFalse((settings.data_dir / "agents" / "scribe").exists())
        event_types = [event.type for event in runtime.events.tail(20)]
        self.assertIn("agent.provisioning.rolled_back", event_types)

    def test_overwrite_commit_failure_restores_previous_agent(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.provisioning.create_agent(create_request())
        original_config = load_structured_file(settings.data_dir / "agents" / "scribe" / "CONFIG.yaml")
        real_replace = os.replace
        calls = 0

        def fail_commit(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("commit failed")
            return real_replace(source, destination)

        provisioning_module.os.replace = fail_commit
        self.addCleanup(setattr, provisioning_module.os, "replace", real_replace)
        overwrite = AgentCreateRequest(
            **{
                **asdict(create_request()),
                "display_name": "Changed",
                "overwrite": True,
            }
        )

        with self.assertRaises(AgentProvisioningError):
            runtime.provisioning.create_agent(overwrite)

        restored = load_structured_file(settings.data_dir / "agents" / "scribe" / "CONFIG.yaml")
        self.assertEqual(restored["name"], original_config["name"])

    def test_expired_approval_returns_structured_error(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        result = runtime.provisioning.create_agent(sensitive_request(), context=guest_context(runtime))
        pending = runtime.provisioning.get_provisioning_request(result.provisioning_request_id)
        approval_path = runtime.data_dir.resolve(f"approvals/{pending.approval_id}.yaml")
        approval = load_structured_file(approval_path)
        approval["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        dump_structured_file(approval_path, approval)

        with self.assertRaises(AgentProvisioningError) as raised:
            runtime.provisioning.approve_provisioning_request(
                runtime.context(),
                pending.id,
            )

        self.assertEqual(raised.exception.code, "approval_expired")
        self.assertEqual(runtime.provisioning.get_provisioning_request(pending.id).status, "expired")

    def test_approval_cannot_be_reused_for_another_agent(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        first = runtime.provisioning.create_agent(
            sensitive_request("builder-one"),
            context=guest_context(runtime),
        )
        second = runtime.provisioning.create_agent(
            sensitive_request("builder-two"),
            context=guest_context(runtime),
        )
        first_request = runtime.provisioning.get_provisioning_request(
            first.provisioning_request_id
        )
        second_request = runtime.provisioning.get_provisioning_request(
            second.provisioning_request_id
        )
        second_raw = asdict(second_request)
        second_raw["approval_id"] = first_request.approval_id
        dump_structured_file(
            runtime.data_dir.resolve(f"agent_provisioning/{second_request.id}.yaml"),
            second_raw,
        )

        with self.assertRaises(AgentProvisioningError) as raised:
            runtime.provisioning.approve_provisioning_request(
                runtime.context(),
                second_request.id,
            )

        self.assertEqual(raised.exception.code, "approval_mismatch")

    def test_manual_preview_api_and_command_do_not_write(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        response = client.post(
            "/api/agents/preview",
            json={"agent_id": "api-dry", "display_name": "API Dry", "role": "assistant"},
        )
        command = runtime.commands.execute(
            runtime.context(),
            '/preview-agent command-dry "Command Dry" "assistant"',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["dry_run"])
        self.assertEqual(command.status, "ok")
        self.assertTrue(command.data["provisioning"]["dry_run"])
        self.assertFalse((settings.data_dir / "agents" / "api-dry").exists())
        self.assertFalse((settings.data_dir / "agents" / "command-dry").exists())


if __name__ == "__main__":
    unittest.main()
