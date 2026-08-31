from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import synapse.coding_sessions as coding_sessions
import synapse.coding_sessions_composition as coding_sessions_composition
import synapse.coding_sessions_integrations as coding_sessions_integrations
from synapse.coding_sessions import (
    CANONICAL_FORMAT,
    CODING_SESSION_RECORD_VERSION,
    CodingSessionLifecycleState,
    CodingSessionPersistenceStream,
    CodingSessionStateDimension,
)
from synapse.coding_sessions.sqlite_persistence import (
    CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM,
    CODING_SESSION_SQLITE_SCHEMA_VERSION,
)
from synapse.coding_sessions_composition import (
    CodingSessionsCapability,
    CodingSessionsCapabilityState,
)

from .support import SOURCE_ROOT, context_graph, cyclic_components

DOMAIN_ROOT = SOURCE_ROOT / "coding_sessions"
INTEGRATION_ROOT = SOURCE_ROOT / "coding_sessions_integrations"
COMPOSITION_ROOT = SOURCE_ROOT / "coding_sessions_composition"

FROZEN_MODULES = {
    "coding_sessions": {
        "__init__.py",
        "canonical.py",
        "causal.py",
        "contracts.py",
        "control.py",
        "errors.py",
        "fencing.py",
        "fencing_sqlite.py",
        "identities.py",
        "intents.py",
        "journal.py",
        "leases.py",
        "lifecycle.py",
        "persistence.py",
        "recovery.py",
        "references.py",
        "restart.py",
        "sqlite_persistence.py",
    },
    "coding_sessions_integrations": {
        "__init__.py",
        "deployment.py",
        "governance.py",
        "private_evals.py",
        "repository_runtime.py",
        "sandbox.py",
        "workers_missions.py",
    },
    "coding_sessions_composition": {"__init__.py", "runtime.py"},
}

FROZEN_EXPORTS = {
    "coding_sessions": (
        215,
        "31ed85a80f90b61cf073d8f2f93448a95daefde4c5bfc122b01954166bfbffe6",
    ),
    "coding_sessions_integrations": (
        88,
        "d46c54eba637c2bd8c48b4f8f645010032195c40fba41e6c09a916efed33bbf8",
    ),
    "coding_sessions_composition": (
        14,
        "a85bcc1a3a47183a15d89ec478527695fc6680ac0584ebba6937e73593bf7c23",
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


def test_frozen_module_and_public_export_surfaces_are_exact() -> None:
    facades = {
        "coding_sessions": coding_sessions,
        "coding_sessions_integrations": coding_sessions_integrations,
        "coding_sessions_composition": coding_sessions_composition,
    }
    roots = {
        "coding_sessions": DOMAIN_ROOT,
        "coding_sessions_integrations": INTEGRATION_ROOT,
        "coding_sessions_composition": COMPOSITION_ROOT,
    }
    for name, root in roots.items():
        assert {path.name for path in root.glob("*.py")} == FROZEN_MODULES[name]
        exports = _exports(root / "__init__.py")
        expected_count, expected_fingerprint = FROZEN_EXPORTS[name]
        assert len(exports) == len(set(exports)) == expected_count
        assert _export_fingerprint(exports) == expected_fingerprint
        assert all(getattr(facades[name], exported, None) is not None for exported in exports)


def test_v1_formats_schema_and_migration_are_frozen() -> None:
    assert CANONICAL_FORMAT == "coding-sessions-json-v1"
    assert CODING_SESSION_RECORD_VERSION == "coding-session-record-v1"
    assert CODING_SESSION_SQLITE_SCHEMA_VERSION == 1
    assert CODING_SESSION_SQLITE_MIGRATION_V1_CHECKSUM == (
        "sha256:23e6daf70fb93da199ea758fd5bd726f603f75b1a8d12388effb19295ef43f40"
    )


def test_lifecycle_stream_and_capability_taxonomies_are_frozen() -> None:
    assert tuple(item.value for item in CodingSessionLifecycleState) == (
        "unknown",
        "planned",
        "prepared",
        "active",
        "suspended",
        "terminal",
    )
    assert tuple(item.value for item in CodingSessionStateDimension) == (
        "lifecycle",
        "terminal-outcome",
        "coordination",
        "repository-correspondence",
        "worker-binding",
        "execution-binding",
        "checkpoint",
        "cancellation",
        "recovery",
        "evaluation",
        "deployment-candidate",
    )
    assert tuple(item.value for item in CodingSessionPersistenceStream) == (
        "contract-bindings",
        "lifecycle-coordination",
        "intents-receipts",
        "journal-checkpoints",
        "control-cancellation",
        "restart-reconciliation",
        "recovery-outcome",
    )
    assert tuple(item.value for item in CodingSessionsCapabilityState) == (
        "supported",
        "degraded",
        "unavailable",
    )
    assert tuple(item.value for item in CodingSessionsCapability) == (
        "persistence",
        "repository-runtime",
        "governance-approvals",
        "workers-missions",
        "sandbox-references",
        "sandbox-concrete-execution",
        "private-evals",
        "deployment-references",
        "deployment-runtime",
    )


def test_prohibited_authority_surface_remains_absent() -> None:
    prohibited = {
        "authorize",
        "choose_branch",
        "choose_repository",
        "choose_worker",
        "commit",
        "deploy",
        "execute",
        "fetch",
        "merge",
        "mutate_repository",
        "pull",
        "push",
        "rebase",
        "release",
        "rollout",
        "schedule_worker",
        "stage",
    }
    exposed = {
        name.lower()
        for package in (
            coding_sessions,
            coding_sessions_integrations,
            coding_sessions_composition,
        )
        for name in package.__all__
    }
    assert not prohibited & exposed


def test_frozen_integration_direction_has_no_coding_sessions_scc() -> None:
    graph = context_graph()
    coding_edges = {
        edge for edge in graph if any(node.startswith("coding_sessions") for node in edge)
    }
    assert coding_edges == {
        ("coding_sessions_composition", "coding_sessions"),
        ("coding_sessions_composition", "coding_sessions_integrations"),
        ("coding_sessions_integrations", "approvals"),
        ("coding_sessions_integrations", "coding_sessions"),
        ("coding_sessions_integrations", "decisions"),
        ("coding_sessions_integrations", "missions"),
        ("coding_sessions_integrations", "private_evals"),
        ("coding_sessions_integrations", "project_governance"),
        ("coding_sessions_integrations", "repository_runtime"),
        ("coding_sessions_integrations", "repository_runtime_integrations"),
        ("coding_sessions_integrations", "sandbox"),
        ("coding_sessions_integrations", "workers"),
        ("sandbox_integrations", "coding_sessions"),
    }
    coding_contexts = {
        "coding_sessions",
        "coding_sessions_composition",
        "coding_sessions_integrations",
    }
    assert all(not coding_contexts & members for members, _ in cyclic_components(graph))
