from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import cast

import synapse.sandbox_driver_composition as composition
import synapse.sandbox_drivers as drivers
from synapse.sandbox_driver_composition import (
    WindowsCapabilityClassification,
    WindowsCompositionConfig,
    WindowsCompositionDependencies,
    WindowsIsolationLevel,
    build_windows_sandbox_driver,
)
from synapse.sandbox_drivers import (
    LocalArtifactCustodyConfig,
    SandboxFencingValidationPort,
    WindowsCommandConfig,
    WindowsExecutionAuthorizationPort,
    WindowsGrantValidationPort,
    WindowsNetworkProfile,
    WindowsProcessApi,
    WindowsSecretDeliveryMode,
    WindowsSecretProviderPort,
)

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for
from .test_audio_speech_boundary import _runtime_context_graph

DRIVER_ROOT = SOURCE_ROOT / "sandbox_drivers"
COMPOSITION_ROOT = SOURCE_ROOT / "sandbox_driver_composition"

FROZEN_MODULES = {
    "sandbox_drivers": {
        "__init__.py",
        "artifact_materialization.py",
        "local_artifact_custody.py",
        "windows_authority.py",
        "windows_command.py",
        "windows_driver_state.py",
        "windows_network.py",
        "windows_output.py",
        "windows_process.py",
        "windows_publication.py",
        "windows_resources.py",
        "windows_secrets.py",
        "windows_supervision.py",
        "windows_workspace.py",
    },
    "sandbox_driver_composition": {"__init__.py", "windows.py"},
}

