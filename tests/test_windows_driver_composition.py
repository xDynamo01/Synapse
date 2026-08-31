from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from tests.factories.windows_authority import ValidGrantStore, process_context
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing, _request, _resolved
from tests.test_windows_workspace_driver import _file_fingerprint

from synapse.sandbox import OpaqueReference
from synapse.sandbox_driver_composition import (
    WindowsCapabilityClassification,
    WindowsCompositionConfig,
    WindowsCompositionDependencies,
    WindowsExecutionProfileV1,
    WindowsIsolationLevel,
    build_windows_sandbox_driver,
)
from synapse.sandbox_drivers import (
    InMemoryWindowsSecretProvider,
    WindowsArtifactPublicationRequestV1,
    WindowsCommandConfig,
    WindowsDeclaredOutputV1,
    WindowsDriverDurableEventV1,
    WindowsDriverEventType,
    WindowsDriverStateIntegrityError,
    WindowsNetworkProfile,
    WindowsProcessStartOutcome,
    WindowsSandboxDriverStore,
)

PUBLICATION = OpaqueReference("capability:composition-publication")


def dependencies(
    *, api=None, authorization=None, grants=None, fencing=None, context=None, secret=None
):
    return WindowsCompositionDependencies(
        api,
        authorization,
        grants,
        fencing,
        context or (lambda workspace: None),
        secret,
    )


def config(tmp_path, selected_dependencies, **changes):
    base = WindowsCompositionConfig(
        tmp_path / "workspaces",
        WindowsCommandConfig(tmp_path / "workspaces", ()),
        selected_dependencies,
        driver_state_path=tmp_path / "driver-state.sqlite3",
        platform_windows=True,
    )
    return replace(base, **changes)


def l1(network=WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED, **changes):
    return WindowsExecutionProfileV1(
        WindowsIsolationLevel.L1_JOB_CONTAINED,
        network,
        **changes,
    )


def test_build_is_side_effect_free_and_initialize_is_explicit(tmp_path) -> None:
    calls = []
    selected = config(
        tmp_path,
        dependencies(
            api=FakeApi(),
            authorization=Authorization(),
            grants=ValidGrantStore(),
            fencing=Fencing(),
            context=lambda workspace: calls.append(workspace),
        ),
    )
    runtime = build_windows_sandbox_driver(selected)
    assert not selected.workspace_root.exists()
    assert not selected.driver_state_path.exists()
    assert calls == []
    assert (
        runtime.health().capability("driver_state_persistence").classification
        is not WindowsCapabilityClassification.AVAILABLE
    )
    assert calls == []
    runtime.initialize()
    assert selected.driver_state_path.exists()
    assert (
        runtime.health().capability("driver_state_persistence").classification
        is WindowsCapabilityClassification.AVAILABLE
    )


def test_missing_dependencies_never_fall_back_permissively(tmp_path) -> None:
    missing_authority = build_windows_sandbox_driver(
        config(tmp_path / "authority", dependencies(api=FakeApi()))
    )
    readiness = missing_authority.execution_readiness(l1())
    assert not readiness.executable
    assert "execution_grant_validator_configured" in readiness.missing_prerequisites
    assert "fencing_validator_configured" in readiness.missing_prerequisites

    no_secret = build_windows_sandbox_driver(
        config(
            tmp_path / "secret",
            dependencies(
                api=FakeApi(),
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
            ),
        )
    )
    assert no_secret.execution_readiness(l1()).executable
    assert not no_secret.execution_readiness(l1(requires_secret=True)).executable

    no_custody = build_windows_sandbox_driver(
        config(
            tmp_path / "custody",
            dependencies(
                api=FakeApi(),
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
            ),
        )
    )
    assert not no_custody.execution_readiness(l1(requires_publication=True)).executable


def test_health_is_factual_profile_specific_and_never_claims_l2_or_secure_sandbox(tmp_path) -> None:
    runtime = build_windows_sandbox_driver(
        config(
            tmp_path,
            dependencies(
                api=FakeApi(),
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
                secret=InMemoryWindowsSecretProvider(
                    {OpaqueReference("secret:test"): b"not-rendered"}
                ),
            ),
        )
    )
    health = runtime.health()
    assert not health.secure_sandbox_claimed
    assert health.bootstrap_activation is WindowsCapabilityClassification.UNAVAILABLE
    assert (
        health.capability("isolation_l1").classification
        is WindowsCapabilityClassification.AVAILABLE
    )
    assert (
        health.capability("isolation_l2").classification
        is WindowsCapabilityClassification.UNAVAILABLE
    )
    assert (
        health.capability("restricted_host_identity").classification
        is WindowsCapabilityClassification.UNAVAILABLE
    )
    assert (
        health.capability("network_disabled").classification
        is WindowsCapabilityClassification.UNAVAILABLE
    )
    assert (
        health.capability("network_unrestricted_governed").classification
        is WindowsCapabilityClassification.AVAILABLE
    )
    assert (
        health.capability("secret_environment_delivery").classification
        is WindowsCapabilityClassification.AVAILABLE
    )
    assert (
        health.capability("secret_pipe_delivery").classification
        is WindowsCapabilityClassification.UNSUPPORTED
    )
    assert "not-rendered" not in repr(health)
    assert runtime.execution_readiness(l1()).executable
    assert not runtime.execution_readiness(l1(WindowsNetworkProfile.DISABLED)).executable
    assert not runtime.execution_readiness(
        WindowsExecutionProfileV1(
            WindowsIsolationLevel.L2_RESTRICTED_WORKSPACE_PROCESS,
            WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED,
        )
    ).executable


