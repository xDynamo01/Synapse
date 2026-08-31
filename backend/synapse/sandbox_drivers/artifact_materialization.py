"""Governed binding correspondence for local artifact materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionRequest,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxMaterializationAction,
    SandboxMaterializationStepOutcome,
    SandboxMaterializationStepRequest,
    SandboxMaterializationStepResult,
    SandboxWorkspaceId,
)

from .local_artifact_custody import LocalArtifactCustodyPort


class WorkspaceMaterializationPort(Protocol):
    def apply(
        self, request: SandboxMaterializationStepRequest
    ) -> SandboxMaterializationStepResult: ...


@dataclass(frozen=True, slots=True)
class GovernedArtifactBinding:
    workspace_id: SandboxWorkspaceId
    artifact_reference: OpaqueReference
    artifact_fingerprint: SandboxArtifactFingerprint
    destination_resource: SandboxFilesystemResource
    destination: SandboxLogicalPath
    action: SandboxMaterializationAction
    provenance_reference: OpaqueReference


class LocalArtifactMaterializationAdapter:
    def __init__(
        self,
        custody: LocalArtifactCustodyPort,
        workspace: WorkspaceMaterializationPort,
    ) -> None:
        self._custody = custody
        self._workspace = workspace

    def materialize(
        self,
        binding: GovernedArtifactBinding,
        request: SandboxMaterializationStepRequest,
    ) -> SandboxMaterializationStepResult:
        operation = request.operation
        if (
            request.workspace_id != binding.workspace_id
            or operation.source_ref != binding.artifact_reference
            or operation.expected_fingerprint != binding.artifact_fingerprint
            or operation.destination_resource != binding.destination_resource
            or operation.destination != binding.destination
            or operation.action != binding.action
        ):
            return SandboxMaterializationStepResult(
                SandboxMaterializationStepOutcome.FAILED,
                ("materialization_binding_mismatch",),
            )
        inspection = self._custody.inspect(
            SandboxArtifactInspectionRequest(
                binding.artifact_reference, binding.artifact_fingerprint
            )
        )
        if inspection.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED:
            return SandboxMaterializationStepResult(
                SandboxMaterializationStepOutcome.FAILED,
                inspection.diagnostic_codes,
            )
        return self._workspace.apply(request)
