from __future__ import annotations

import ast

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for

ROOT = SOURCE_ROOT / "sandbox_drivers"


def test_driver_depends_on_sandbox_only_and_creates_no_scc() -> None:
    graph = context_graph()
    assert {edge for edge in graph if "sandbox_drivers" in edge} == {
        ("deployment_integrations", "sandbox_drivers"),
        ("sandbox_drivers", "sandbox"),
        ("sandbox_integrations", "sandbox_drivers"),
        ("sandbox_driver_composition", "sandbox_drivers"),
    }
    assert ("sandbox_integrations", "coding_sessions") in graph
    assert all("sandbox_drivers" not in members for members, _ in cyclic_components(graph))
    assert not any(module.startswith("synapse.coding_sessions") for path in ROOT.glob("*.py") for module in imports_for(path))


def test_driver_has_no_subprocess_network_shell_or_file_association_surface() -> None:
    forbidden_imports = {"subprocess", "socket", "requests", "httpx"}
    forbidden_calls = {
        "Popen",
        "run",
        "system",
        "ShellExecute",
        "startfile",
    }
    assert not [(path.name, module) for path in ROOT.glob("*.py") for module in imports_for(path) if module.split(".", 1)[0] in forbidden_imports]
    assert not [(path.name, getattr(node.func, "attr", getattr(node.func, "id", ""))) for path in ROOT.glob("*.py") for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in forbidden_calls]


def test_win32_process_calls_are_confined_to_the_native_boundary() -> None:
    process_file = ROOT / "windows_process.py"
    other_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.glob("*.py")
        if path != process_file
    )
    assert "CreateProcess" not in other_source
    source = process_file.read_text(encoding="utf-8")
    for required in (
        "CreateProcessW",
        "CreateJobObjectW",
        "SetInformationJobObject",
        "AssignProcessToJobObject",
        "IsProcessInJob",
        "ResumeThread",
        "CloseHandle",
        "WaitForSingleObject",
        "GetExitCodeProcess",
        "QueryInformationJobObject",
        "TerminateJobObject",
    ):
        assert required in source
    assert "CREATE_BREAKAWAY_FROM_JOB" not in source
