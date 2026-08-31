"""Abstract deterministic materialization orchestration over logical DTOs only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidMaterialization
from .execution_plan import SandboxExecutionPlan
from .filesystem_boundary import (
    SandboxFilesystemGrant,
    SandboxFilesystemOperation,
    SandboxFilesystemResource,
    SandboxFilesystemSpecification,
    SandboxLogicalPath,
)
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxMaterializationId,
    SandboxMaterializationPlanId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxWorkspaceId,
    derive_identity,
)
from .network_boundary import SandboxNetworkSpecification
from .process_boundary import SandboxProcessSpecification
from .resource_limits import SandboxResourceSpecification
from .secrets_boundary import SandboxSecretLeaseSpecification
from .states import SandboxCleanupState

MATERIALIZATION_PLAN_FORMAT = "sandbox-materialization-plan-v1"
_SAFE_DIAGNOSTIC = re.compile(r"[a-z][a-z0-9_.-]{0,95}")


def _diagnostics_are_canonical(codes: tuple[str, ...]) -> bool:
    return codes == tuple(sorted(set(codes))) and all(
        _SAFE_DIAGNOSTIC.fullmatch(code) is not None for code in codes
    )


class SandboxMaterializationAction(StrEnum):
    PREPARE_WORKSPACE = "prepare_workspace"
    STAGE_ARTIFACT = "stage_artifact"
    BIND_READONLY_INPUT = "bind_readonly_input"
    PREPARE_OUTPUT = "prepare_output"
    PREPARE_TEMPORARY = "prepare_temporary"
    BIND_RUNTIME_ASSET = "bind_runtime_asset"
    VERIFY_CONTENT = "verify_content"
    SEAL_WORKSPACE = "seal_workspace"
    CLEANUP_WORKSPACE = "cleanup_workspace"


class SandboxMaterializationBindingKind(StrEnum):
    ARTIFACT_INPUT = "artifact_input"
    READONLY_INPUT = "readonly_input"
    WRITABLE_OUTPUT = "writable_output"
    TEMPORARY_AREA = "temporary_area"
    STATE_ROOT = "state_root"
    RUNTIME_ASSET = "runtime_asset"


class SandboxMaterializationCleanupPolicy(StrEnum):
    ON_FAILURE = "on_failure"
    AFTER_USE = "after_use"


class SandboxMaterializationStepOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class SandboxMaterializationVerificationOutcome(StrEnum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    MISMATCH = "mismatch"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    CLEANUP_REQUIRED = "cleanup_required"
    CLEANUP_FAILED = "cleanup_failed"


class SandboxMaterializationResultOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CLEANUP_REQUIRED = "cleanup_required"


@dataclass(frozen=True, slots=True)
class SandboxLogicalWorkspaceRoot:
    value: str

    def __post_init__(self) -> None:
        if self.value != "workspace":
            raise InvalidMaterialization("workspace.root_invalid")


@dataclass(frozen=True, slots=True)
class SandboxMaterializationAsset:
    source_ref: OpaqueReference
    expected_fingerprint: SandboxArtifactFingerprint
    destination_resource: SandboxFilesystemResource
    destination: SandboxLogicalPath
    kind: SandboxMaterializationBindingKind
    read_only: bool


@dataclass(frozen=True, slots=True)
class SandboxMaterializationOperation:
    ordinal: int
    action: SandboxMaterializationAction
    destination_resource: SandboxFilesystemResource | None
    destination: SandboxLogicalPath | None
    source_ref: OpaqueReference | None
    expected_fingerprint: SandboxArtifactFingerprint | None

    def __post_init__(self) -> None:
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal <= 0:
            raise InvalidMaterialization("operation.ordinal_invalid")
        asset_actions = {
            SandboxMaterializationAction.STAGE_ARTIFACT,
            SandboxMaterializationAction.BIND_READONLY_INPUT,
            SandboxMaterializationAction.BIND_RUNTIME_ASSET,
        }
        destination_actions = asset_actions | {
            SandboxMaterializationAction.PREPARE_OUTPUT,
            SandboxMaterializationAction.PREPARE_TEMPORARY,
        }
        if self.action in destination_actions and (
            self.destination_resource is None or self.destination is None
        ):
            raise InvalidMaterialization("operation.destination_required")
        if self.action in asset_actions and (
            self.source_ref is None or self.expected_fingerprint is None
        ):
            raise InvalidMaterialization("operation.source_required")
        if self.action not in destination_actions and (
            self.destination_resource is not None or self.destination is not None
        ):
            raise InvalidMaterialization("operation.destination_unexpected")


@dataclass(frozen=True, slots=True)
class SandboxMaterializationRequest:
    plan: SandboxExecutionPlan
    capabilities: SandboxCapabilityGrantSet
    filesystem: SandboxFilesystemSpecification
    network: SandboxNetworkSpecification
    process: SandboxProcessSpecification
    resources: SandboxResourceSpecification
    secrets: SandboxSecretLeaseSpecification | None
    cleanup_policy: SandboxMaterializationCleanupPolicy
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise InvalidMaterialization("request.occurred_at_invalid")


@dataclass(frozen=True, slots=True)
class SandboxMaterializationPlan:
    format_version: str
    materialization_plan_id: SandboxMaterializationPlanId
    materialization_plan_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    capability_grant_set_fingerprint: SandboxArtifactFingerprint
    filesystem_specification_fingerprint: SandboxArtifactFingerprint
    network_specification_fingerprint: SandboxArtifactFingerprint
    process_specification_fingerprint: SandboxArtifactFingerprint
    resource_specification_fingerprint: SandboxArtifactFingerprint
    secret_specification_fingerprint: SandboxArtifactFingerprint | None
    workspace_id: SandboxWorkspaceId
    workspace_root: SandboxLogicalWorkspaceRoot
    artifact_inputs: tuple[SandboxMaterializationAsset, ...]
    readonly_inputs: tuple[SandboxMaterializationAsset, ...]
    writable_outputs: tuple[SandboxMaterializationAsset, ...]
    temporary_areas: tuple[SandboxMaterializationAsset, ...]
    state_roots: tuple[SandboxMaterializationAsset, ...]
    runtime_assets: tuple[SandboxMaterializationAsset, ...]
    operations: tuple[SandboxMaterializationOperation, ...]
    expected_workspace_fingerprint: SandboxArtifactFingerprint
    cleanup_policy: SandboxMaterializationCleanupPolicy

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.plan_id,
            self.plan_fingerprint,
            self.capability_grant_set_fingerprint,
            self.filesystem_specification_fingerprint,
            self.network_specification_fingerprint,
            self.process_specification_fingerprint,
            self.resource_specification_fingerprint,
            self.secret_specification_fingerprint,
            self.workspace_id,
            self.workspace_root,
            self.artifact_inputs,
            self.readonly_inputs,
            self.writable_outputs,
            self.temporary_areas,
            self.state_roots,
            self.runtime_assets,
            self.operations,
            self.expected_workspace_fingerprint,
            self.cleanup_policy,
        )

    def __post_init__(self) -> None:
        if self.format_version != MATERIALIZATION_PLAN_FORMAT:
            raise InvalidMaterialization("plan.format_unsupported")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.materialization_plan_fingerprint:
            raise InvalidMaterialization("plan.fingerprint_mismatch")
        if derive_identity(SandboxMaterializationPlanId, expected) != self.materialization_plan_id:
            raise InvalidMaterialization("plan.identity_mismatch")
        if self.operations != tuple(
            sorted(self.operations, key=lambda item: item.ordinal)
        ) or tuple(item.ordinal for item in self.operations) != tuple(
            range(1, len(self.operations) + 1)
        ):
            raise InvalidMaterialization("plan.operations_not_canonical")
        collections = (
            self.readonly_inputs,
            self.writable_outputs,
            self.temporary_areas,
            self.state_roots,
        )
        for collection in collections:
            if collection != tuple(
                sorted(
                    collection,
                    key=lambda item: (
                        item.destination_resource.value,
                        item.destination.value,
                    ),
                )
            ):
                raise InvalidMaterialization("plan.assets_not_canonical")
        if len(self.artifact_inputs) != 1 or len(self.runtime_assets) != 1:
            raise InvalidMaterialization("plan.required_assets_invalid")
        SandboxMaterializationPlanService._validate_destinations(
            self.artifact_inputs,
            self.runtime_assets,
            *collections,
        )
        expected_operations = SandboxMaterializationPlanService._operations(
            self.artifact_inputs[0],
            self.runtime_assets[0],
            self.readonly_inputs,
            self.writable_outputs,
            self.temporary_areas,
            self.state_roots,
        )
        if self.operations != expected_operations:
            raise InvalidMaterialization("plan.operations_mismatch")
        expected_workspace = SandboxArtifactFingerprint.from_content(
            (
                self.workspace_id,
                self.artifact_inputs[0],
                self.runtime_assets[0],
                *collections,
                self.operations,
            )
        )
        if self.expected_workspace_fingerprint != expected_workspace:
            raise InvalidMaterialization("plan.workspace_fingerprint_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxArtifactInspectionRequest:
    source_ref: OpaqueReference
    expected_fingerprint: SandboxArtifactFingerprint


@dataclass(frozen=True, slots=True)
class SandboxArtifactInspectionResult:
    outcome: SandboxMaterializationStepOutcome
    observed_fingerprint: SandboxArtifactFingerprint | None
    stale: bool
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxWorkspacePreparationRequest:
    workspace_id: SandboxWorkspaceId
    workspace_root: SandboxLogicalWorkspaceRoot
    cleanup_policy: SandboxMaterializationCleanupPolicy


@dataclass(frozen=True, slots=True)
class SandboxMaterializationStepRequest:
    workspace_id: SandboxWorkspaceId
    operation: SandboxMaterializationOperation


@dataclass(frozen=True, slots=True)
class SandboxMaterializationStepResult:
    outcome: SandboxMaterializationStepOutcome
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxMaterializedFingerprintRequest:
    workspace_id: SandboxWorkspaceId
    destination_resource: SandboxFilesystemResource
    destination: SandboxLogicalPath


@dataclass(frozen=True, slots=True)
class SandboxMaterializedFingerprintResult:
    outcome: SandboxMaterializationStepOutcome
    observed_fingerprint: SandboxArtifactFingerprint | None
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxWorkspaceVerificationRequest:
    workspace_id: SandboxWorkspaceId
    materialization_plan_fingerprint: SandboxArtifactFingerprint
    expected_workspace_fingerprint: SandboxArtifactFingerprint


@dataclass(frozen=True, slots=True)
class SandboxWorkspaceVerificationResult:
    outcome: SandboxMaterializationStepOutcome
    observed_workspace_fingerprint: SandboxArtifactFingerprint | None
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxWorkspaceCleanupRequest:
    workspace_id: SandboxWorkspaceId
    materialization_plan_fingerprint: SandboxArtifactFingerprint


class SandboxArtifactCustodyPort(Protocol):
    def inspect(
        self, request: SandboxArtifactInspectionRequest
    ) -> SandboxArtifactInspectionResult: ...


class SandboxWorkspacePreparationPort(Protocol):
    def prepare(
        self, request: SandboxWorkspacePreparationRequest
    ) -> SandboxMaterializationStepResult: ...

    def apply(
        self, request: SandboxMaterializationStepRequest
    ) -> SandboxMaterializationStepResult: ...

    def seal(
        self, request: SandboxMaterializationStepRequest
    ) -> SandboxMaterializationStepResult: ...

    def cleanup(
        self, request: SandboxWorkspaceCleanupRequest
    ) -> SandboxMaterializationStepResult: ...


class SandboxMaterializationVerificationPort(Protocol):
    def refingerprint(
        self, request: SandboxMaterializedFingerprintRequest
    ) -> SandboxMaterializedFingerprintResult: ...

    def verify(
        self, request: SandboxWorkspaceVerificationRequest
    ) -> SandboxWorkspaceVerificationResult: ...


@dataclass(frozen=True, slots=True)
class SandboxMaterializationStepRecord:
    ordinal: int
    action: SandboxMaterializationAction
    outcome: SandboxMaterializationStepOutcome
    observed_fingerprint: SandboxArtifactFingerprint | None
    diagnostic_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ordinal, int) or isinstance(self.ordinal, bool) or self.ordinal <= 0:
            raise InvalidMaterialization("step.ordinal_invalid")
        if not _diagnostics_are_canonical(self.diagnostic_codes):
            raise InvalidMaterialization("step.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxMaterializationVerification:
    outcome: SandboxMaterializationVerificationOutcome
    expected_workspace_fingerprint: SandboxArtifactFingerprint
    observed_workspace_fingerprint: SandboxArtifactFingerprint | None
    diagnostic_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _diagnostics_are_canonical(self.diagnostic_codes):
            raise InvalidMaterialization("verification.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxMaterializationRecord:
    materialization_id: SandboxMaterializationId
    materialization_fingerprint: SandboxArtifactFingerprint
    materialization_plan_id: SandboxMaterializationPlanId
    materialization_plan_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    workspace_id: SandboxWorkspaceId
    expected_artifacts: tuple[SandboxMaterializationAsset, ...]
    observed_artifacts: tuple[tuple[OpaqueReference, SandboxArtifactFingerprint], ...]
    completed_operations: tuple[SandboxMaterializationStepRecord, ...]
    verification: SandboxMaterializationVerification
    cleanup_state: SandboxCleanupState
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.materialization_plan_id,
            self.materialization_plan_fingerprint,
            self.plan_id,
            self.plan_fingerprint,
            self.workspace_id,
            self.expected_artifacts,
            self.observed_artifacts,
            self.completed_operations,
            self.verification,
            self.cleanup_state,
        )

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise InvalidMaterialization("record.occurred_at_invalid")
        if self.verification.outcome is not SandboxMaterializationVerificationOutcome.VERIFIED:
            raise InvalidMaterialization("record.verification_required")
        if self.observed_artifacts != tuple(
            sorted(self.observed_artifacts, key=lambda item: item[0].value)
        ):
            raise InvalidMaterialization("record.observed_artifacts_not_canonical")
        if tuple(item.ordinal for item in self.completed_operations) != tuple(
            range(1, len(self.completed_operations) + 1)
        ):
            raise InvalidMaterialization("record.operations_not_canonical")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.materialization_fingerprint:
            raise InvalidMaterialization("record.fingerprint_mismatch")
        if derive_identity(SandboxMaterializationId, expected) != self.materialization_id:
            raise InvalidMaterialization("record.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxMaterializationResult:
    outcome: SandboxMaterializationResultOutcome
    materialization_plan: SandboxMaterializationPlan
    steps: tuple[SandboxMaterializationStepRecord, ...]
    verification: SandboxMaterializationVerification
    cleanup_state: SandboxCleanupState
    record: SandboxMaterializationRecord | None

    def __post_init__(self) -> None:
        if (self.outcome is SandboxMaterializationResultOutcome.SUCCEEDED) != (
            self.record is not None
        ):
            raise InvalidMaterialization("result.record_outcome_conflict")


class SandboxMaterializationPlanService:
    """Build a canonical logical workspace plan before any port interaction."""

    @classmethod
    def build(cls, request: SandboxMaterializationRequest) -> SandboxMaterializationPlan:
        cls.validate_bindings(request)
        artifact_path = SandboxLogicalPath.parse("artifact/workload", case_sensitive=True)
        artifact_asset = SandboxMaterializationAsset(
            request.plan.artifact_ref,
            request.plan.artifact_fingerprint,
            SandboxFilesystemResource.ARTIFACT,
            artifact_path,
            SandboxMaterializationBindingKind.ARTIFACT_INPUT,
            True,
        )
        runtime_ref = OpaqueReference(
            f"runtime:{request.plan.runtime.kind.value}:{request.plan.runtime.version}"
        )
        runtime_fingerprint = SandboxArtifactFingerprint.from_content(request.plan.runtime)
        runtime_asset = SandboxMaterializationAsset(
            runtime_ref,
            runtime_fingerprint,
            SandboxFilesystemResource.ARTIFACT,
            SandboxLogicalPath.parse("runtime/asset", case_sensitive=True),
            SandboxMaterializationBindingKind.RUNTIME_ASSET,
            True,
        )
        readonly: list[SandboxMaterializationAsset] = []
        outputs: list[SandboxMaterializationAsset] = []
        temporary: list[SandboxMaterializationAsset] = []
        state: list[SandboxMaterializationAsset] = []
        for grant in request.filesystem.grants:
            if grant.resource in {
                SandboxFilesystemResource.ARTIFACT,
                SandboxFilesystemResource.WORKSPACE,
            }:
                continue
            asset = cls._asset_from_filesystem_grant(grant)
            if asset.kind is SandboxMaterializationBindingKind.READONLY_INPUT:
                readonly.append(asset)
            elif asset.kind is SandboxMaterializationBindingKind.WRITABLE_OUTPUT:
                outputs.append(asset)
            elif asset.kind is SandboxMaterializationBindingKind.TEMPORARY_AREA:
                temporary.append(asset)
            else:
                state.append(asset)
        collections = tuple(
            tuple(
                sorted(
                    items,
                    key=lambda item: (item.destination_resource.value, item.destination.value),
                )
            )
            for items in (readonly, outputs, temporary, state)
        )
        cls._validate_destinations(
            (artifact_asset, runtime_asset),
            *collections,
        )
        workspace_id_raw = derive_identity(
            SandboxWorkspaceId,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.filesystem.specification_fingerprint,
        )
        workspace_id = SandboxWorkspaceId(workspace_id_raw.value)
        operations = cls._operations(
            artifact_asset,
            runtime_asset,
            collections[0],
            collections[1],
            collections[2],
            collections[3],
        )
        expected_workspace_fingerprint = SandboxArtifactFingerprint.from_content(
            (
                workspace_id,
                artifact_asset,
                runtime_asset,
                *collections,
                operations,
            )
        )
        secret_fingerprint = (
            request.secrets.specification_fingerprint if request.secrets is not None else None
        )
        semantic = (
            MATERIALIZATION_PLAN_FORMAT,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.capabilities.grant_set_fingerprint,
            request.filesystem.specification_fingerprint,
            request.network.specification_fingerprint,
            request.process.specification_fingerprint,
            request.resources.specification_fingerprint,
            secret_fingerprint,
            workspace_id,
            SandboxLogicalWorkspaceRoot("workspace"),
            (artifact_asset,),
            collections[0],
            collections[1],
            collections[2],
            collections[3],
            (runtime_asset,),
            operations,
            expected_workspace_fingerprint,
            request.cleanup_policy,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxMaterializationPlanId, fingerprint)
        return SandboxMaterializationPlan(
            MATERIALIZATION_PLAN_FORMAT,
            SandboxMaterializationPlanId(identity.value),
            fingerprint,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.capabilities.grant_set_fingerprint,
            request.filesystem.specification_fingerprint,
            request.network.specification_fingerprint,
            request.process.specification_fingerprint,
            request.resources.specification_fingerprint,
            secret_fingerprint,
            workspace_id,
            SandboxLogicalWorkspaceRoot("workspace"),
            (artifact_asset,),
            collections[0],
            collections[1],
            collections[2],
            collections[3],
            (runtime_asset,),
            operations,
            expected_workspace_fingerprint,
            request.cleanup_policy,
        )

    @staticmethod
    def validate_bindings(request: SandboxMaterializationRequest) -> None:
        plan = request.plan
        diagnostics = []
        for name, candidate_id, candidate_fingerprint in (
            (
                "capability",
                request.capabilities.plan_id,
                request.capabilities.plan_fingerprint,
            ),
            (
                "filesystem",
                request.filesystem.plan_id,
                request.filesystem.plan_fingerprint,
            ),
            (
                "network",
                request.network.plan_id,
                request.network.plan_fingerprint,
            ),
            (
                "process",
                request.process.plan_id,
                request.process.plan_fingerprint,
            ),
            (
                "resources",
                request.resources.plan_id,
                request.resources.plan_fingerprint,
            ),
        ):
            if candidate_id != plan.plan_id:
                diagnostics.append(f"binding.{name}_plan_identity_mismatch")
            if candidate_fingerprint != plan.plan_fingerprint:
                diagnostics.append(f"binding.{name}_plan_fingerprint_mismatch")
        if (
            request.process.filesystem_specification_fingerprint
            != request.filesystem.specification_fingerprint
        ):
            diagnostics.append("binding.process_filesystem_mismatch")
        if (
            request.process.network_specification_fingerprint
            != request.network.specification_fingerprint
        ):
            diagnostics.append("binding.process_network_mismatch")
        if (
            request.resources.filesystem_specification_fingerprint
            != request.filesystem.specification_fingerprint
        ):
            diagnostics.append("binding.resources_filesystem_mismatch")
        if (
            request.resources.network_specification_fingerprint
            != request.network.specification_fingerprint
        ):
            diagnostics.append("binding.resources_network_mismatch")
        if (
            request.resources.process_specification_fingerprint
            != request.process.specification_fingerprint
        ):
            diagnostics.append("binding.resources_process_mismatch")
        if request.secrets is not None:
            if request.secrets.plan_id != plan.plan_id:
                diagnostics.append("binding.secrets_plan_identity_mismatch")
            if request.secrets.plan_fingerprint != plan.plan_fingerprint:
                diagnostics.append("binding.secrets_plan_fingerprint_mismatch")
            if (
                request.secrets.resource_specification_fingerprint
                != request.resources.specification_fingerprint
            ):
                diagnostics.append("binding.secrets_resources_mismatch")
        if diagnostics:
            raise InvalidMaterialization(tuple(sorted(diagnostics)))

    @staticmethod
    def _asset_from_filesystem_grant(
        grant: SandboxFilesystemGrant,
    ) -> SandboxMaterializationAsset:
        mutation = grant.operation in {
            SandboxFilesystemOperation.CREATE,
            SandboxFilesystemOperation.WRITE,
            SandboxFilesystemOperation.APPEND,
            SandboxFilesystemOperation.DELETE,
        }
        if grant.resource is SandboxFilesystemResource.INPUT:
            kind = SandboxMaterializationBindingKind.READONLY_INPUT
            read_only = True
        elif grant.resource is SandboxFilesystemResource.OUTPUT:
            kind = SandboxMaterializationBindingKind.WRITABLE_OUTPUT
            read_only = False
        elif grant.resource is SandboxFilesystemResource.TEMPORARY:
            kind = SandboxMaterializationBindingKind.TEMPORARY_AREA
            read_only = False
        elif grant.resource is SandboxFilesystemResource.STATE:
            kind = SandboxMaterializationBindingKind.STATE_ROOT
            read_only = not mutation
        else:
            raise InvalidMaterialization("filesystem.resource_unsupported")
        if grant.resource is SandboxFilesystemResource.INPUT and mutation:
            raise InvalidMaterialization("filesystem.readonly_input_conflict")
        fingerprint = SandboxArtifactFingerprint.from_content(grant)
        return SandboxMaterializationAsset(
            grant.scope_ref,
            fingerprint,
            grant.resource,
            grant.path,
            kind,
            read_only,
        )

    @staticmethod
    def _validate_destinations(
        *collections: tuple[SandboxMaterializationAsset, ...],
    ) -> None:
        destinations: dict[
            tuple[SandboxFilesystemResource, SandboxLogicalPath],
            SandboxMaterializationAsset,
        ] = {}
        for asset in (item for collection in collections for item in collection):
            key = (asset.destination_resource, asset.destination)
            existing = destinations.get(key)
            if existing is not None:
                if existing != asset or existing.read_only != asset.read_only:
                    raise InvalidMaterialization("workspace.destination_conflict")
                raise InvalidMaterialization("workspace.destination_duplicate")
            destinations[key] = asset

    @staticmethod
    def _operations(
        artifact: SandboxMaterializationAsset,
        runtime: SandboxMaterializationAsset,
        readonly: tuple[SandboxMaterializationAsset, ...],
        outputs: tuple[SandboxMaterializationAsset, ...],
        temporary: tuple[SandboxMaterializationAsset, ...],
        state: tuple[SandboxMaterializationAsset, ...],
    ) -> tuple[SandboxMaterializationOperation, ...]:
        pending: list[tuple[SandboxMaterializationAction, SandboxMaterializationAsset | None]] = [
            (SandboxMaterializationAction.PREPARE_WORKSPACE, None),
            (SandboxMaterializationAction.STAGE_ARTIFACT, artifact),
        ]
        pending.extend(
            (SandboxMaterializationAction.BIND_READONLY_INPUT, item) for item in readonly
        )
        pending.extend(
            (SandboxMaterializationAction.BIND_READONLY_INPUT, item)
            for item in state
            if item.read_only
        )
        pending.extend((SandboxMaterializationAction.PREPARE_OUTPUT, item) for item in outputs)
        pending.extend(
            (SandboxMaterializationAction.PREPARE_OUTPUT, item)
            for item in state
            if not item.read_only
        )
        pending.extend((SandboxMaterializationAction.PREPARE_TEMPORARY, item) for item in temporary)
        pending.append((SandboxMaterializationAction.BIND_RUNTIME_ASSET, runtime))
        pending.extend(
            (
                (SandboxMaterializationAction.VERIFY_CONTENT, None),
                (SandboxMaterializationAction.SEAL_WORKSPACE, None),
            )
        )
        return tuple(
            SandboxMaterializationOperation(
                index,
                action,
                asset.destination_resource if asset is not None else None,
                asset.destination if asset is not None else None,
                asset.source_ref if asset is not None else None,
                asset.expected_fingerprint if asset is not None else None,
            )
            for index, (action, asset) in enumerate(pending, start=1)
        )


class SandboxMaterializationApplicationService:
    """Apply an already validated logical plan through abstract typed ports."""

    def __init__(
        self,
        custody: SandboxArtifactCustodyPort,
        workspace: SandboxWorkspacePreparationPort,
        verification: SandboxMaterializationVerificationPort,
    ) -> None:
        self._custody = custody
        self._workspace = workspace
        self._verification = verification

    def materialize(self, request: SandboxMaterializationRequest) -> SandboxMaterializationResult:
        plan = SandboxMaterializationPlanService.build(request)
        inspected = self._inspect_assets(plan)
        if isinstance(inspected, SandboxMaterializationResult):
            return inspected
        observed_artifacts = inspected
        steps: list[SandboxMaterializationStepRecord] = []
        partial = False
        for operation in plan.operations:
            if operation.action is SandboxMaterializationAction.PREPARE_WORKSPACE:
                result = self._workspace.prepare(
                    SandboxWorkspacePreparationRequest(
                        plan.workspace_id,
                        plan.workspace_root,
                        plan.cleanup_policy,
                    )
                )
                step = self._step(operation, result)
            elif operation.action is SandboxMaterializationAction.VERIFY_CONTENT:
                verification_result = self._verification.verify(
                    SandboxWorkspaceVerificationRequest(
                        plan.workspace_id,
                        plan.materialization_plan_fingerprint,
                        plan.expected_workspace_fingerprint,
                    )
                )
                step = SandboxMaterializationStepRecord(
                    operation.ordinal,
                    operation.action,
                    verification_result.outcome,
                    verification_result.observed_workspace_fingerprint,
                    self._safe_diagnostics(
                        verification_result.diagnostic_codes,
                        "verification.failed",
                    ),
                )
                if (
                    verification_result.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED
                    or verification_result.observed_workspace_fingerprint
                    != plan.expected_workspace_fingerprint
                ):
                    steps.append(step)
                    return self._partial_failure(
                        plan,
                        steps,
                        observed_artifacts,
                        SandboxMaterializationVerificationOutcome.MISMATCH,
                        verification_result.observed_workspace_fingerprint,
                    )
            elif operation.action is SandboxMaterializationAction.SEAL_WORKSPACE:
                result = self._workspace.seal(
                    SandboxMaterializationStepRequest(plan.workspace_id, operation)
                )
                step = self._step(operation, result)
            else:
                result = self._workspace.apply(
                    SandboxMaterializationStepRequest(plan.workspace_id, operation)
                )
                step = self._step(operation, result)
                if (
                    result.outcome is SandboxMaterializationStepOutcome.SUCCEEDED
                    and operation.action
                    in {
                        SandboxMaterializationAction.STAGE_ARTIFACT,
                        SandboxMaterializationAction.BIND_READONLY_INPUT,
                        SandboxMaterializationAction.BIND_RUNTIME_ASSET,
                    }
                    and operation.expected_fingerprint is not None
                    and operation.destination_resource is not None
                    and operation.destination is not None
                ):
                    observed = self._verification.refingerprint(
                        SandboxMaterializedFingerprintRequest(
                            plan.workspace_id,
                            operation.destination_resource,
                            operation.destination,
                        )
                    )
                    if (
                        observed.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED
                        or observed.observed_fingerprint != operation.expected_fingerprint
                    ):
                        mismatch_step = SandboxMaterializationStepRecord(
                            operation.ordinal,
                            operation.action,
                            SandboxMaterializationStepOutcome.FAILED,
                            observed.observed_fingerprint,
                            ("materialization.fingerprint_mismatch",),
                        )
                        steps.append(mismatch_step)
                        return self._partial_failure(
                            plan,
                            steps,
                            observed_artifacts,
                            SandboxMaterializationVerificationOutcome.MISMATCH,
                            None,
                        )
            steps.append(step)
            if step.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED:
                if partial:
                    return self._partial_failure(
                        plan,
                        steps,
                        observed_artifacts,
                        self._verification_outcome(step.outcome),
                        None,
                    )
                return self._failure_without_cleanup(
                    plan,
                    steps,
                    self._verification_outcome(step.outcome),
                )
            partial = True
        verification = SandboxMaterializationVerification(
            SandboxMaterializationVerificationOutcome.VERIFIED,
            plan.expected_workspace_fingerprint,
            plan.expected_workspace_fingerprint,
            (),
        )
        completed = tuple(steps)
        expected_assets = plan.artifact_inputs + plan.readonly_inputs + plan.runtime_assets
        record_content = (
            plan.materialization_plan_id,
            plan.materialization_plan_fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.workspace_id,
            expected_assets,
            observed_artifacts,
            completed,
            verification,
            SandboxCleanupState.NOT_REQUIRED,
        )
        record_fingerprint = SandboxArtifactFingerprint.from_content(record_content)
        record_id_raw = derive_identity(SandboxMaterializationId, record_fingerprint)
        record = SandboxMaterializationRecord(
            SandboxMaterializationId(record_id_raw.value),
            record_fingerprint,
            plan.materialization_plan_id,
            plan.materialization_plan_fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.workspace_id,
            expected_assets,
            observed_artifacts,
            completed,
            verification,
            SandboxCleanupState.NOT_REQUIRED,
            request.occurred_at,
        )
        return SandboxMaterializationResult(
            SandboxMaterializationResultOutcome.SUCCEEDED,
            plan,
            completed,
            verification,
            SandboxCleanupState.NOT_REQUIRED,
            record,
        )

    def _inspect_assets(
        self, plan: SandboxMaterializationPlan
    ) -> (
        tuple[tuple[OpaqueReference, SandboxArtifactFingerprint], ...]
        | SandboxMaterializationResult
    ):
        observed = []
        for asset in plan.artifact_inputs + plan.readonly_inputs + plan.runtime_assets:
            result = self._custody.inspect(
                SandboxArtifactInspectionRequest(
                    asset.source_ref,
                    asset.expected_fingerprint,
                )
            )
            if (
                result.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED
                or result.stale
                or result.observed_fingerprint != asset.expected_fingerprint
            ):
                outcome = (
                    SandboxMaterializationVerificationOutcome.STALE
                    if result.stale
                    else (
                        SandboxMaterializationVerificationOutcome.MISMATCH
                        if result.observed_fingerprint is not None
                        else self._verification_outcome(result.outcome)
                    )
                )
                verification = SandboxMaterializationVerification(
                    outcome,
                    plan.expected_workspace_fingerprint,
                    None,
                    self._safe_diagnostics(
                        result.diagnostic_codes,
                        f"artifact.{outcome.value}",
                    ),
                )
                return SandboxMaterializationResult(
                    SandboxMaterializationResultOutcome.FAILED,
                    plan,
                    (),
                    verification,
                    SandboxCleanupState.NOT_REQUIRED,
                    None,
                )
            assert result.observed_fingerprint is not None
            observed.append((asset.source_ref, result.observed_fingerprint))
        return tuple(sorted(observed, key=lambda item: item[0].value))

    def _partial_failure(
        self,
        plan: SandboxMaterializationPlan,
        steps: list[SandboxMaterializationStepRecord],
        observed: tuple[tuple[OpaqueReference, SandboxArtifactFingerprint], ...],
        original_outcome: SandboxMaterializationVerificationOutcome,
        observed_workspace: SandboxArtifactFingerprint | None,
    ) -> SandboxMaterializationResult:
        del observed
        cleanup = self._workspace.cleanup(
            SandboxWorkspaceCleanupRequest(
                plan.workspace_id,
                plan.materialization_plan_fingerprint,
            )
        )
        cleanup_step = SandboxMaterializationStepRecord(
            len(steps) + 1,
            SandboxMaterializationAction.CLEANUP_WORKSPACE,
            cleanup.outcome,
            None,
            self._safe_diagnostics(cleanup.diagnostic_codes, "cleanup.failed"),
        )
        completed = tuple((*steps, cleanup_step))
        if cleanup.outcome is SandboxMaterializationStepOutcome.SUCCEEDED:
            outcome = SandboxMaterializationVerificationOutcome.CLEANUP_REQUIRED
            cleanup_state = SandboxCleanupState.VERIFIED
        else:
            outcome = SandboxMaterializationVerificationOutcome.CLEANUP_FAILED
            cleanup_state = SandboxCleanupState.FAILED
        diagnostics = tuple(
            sorted(
                {
                    f"materialization.original_{original_outcome.value}",
                    *cleanup_step.diagnostic_codes,
                }
            )
        )
        verification = SandboxMaterializationVerification(
            outcome,
            plan.expected_workspace_fingerprint,
            observed_workspace,
            diagnostics,
        )
        return SandboxMaterializationResult(
            SandboxMaterializationResultOutcome.CLEANUP_REQUIRED,
            plan,
            completed,
            verification,
            cleanup_state,
            None,
        )

    @staticmethod
    def _failure_without_cleanup(
        plan: SandboxMaterializationPlan,
        steps: list[SandboxMaterializationStepRecord],
        outcome: SandboxMaterializationVerificationOutcome,
    ) -> SandboxMaterializationResult:
        verification = SandboxMaterializationVerification(
            outcome,
            plan.expected_workspace_fingerprint,
            None,
            tuple(sorted({code for step in steps for code in step.diagnostic_codes})),
        )
        return SandboxMaterializationResult(
            SandboxMaterializationResultOutcome.FAILED,
            plan,
            tuple(steps),
            verification,
            SandboxCleanupState.NOT_REQUIRED,
            None,
        )

    @staticmethod
    def _step(
        operation: SandboxMaterializationOperation,
        result: SandboxMaterializationStepResult,
    ) -> SandboxMaterializationStepRecord:
        return SandboxMaterializationStepRecord(
            operation.ordinal,
            operation.action,
            result.outcome,
            None,
            SandboxMaterializationApplicationService._safe_diagnostics(
                result.diagnostic_codes,
                f"materialization.{result.outcome.value}",
            ),
        )

    @staticmethod
    def _safe_diagnostics(
        codes: tuple[str, ...],
        fallback: str,
    ) -> tuple[str, ...]:
        if not codes:
            return ()
        safe = {
            code
            for code in codes
            if isinstance(code, str) and _SAFE_DIAGNOSTIC.fullmatch(code) is not None
        }
        return tuple(sorted(safe or {fallback}))

    @staticmethod
    def _verification_outcome(
        outcome: SandboxMaterializationStepOutcome,
    ) -> SandboxMaterializationVerificationOutcome:
        return {
            SandboxMaterializationStepOutcome.SUCCEEDED: SandboxMaterializationVerificationOutcome.INCOMPLETE,
            SandboxMaterializationStepOutcome.FAILED: SandboxMaterializationVerificationOutcome.INCOMPLETE,
            SandboxMaterializationStepOutcome.UNAVAILABLE: SandboxMaterializationVerificationOutcome.UNAVAILABLE,
            SandboxMaterializationStepOutcome.UNSUPPORTED: SandboxMaterializationVerificationOutcome.UNSUPPORTED,
        }[outcome]
