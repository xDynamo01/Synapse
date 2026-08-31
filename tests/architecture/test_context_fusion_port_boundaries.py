from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend" / "synapse"
CONTEXT = BACKEND / "context_fusion"
ADAPTER = BACKEND / "bootstrap" / "adapters" / "context_fusion.py"
BOOTSTRAP = BACKEND / "bootstrap" / "features" / "integration.py"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def calls(path: Path) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
    ]


def test_context_fusion_imports_only_own_contracts_and_foundation() -> None:
    allowed = ("synapse.context_fusion", "synapse.core")
    for path in CONTEXT.glob("*.py"):
        forbidden = {
            name
            for name in imports(path)
            if name.startswith("synapse.") and not name.startswith(allowed)
        }
        assert forbidden == set(), (path, forbidden)


def test_context_fusion_does_not_import_forbidden_layers_or_storage() -> None:
    forbidden = (".api", ".commands", ".bootstrap", ".store", ".storage")
    for path in CONTEXT.glob("*.py"):
        assert not any(token in name for name in imports(path) for token in forbidden)


def test_runtime_constructor_receives_consumer_owned_ports() -> None:
    source = (CONTEXT / "runtime.py").read_text(encoding="utf-8")
    for contract in (
        "ConversationContextReader",
        "MissionContextReader",
        "PerceptionContextReader",
        "MultimodalContextReader",
        "MemoryContextReader",
        "RuntimeStatusContextReader",
    ):
        assert contract in source
    for concrete in (
        "ConversationRuntime",
        "MissionRuntime",
        "PerceptionRuntime",
        "MemoryStore",
        "MultimodalCommunicationRuntime",
    ):
        assert concrete not in source


def test_adapters_do_not_access_storage_or_mutating_methods() -> None:
    assert not any(
        token in name for name in imports(ADAPTER) for token in (".store", ".storage")
    )
    forbidden_calls = {
        "create",
        "update",
        "delete",
        "save",
        "write",
        "persist",
        "unlink",
        "emit_signal",
    }
    invoked = {
        node.func.attr
        for node in calls(ADAPTER)
        if isinstance(node.func, ast.Attribute)
    }
    assert invoked.isdisjoint(forbidden_calls)


def test_owner_domains_do_not_depend_on_context_fusion_to_supply_reads() -> None:
    for domain in ("conversations", "missions", "delegation", "perception", "multimodal", "memory"):
        for path in (BACKEND / domain).rglob("*.py"):
            assert not any(name.startswith("synapse.context_fusion") for name in imports(path))


def test_bootstrap_registers_each_adapter_and_one_runtime() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    for adapter in (
        "ConversationContextAdapter",
        "MissionContextAdapter",
        "PerceptionContextAdapter",
        "MultimodalContextAdapter",
        "MemoryContextAdapter",
        "RuntimeStatusContextAdapter",
    ):
        assert source.count(f"{adapter}(") == 1
    assert source.count("ContextFusionRuntime(") == 1


def test_port_dtos_do_not_import_runtimes() -> None:
    assert not any(".runtime" in name for name in imports(CONTEXT / "contracts.py"))


def test_context_fusion_has_no_functional_domain_edge_after_inversion() -> None:
    outgoing = {
        name.split(".")[1]
        for path in CONTEXT.glob("*.py")
        for name in imports(path)
        if name.startswith("synapse.")
    }
    assert outgoing <= {"context_fusion", "core"}
