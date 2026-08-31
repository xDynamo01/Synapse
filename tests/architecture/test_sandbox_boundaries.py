import ast

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for

SANDBOX_ROOT = SOURCE_ROOT / "sandbox"
SANDBOX_INTEGRATION_ROOT = SOURCE_ROOT / "sandbox_integrations"
SANDBOX_COMPOSITION_ROOT = SOURCE_ROOT / "sandbox_composition"
SANDBOX_DRIVERS_ROOT = SOURCE_ROOT / "sandbox_drivers"
SANDBOX_DRIVER_COMPOSITION_ROOT = SOURCE_ROOT / "sandbox_driver_composition"
CODING_SESSIONS_SANDBOX_ADAPTER = SOURCE_ROOT / "coding_sessions_integrations" / "sandbox.py"
DEPLOYMENT_CUSTODY_ADAPTER = SOURCE_ROOT / "deployment_integrations" / "custody.py"
DEPLOYMENT_HANDOFF_ADAPTER = SOURCE_ROOT / "deployment_integrations" / "sandbox_handoff.py"
BOOTSTRAP_SANDBOX_ADAPTERS = {
    SOURCE_ROOT / "bootstrap" / "adapters" / "sandbox.py",
    SOURCE_ROOT / "bootstrap" / "adapters" / "sandbox_policy.py",
}
FORBIDDEN_CONTEXTS = {
    "api",
    "approvals",
    "bootstrap",
    "commands",
    "governance",
    "private_evals",
    "project_governance",
    "resources",
    "skills",
    "tools",
    "workers",
}
FORBIDDEN_CALLS = {"open", "exec", "eval", "run", "execute", "Popen"}
FORBIDDEN_IO_MODULES = {
    "http",
    "httpx",
    "requests",
    "socket",
    "subprocess",
    "urllib",
}
SANDBOX_IO_ADAPTERS = {"sqlite_persistence.py"}


def test_sandbox_imports_only_stdlib_and_itself() -> None:
    violations = []
    for path in SANDBOX_ROOT.glob("*.py"):
        for module in imports_for(path):
            if module.startswith("synapse.") and not module.startswith("synapse.sandbox"):
                violations.append((path.name, module))
            if module.split(".", 1)[0] in FORBIDDEN_CONTEXTS:
                violations.append((path.name, module))
            if module.split(".", 1)[0] in FORBIDDEN_IO_MODULES:
                violations.append((path.name, module))
    assert not violations


def test_existing_contexts_do_not_import_sandbox() -> None:
    violations = []
    for path in SOURCE_ROOT.rglob("*.py"):
        if SANDBOX_ROOT in path.parents:
            continue
        if SANDBOX_INTEGRATION_ROOT in path.parents:
            continue
        if SANDBOX_COMPOSITION_ROOT in path.parents:
            continue
        if SANDBOX_DRIVERS_ROOT in path.parents:
            continue
        if SANDBOX_DRIVER_COMPOSITION_ROOT in path.parents:
            continue
        if path == CODING_SESSIONS_SANDBOX_ADAPTER:
            continue
        if path in {DEPLOYMENT_CUSTODY_ADAPTER, DEPLOYMENT_HANDOFF_ADAPTER}:
            continue
        if path in BOOTSTRAP_SANDBOX_ADAPTERS:
            continue
        for module in imports_for(path):
            if module.startswith("synapse.sandbox"):
                violations.append((path.relative_to(SOURCE_ROOT), module))
    assert not violations


def test_sandbox_contains_no_execution_or_io_surface() -> None:
    violations = []
    for path in SANDBOX_ROOT.glob("*.py"):
        if path.name in SANDBOX_IO_ADAPTERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in FORBIDDEN_CALLS
            ):
                violations.append((path.name, node.name))
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in FORBIDDEN_CALLS:
                    violations.append((path.name, name))
    assert not violations


def test_sandbox_sqlite_adapter_has_no_operational_authority() -> None:
    path = SANDBOX_ROOT / "sqlite_persistence.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    forbidden_methods = {"cleanup", "evaluate_policy", "execute_workload", "supervise"}
    assert not [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in forbidden_methods
    ]


def test_sandbox_adds_no_governed_edge_and_is_outside_sccs() -> None:
    graph = context_graph()
    assert {edge for edge in graph if "sandbox" in edge} == {
        ("coding_sessions_integrations", "sandbox"),
        ("deployment_integrations", "sandbox"),
        ("sandbox_composition", "sandbox"),
        ("sandbox_integrations", "sandbox"),
        ("sandbox_drivers", "sandbox"),
        ("sandbox_driver_composition", "sandbox"),
    }
    assert all("sandbox" not in members for members, _ in cyclic_components(graph))


def test_skills_handoff_adapter_is_the_only_authorized_skills_sandbox_edge() -> None:
    graph = context_graph()
    assert ("sandbox_integrations", "skills") in graph
    adapter_files = tuple(SANDBOX_INTEGRATION_ROOT.rglob("*.py"))
    assert adapter_files
    assert not any(
        module.split(".", 1)[0]
        in {"http", "httpx", "os", "pathlib", "requests", "socket", "sqlite3", "subprocess"}
        for path in adapter_files
        for module in imports_for(path)
    )
    forbidden_calls = {
        "cleanup",
        "evaluate_policy",
        "execute",
        "execute_workload",
        "open",
        "persist",
        "save",
        "supervise",
    }
    assert not [
        (path.name, name)
        for path in adapter_files
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        for name in (getattr(node.func, "id", getattr(node.func, "attr", "")),)
        if name in forbidden_calls
    ]


def test_composition_root_has_only_the_governed_global_activation() -> None:
    graph = context_graph()
    assert {edge for edge in graph if edge[0] == "sandbox_composition"} == {
        ("sandbox_composition", "sandbox"),
        ("sandbox_composition", "sandbox_integrations"),
    }
    assert not any(
        module.startswith("synapse.sandbox_composition")
        for path in SANDBOX_ROOT.rglob("*.py")
        for module in imports_for(path)
    )
    bootstrap = SOURCE_ROOT / "bootstrap"
    imports = {
        (path, module)
        for path in bootstrap.rglob("*.py")
        for module in imports_for(path)
        if module.startswith(("synapse.sandbox", "synapse.sandbox_composition"))
    }
    assert {path for path, _ in imports} == BOOTSTRAP_SANDBOX_ADAPTERS
    assert not any(module.startswith("synapse.sandbox_drivers") for _, module in imports)


def test_public_exports_resolve() -> None:
    source = (SANDBOX_ROOT / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    exported = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    assert isinstance(exported, (ast.List, ast.Tuple))
    assert all(
        isinstance(item, ast.Constant) and isinstance(item.value, str) for item in exported.elts
    )
