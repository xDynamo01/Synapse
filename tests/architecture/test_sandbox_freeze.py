from __future__ import annotations

import ast

from tests.architecture.support import SOURCE_ROOT, context_graph, cyclic_components, imports_for
from tests.architecture.test_audio_speech_boundary import _runtime_context_graph

import synapse.sandbox as sandbox
import synapse.sandbox_composition as sandbox_composition
import synapse.sandbox_integrations as sandbox_integrations
from synapse.sandbox.sqlite_persistence import _MIGRATION_CHECKSUM

SANDBOX_ROOT = SOURCE_ROOT / "sandbox"
INTEGRATION_ROOT = SOURCE_ROOT / "sandbox_integrations"
COMPOSITION_ROOT = SOURCE_ROOT / "sandbox_composition"
BOOTSTRAP_ROOT = SOURCE_ROOT / "bootstrap"
AUTHORIZED_BOOTSTRAP_ADAPTERS = {
    BOOTSTRAP_ROOT / "adapters" / "sandbox.py",
    BOOTSTRAP_ROOT / "adapters" / "sandbox_policy.py",
}

FROZEN_MODULE_COUNTS = {
    SANDBOX_ROOT: 24,
    INTEGRATION_ROOT: 3,
    COMPOSITION_ROOT: 2,
}
FROZEN_EXPORT_COUNTS = {
    sandbox: 358,
    sandbox_integrations: 8,
    sandbox_composition: 12,
}
REMOVED_PROVISIONAL_EXPORTS = {
    "ResourceUsageSummary",
    "SandboxAdmissionState",
    "SandboxAuthorizationState",
    "SandboxExecutabilityState",
    "SandboxExecutionState",
    "SandboxMaterializationState",
    "SandboxOutcome",
}
FROZEN_MIGRATION_CHECKSUM = "c83b149985d436d8d9959fd51b0bcdba94376f6f2377967553b33d5a4ae4cb59"


def test_frozen_module_and_public_export_baselines_are_exact() -> None:
    assert {
        root: len(tuple(root.glob("*.py"))) for root in FROZEN_MODULE_COUNTS
    } == FROZEN_MODULE_COUNTS
    for module, expected_count in FROZEN_EXPORT_COUNTS.items():
        exports = tuple(module.__all__)
        assert len(exports) == expected_count
        assert len(set(exports)) == expected_count
        assert all(hasattr(module, name) for name in exports)
        assert REMOVED_PROVISIONAL_EXPORTS.isdisjoint(exports)


def test_frozen_formats_schema_and_migration_checksum_are_exact() -> None:
    assert sandbox.CANONICAL_FORMAT == "sandbox-json-v1"
    assert sandbox.SANDBOX_RECORD_FORMAT == "sandbox-record-v1"
    assert sandbox.SANDBOX_SCHEMA_VERSION == 1
    assert _MIGRATION_CHECKSUM == FROZEN_MIGRATION_CHECKSUM


def test_frozen_runtime_and_source_graph_baselines_are_exact() -> None:
    runtime = _runtime_context_graph()
    source = context_graph()
    assert len(runtime) == 304
    assert [(len(members), edges) for members, edges in cyclic_components(runtime)] == [(11, 31)]
    assert len(source) == 339
    assert sorted(
        (len(members), edges) for members, edges in cyclic_components(source)
    ) == [(3, 4), (24, 80)]
    sandbox_contexts = {
        "sandbox",
        "sandbox_integrations",
        "sandbox_composition",
        "sandbox_drivers",
        "sandbox_driver_composition",
    }
    assert all(
        sandbox_contexts.isdisjoint(members)
        for graph in (runtime, source)
        for members, _ in cyclic_components(graph)
    )


def test_frozen_boundary_has_only_governed_bootstrap_activation_and_no_driver() -> None:
    imports = {
        (path, module)
        for path in BOOTSTRAP_ROOT.rglob("*.py")
        for module in imports_for(path)
        if module.startswith(("synapse.sandbox", "synapse.sandbox_composition"))
    }
    assert {path for path, _ in imports} == AUTHORIZED_BOOTSTRAP_ADAPTERS
    assert not any(module.startswith("synapse.sandbox_drivers") for _, module in imports)
    forbidden_imports = {"http", "httpx", "requests", "socket", "subprocess", "urllib"}
    assert not [
        (path.relative_to(SOURCE_ROOT), module)
        for root in (SANDBOX_ROOT, INTEGRATION_ROOT, COMPOSITION_ROOT)
        for path in root.rglob("*.py")
        for module in imports_for(path)
        if module.split(".", 1)[0] in forbidden_imports
    ]
    assert not hasattr(sandbox_composition.SandboxRuntime, "execute")


def test_frozen_recovery_reader_is_read_only() -> None:
    path = SANDBOX_ROOT / "sqlite_persistence.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    recovery = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SQLiteSandboxRecoveryReader"
    )
    methods = {
        node.name
        for node in recovery.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {"__init__", "findings"}
    forbidden_calls = {"cleanup", "retry", "supervise", "terminate"}
    assert not [
        name
        for node in ast.walk(recovery)
        if isinstance(node, ast.Call)
        for name in (getattr(node.func, "id", getattr(node.func, "attr", "")),)
        if name in forbidden_calls
    ]
    recovery_source = ast.get_source_segment(path.read_text(encoding="utf-8"), recovery)
    assert recovery_source is not None
    assert not any(
        statement in recovery_source.upper()
        for statement in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "ALTER ")
    )


def test_freeze_documentation_has_no_stale_module_status() -> None:
    document = (
        SOURCE_ROOT.parent.parent / "docs" / "architecture" / "sandbox-execution-boundary.md"
    ).read_text(encoding="utf-8")
    assert "module NOT IMPLEMENTED" not in document
    assert "Sandbox Execution Boundary — IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN" in document
