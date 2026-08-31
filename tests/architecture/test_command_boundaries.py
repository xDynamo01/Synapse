from __future__ import annotations

import ast
import csv
from pathlib import Path

from synapse.commands.handlers import build_command_handlers
from synapse.commands.registry import CommandRegistry
from synapse.commands.services import CommandServices

from .support import SOURCE_ROOT, imports_for

COMMANDS_ROOT = SOURCE_ROOT / "commands"
HANDLERS_ROOT = COMMANDS_ROOT / "handlers"
BASELINE = SOURCE_ROOT.parent.parent / "docs" / "validation" / "command-surface-before.csv"


def _handler_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in HANDLERS_ROOT.glob("*.py")
        if path.name not in {"__init__.py", "base.py"}
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_command_runtime_is_only_a_facade_and_dispatcher() -> None:
    tree = _tree(COMMANDS_ROOT / "runtime.py")
    runtime = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CommandRuntime"
    )
    methods = {
        node.name
        for node in runtime.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {
        "__init__",
        "execute",
        "chat",
        "world_state",
        "attention",
        "agent_loop",
        "desktop",
    }


def test_handlers_do_not_import_forbidden_infrastructure() -> None:
    forbidden = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.memory.store",
        "synapse.model_providers.lmstudio",
    )
    violations = []
    for path in _handler_paths():
        for module in imports_for(path):
            if module.startswith(forbidden) or module.endswith((".store", ".storage")):
                violations.append(f"{path.name}: {module}")
    assert not violations, "Forbidden handler imports:\n" + "\n".join(violations)


def test_handlers_do_not_instantiate_runtimes_or_execute_subprocesses() -> None:
    violations = []
    for path in _handler_paths():
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.endswith("Runtime") or node.func.id in {
                    "Popen",
                    "run",
                    "check_call",
                    "check_output",
                }:
                    violations.append(f"{path.name}:{node.lineno}: {node.func.id}")
    assert not violations, "Forbidden handler construction/execution:\n" + "\n".join(
        violations
    )


def test_handlers_do_not_access_stores_or_data_dir_directly() -> None:
    violations = []
    for path in _handler_paths():
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Attribute):
                continue
            direct_store = (
                isinstance(node.value, ast.Name)
                and node.value.id == "self"
                and node.attr in {"config", "memory", "store", "storage"}
            )
            if direct_store or node.attr == "data_dir":
                violations.append(f"{path.name}:{node.lineno}: {node.attr}")
    assert not violations, "Direct handler state access:\n" + "\n".join(violations)


def test_registry_has_no_domain_or_infrastructure_dependencies() -> None:
    imports = imports_for(COMMANDS_ROOT / "registry.py")
    assert all(
        module.startswith(("__future__", "dataclasses", "typing", "synapse.commands"))
        for module in imports
    )


def test_registered_surface_matches_frozen_baseline() -> None:
    with BASELINE.open(encoding="utf-8", newline="") as file:
        baseline = list(csv.DictReader(file))

    handlers = build_command_handlers(CommandServices())
    registry = CommandRegistry()
    registry.register_all(handlers)
    metadata = registry.list_commands()

    expected_names = tuple(
        name
        for row in baseline
        for name in (row["command"], *filter(None, row["aliases"].split("|")))
    )
    assert set(registry.names) == set(expected_names)
    assert len(registry.names) == len(set(registry.names))
    assert len(metadata) == len(baseline)

    actual = {
        item.name: {
            "aliases": "|".join(item.aliases),
            "argument_names": "|".join(item.argument_names),
            "defaults": "|".join(item.defaults),
            "domain": item.domain,
            "category": item.category,
            "status": item.status,
            "source_sha256": item.source_sha256,
        }
        for item in metadata
    }
    expected = {
        row["command"]: {
            key: row[key]
            for key in (
                "aliases",
                "argument_names",
                "defaults",
                "domain",
                "category",
                "status",
                "source_sha256",
            )
        }
        for row in baseline
    }
    assert actual == expected


def test_every_concrete_handler_is_explicitly_registered() -> None:
    handlers = build_command_handlers(CommandServices())
    registered_modules = {type(handler).__module__ for handler in handlers}
    expected_modules = {
        f"synapse.commands.handlers.{path.stem}" for path in _handler_paths()
    }
    assert registered_modules == expected_modules
    assert all(handler.metadata for handler in handlers)
