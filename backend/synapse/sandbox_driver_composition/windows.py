"""Side-effect-free build and explicit initialization of local Windows drivers."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol

from synapse.sandbox import SandboxArtifactFingerprint, SandboxWorkspaceId
from synapse.sandbox_drivers import (
    LocalArtifactCustody,
    LocalArtifactCustodyConfig,
    SandboxFencingValidationPort,
    WindowsAuthorityContextV1,
    WindowsCleanupCampaign,
    WindowsCommandConfig,
    WindowsCommandResolver,
    WindowsDeclaredOutputV1,
    WindowsExecutionAuthorityGuard,
    WindowsExecutionAuthorizationPort,
    WindowsExecutionGrantV1,
    WindowsNetworkMechanismPort,
    WindowsNetworkPolicyLayer,
    WindowsNetworkProfile,
    WindowsOutputPublicationAdapter,
    WindowsProcessApi,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
    WindowsProcessStartRequest,
    WindowsProcessStartResult,
    WindowsRestartProjectionV1,
    WindowsSandboxDriverStore,
    WindowsSandboxReconciliationPlanner,
    WindowsSecretMaterializer,
    WindowsSecretProviderPort,
    WindowsWorkspaceConfig,
    WindowsWorkspaceDriver,
)


class WindowsCapabilityClassification(StrEnum):
    IMPLEMENTED = "implemented"
    AVAILABLE = "available"
    CONFIGURED = "configured"
    ENFORCED = "enforced"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    EXTERNALLY_BLOCKED = "externally_blocked"


class WindowsIsolationLevel(StrEnum):
    L0_SUPERVISED = "l0_supervised"
    L1_JOB_CONTAINED = "l1_job_contained_windows_process"
    L2_RESTRICTED_WORKSPACE_PROCESS = "l2_restricted_workspace_process"


class WindowsExecutionGrantValidatorPort(Protocol):
    def validate(self, grant: WindowsExecutionGrantV1) -> bool: ...


@dataclass(frozen=True, slots=True)
class WindowsCompositionCapabilityFact:
    capability: str
    classification: WindowsCapabilityClassification
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class WindowsCompositionDependencies:
    process_api: WindowsProcessApi | None
    execution_authorization: WindowsExecutionAuthorizationPort | None
    grant_validator: WindowsExecutionGrantValidatorPort | None
    fencing_validator: SandboxFencingValidationPort | None
    authority_context: Callable[[SandboxWorkspaceId], WindowsAuthorityContextV1 | None]
    secret_provider: WindowsSecretProviderPort | None = None
    network_mechanism: WindowsNetworkMechanismPort | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class WindowsCompositionConfig:
    workspace_root: Path
    command: WindowsCommandConfig
    dependencies: WindowsCompositionDependencies
    artifact_custody: LocalArtifactCustodyConfig | None = None
    publication_custody_root: Path | None = None
    declared_outputs: tuple[tuple[SandboxWorkspaceId, WindowsDeclaredOutputV1], ...] = ()
    driver_state_path: Path | None = None
    platform_windows: bool = os.name == "nt"


@dataclass(frozen=True, slots=True)
class WindowsExecutionProfileV1:
    isolation_level: WindowsIsolationLevel
    network_profile: WindowsNetworkProfile
    requires_secret: bool = False
    requires_publication: bool = False
    requires_durable_state: bool = False


@dataclass(frozen=True, slots=True)
class WindowsExecutionReadinessV1:
    profile: WindowsExecutionProfileV1
    executable: bool
    satisfied_prerequisites: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsLocalCompositionHealth:
    configuration_fingerprint: SandboxArtifactFingerprint
    capabilities: tuple[WindowsCompositionCapabilityFact, ...]
    bootstrap_activation: WindowsCapabilityClassification
    secure_sandbox_claimed: bool

    def capability(self, name: str) -> WindowsCompositionCapabilityFact:
        return next(item for item in self.capabilities if item.capability == name)


@dataclass(slots=True)
class WindowsLocalComposition:
    config: WindowsCompositionConfig
    workspace: WindowsWorkspaceDriver
    command: WindowsCommandResolver
    network: WindowsNetworkPolicyLayer
    process: WindowsProcessDriver | None
    artifact_custody: LocalArtifactCustody | None
    publication: WindowsOutputPublicationAdapter | None
    secret_materializer: WindowsSecretMaterializer | None
    state_store: WindowsSandboxDriverStore | None
    reconciliation: WindowsSandboxReconciliationPlanner
    cleanup: WindowsCleanupCampaign
    _configuration_fingerprint: SandboxArtifactFingerprint

    def initialize(self) -> None:
        if self.state_store is not None:
            self.state_store.initialize()

    def health(self) -> WindowsLocalCompositionHealth:
        dependencies = self.config.dependencies
        network_health = self.network.health()
        state_health = self.state_store.health() if self.state_store is not None else None
        process_available = (
            self.process is not None
            and self.config.platform_windows
            and dependencies.process_api is not None
        )
        facts = (
            self._fact("contracts", True),
            self._fact("platform_windows", self.config.platform_windows),
            self._fact("workspace_driver", True),
            self._fact("artifact_custody", self.artifact_custody is not None),
            self._fact("command_resolution", True),
            self._fact("process_creation", process_available),
            self._fact("job_object_containment", process_available),
            self._fact("supervision", process_available),
            self._fact("output_capture", process_available),
            self._implemented("resource_process_count", "availability-requires-probe"),
            self._implemented("resource_process_memory", "availability-requires-probe"),
            self._implemented("resource_job_memory", "availability-requires-probe"),
            self._implemented("resource_cpu_time", "availability-requires-probe"),
            self._implemented("resource_cpu_rate", "availability-requires-probe"),
            self._fact(
                "execution_grant_validator_configured", dependencies.grant_validator is not None
            ),
            self._fact("fencing_validator_configured", dependencies.fencing_validator is not None),
            self._fact("current_authority", False, "contextual-not-evaluated-by-health"),
            self._fact("secret_provider", dependencies.secret_provider is not None),
            self._fact("secret_environment_delivery", dependencies.secret_provider is not None),
            self._fact("secret_pipe_delivery", False, "unsupported-v1", unsupported=True),
            self._fact("secret_temporary_file_delivery", False, "unsupported-v1", unsupported=True),
            self._fact("network_disabled", network_health.disabled_enforceable),
            self._fact("network_loopback_only", network_health.loopback_only_enforceable),
            self._fact("network_allowlisted", network_health.allowlist_enforceable),
            self._fact("network_unrestricted_governed", True),
            self._fact("local_publication_custody", self.publication is not None),
            self._fact(
                "driver_state_persistence", bool(state_health and state_health.store_available)
            ),
            self._fact(
                "replay_reconciliation", bool(state_health and state_health.replay_available)
            ),
            self._fact(
                "anonymous_job_live_recovery", False, "unsupported-anonymous-job", unsupported=True
            ),
            self._fact(
                "orphan_detection", bool(state_health and state_health.orphan_detection_available)
            ),
            self._fact("restricted_host_identity", False, "unavailable-v1"),
            self._fact("vm_container_boundary", False, "unsupported-v1", unsupported=True),
            self._fact("isolation_l0", process_available),
            self._fact("isolation_l1", process_available),
            self._fact("isolation_l2", False, "restricted-identity-unavailable"),
        )
        return WindowsLocalCompositionHealth(
            self._configuration_fingerprint,
            facts,
            WindowsCapabilityClassification.UNAVAILABLE,
            False,
        )

    def probe(self) -> WindowsLocalCompositionHealth:
        health = self.health()
        if self.process is None:
            return health
        process = self.process.health()
        observed = {
            "resource_process_count": process.process_count_enforcement,
            "resource_process_memory": process.process_memory_enforcement,
            "resource_job_memory": process.job_memory_enforcement,
            "resource_cpu_time": process.cpu_time_enforcement,
            "resource_cpu_rate": process.cpu_rate_enforcement,
        }
        facts = tuple(
            replace(
                item,
                classification=(
                    WindowsCapabilityClassification.AVAILABLE
                    if observed[item.capability]
                    else WindowsCapabilityClassification.UNAVAILABLE
                ),
                limitation=None if observed[item.capability] else "host-capability-unavailable",
            )
            if item.capability in observed
            else item
            for item in health.capabilities
        )
        return replace(health, capabilities=facts)

    def execution_readiness(
        self, profile: WindowsExecutionProfileV1
    ) -> WindowsExecutionReadinessV1:
        health = self.health()
        required = [
            "platform_windows",
            "workspace_driver",
            "command_resolution",
            "process_creation",
            "job_object_containment",
            "execution_grant_validator_configured",
            "fencing_validator_configured",
        ]
        if profile.isolation_level is WindowsIsolationLevel.L2_RESTRICTED_WORKSPACE_PROCESS:
            required.append("isolation_l2")
        elif profile.isolation_level is WindowsIsolationLevel.L1_JOB_CONTAINED:
            required.append("isolation_l1")
        if profile.network_profile is WindowsNetworkProfile.DISABLED:
            required.append("network_disabled")
        elif profile.network_profile is WindowsNetworkProfile.LOOPBACK_ONLY:
            required.append("network_loopback_only")
        elif profile.network_profile is WindowsNetworkProfile.ALLOWLISTED:
            required.append("network_allowlisted")
        else:
            required.append("network_unrestricted_governed")
        if profile.requires_secret:
            required.extend(("secret_provider", "secret_environment_delivery"))
        if profile.requires_publication:
            required.append("local_publication_custody")
        if profile.requires_durable_state:
            required.extend(("driver_state_persistence", "replay_reconciliation"))
        satisfied = tuple(
            item
            for item in required
            if health.capability(item).classification
            in {
                WindowsCapabilityClassification.AVAILABLE,
                WindowsCapabilityClassification.CONFIGURED,
                WindowsCapabilityClassification.ENFORCED,
                WindowsCapabilityClassification.IMPLEMENTED,
            }
        )
        missing = tuple(item for item in required if item not in satisfied)
        return WindowsExecutionReadinessV1(profile, not missing, satisfied, missing)

    def execute(
        self,
        profile: WindowsExecutionProfileV1,
        request: WindowsProcessStartRequest,
    ) -> WindowsProcessStartResult:
        readiness = self.execution_readiness(profile)
        if not readiness.executable or self.process is None:
            return WindowsProcessStartResult(
                WindowsProcessStartOutcome.FAILED,
                False,
                False,
                False,
                True,
                None,
                tuple(f"readiness_missing:{item}" for item in readiness.missing_prerequisites),
            )
        return self.process.start(request)

    def replay(self) -> tuple[WindowsRestartProjectionV1, ...]:
        if self.state_store is None:
            return ()
        return self.reconciliation.project(self.state_store.replay())

    @staticmethod
    def _fact(
        name: str,
        available: bool,
        limitation: str | None = None,
        *,
        unsupported: bool = False,
    ) -> WindowsCompositionCapabilityFact:
        classification = (
            WindowsCapabilityClassification.AVAILABLE
            if available
            else (
                WindowsCapabilityClassification.UNSUPPORTED
                if unsupported
                else WindowsCapabilityClassification.UNAVAILABLE
            )
        )
        return WindowsCompositionCapabilityFact(name, classification, limitation)

    @staticmethod
    def _implemented(name: str, limitation: str) -> WindowsCompositionCapabilityFact:
        return WindowsCompositionCapabilityFact(
            name, WindowsCapabilityClassification.IMPLEMENTED, limitation
        )


def build_windows_sandbox_driver(
    config: WindowsCompositionConfig,
) -> WindowsLocalComposition:
    dependencies = config.dependencies
    guard = WindowsExecutionAuthorityGuard(
        dependencies.grant_validator, dependencies.fencing_validator
    )
    custody = LocalArtifactCustody(config.artifact_custody) if config.artifact_custody else None
    workspace = WindowsWorkspaceDriver(
        WindowsWorkspaceConfig(config.workspace_root, custody=custody),
        guard,
        dependencies.authority_context,
    )
    network = WindowsNetworkPolicyLayer(dependencies.network_mechanism)
    secret_materializer = (
        WindowsSecretMaterializer(dependencies.secret_provider, now=dependencies.clock)
        if dependencies.secret_provider is not None
        else None
    )
    process = None
    if (
        dependencies.process_api is not None
        and dependencies.execution_authorization is not None
        and dependencies.grant_validator is not None
        and dependencies.fencing_validator is not None
    ):
        process = WindowsProcessDriver(
            dependencies.process_api,
            dependencies.execution_authorization,
            dependencies.fencing_validator,
            secret_materializer=secret_materializer,
            network_policy_layer=network,
            platform_available=config.platform_windows,
        )
    publication = (
        WindowsOutputPublicationAdapter(
            config.workspace_root,
            config.publication_custody_root,
            guard,
            config.declared_outputs,
        )
        if config.publication_custody_root is not None
        else None
    )
    store = (
        WindowsSandboxDriverStore(config.driver_state_path)
        if config.driver_state_path is not None
        else None
    )
    fingerprint = SandboxArtifactFingerprint.from_content(
        (
            "windows-sandbox-driver-composition-v1",
            config.platform_windows,
            config.command.config_version,
            tuple(item.logical_name for item in config.command.entrypoints),
            bool(config.artifact_custody),
            bool(config.publication_custody_root),
            tuple(
                (workspace.value, declared.logical_path)
                for workspace, declared in config.declared_outputs
            ),
            bool(config.driver_state_path),
            bool(dependencies.process_api),
            bool(dependencies.execution_authorization),
            bool(dependencies.grant_validator),
            bool(dependencies.fencing_validator),
            bool(dependencies.secret_provider),
            bool(dependencies.network_mechanism),
        )
    )
    return WindowsLocalComposition(
        config,
        workspace,
        WindowsCommandResolver(config.command),
        network,
        process,
        custody,
        publication,
        secret_materializer,
        store,
        WindowsSandboxReconciliationPlanner(),
        WindowsCleanupCampaign(guard),
        fingerprint,
    )
