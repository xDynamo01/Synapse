from __future__ import annotations

import ast

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for

CODING_SESSIONS_ROOT = SOURCE_ROOT / "coding_sessions"
CODING_SESSIONS_INTEGRATIONS_ROOT = SOURCE_ROOT / "coding_sessions_integrations"
CODING_SESSIONS_COMPOSITION_ROOT = SOURCE_ROOT / "coding_sessions_composition"
SQLITE_ADAPTERS = {"sqlite_persistence.py", "fencing_sqlite.py"}
FORBIDDEN_CONTEXTS = {
    "approvals",
    "bootstrap",
    "missions",
    "private_evals",
    "project_governance",
    "repository_runtime",
    "repository_runtime_composition",
    "repository_runtime_integrations",
    "sandbox",
    "sandbox_composition",
    "sandbox_integrations",
    "workers",
}
FORBIDDEN_MODULES = {
    "asyncio",
    "http",
    "httpx",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
}


def test_coding_sessions_foundation_is_pure_and_inward_only() -> None:
    violations = []
    for path in CODING_SESSIONS_ROOT.glob("*.py"):
        for module in imports_for(path):
            root = module.split(".", 1)[0]
            target = module.split(".", 2)[1] if module.startswith("synapse.") else ""
            if path.name in SQLITE_ADAPTERS and root == "sqlite3":
                continue
            if root in FORBIDDEN_MODULES or target in FORBIDDEN_CONTEXTS:
                violations.append((path.name, module))
    assert not violations
    assert not {edge for edge in context_graph() if edge[0] == "coding_sessions"}


def test_coding_sessions_foundation_has_no_io_persistence_or_execution_surface() -> None:
    forbidden_calls = {"open", "read", "write", "execute", "run", "connect"}
    forbidden_names = {
        "active_session",
        "adapter",
        "checkpoint_store",
        "current_lease",
        "current_checkpoint",
        "execute",
        "invoke",
        "journal_store",
        "load_latest",
        "resume_automatically",
        "repair_automatically",
        "recover_automatically",
        "latest_lease",
        "latest_session",
        "get_current",
        "get_latest",
        "repository_runtime",
        "session_store",
    }
    violations = []
    for path in CODING_SESSIONS_ROOT.glob("*.py"):
        if path.name in SQLITE_ADAPTERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in forbidden_calls:
                    violations.append((path.name, name))
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.lower() in forbidden_names:
                    violations.append((path.name, node.name))
    assert not violations


def test_only_nominal_sqlite_adapters_may_import_sqlite() -> None:
    sqlite_importers = {
        path.name
        for path in CODING_SESSIONS_ROOT.glob("*.py")
        if "sqlite3" in imports_for(path)
    }
    assert sqlite_importers == SQLITE_ADAPTERS
    for adapter in SQLITE_ADAPTERS:
        adapter_imports = imports_for(CODING_SESSIONS_ROOT / adapter)
        assert not {
            module
            for module in adapter_imports
            if module.startswith("synapse.")
            and module.split(".", 2)[1] in FORBIDDEN_CONTEXTS
        }


def test_coding_sessions_contract_models_do_not_claim_runtime_state_or_authority() -> None:
    from synapse.coding_sessions import CodingSessionContractAssessment

    forbidden = {
        "activate",
        "authorize",
        "cancel",
        "execute",
        "lease",
        "pause",
        "prepare",
        "resume",
        "transition",
    }
    assert not forbidden & set(dir(CodingSessionContractAssessment))


def test_coding_sessions_is_outside_existing_sccs() -> None:
    assert all(
        "coding_sessions" not in members for members, _ in cyclic_components(context_graph())
    )