def test_configuration_fingerprint_is_deterministic_and_path_or_secret_independent(
    tmp_path,
) -> None:
    first = build_windows_sandbox_driver(
        config(
            tmp_path / "one",
            dependencies(
                api=FakeApi(),
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
                secret=InMemoryWindowsSecretProvider(
                    {OpaqueReference("secret:x"): b"synthetic-secret-alpha"}
                ),
            ),
        )
    )
    second = build_windows_sandbox_driver(
        config(
            tmp_path / "two",
            dependencies(
                api=FakeApi(),
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
                secret=InMemoryWindowsSecretProvider(
                    {OpaqueReference("secret:x"): b"synthetic-secret-beta"}
                ),
            ),
        )
    )
    assert first.health().configuration_fingerprint == second.health().configuration_fingerprint
    assert "synthetic-secret-alpha" not in repr(first.health())
    assert "synthetic-secret-beta" not in repr(second.health())


def test_negative_network_profile_and_missing_authority_create_zero_process(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path / "fixture")
    api = FakeApi()
    runtime = build_windows_sandbox_driver(
        config(
            tmp_path,
            dependencies(
                api=api,
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
                context=lambda selected: process_context(
                    command, selected, OpaqueReference("grant:one")
                ),
            ),
        )
    )
    result = runtime.execute(l1(WindowsNetworkProfile.DISABLED), _request(workspace, command))
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert api.calls == []

    api2 = FakeApi()
    missing = build_windows_sandbox_driver(config(tmp_path / "missing", dependencies(api=api2)))
    result2 = missing.execute(l1(), _request(workspace, command))
    assert result2.outcome is WindowsProcessStartOutcome.FAILED
    assert api2.calls == []


def test_local_execution_publication_cleanup_and_restart_journey(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path / "fixture")
    context = process_context(command, workspace, OpaqueReference("grant:one"))
    context = replace(context, grant=replace(context.grant, capabilities=(PUBLICATION,)))
    content = b"controlled-output"
    declared = WindowsDeclaredOutputV1(
        "result.bin",
        _file_fingerprint(content),
        OpaqueReference("output-binding:composition"),
        OpaqueReference("execution:composition"),
    )
    runtime_config = config(
        tmp_path,
        dependencies(
            api=FakeApi(),
            authorization=Authorization(),
            grants=ValidGrantStore(),
            fencing=Fencing(),
            context=lambda selected: context if selected == workspace else None,
        ),
        workspace_root=tmp_path / "fixture" / "workspaces",
        command=WindowsCommandConfig(tmp_path / "fixture" / "workspaces", ()),
        publication_custody_root=tmp_path / "publication",
        declared_outputs=((workspace, declared),),
    )
    runtime = build_windows_sandbox_driver(runtime_config)
    assert not runtime.execution_readiness(l1(requires_durable_state=True)).executable
    runtime.initialize()
    assert runtime.execution_readiness(
        l1(requires_publication=True, requires_durable_state=True)
    ).executable
    started = runtime.execute(l1(), _request(workspace, command))
    assert started.outcome is WindowsProcessStartOutcome.STARTED
    output = runtime_config.workspace_root / "workspace-process" / "output" / "result.bin"
    output.write_bytes(content)
    candidate, diagnostics = runtime.publication.inspect(
        execution_reference=OpaqueReference("execution:composition"),
        attempt_reference=context.attempt_reference,
        workspace_id=workspace,
        declared=declared,
        occurrence_reference=OpaqueReference("occurrence:composition"),
    )
    assert candidate is not None and diagnostics == ()
    publication = runtime.publication.publish(
        WindowsArtifactPublicationRequestV1(
            candidate,
            candidate.fingerprint,
            OpaqueReference("publication:composition"),
            PUBLICATION,
            context,
        )
    )
    assert publication.publication_verified
    assert started.managed_process is not None
    cleanup = runtime.cleanup.run(
        context.attempt_reference,
        workspace,
        (("handle_resources", started.managed_process.close_custody_handles),),
        context,
    )
    assert not cleanup.reconciliation_required
    runtime.state_store.append(
        WindowsDriverDurableEventV1(
            OpaqueReference("driver-event:composition"),
            OpaqueReference("driver-attempt:composition"),
            workspace,
            1,
            WindowsDriverEventType.ATTEMPT_CREATED,
            datetime.now(timezone.utc),
            publication_state="published",
            cleanup_state="completed",
        )
    )
    restarted = build_windows_sandbox_driver(runtime_config)
    restarted.initialize()
    projections = restarted.replay()
    assert len(projections) == 1
    assert projections[0].historical_event_count == 1


def test_incompatible_store_is_explicitly_blocked(tmp_path) -> None:
    path = tmp_path / "driver-state.sqlite3"
    store = WindowsSandboxDriverStore(path)
    store.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE driver_schema SET schema_version=999")
    runtime = build_windows_sandbox_driver(
        config(
            tmp_path,
            dependencies(
                api=FakeApi(),
                authorization=Authorization(),
                grants=ValidGrantStore(),
                fencing=Fencing(),
            ),
        )
    )
    with pytest.raises(WindowsDriverStateIntegrityError):
        runtime.initialize()
