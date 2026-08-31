from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import synapse.deployment as deployment
import synapse.deployment_adapters as deployment_adapters
import synapse.deployment_adapters.sqlite_persistence as sqlite_persistence
import synapse.deployment_integrations as deployment_integrations
from synapse.deployment import (
    DEPLOYMENT_CANONICAL_FORMAT_V1,
    DEPLOYMENT_FENCING_AUTHORITY_VERSION,
    DEPLOYMENT_FENCING_TOKEN_VERSION,
    DEPLOYMENT_IDEMPOTENCY_RECORD_VERSION,
    DEPLOYMENT_JOURNAL_FORMAT_V1,
    DEPLOYMENT_JOURNAL_SCHEMA_VERSION,
)

from .support import SOURCE_ROOT, context_graph, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph, _runtime_imports

DOMAIN_ROOT = SOURCE_ROOT / "deployment"
ADAPTERS_ROOT = SOURCE_ROOT / "deployment_adapters"
INTEGRATIONS_ROOT = SOURCE_ROOT / "deployment_integrations"

FROZEN_MODULES = {
    "deployment": {
        "__init__.py",
        "application.py",
        "canonical.py",
        "eligibility.py",
        "errors.py",
        "fencing.py",
        "identities.py",
        "local_rollback.py",
        "models.py",
        "operational.py",
        "persistence.py",
        "ports.py",
        "preparation.py",
        "state_machines.py",
        "verification.py",
    },
    "deployment_adapters": {
        "__init__.py",
        "local_active_state.py",
        "local_observation.py",
        "local_rollback.py",
        "local_service.py",
        "sqlite_persistence.py",
    },
    "deployment_integrations": {
        "__init__.py",
        "custody.py",
        "governance.py",
        "local_apply.py",
        "local_rollback.py",
        "local_verification.py",
        "sandbox_handoff.py",
    },
}

FROZEN_EXPORTS = {
    "deployment": (
        261,
        "d63359989f4e959e5ab58b5a402a8a0f08a1f2bfaf3f19ec6d26fa69f24c2d59",
    ),
    "deployment_adapters": (
        13,
        "3dd88876f258e78937e3652f423a24f413742a712a277716c5283055da67323f",
    ),
    "deployment_integrations": (
        25,
        "544c040e18eb3174a779b2b667239888c6433d441fd81238b5badf060cf3936a",
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
    return hashlib.sha256(("\n".join(sorted(exports)) + "\n").encode()).hexdigest()


def test_frozen_modules_and_public_exports_are_exact() -> None:
    packages = {
        "deployment": deployment,
        "deployment_adapters": deployment_adapters,
        "deployment_integrations": deployment_integrations,
    }
    roots = {
        "deployment": DOMAIN_ROOT,
        "deployment_adapters": ADAPTERS_ROOT,
        "deployment_integrations": INTEGRATIONS_ROOT,
    }
    for name, root in roots.items():
        assert {path.name for path in root.glob("*.py")} == FROZEN_MODULES[name]
        exports = _exports(root / "__init__.py")
        expected_count, expected_fingerprint = FROZEN_EXPORTS[name]
        assert len(exports) == len(set(exports)) == expected_count
        assert _export_fingerprint(exports) == expected_fingerprint
        assert all(getattr(packages[name], exported, None) is not None for exported in exports)


def test_v1_formats_schema_and_migrations_are_frozen() -> None:
    assert DEPLOYMENT_CANONICAL_FORMAT_V1 == "deployment-json-v1"
    assert DEPLOYMENT_JOURNAL_FORMAT_V1 == "deployment-journal-json-v1"
    assert DEPLOYMENT_JOURNAL_SCHEMA_VERSION == 1
    assert DEPLOYMENT_FENCING_AUTHORITY_VERSION == "deployment-fencing-authority-v1"
    assert DEPLOYMENT_FENCING_TOKEN_VERSION == "deployment-fencing-token-v1"
    assert DEPLOYMENT_IDEMPOTENCY_RECORD_VERSION == "deployment-idempotency-record-v1"
    assert sqlite_persistence._MIGRATION_ID == "deployment-journal-v1"
    assert sqlite_persistence._MIGRATION_CHECKSUM == (
        "454c5357ec28eeac6ee57c4f8a70413fd827dfff9f635afc3cbdb9a68b713198"
    )
    assert sqlite_persistence._AUTHORITY_MIGRATION_ID == "deployment-authority-v1"
    assert sqlite_persistence._AUTHORITY_MIGRATION_CHECKSUM == (
        "39d502b8e127c75e094d568656fa15bb0baa97174c8957045bf15cf254fd5756"
    )


def test_authority_separation_and_prohibited_global_surface_are_frozen() -> None:
    required = {
        "DeploymentFencingAuthority",
        "DeploymentAuthorizationPort",
        "DeploymentArtifactFactsPort",
        "DeploymentPreparationPort",
        "DeploymentApplyPort",
        "DeploymentObservationPort",
        "DeploymentVerificationPort",
        "DeploymentRollbackPreparationPort",
        "DeploymentRollbackApplyPort",
        "DeploymentRollbackObservationPort",
        "DeploymentRollbackVerificationPort",
    }
    assert required.issubset(deployment.__all__)
    prohibited = {
        "approve",
        "authorize_deployment",
        "commit",
        "push",
        "mutate_repository",
        "select_eval_baseline",
        "start_global_runtime",
    }
    exposed = {
        name.lower()
        for package in (deployment, deployment_adapters, deployment_integrations)
        for name in package.__all__
    }
    assert not prohibited & exposed


def test_frozen_dependency_edges_and_scc_baseline_are_exact() -> None:
    runtime = _runtime_context_graph()
    source = context_graph()
    expected = {
        ("deployment_adapters", "deployment"),
        ("deployment_composition", "deployment"),
        ("deployment_composition", "deployment_adapters"),
        ("deployment_composition", "deployment_integrations"),
        ("deployment_integrations", "approvals"),
        ("deployment_integrations", "decisions"),
        ("deployment_integrations", "deployment"),
        ("deployment_integrations", "sandbox"),
        ("deployment_integrations", "sandbox_drivers"),
    }
    for graph in (runtime, source):
        edges = {
            edge for edge in graph if edge[0].startswith("deployment") or edge[1] == "deployment"
        }
        assert edges == expected
        assert all(
            not any(name.startswith("deployment") for name in members)
            for members, _ in cyclic_components(graph)
        )
    assert len(runtime) == 304
    assert len(source) == 339


def test_global_bootstrap_activation_and_reverse_composition_are_absent() -> None:
    bootstrap_imports = {
        module
        for path in (SOURCE_ROOT / "bootstrap").rglob("*.py")
        for module in _runtime_imports(path)
    }
    assert not bootstrap_imports.intersection(
        {
            "synapse.deployment",
            "synapse.deployment_adapters",
            "synapse.deployment_integrations",
        }
    )
    assert "synapse.deployment_composition" in bootstrap_imports
    reverse_imports = {
        module
        for root in (DOMAIN_ROOT, ADAPTERS_ROOT, INTEGRATIONS_ROOT)
        for path in root.glob("*.py")
        for module in _runtime_imports(path)
        if module.startswith("synapse.bootstrap")
    }
    assert reverse_imports == set()
