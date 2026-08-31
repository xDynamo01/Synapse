from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import synapse.repository_runtime as repository_runtime
import synapse.repository_runtime_composition as repository_runtime_composition
import synapse.repository_runtime_integrations as repository_runtime_integrations
from synapse.repository_runtime import (
    CANONICAL_FORMAT,
    REPOSITORY_MIGRATION_V1_CHECKSUM,
    REPOSITORY_RECORD_FORMAT,
    REPOSITORY_SCHEMA_VERSION,
    RepositoryAdapterCapabilityState,
    RepositoryAdapterFeature,
)

from .support import SOURCE_ROOT, context_graph, cyclic_components

RUNTIME_ROOT = SOURCE_ROOT / "repository_runtime"
INTEGRATION_ROOT = SOURCE_ROOT / "repository_runtime_integrations"
COMPOSITION_ROOT = SOURCE_ROOT / "repository_runtime_composition"

FROZEN_MODULES = {
    "repository_runtime": {
        "__init__.py",
        "application.py",
        "authorization.py",
        "canonical.py",
        "changes.py",
        "classification.py",
        "contracts.py",
        "errors.py",
        "identities.py",
        "local_adapter.py",
        "models.py",
        "mutations.py",
        "observation.py",
        "persistence.py",
        "persistence_contracts.py",
        "recovery.py",
        "restore_points.py",
        "snapshot.py",
        "sqlite_persistence.py",
        "states.py",
        "verification.py",
    },
    "repository_runtime_integrations": {"__init__.py", "coding_sessions.py"},
    "repository_runtime_composition": {"__init__.py", "runtime.py"},
}

FROZEN_EXPORTS = {
    "repository_runtime": (
        255,
        "370c4664ad3ce9c166c75049e40c80414dc482467c45043602e2bd4f2a5dc4dc",
    ),
    "repository_runtime_integrations": (
        25,
        "f6374e4d002e7c643bc8f531d3f4a5952cdd8e3227de073fdea4586e520e21f5",
    ),
    "repository_runtime_composition": (
        11,
        "ab7c029d535c5795e06df2fcea626d4f4119e6b65afffc7604cb8a9886fe2c3b",
    ),
}


def _exports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    value = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    assert isinstance(value, (ast.List, ast.Tuple))
    exports = tuple(
        item.value
        for item in value.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    )
    assert len(exports) == len(value.elts)
    return exports


def _export_fingerprint(exports: tuple[str, ...]) -> str:
    payload = "\n".join(sorted(exports)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_frozen_module_and_public_export_surfaces_are_exact() -> None:
    facades = {
        "repository_runtime": repository_runtime,
        "repository_runtime_integrations": repository_runtime_integrations,
        "repository_runtime_composition": repository_runtime_composition,
    }
    roots = {
        "repository_runtime": RUNTIME_ROOT,
        "repository_runtime_integrations": INTEGRATION_ROOT,
        "repository_runtime_composition": COMPOSITION_ROOT,
    }
    for name, root in roots.items():
        assert {path.name for path in root.glob("*.py")} == FROZEN_MODULES[name]
        exports = _exports(root / "__init__.py")
        expected_count, expected_fingerprint = FROZEN_EXPORTS[name]
        assert len(exports) == len(set(exports)) == expected_count
        assert _export_fingerprint(exports) == expected_fingerprint
        assert all(getattr(facades[name], exported, None) is not None for exported in exports)


def test_v1_canonical_persistence_and_migration_contracts_are_frozen() -> None:
    assert CANONICAL_FORMAT == "repository-json-v1"
    assert REPOSITORY_RECORD_FORMAT == "repository-record-v1"
    assert REPOSITORY_SCHEMA_VERSION == 1
    assert REPOSITORY_MIGRATION_V1_CHECKSUM == (
        "sha256:88f94a662d93d0a0dc48724d75260e0e56ce0a348c8a264f83194216325f7c84"
    )


def test_capability_taxonomy_and_prohibited_surface_are_frozen() -> None:
    assert tuple(item.value for item in RepositoryAdapterCapabilityState) == (
        "supported",
        "unsupported",
        "degraded",
        "unavailable",
    )
    assert tuple(item.value for item in RepositoryAdapterFeature) == (
        "windows",
        "worktrees",
        "common_git_dir",
        "detached_head",
        "unborn_head",
        "submodules",
        "nested_repositories",
        "sparse_checkout",
        "lfs",
        "hooks",
        "filters",
        "encodings",
        "case_sensitivity",
        "reparse_points",
        "mutation",
        "recovery",
        "staging",
        "commit",
        "push",
    )
    prohibited = {
        "stage",
        "commit",
        "push",
        "fetch",
        "pull",
        "merge",
        "rebase",
        "create_branch",
        "checkout_branch",
        "mutate_remote",
    }
    assert not prohibited & set(repository_runtime.__all__)
    assert not prohibited & set(repository_runtime_composition.__all__)


def test_frozen_integration_direction_has_no_repository_runtime_scc() -> None:
    graph = context_graph()
    repository_edges = {
        edge for edge in graph if any(node.startswith("repository_runtime") for node in edge)
    }
    assert repository_edges == {
        ("coding_sessions_integrations", "repository_runtime"),
        ("coding_sessions_integrations", "repository_runtime_integrations"),
        ("repository_runtime_composition", "repository_runtime"),
        ("repository_runtime_composition", "repository_runtime_integrations"),
        ("repository_runtime_integrations", "repository_runtime"),
    }
    repository_contexts = {
        "repository_runtime",
        "repository_runtime_composition",
        "repository_runtime_integrations",
    }
    assert all(
        not repository_contexts & members for members, _ in cyclic_components(graph)
    )
