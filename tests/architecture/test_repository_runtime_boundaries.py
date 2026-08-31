import ast

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for

REPOSITORY_ROOT = SOURCE_ROOT / "repository_runtime"
INTEGRATION_ROOT = SOURCE_ROOT / "repository_runtime_integrations"
COMPOSITION_ROOT = SOURCE_ROOT / "repository_runtime_composition"
FORBIDDEN_CONTEXTS = {
    "api",
    "approvals",
    "bootstrap",
    "commands",
    "governance",
    "private_evals",
    "project_governance",
    "resources",
    "sandbox",
    "skills",
    "tools",
    "workers",
}
FORBIDDEN_MODULES = {
    "dulwich",
    "git",
    "gitlab",
    "http",
    "httpx",
    "os",
    "pathlib",
    "pygit2",
    "requests",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
}
FORBIDDEN_CALLS = {"open", "run", "execute", "observe", "read", "write"}


def test_repository_runtime_imports_only_stdlib_and_itself() -> None:
    violations = []
    for path in REPOSITORY_ROOT.glob("*.py"):
        for module in imports_for(path):
            root = module.split(".", 1)[0]
            if module.startswith("synapse.") and not module.startswith(
                "synapse.repository_runtime"
            ):
                violations.append((path.name, module))
            allowed_adapter_import = path.name == "local_adapter.py" and root in {
                "os",
                "pathlib",
                "shutil",
                "subprocess",
            }
            if root in FORBIDDEN_CONTEXTS | FORBIDDEN_MODULES and not (
                (path.name == "sqlite_persistence.py" and root == "sqlite3")
                or allowed_adapter_import
            ):
                violations.append((path.name, module))
    assert not violations


def test_repository_runtime_has_no_concrete_io_git_or_forbidden_execution_surface() -> None:
    violations = []
    for path in REPOSITORY_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                "run",
                "execute",
                "observe",
                "read_repository",
                "write",
            }:
                violations.append((path.name, node.name))
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in FORBIDDEN_CALLS and not (
                    (path.name == "sqlite_persistence.py" and name == "execute")
                    or path.name == "local_adapter.py"
                ):
                    violations.append((path.name, name))
    assert not violations


def test_only_declared_consumer_owned_ports_are_exposed() -> None:
    path = REPOSITORY_ROOT / "contracts.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    protocols = {
        node.name: {
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    assert protocols == {
        "RepositoryAuthorizationFactsPort": {"facts_for"},
        "RepositoryMutationCleanupPort": {"request_cleanup"},
        "RepositoryMutationInterruptionPort": {"interrupt_sequence"},
        "RepositoryMutationObservationPort": {"observe_result"},
        "RepositoryMutationOperationPort": {"apply_operation"},
        "RepositoryMutationPreconditionPort": {"revalidate_preconditions"},
        "RepositoryObservationView": {"repository_id", "checkout_id", "fingerprint"},
        "RepositoryObservationFactsPort": {"facts_for"},
        "RepositoryPathFingerprintFactsPort": {"fingerprint_facts_for"},
        "RepositoryRecoveryInterruptionPort": {"interrupt_recovery"},
        "RepositoryRecoveryObservationPort": {"observe_recovery_step"},
        "RepositoryRecoveryPreconditionPort": {"revalidate_recovery_preconditions"},
        "RepositoryRecoveryStepPort": {"apply_recovery_step"},
        "RepositoryRecoveryVerificationPort": {"verify_recovered_state"},
        "RepositoryRestorePointMaterializationPort": {"materialize_restore_point"},
    }


def test_persistence_ports_and_sqlite_exception_are_narrow() -> None:
    path = REPOSITORY_ROOT / "persistence_contracts.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    protocols = {
        node.name: {
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    assert protocols == {
        "RepositoryArtifactStore": {"append", "get_exact", "replay", "restart_state"},
        "RepositoryMutationLifecycleStore": set(),
        "RepositoryObservationSnapshotStore": set(),
        "RepositoryPlanningAuthorizationStore": set(),
        "RepositoryRecoveryEvidenceStore": set(),
    }
    adapter = (REPOSITORY_ROOT / "sqlite_persistence.py").read_text(encoding="utf-8")
    assert "import sqlite3" in adapter
    assert all(
        token not in adapter
        for token in ("apply_operation", "apply_recovery_step", "observe_result")
    )


def test_local_adapter_git_commands_are_closed_and_non_publishing() -> None:
    path = REPOSITORY_ROOT / "local_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    invoked = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") == "_git"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert invoked <= {
        "--version",
        "config",
        "ls-files",
        "rev-parse",
        "status",
        "symbolic-ref",
    }
    assert not invoked & {
        "add",
        "branch",
        "checkout",
        "commit",
        "fetch",
        "merge",
        "pull",
        "push",
        "rebase",
        "reset",
        "restore",
        "switch",
        "tag",
    }


def test_repository_composition_edges_are_one_way_and_outside_sccs() -> None:
    graph = context_graph()
    assert {
        edge for edge in graph if any(node.startswith("repository_runtime") for node in edge)
    } == {
        ("coding_sessions_integrations", "repository_runtime"),
        ("coding_sessions_integrations", "repository_runtime_integrations"),
        ("repository_runtime_composition", "repository_runtime"),
        ("repository_runtime_composition", "repository_runtime_integrations"),
        ("repository_runtime_integrations", "repository_runtime"),
    }
    assert all(
        not (
            {
                "repository_runtime",
                "repository_runtime_composition",
                "repository_runtime_integrations",
            }
            & members
        )
        for members, _ in cyclic_components(graph)
    )


def test_coding_sessions_integration_is_pure_reference_only() -> None:
    violations = []
    for path in INTEGRATION_ROOT.glob("*.py"):
        for module in imports_for(path):
            root = module.split(".", 1)[0]
            if root in FORBIDDEN_MODULES:
                violations.append((path.name, module))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in FORBIDDEN_CALLS:
                    violations.append((path.name, name))
    repository_imports = {
        module
        for path in REPOSITORY_ROOT.glob("*.py")
        for module in imports_for(path)
        if "repository_runtime_integrations" in module
    }
    assert not violations
    assert not repository_imports


def test_repository_composition_has_only_the_authorized_global_bootstrap_imports() -> None:
    domain_imports = {
        module
        for root in (REPOSITORY_ROOT, INTEGRATION_ROOT)
        for path in root.glob("*.py")
        for module in imports_for(path)
        if "repository_runtime_composition" in module
    }
    bootstrap_imports = {
        module
        for path in (SOURCE_ROOT / "bootstrap").rglob("*.py")
        for module in imports_for(path)
        if "repository_runtime" in module
    }
    composition_imports = {
        module for path in COMPOSITION_ROOT.glob("*.py") for module in imports_for(path)
    }
    assert not domain_imports
    assert bootstrap_imports == {
        "synapse.bootstrap.adapters.repository_runtime",
        "synapse.health.contributors.repository_runtime",
        "synapse.repository_runtime",
        "synapse.repository_runtime_composition",
    }
    assert "synapse.repository_runtime" in composition_imports
    assert "synapse.repository_runtime_integrations" in composition_imports


def test_public_exports_are_explicit_and_resolve() -> None:
    source = (REPOSITORY_ROOT / "__init__.py").read_text(encoding="utf-8")
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