def test_coding_sessions_repository_compatibility_edges_are_one_way_and_explicit() -> None:
    graph = context_graph()
    assert {edge for edge in graph if edge[0] == "coding_sessions_integrations"} == {
        ("coding_sessions_integrations", "approvals"),
        ("coding_sessions_integrations", "coding_sessions"),
        ("coding_sessions_integrations", "decisions"),
        ("coding_sessions_integrations", "missions"),
        ("coding_sessions_integrations", "project_governance"),
        ("coding_sessions_integrations", "private_evals"),
        ("coding_sessions_integrations", "repository_runtime"),
        ("coding_sessions_integrations", "repository_runtime_integrations"),
        ("coding_sessions_integrations", "sandbox"),
        ("coding_sessions_integrations", "workers"),
    }
    assert not {
        edge
        for edge in graph
        if edge[0] in {"repository_runtime", "repository_runtime_integrations"}
        and edge[1] in {"coding_sessions", "coding_sessions_integrations"}
    }
    assert not {
        edge
        for edge in graph
        if edge[0] == "private_evals"
        and edge[1] in {"coding_sessions", "coding_sessions_integrations"}
    }
    assert not {
        edge
        for edge in graph
        if edge[0] == "sandbox"
        and edge[1] in {"coding_sessions", "coding_sessions_integrations"}
    }
    assert not {
        edge
        for edge in graph
        if edge[0] in {"missions", "workers"}
        and edge[1] in {"coding_sessions", "coding_sessions_integrations"}
    }
    assert all(
        "coding_sessions_integrations" not in members
        for members, _ in cyclic_components(graph)
    )


def test_coding_sessions_repository_compatibility_adapter_has_no_io_surface() -> None:
    allowed_by_module = {
        "deployment.py": {"coding_sessions"},
        "repository_runtime.py": {"coding_sessions", "repository_runtime", "repository_runtime_integrations"},
        "governance.py": {"approvals", "coding_sessions", "decisions", "project_governance"},
        "private_evals.py": {"coding_sessions", "private_evals"},
        "sandbox.py": {"coding_sessions", "sandbox"},
        "workers_missions.py": {"coding_sessions", "missions", "workers"},
        "__init__.py": {"coding_sessions_integrations"},
    }
    forbidden_modules = {
        "asyncio",
        "http",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {"connect", "execute", "open", "read", "run", "write"}
    violations = []
    for path in CODING_SESSIONS_INTEGRATIONS_ROOT.glob("*.py"):
        allowed_contexts = allowed_by_module[path.name]
        modules = imports_for(path)
        for module in modules:
            root = module.split(".", 1)[0]
            if root in forbidden_modules:
                violations.append((path.name, module))
            if module.startswith("synapse.") and module.split(".", 2)[1] not in allowed_contexts:
                violations.append((path.name, module))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in forbidden_calls:
                    violations.append((path.name, name))
    assert not violations


def test_public_exports_are_minimal_explicit_and_resolve() -> None:
    import synapse.coding_sessions as coding_sessions

    source = (CODING_SESSIONS_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "canonical_bytes" not in coding_sessions.__all__
    assert "content_fingerprint" not in coding_sessions.__all__
    assert len(coding_sessions.__all__) == len(set(coding_sessions.__all__))
    assert coding_sessions.__all__ == sorted(coding_sessions.__all__)
    assert all(hasattr(coding_sessions, name) for name in coding_sessions.__all__)
    assert "repository_runtime" not in source


def test_coding_sessions_composition_is_opt_in_and_one_way() -> None:
    graph = context_graph()
    assert {edge for edge in graph if edge[0] == "coding_sessions_composition"} == {
        ("coding_sessions_composition", "coding_sessions"),
        ("coding_sessions_composition", "coding_sessions_integrations"),
    }
    assert not {
        edge
        for edge in graph
        if edge[0] in {"bootstrap", "coding_sessions", "coding_sessions_integrations"}
        and edge[1] == "coding_sessions_composition"
    }
    imports = {
        module
        for path in CODING_SESSIONS_COMPOSITION_ROOT.glob("*.py")
        for module in imports_for(path)
    }
    assert not any(module.startswith("synapse.bootstrap") for module in imports)
    assert all(
        "coding_sessions_composition" not in members
        for members, _ in cyclic_components(graph)
    )
