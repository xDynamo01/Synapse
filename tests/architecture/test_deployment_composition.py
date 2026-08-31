from __future__ import annotations

import ast
from pathlib import Path

from .support import SOURCE_ROOT, production_files

COMPOSITION_ROOT = SOURCE_ROOT / "deployment_composition"
BOOTSTRAP_ROOT = SOURCE_ROOT / "bootstrap"


def test_deployment_composition_surface_is_small_and_explicit() -> None:
    assert tuple(path.name for path in sorted(COMPOSITION_ROOT.glob("*.py"))) == (
        "__init__.py",
        "runtime.py",
    )
    assert len((COMPOSITION_ROOT / "runtime.py").read_text(encoding="utf-8").splitlines()) < 340


def test_global_bootstrap_constructs_deployment_once_without_starting_it() -> None:
    importers = []
    for path in BOOTSTRAP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        if any(module.startswith("synapse.deployment_composition") for module in imports):
            importers.append(path.relative_to(SOURCE_ROOT))
    assert importers == [
        Path("bootstrap/container.py"),
        Path("bootstrap/adapters/deployment.py"),
        Path("bootstrap/adapters/global_runtimes.py"),
    ]
    application = (BOOTSTRAP_ROOT / "application.py").read_text(encoding="utf-8")
    global_runtimes = (BOOTSTRAP_ROOT / "adapters" / "global_runtimes.py").read_text(
        encoding="utf-8"
    )
    assert application.count("build_all(") == 1
    assert global_runtimes.count("build_deployment_runtime(") == 1
    assert "deployment.start(" not in application


def test_deployment_domain_does_not_import_its_composition_surface() -> None:
    offenders: list[Path] = []
    for path in production_files():
        if COMPOSITION_ROOT in path.parents:
            continue
        relative = path.relative_to(SOURCE_ROOT)
        if relative.parts[0] not in {
            "deployment",
            "deployment_adapters",
            "deployment_integrations",
        }:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        if any(module.startswith("synapse.deployment_composition") for module in imports):
            offenders.append(relative)
    assert offenders == []
