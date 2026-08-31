from __future__ import annotations

import ast

from .support import SOURCE_ROOT, imports_for

BOUNDARY_ROOT = SOURCE_ROOT / "intelligence_boundary"


def test_boundary_does_not_import_consumers_or_concrete_providers() -> None:
    forbidden = (
        "synapse.models",
        "synapse.tools",
        "synapse.mcp",
        "synapse.skills",
        "synapse.missions",
        "synapse.project_governance",
        "synapse.voice",
        "synapse.vision",
        "synapse.speech_adapters",
        "synapse.bootstrap",
    )
    violations = []
    for path in BOUNDARY_ROOT.glob("*.py"):
        for module in imports_for(path):
            if module.startswith(forbidden):
                violations.append(f"{path.name}: {module}")
    assert not violations, "\n".join(violations)


def test_consumers_import_only_boundary_contracts_and_models() -> None:
    consumers = (
        SOURCE_ROOT / "models" / "router.py",
        SOURCE_ROOT / "tools" / "runtime.py",
        SOURCE_ROOT / "mcp_bridge" / "runtime.py",
    )
    violations = []
    for path in consumers:
        for module in imports_for(path):
            if module.startswith("synapse.intelligence_boundary") and module not in {
                "synapse.intelligence_boundary.contracts",
                "synapse.intelligence_boundary.models",
            }:
                violations.append(f"{path}: {module}")
    assert not violations, "\n".join(violations)


def test_model_and_tool_transports_are_preceded_by_egress_gate() -> None:
    model = (SOURCE_ROOT / "models" / "router.py").read_text(encoding="utf-8")
    assert model.index("_authorize_request(request_payload)") < model.index(
        "adapter.generate(request_payload)"
    )
    tools = (SOURCE_ROOT / "tools" / "runtime.py").read_text(encoding="utf-8")
    assert tools.index("_authorize_tool_egress(") < tools.index("self._invoke_handler(")
    for path in (
        SOURCE_ROOT / "api" / "routers" / "models.py",
        SOURCE_ROOT / "commands" / "handlers" / "models_providers.py",
    ):
        assert ".lmstudio.chat_completion(" not in path.read_text(encoding="utf-8")


def test_current_speech_and_vision_adapters_have_no_external_transport() -> None:
    transport_markers = ("urlopen(", "httpx.", "aiohttp.", "requests.")
    for root in (SOURCE_ROOT / "speech_adapters", SOURCE_ROOT / "vision"):
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert not any(marker in text for marker in transport_markers), path


def test_desktop_tool_adapters_declare_their_local_process_boundary() -> None:
    text = (
        SOURCE_ROOT / "bootstrap" / "adapters" / "tool_execution.py"
    ).read_text(encoding="utf-8")
    assert '"processing_boundary": "local_process"' in text


def test_mcp_external_tools_declare_external_boundary() -> None:
    text = (SOURCE_ROOT / "mcp_bridge" / "runtime.py").read_text(encoding="utf-8")
    assert '"processing_boundary": "external_mcp"' in text
    assert "MCPToolExecutorAdapter" in text


def test_ledger_contract_has_no_payload_or_secret_fields() -> None:
    tree = ast.parse((BOUNDARY_ROOT / "models.py").read_text(encoding="utf-8"))
    ledger = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EgressLedgerRecord"
    )
    fields = {
        node.target.id
        for node in ledger.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert not fields.intersection({"payload", "content", "secret", "api_key", "credential"})


def test_no_bypass_delivery_surface_exists() -> None:
    roots = (SOURCE_ROOT / "api", SOURCE_ROOT / "commands")
    forbidden = {
        "egress-force",
        "force-allow",
        "trust-all-providers",
        "disable-boundary",
        "mark-all-public",
        "clear-ledger",
        "bypass-egress",
    }
    violations = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for item in forbidden:
                if item in text:
                    violations.append(f"{path}: {item}")
    assert not violations, "\n".join(violations)


def test_ephemeral_approval_is_explicitly_denied() -> None:
    text = (BOUNDARY_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert 'actor_type == "ephemeral_agent"' in text
    assert "ephemeral agents cannot approve egress" in text


def test_trust_is_not_hardcoded_in_concrete_external_provider() -> None:
    for path in (
        SOURCE_ROOT / "models" / "adapters.py",
        SOURCE_ROOT / "model_providers" / "lmstudio.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert "ProviderTrustProfile(" not in text
        assert "trust-all" not in text.lower()
