from __future__ import annotations

import ast
import csv
import tempfile
from copy import copy
from pathlib import Path

import pytest

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.health.contracts import HealthCheckContext

from .support import SOURCE_ROOT, imports_for

HEALTH = SOURCE_ROOT / "health"
CONTRIBUTORS = HEALTH / "contributors"
BASELINE = SOURCE_ROOT.parent.parent / "docs" / "validation" / "health-surface-before.csv"


@pytest.fixture(scope="module")
def runtime():
    with tempfile.TemporaryDirectory() as directory:
        yield create_runtime(
            Settings(
                project_root=SOURCE_ROOT.parent.parent,
                data_dir=Path(directory) / "data",
                host="127.0.0.1",
                port=8717,
                default_actor_id="local_owner",
            )
        )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _contributor_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in CONTRIBUTORS.glob("*.py")
        if path.name not in {"__init__.py", "base.py"}
    )


def _declared_component_ids(runtime) -> list[str]:
    context = HealthCheckContext(
        timestamp="structural-health-surface",
        correlation_id=None,
        mode="structural",
        timeout_budget_seconds=0.0,
        include_diagnostics=False,
        metadata={},
    )
    declared = []
    for registration in runtime.health.registry.list_contributors():
        contributor = registration.contributor
        assert contributor is not None
        if registration.contributor_id == "voice":
            contributor = copy(contributor)
            for dependency in (
                "voice",
                "speech_adapters",
                "speech_pipeline",
                "multimodal",
                "audio",
            ):
                setattr(contributor, dependency, None)
        declared.extend(contributor.collect_health(context).components)
    return [item.component_id for _, item in sorted(declared, key=lambda pair: pair[0])]


def test_health_runtime_and_registry_are_domain_neutral() -> None:
    allowed = ("__future__", "dataclasses", "datetime", "queue", "threading", "time", "typing", "synapse.health", "synapse.observability")
    for name in ("runtime.py", "registry.py", "contracts.py"):
        imports = imports_for(HEALTH / name)
        assert all(module.startswith(allowed) for module in imports), (name, imports)


def test_readiness_runtime_imports_only_neutral_contracts() -> None:
    allowed = ("__future__", "dataclasses", "typing", "synapse.core", "synapse.health", "synapse.readiness")
    imports = imports_for(SOURCE_ROOT / "readiness" / "runtime.py")
    assert all(module.startswith(allowed) for module in imports), imports


def test_contributors_do_not_import_delivery_storage_or_bootstrap() -> None:
    forbidden = ("synapse.api", "synapse.commands", "synapse.bootstrap")
    violations = []
    for path in _contributor_paths():
        for module in imports_for(path):
            if module.startswith(forbidden) or module.endswith((".store", ".storage")):
                violations.append(f"{path.name}: {module}")
    assert not violations, "Forbidden contributor imports:\n" + "\n".join(violations)


def test_contributors_do_not_construct_runtimes_or_call_mutating_operations() -> None:
    forbidden_calls = {"create", "delete", "emit", "start", "stop", "update", "write"}
    violations = []
    for path in _contributor_paths():
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id.endswith("Runtime"):
                violations.append(f"{path.name}:{node.lineno}:{node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_calls:
                violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert not violations, "Contributor side effects/construction:\n" + "\n".join(violations)


def test_production_component_ids_match_baseline_and_are_unique(runtime) -> None:
    with BASELINE.open(encoding="utf-8", newline="") as file:
        expected = [row["component_id"] for row in csv.DictReader(file)]
    actual = _declared_component_ids(runtime)
    assert actual == expected
    assert len(actual) == len(set(actual))
    assert "voice" in actual
    assert "intelligence_boundary" in actual


def test_bootstrap_registers_every_production_contributor(runtime) -> None:
    modules = {path.stem for path in _contributor_paths()}
    registered = runtime.health.registry.list_contributors()
    contributor_modules = {
        type(item.contributor).__module__.rsplit(".", 1)[-1]
        for item in registered
        if item.contributor is not None
    }
    assert contributor_modules == modules
    assert len(runtime.health.registry.contributor_ids) == len(set(runtime.health.registry.contributor_ids))


def test_domains_do_not_import_concrete_health_runtime() -> None:
    violations = []
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT)
        if relative.parts[0] in {"bootstrap", "health"}:
            continue
        for module in imports_for(path):
            if module == "synapse.health.runtime":
                violations.append(str(relative))
    assert not violations, "Concrete HealthRuntime imports:\n" + "\n".join(violations)
