from __future__ import annotations

import ast
from pathlib import Path

from .support import SOURCE_ROOT, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph, _runtime_imports

ATTENTION_ROOT = SOURCE_ROOT / "attention"
WORLD_STATE_ROOT = SOURCE_ROOT / "world_state"
ADAPTER = SOURCE_ROOT / "bootstrap" / "adapters" / "world_state.py"
BOOTSTRAP = SOURCE_ROOT / "bootstrap" / "features" / "world.py"


def _imports(root: Path) -> set[str]:
    return {module for path in root.rglob("*.py") for module in _runtime_imports(path)}


def test_world_state_is_independent_of_attention() -> None:
    assert not any(module.startswith("synapse.attention") for module in _imports(WORLD_STATE_ROOT))


def test_attention_uses_only_world_state_read_models_and_its_port() -> None:
    imports = _imports(ATTENTION_ROOT)
    assert "synapse.world_state.runtime" not in imports
    assert not any(module.endswith((".storage", ".store")) for module in imports)
    runtime = (ATTENTION_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "WorldStateReadPort | None" in runtime
    assert "WorldStateRuntime" not in runtime
    assert "apply_state_update" not in runtime


def test_world_state_read_port_is_snapshot_only() -> None:
    tree = ast.parse((ATTENTION_ROOT / "contracts.py").read_text(encoding="utf-8"))
    port = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorldStateReadPort"
    )
    methods = [node.name for node in port.body if isinstance(node, ast.FunctionDef)]
    assert methods == ["snapshot"]


def test_read_adapter_is_bootstrap_owned_and_cannot_mutate_or_store() -> None:
    imports = _runtime_imports(ADAPTER)
    assert not any(module.endswith((".storage", ".store")) for module in imports)
    assert "synapse.core.data_dir" not in imports

    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    adapter = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorldStateReadAdapter"
    )
    calls = {
        node.func.attr
        for node in ast.walk(adapter)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls == {"snapshot"}


def test_bootstrap_builds_one_port_adapter_and_keeps_agent_loop_as_coordinator() -> None:
    tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert calls.count("WorldStateRuntime") == 1
    assert calls.count("WorldStateReadAdapter") == 1
    assert calls.count("AttentionRuntime") == 1
    assert calls.count("RuntimeEventStateAdapter") == 1
    assert calls.count("AgentLoopRuntime") == 1

    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "AttentionRuntime(d.data_dir, d.events, world_state_read)" in source
    agent_loop_call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AgentLoopRuntime"
    )
    assert [node.id for node in agent_loop_call.args[:5] if isinstance(node, ast.Name)] == [
        "world_state",
        "attention",
        "attention_decisions",
    ]


def test_attention_world_state_scc_is_removed_without_new_cycle() -> None:
    graph = _runtime_context_graph()
    assert len(graph) == 313  # Includes governed Project Knowledge and local model surfaces.
    assert ("world_state", "attention") not in graph
    assert ("attention", "world_state") in graph
    assert cyclic_components(graph) == [
        (
            frozenset(
                {
                    "agents",
                    "approvals",
                    "context",
                    "conversations",
                    "decisions",
                    "delegation",
                    "missions",
                    "models",
                    "policies",
                    "tools",
                    "voice",
                }
            ),
                31,
        )
    ]
