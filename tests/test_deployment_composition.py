from __future__ import annotations

from pathlib import Path

import pytest

from synapse.deployment import LocalApplyRequestV1
from synapse.deployment_composition import (
    DeploymentCompositionCapabilityState,
    DeploymentCompositionLifecycleState,
    DeploymentCompositionReconciliationState,
    DeploymentRuntimeBuildError,
    DeploymentRuntimeClosedError,
    DeploymentRuntimeCloseError,
    DeploymentRuntimeConfig,
    DeploymentRuntimeDependencies,
    DeploymentRuntimeManagedResource,
    DeploymentRuntimeStartupError,
    build_deployment_runtime,
)


class ManagedResource:
    def __init__(
        self,
        name: str,
        actions: list[str],
        *,
        fail_open: bool = False,
        fail_close: bool = False,
    ) -> None:
        self.name = name
        self.actions = actions
        self.fail_open = fail_open
        self.fail_close = fail_close
        self.is_open = False

    def open(self) -> None:
        self.actions.append(f"open:{self.name}")
        if self.fail_open:
            raise RuntimeError("resource unavailable")
        self.is_open = True

    def close(self) -> None:
        self.actions.append(f"close:{self.name}")
        self.is_open = False
        if self.fail_close:
            raise RuntimeError("resource close failed")

    def healthy(self) -> bool:
        return self.is_open


class ApplyAuthorization:
    def validate(self, request: LocalApplyRequestV1) -> bool:
        return True


def config(
    tmp_path: Path,
    *,
    reconciliation_required: bool = False,
    managed_resources: tuple[DeploymentRuntimeManagedResource, ...] = (),
) -> DeploymentRuntimeConfig:
    return DeploymentRuntimeConfig(
        tmp_path / "deployment.sqlite3",
        reconciliation_required=reconciliation_required,
        managed_resources=managed_resources,
    )


def test_build_is_inert_and_unconfigured_capabilities_remain_unavailable(tmp_path: Path) -> None:
    runtime = build_deployment_runtime(config(tmp_path))

    health = runtime.health()
    assert not (tmp_path / "deployment.sqlite3").exists()
    assert health.lifecycle is DeploymentCompositionLifecycleState.CONSTRUCTED
    assert health.persistence is DeploymentCompositionCapabilityState.NOT_EVALUATED
    assert health.fencing is DeploymentCompositionCapabilityState.NOT_EVALUATED
    assert health.apply is DeploymentCompositionCapabilityState.UNAVAILABLE
    assert health.verification is DeploymentCompositionCapabilityState.UNAVAILABLE
    assert health.rollback is DeploymentCompositionCapabilityState.UNAVAILABLE


def test_explicit_start_initializes_persistence_and_close_is_idempotent(tmp_path: Path) -> None:
    actions: list[str] = []
    resource = ManagedResource("custody", actions)
    runtime = build_deployment_runtime(config(tmp_path, managed_resources=(resource,)))

    health = runtime.start()
    assert actions == ["open:custody"]
    assert health.lifecycle is DeploymentCompositionLifecycleState.STARTED
    assert health.persistence is DeploymentCompositionCapabilityState.AVAILABLE
    assert health.fencing is DeploymentCompositionCapabilityState.AVAILABLE
    assert health.managed_resources is DeploymentCompositionCapabilityState.AVAILABLE
    runtime.close()
    runtime.close()
    assert actions == ["open:custody", "close:custody"]
    with pytest.raises(DeploymentRuntimeClosedError):
        runtime.health()


def test_start_failure_rolls_back_opened_resources(tmp_path: Path) -> None:
    actions: list[str] = []
    first = ManagedResource("first", actions)
    failing = ManagedResource("failing", actions, fail_open=True)
    runtime = build_deployment_runtime(config(tmp_path, managed_resources=(first, failing)))

    with pytest.raises(DeploymentRuntimeStartupError):
        runtime.start()
    assert actions == ["open:first", "open:failing", "close:first"]
    assert runtime.health().lifecycle is DeploymentCompositionLifecycleState.DEGRADED


def test_close_failure_does_not_prevent_remaining_cleanup(tmp_path: Path) -> None:
    actions: list[str] = []
    first = ManagedResource("first", actions)
    failing = ManagedResource("failing", actions, fail_close=True)
    last = ManagedResource("last", actions)
    runtime = build_deployment_runtime(config(tmp_path, managed_resources=(first, failing, last)))
    runtime.start()

    with pytest.raises(DeploymentRuntimeCloseError):
        runtime.close()
    assert actions[-3:] == ["close:last", "close:failing", "close:first"]


def test_reconciliation_fact_is_preserved_without_inventing_recovery(tmp_path: Path) -> None:
    runtime = build_deployment_runtime(config(tmp_path, reconciliation_required=True))

    assert runtime.health().reconciliation is (DeploymentCompositionReconciliationState.REQUIRED)


def test_partial_operational_dependency_group_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(
        DeploymentRuntimeBuildError,
        match="deployment apply dependencies are incomplete",
    ):
        build_deployment_runtime(
            config(tmp_path),
            DeploymentRuntimeDependencies(apply_authorization=ApplyAuthorization()),
        )
