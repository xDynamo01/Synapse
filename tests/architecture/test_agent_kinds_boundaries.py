from __future__ import annotations

import ast

from synapse.agents.models import AgentKind

from .support import SOURCE_ROOT, imports_for


def test_exactly_three_explicit_agent_kinds_exist() -> None:
    assert {item.value for item in AgentKind} == {"primary", "persistent", "ephemeral"}


def test_legacy_agent_creator_has_no_active_reference() -> None:
    forbidden = ("AgentCreator", "agent_creator", "agent creator")
    violations = []
    for root in (SOURCE_ROOT, SOURCE_ROOT.parent.parent / "data" / "config"):
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".yaml", ".json"}:
                continue
            text = path.read_text(encoding="utf-8").lower()
            if any(item.lower() in text for item in forbidden):
                violations.append(str(path))
    assert not violations
    assert not (SOURCE_ROOT / "api" / "agent_creator_adapter.py").exists()


def test_persistent_and_ephemeral_creation_authorities_are_separate() -> None:
    provisioning = (SOURCE_ROOT / "agents" / "provisioning.py").read_text(encoding="utf-8")
    ephemeral = (SOURCE_ROOT / "ephemeral_agents" / "runtime.py").read_text(encoding="utf-8")
    assert "AgentProvisioning creates persistent agents only" in provisioning
    assert "Only Mission or Swarm may create ephemeral agents" in ephemeral
    assert "AgentProvisioning" not in ephemeral
    assert "AgentRegistry" not in ephemeral
    assert "data/agents" not in ephemeral
    assert 'resolve("agents/' not in ephemeral


def test_ephemeral_runtime_does_not_import_delivery_providers_or_tool_execution() -> None:
    root = SOURCE_ROOT / "ephemeral_agents"
    imports = {module for path in root.glob("*.py") for module in imports_for(path)}
    assert not any(
        module.startswith(("synapse.api", "synapse.commands", "synapse.bootstrap"))
        for module in imports
    )
    assert not any("provider" in module for module in imports)
    runtime = (root / "runtime.py").read_text(encoding="utf-8")
    assert ".execute_tool(" not in runtime
    assert ".execute(" not in runtime


def test_only_swarm_or_mission_can_apply_ephemeral_workforce() -> None:
    router = (SOURCE_ROOT / "api" / "routers" / "agent_kinds.py").read_text(encoding="utf-8")
    commands = (SOURCE_ROOT / "commands" / "handlers" / "agent_kinds.py").read_text(encoding="utf-8")
    assert "create_instance" not in router
    assert "create_instance" not in commands
    assert "spawn" not in router.lower()
    assert "spawn" not in commands.lower()
    assert "create_instance" in (SOURCE_ROOT / "swarm" / "runtime.py").read_text(encoding="utf-8")


def test_primary_runtime_coordinates_but_does_not_duplicate_chat_loop_or_voice() -> None:
    path = SOURCE_ROOT / "primary_agent" / "runtime.py"
    imports = imports_for(path)
    assert not any(
        module.startswith(("synapse.chat", "synapse.agent_loop", "synapse.voice"))
        for module in imports
    )
    text = path.read_text(encoding="utf-8")
    assert "model_provider" not in text
    assert "execute_tool" not in text
    assert "start_recording" not in text


def test_primary_bootstrap_contract_is_frontend_agnostic() -> None:
    models = (SOURCE_ROOT / "primary_agent" / "models.py").read_text(encoding="utf-8")
    for forbidden in ("pane", "sidebar", "dockview", "theme", "layout"):
        assert forbidden not in models.lower()


def test_ephemeral_lifecycle_and_cleanup_are_explicit() -> None:
    tree = ast.parse(
        (SOURCE_ROOT / "ephemeral_agents" / "runtime.py").read_text(encoding="utf-8")
    )
    methods = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"create_instance", "heartbeat", "complete", "cancel", "destroy", "reconcile", "cleanup"} <= methods


def test_human_editable_agent_content_is_not_in_storage_primitive() -> None:
    storage_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (SOURCE_ROOT / "storage").glob("*.py")
    )
    assert "SOUL.md" not in storage_text
    assert "SKILLS.md" not in storage_text
    assert "CONFIG.yaml" not in storage_text


def test_prefabricated_agent_templates_remain_absent() -> None:
    assert not (SOURCE_ROOT / "agent_templates").exists()
    active = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SOURCE_ROOT.rglob("*.py")
        if "test" not in path.parts
    ).lower()
    assert "create_from_template" not in active
    assert "default_agent_template" not in active
