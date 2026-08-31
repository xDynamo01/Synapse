"""Consumer-owned dry handoff from Deployment preparation to Sandbox Windows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from synapse.deployment import (
    CapabilityReference,
    DeploymentSandboxHandoffDraftV1,
    LocalRevisionPreparationResultV1,
    SandboxLocalApplyCommandV1,
    SandboxLocalApplyOutcome,
    SandboxLocalApplyResultV1,
)
from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxLogicalWorkspaceRoot,
    SandboxMaterializationAction,
    SandboxMaterializationCleanupPolicy,
    SandboxMaterializationOperation,
    SandboxMaterializationStepRequest,
    SandboxWorkspaceId,
    SandboxWorkspacePreparationRequest,
)
from synapse.sandbox_drivers import (
    WindowsProcessStartOutcome,
    WindowsProcessStartRequest,
    WindowsProcessStartResult,
)


@dataclass(frozen=True, slots=True)
class DeploymentSandboxWindowsHandoffV1:
    workspace_request: SandboxWorkspacePreparationRequest
    artifact_request: SandboxMaterializationStepRequest
    command_entrypoint: OpaqueReference
    resource_profile: OpaqueReference
    network_profile: OpaqueReference | None
    secret_references: tuple[OpaqueReference, ...]
    deployment_authorization_reference: OpaqueReference
    deployment_fencing_reference: OpaqueReference
    sandbox_fencing_reference: OpaqueReference | None
    execution_requested: bool = False
    target_activation_requested: bool = False

    @property
    def sandbox_fencing_required(self) -> bool:
        return True


class DeploymentSandboxWindowsHandoffAdapter:
    """Translate only; it owns no Sandbox execution or fencing authority."""

    def translate(
        self, result: LocalRevisionPreparationResultV1
    ) -> DeploymentSandboxWindowsHandoffV1 | None:
        draft = result.handoff
        if draft is None:
            return None
        return _translate(draft)


class WindowsProcessStartPort(Protocol):
    def start(self, request: WindowsProcessStartRequest) -> WindowsProcessStartResult: ...


@dataclass(frozen=True, slots=True)
class DeploymentWindowsProcessBindingV1:
    workspace_reference: CapabilityReference
    sandbox_fencing_reference: CapabilityReference
    request: WindowsProcessStartRequest


class DeploymentWindowsProcessApplyAdapter:
    """Narrow bridge to the frozen Windows process driver start boundary."""

    def __init__(
        self,
        driver: WindowsProcessStartPort,
        bindings: tuple[DeploymentWindowsProcessBindingV1, ...],
    ) -> None:
        self._driver = driver
        self._bindings = {item.workspace_reference: item for item in bindings}

    def start(self, command: SandboxLocalApplyCommandV1) -> SandboxLocalApplyResultV1:
        binding = self._bindings.get(command.workspace_reference)
        if binding is None:
            return _apply_failure("sandbox-handoff-unavailable")
        request = binding.request
        if (
            request.workspace_id.value != command.workspace_reference.value
            or request.grant_reference.value != command.sandbox_authorization_reference.value
            or request.authority_context is None
            or binding.sandbox_fencing_reference != command.sandbox_fencing_reference
        ):
            return _apply_failure("sandbox-authority-invalid")
        result = self._driver.start(request)
        outcome = {
            WindowsProcessStartOutcome.STARTED: SandboxLocalApplyOutcome.STARTED,
            WindowsProcessStartOutcome.FAILED: (
                SandboxLocalApplyOutcome.PARTIAL
                if result.process_created
                else SandboxLocalApplyOutcome.FAILED
            ),
            WindowsProcessStartOutcome.UNAVAILABLE: SandboxLocalApplyOutcome.UNKNOWN,
        }[result.outcome]
        return SandboxLocalApplyResultV1(
            outcome,
            (
                CapabilityReference(result.managed_process.process_reference.value)
                if result.managed_process is not None
                else None
            ),
            result.process_started,
            result.containment_established,
            result.diagnostic_codes,
        )


def _translate(draft: DeploymentSandboxHandoffDraftV1) -> DeploymentSandboxWindowsHandoffV1:
    workspace_id = SandboxWorkspaceId(draft.workspace_reference.value)
    return DeploymentSandboxWindowsHandoffV1(
        SandboxWorkspacePreparationRequest(
            workspace_id,
            SandboxLogicalWorkspaceRoot("workspace"),
            SandboxMaterializationCleanupPolicy.ON_FAILURE,
        ),
        SandboxMaterializationStepRequest(
            workspace_id,
            SandboxMaterializationOperation(
                1,
                SandboxMaterializationAction.STAGE_ARTIFACT,
                SandboxFilesystemResource.ARTIFACT,
                SandboxLogicalPath.parse("revision", case_sensitive=False),
                OpaqueReference(draft.artifact_reference),
                SandboxArtifactFingerprint(draft.artifact_fingerprint),
            ),
        ),
        OpaqueReference(draft.command_entrypoint.value),
        OpaqueReference(draft.resource_profile.value),
        OpaqueReference(draft.network_profile.value) if draft.network_profile else None,
        tuple(OpaqueReference(item.value) for item in draft.secret_references),
        OpaqueReference(draft.authorization_reference.value),
        OpaqueReference(draft.deployment_fencing_reference.value),
        None,
    )


def _apply_failure(code: str) -> SandboxLocalApplyResultV1:
    return SandboxLocalApplyResultV1(SandboxLocalApplyOutcome.FAILED, None, False, False, (code,))
