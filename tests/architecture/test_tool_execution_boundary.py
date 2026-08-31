from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend" / "synapse"


def _python_files() -> list[Path]:
    return sorted(BACKEND.rglob("*.py"))


def test_registry_is_descriptor_only() -> None:
    tree = ast.parse((BACKEND / "tools" / "registry.py").read_text(encoding="utf-8"))
    registry = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RuntimeToolRegistry"
    )
    methods = {node.name for node in registry.body if isinstance(node, ast.FunctionDef)}
    assert "execute" not in methods
    assert "execute_tool_call" not in methods


def test_bootstrap_constructs_one_registry_and_one_executor() -> None:
    bootstrap = BACKEND / "bootstrap"
    calls: list[tuple[str, str]] = []
    for path in bootstrap.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"RuntimeToolRegistry", "ToolRuntime"}:
                    calls.append((node.func.id, path.relative_to(BACKEND).as_posix()))
    assert [path for name, path in calls if name == "RuntimeToolRegistry"] == [
        "bootstrap/features/platform.py"
    ]
    assert [path for name, path in calls if name == "ToolRuntime"] == [
        "bootstrap/features/integration.py"
    ]


def test_technology_execution_is_confined_to_explicit_adapters() -> None:
    violations: list[str] = []
    for path in _python_files():
        relative = path.relative_to(BACKEND).as_posix()
        source = path.read_text(encoding="utf-8")
        if ".execute_tool(" in source and relative not in {
            "mcp/runtime.py",
            "mcp_bridge/runtime.py",
        }:
            violations.append(relative)
        if relative.startswith("desktop_automation/"):
            continue
        if any(
            needle in source
            for needle in (
                "desktop.execute(",
                "desktop.preview(",
                "desktop.cancel(",
                "desktop.recover(",
                "desktop_runtime.execute(",
            )
        ) and relative != "bootstrap/adapters/tool_execution.py":
            violations.append(relative)
    assert violations == []


def test_technology_adapters_do_not_own_governance() -> None:
    adapter_sources = [
        (BACKEND / "bootstrap" / "adapters" / "tool_execution.py").read_text(
            encoding="utf-8"
        ),
        (BACKEND / "mcp_bridge" / "runtime.py").read_text(encoding="utf-8"),
    ]
    forbidden = ("PermissionManager", "ApprovalManager", "DecisionRuntime", "PolicyRuntime")
    assert not any(name in source for source in adapter_sources for name in forbidden)


def test_consumers_do_not_import_concrete_execution_adapters() -> None:
    violations = []
    for path in _python_files():
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith("bootstrap/"):
            continue
        if "synapse.bootstrap.adapters.tool_execution" in path.read_text(encoding="utf-8"):
            violations.append(relative)
    assert violations == []
