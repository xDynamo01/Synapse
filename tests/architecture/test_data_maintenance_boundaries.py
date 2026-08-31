from __future__ import annotations

import ast

from .support import SOURCE_ROOT, imports_for

MAINTENANCE = SOURCE_ROOT / "maintenance"


def test_api_and_commands_do_not_access_data_dir_for_maintenance() -> None:
    violations = []
    for root in (SOURCE_ROOT / "api", SOURCE_ROOT / "commands"):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "data_dir":
                    violations.append(f"{path.name}:{node.lineno}")
    assert not violations


def test_maintenance_delivery_modules_do_not_import_filesystem_libraries() -> None:
    paths = (
        SOURCE_ROOT / "api" / "routers" / "maintenance.py",
        SOURCE_ROOT / "commands" / "handlers" / "maintenance.py",
    )
    for path in paths:
        imports = imports_for(path)
        assert not any(module in {"os", "pathlib", "shutil"} for module in imports)


def test_maintenance_runtime_is_domain_neutral() -> None:
    imports = imports_for(MAINTENANCE / "runtime.py")
    forbidden = (
        "synapse.agents",
        "synapse.missions",
        "synapse.voice",
        "synapse.perception",
        "synapse.retention",
        "synapse.notifications",
        "synapse.api",
        "synapse.commands",
        "synapse.bootstrap",
    )
    assert not any(module.startswith(forbidden) for module in imports)


def test_maintenance_registry_has_no_filesystem_dependency() -> None:
    imports = imports_for(MAINTENANCE / "registry.py")
    assert not any(module in {"os", "pathlib", "shutil"} for module in imports)
    text = (MAINTENANCE / "registry.py").read_text(encoding="utf-8")
    assert not any(token in text for token in (".unlink(", ".rglob(", ".resolve("))


def test_contributors_do_not_import_delivery_or_bootstrap() -> None:
    imports = imports_for(MAINTENANCE / "contributors.py")
    assert not any(
        module.startswith(("synapse.api", "synapse.commands", "synapse.bootstrap"))
        for module in imports
    )


def test_public_maintenance_contract_has_no_arbitrary_path_field() -> None:
    api = (SOURCE_ROOT / "api" / "routers" / "maintenance.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(api)
    payloads = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Payload")
    }
    forbidden = {"path", "directory", "target", "wildcard", "glob"}
    for payload in payloads.values():
        fields = {
            node.target.id
            for node in payload.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
        }
        assert not fields & forbidden


def test_destructive_execution_requires_stored_plan_guards() -> None:
    text = (MAINTENANCE / "runtime.py").read_text(encoding="utf-8")
    for guard in (
        "get_plan(request.plan_id)",
        "request.checksum != plan.checksum",
        "request.expected_revision != plan.revision",
        "request.confirmed",
        "_authorize_execution",
        "self.lock.acquire()",
    ):
        assert guard in text


def test_every_maintenance_action_resolves_registered_contributor() -> None:
    tree = ast.parse((MAINTENANCE / "runtime.py").read_text(encoding="utf-8"))
    execute_action = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_execute_action"
    )
    text = ast.unparse(execute_action)
    assert "self.registry.get(action.contributor_id)" in text
    assert "contributor.execute_cleanup" in text


def test_data_dir_has_no_administrative_maintenance_behavior() -> None:
    path = SOURCE_ROOT / "core" / "data_dir.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    data_dir = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DataDir"
    )
    methods = {
        node.name
        for node in data_dir.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "cleanup_temp" not in methods
    assert "diagnostics" not in methods
    imports = imports_for(path)
    assert not any(
        module.startswith(("synapse.maintenance", "synapse.retention"))
        for module in imports
    )


def test_storage_primitives_do_not_depend_on_maintenance() -> None:
    imports = {
        module
        for path in (SOURCE_ROOT / "storage").glob("*.py")
        for module in imports_for(path)
    }
    assert not any(module.startswith("synapse.maintenance") for module in imports)


def test_legacy_foundation_adapter_and_generic_cleanup_surfaces_are_absent() -> None:
    assert not (SOURCE_ROOT / "api" / "foundation_adapter.py").exists()
    delivery = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (SOURCE_ROOT / "api", SOURCE_ROOT / "commands")
        for path in root.rglob("*.py")
    )
    for forbidden in (
        "/foundation/cleanup-temp",
        "/retention/cleanup-all",
        'name=\'/cleanup-temp\'',
        'name=\'/retention-cleanup\'',
        'name=\'/retention-cleanup-all\'',
    ):
        assert forbidden not in delivery


def test_retention_cleanup_is_adapted_once_by_owning_contributor() -> None:
    runtime = (MAINTENANCE / "runtime.py").read_text(encoding="utf-8")
    contributors = (MAINTENANCE / "contributors.py").read_text(encoding="utf-8")
    assert "cleanup_domain(" not in runtime
    assert contributors.count("self.retention.cleanup_domain(") == 2
