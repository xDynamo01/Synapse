from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend" / "synapse"


def _methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {node.name for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_catalog_is_discovery_only() -> None:
    methods = _methods(BACKEND / "providers" / "catalog.py", "ProviderCatalog")
    assert not methods & {"execute", "load", "invoke", "store", "fallback", "create"}
    assert {"register", "get", "list", "set_availability"} <= methods


def test_canonical_manifest_has_no_execution_contract() -> None:
    methods = _methods(BACKEND / "providers" / "taxonomy.py", "CanonicalProviderManifest")
    assert not methods & {"execute", "invoke", "complete", "transcribe", "synthesize"}


def test_concrete_domains_are_confined_to_bootstrap_projection() -> None:
    catalog_source = (BACKEND / "providers" / "catalog.py").read_text(encoding="utf-8")
    taxonomy_source = (BACKEND / "providers" / "taxonomy.py").read_text(encoding="utf-8")
    forbidden = (
        "model_hub", "speech_adapters", "vision", "desktop_automation",
        "system_insight", "notifications",
    )
    imports = []
    for source in (catalog_source, taxonomy_source):
        tree = ast.parse(source)
        imports.extend(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        imports.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
    assert not any(any(name in imported for name in forbidden) for imported in imports)


def test_bootstrap_constructs_one_catalog_and_projects_explicitly() -> None:
    models_source = (BACKEND / "bootstrap" / "features" / "models.py").read_text(
        encoding="utf-8"
    )
    integration_source = (
        BACKEND / "bootstrap" / "features" / "integration.py"
    ).read_text(encoding="utf-8")
    assert models_source.count("ProviderCatalog()") == 1
    assert "register_model_provider_projections" in models_source
    assert "register_runtime_provider_projections" in integration_source