FROZEN_EXPORTS = {
    "sandbox_drivers": (
        119,
        "e17ef1db9ab4110e6dc87bf9c9f3ce541be8907ea026460da84f39724c4d7e16",
    ),
    "sandbox_driver_composition": (
        10,
        "40498ab2e4a8b1ac74a3cee467203beba9070832488eace2e6d0dceb1f52d46c",
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


def test_frozen_module_and_deliberate_public_export_surfaces_are_exact() -> None:
    packages = {
        "sandbox_drivers": (DRIVER_ROOT, drivers),
        "sandbox_driver_composition": (COMPOSITION_ROOT, composition),
    }
    for name, (root, facade) in packages.items():
        assert {path.name for path in root.glob("*.py")} == FROZEN_MODULES[name]
        exports = _exports(root / "__init__.py")
        expected_count, expected_fingerprint = FROZEN_EXPORTS[name]
        assert len(exports) == len(set(exports)) == expected_count
        assert _export_fingerprint(exports) == expected_fingerprint
        assert all(getattr(facade, exported, None) is not None for exported in exports)


def test_capability_and_unsupported_taxonomies_are_frozen(tmp_path: Path) -> None:
    assert tuple(item.value for item in WindowsIsolationLevel) == (
        "l0_supervised",
        "l1_job_contained_windows_process",
        "l2_restricted_workspace_process",
    )
    assert tuple(item.value for item in WindowsNetworkProfile) == (
        "disabled",
        "loopback_only",
        "allowlisted",
        "unrestricted_by_driver_but_governed",
    )
    assert tuple(item.value for item in WindowsSecretDeliveryMode) == ("environment",)

    opaque = object()
    dependencies = WindowsCompositionDependencies(
        cast(WindowsProcessApi, opaque),
        cast(WindowsExecutionAuthorizationPort, opaque),
        cast(WindowsGrantValidationPort, opaque),
        cast(SandboxFencingValidationPort, opaque),
        lambda workspace_id: None,
        cast(WindowsSecretProviderPort, opaque),
    )
    config = WindowsCompositionConfig(
        tmp_path / "workspaces",
        WindowsCommandConfig(tmp_path / "workspaces", ()),
        dependencies,
        artifact_custody=LocalArtifactCustodyConfig((), ()),
        publication_custody_root=tmp_path / "publication",
        driver_state_path=tmp_path / "driver.sqlite3",
        platform_windows=True,
    )
    runtime = build_windows_sandbox_driver(config)
    health = runtime.health()
    expected = {
        "workspace_driver": WindowsCapabilityClassification.AVAILABLE,
        "artifact_custody": WindowsCapabilityClassification.AVAILABLE,
        "command_resolution": WindowsCapabilityClassification.AVAILABLE,
        "process_creation": WindowsCapabilityClassification.AVAILABLE,
        "job_object_containment": WindowsCapabilityClassification.AVAILABLE,
        "supervision": WindowsCapabilityClassification.AVAILABLE,
        "output_capture": WindowsCapabilityClassification.AVAILABLE,
        "execution_grant_validator_configured": WindowsCapabilityClassification.AVAILABLE,
        "fencing_validator_configured": WindowsCapabilityClassification.AVAILABLE,
        "secret_environment_delivery": WindowsCapabilityClassification.AVAILABLE,
        "secret_pipe_delivery": WindowsCapabilityClassification.UNSUPPORTED,
        "secret_temporary_file_delivery": WindowsCapabilityClassification.UNSUPPORTED,
        "network_disabled": WindowsCapabilityClassification.UNAVAILABLE,
        "network_loopback_only": WindowsCapabilityClassification.UNAVAILABLE,
        "network_allowlisted": WindowsCapabilityClassification.UNAVAILABLE,
        "network_unrestricted_governed": WindowsCapabilityClassification.AVAILABLE,
        "local_publication_custody": WindowsCapabilityClassification.AVAILABLE,
        "anonymous_job_live_recovery": WindowsCapabilityClassification.UNSUPPORTED,
        "restricted_host_identity": WindowsCapabilityClassification.UNAVAILABLE,
        "vm_container_boundary": WindowsCapabilityClassification.UNSUPPORTED,
        "isolation_l0": WindowsCapabilityClassification.AVAILABLE,
        "isolation_l1": WindowsCapabilityClassification.AVAILABLE,
        "isolation_l2": WindowsCapabilityClassification.UNAVAILABLE,
    }
    assert {name: health.capability(name).classification for name in expected} == expected
    assert health.bootstrap_activation is WindowsCapabilityClassification.UNAVAILABLE
    assert not health.secure_sandbox_claimed
    assert not config.workspace_root.exists()
    assert not config.driver_state_path.exists()
    runtime.health()
    assert not config.workspace_root.exists()
    assert not config.driver_state_path.exists()


def test_driver_state_v1_append_only_integrity_and_replay_limits_are_frozen() -> None:
    assert drivers.WINDOWS_DRIVER_STATE_SCHEMA_VERSION == 1
    assert drivers.WINDOWS_DRIVER_STATE_SCHEMA_ID == "windows-sandbox-driver-state-v1"
    source = (DRIVER_ROOT / "windows_driver_state.py").read_text(encoding="utf-8")
    assert "driver_events_no_update" in source and "driver_events_no_delete" in source
    assert "append_only" in source and "sha256:" in source
    assert "handles_recoverable: bool = False" in source
    assert "automatic_actions: tuple[WindowsReconciliationAction, ...] = ()" in source
    assert "automatic_destructive_reconciliation_enabled" in source
    persisted_fields = source.split("CREATE TABLE IF NOT EXISTS driver_events(", 1)[1].split(
        ");", 1
    )[0]
    assert "handle" not in persisted_fields.lower()
    assert "secret_value" not in source and "secret_plaintext" not in source


def test_process_fencing_output_secret_and_artifact_distinctions_remain_explicit() -> None:
    process = (DRIVER_ROOT / "windows_process.py").read_text(encoding="utf-8")
    start_flow = process.split("secret_environment = tuple(", 1)[1].split(
        "managed = ManagedWindowsProcess(", 1
    )[0]
    assert start_flow.index("create_process_suspended") < start_flow.index("assign_process")
    assert start_flow.index("assign_process") < start_flow.index("process_in_job")
    assert start_flow.index("process_in_job") < start_flow.index("resume_thread")
    assert "containment_verification_failed" in process
    assert "fencing" in process.lower() and "authorization" in process.lower()
    output = (DRIVER_ROOT / "windows_output.py").read_text(encoding="utf-8")
    publication = (DRIVER_ROOT / "windows_publication.py").read_text(encoding="utf-8")
    secrets = (DRIVER_ROOT / "windows_secrets.py").read_text(encoding="utf-8")
    supervision = (DRIVER_ROOT / "windows_supervision.py").read_text(encoding="utf-8")
    assert "TRUNCATED" in output and "EOF" in output and "INCOMPLETE" in output
    assert "WindowsTerminationConfirmation(True, proof, ())" in supervision
    assert "PublishedArtifact" not in output
    assert "WindowsArtifactPublicationState" in publication
    assert "environment_name" in secrets and "secret_value" not in secrets


def test_dependency_graph_reverse_imports_bootstrap_and_scc_baselines_are_frozen() -> None:
    expected_edges = {
        ("coding_sessions_integrations", "sandbox"),
        ("deployment_integrations", "sandbox"),
        ("deployment_integrations", "sandbox_drivers"),
        ("sandbox_composition", "sandbox"),
        ("sandbox_driver_composition", "sandbox"),
        ("sandbox_driver_composition", "sandbox_drivers"),
        ("sandbox_drivers", "sandbox"),
        ("sandbox_integrations", "sandbox"),
        ("sandbox_integrations", "sandbox_drivers"),
    }
    # Primary MoM adds api -> mom -> core without changing existing cycles.
    for graph, count in ((_runtime_context_graph(), 313), (context_graph(), 352)):
        assert len(graph) == count
        assert {
            edge
            for edge in graph
            if any(node.startswith("sandbox_driver") for node in edge) or edge[1] == "sandbox"
        } == expected_edges
        assert all(
            not any(name.startswith("sandbox_driver") for name in members)
            for members, _ in cyclic_components(graph)
        )

    driver_imports = {module for path in DRIVER_ROOT.glob("*.py") for module in imports_for(path)}
    sandbox_imports = {
        module for path in (SOURCE_ROOT / "sandbox").glob("*.py") for module in imports_for(path)
    }
    bootstrap_imports = {
        module for path in (SOURCE_ROOT / "bootstrap").rglob("*.py") for module in imports_for(path)
    }
    assert not any(
        module.startswith("synapse.sandbox_driver_composition") for module in driver_imports
    )
    assert not any(module.startswith("synapse.sandbox_driver") for module in sandbox_imports)
    assert not any(module.startswith("synapse.sandbox_driver") for module in bootstrap_imports)
