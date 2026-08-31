"""Pure final result and bounded evidence materialization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .admission_policy import (
    SandboxAdmissionDecision,
    SandboxAdmissionDecisionOutcome,
)
from .cancellation import (
    SandboxCancellationClassification,
    SandboxCancellationResult,
    SandboxCancellationState,
)
from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidResultMaterialization
from .execution_plan import SandboxExecutionPlan
from .filesystem_boundary import SandboxFilesystemSpecification
from .identities import (
    OpaqueReference,
    SandboxAdmissionId,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxCancellationResultId,
    SandboxEvidenceId,
    SandboxEvidencePolicyId,
    SandboxEvidenceProjectionId,
    SandboxExecutionResultId,
    SandboxMaterializationId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxSupervisionResultId,
    SandboxTerminationProofId,
    derive_identity,
)
from .materialization import SandboxMaterializationPlan, SandboxMaterializationRecord
from .network_boundary import SandboxNetworkSpecification
from .process_boundary import SandboxProcessSpecification
from .resource_limits import SandboxResourceSpecification
from .runtime_supervision import (
    SandboxExecutionAttempt,
    SandboxExitClassification,
    SandboxSupervisionResult,
    SandboxSupervisionState,
    SandboxTerminationProof,
)
from .secrets_boundary import SandboxSecretLeaseSpecification

RESULT_MATERIALIZATION_FORMAT = "sandbox-result-materialization-v1"
_CODE = re.compile(r"[a-z][a-z0-9_.-]{0,95}")
_SENSITIVE = ("secret=", "token=", "password=", "credential=", "private_key")


def _aware(value: datetime, code: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidResultMaterialization(code)


def _codes(values: tuple[str, ...], code: str) -> None:
    if values != tuple(sorted(set(values))) or any(
        _CODE.fullmatch(value) is None for value in values
    ):
        raise InvalidResultMaterialization(code)


def _safe_summary(value: str, maximum: int) -> None:
    encoded = value.encode("utf-8") if isinstance(value, str) else b""
    lowered = value.lower() if isinstance(value, str) else ""
    if not encoded or len(encoded) > maximum:
        raise InvalidResultMaterialization("evidence.summary_limit_exceeded")
    if any(marker in lowered for marker in _SENSITIVE):
        raise InvalidResultMaterialization("evidence.summary_sensitive")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
        raise InvalidResultMaterialization("evidence.summary_path_forbidden")


class SandboxEvidenceCategory(StrEnum):
    ADMISSION = "admission"
    PLAN = "plan"
    GRANTS = "grants"
    MATERIALIZATION = "materialization"
    RUNTIME_LIFECYCLE = "runtime_lifecycle"
    RESOURCE_USAGE = "resource_usage"
    FILESYSTEM_VIOLATIONS = "filesystem_violations"
    NETWORK_VIOLATIONS = "network_violations"
    PROCESS_VIOLATIONS = "process_violations"
    CANCELLATION_TIMEOUT = "cancellation_timeout"
    TERMINATION = "termination"
    CLEANUP_REQUIREMENT = "cleanup_requirement"
    DIAGNOSTICS = "diagnostics"


class SandboxEvidenceRedactionLevel(StrEnum):
    REDACTED = "redacted"
    METADATA_ONLY = "metadata_only"


class SandboxEvidenceDisclosureLevel(StrEnum):
    PRIVATE = "private"
    RESTRICTED = "restricted"
    AUDIT = "audit"


class SandboxEvidenceRetentionDisposition(StrEnum):
    EXPIRE = "expire"
    REVIEW = "review"


class SandboxExecutionResultOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
    POLICY_DENIED = "policy_denied"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    TERMINATION_UNVERIFIED = "termination_unverified"
    CLEANUP_REQUIRED = "cleanup_required"
    MANUAL_INTERVENTION = "manual_intervention"


class SandboxFunctionalResult(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"


class SandboxResultMaterializationStatus(StrEnum):
    MATERIALIZED = "materialized"
    INCOMPLETE = "incomplete"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    LIMIT_EXCEEDED = "limit_exceeded"
    REDACTION_FAILED = "redaction_failed"


@dataclass(frozen=True, slots=True)
class SandboxEvidenceRetention:
    retention_days: int
    disposition: SandboxEvidenceRetentionDisposition

    def __post_init__(self) -> None:
        if (
            not isinstance(self.retention_days, int)
            or isinstance(self.retention_days, bool)
            or self.retention_days <= 0
            or self.retention_days > 3650
        ):
            raise InvalidResultMaterialization("retention.days_invalid")


@dataclass(frozen=True, slots=True)
class SandboxEvidencePolicy:
    policy_id: SandboxEvidencePolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    version: SandboxPolicyVersion
    required_categories: tuple[SandboxEvidenceCategory, ...]
    max_items: int
    max_summary_bytes: int
    max_total_estimated_bytes: int
    max_diagnostics: int
    max_stdio_references: int
    allowed_disclosures: tuple[SandboxEvidenceDisclosureLevel, ...]
    retention: SandboxEvidenceRetention

    def semantic_content(self) -> tuple[object, ...]:
        return (
            RESULT_MATERIALIZATION_FORMAT,
            self.version,
            self.required_categories,
            self.max_items,
            self.max_summary_bytes,
            self.max_total_estimated_bytes,
            self.max_diagnostics,
            self.max_stdio_references,
            self.allowed_disclosures,
            self.retention,
        )

    def __post_init__(self) -> None:
        if self.required_categories != tuple(
            sorted(set(self.required_categories), key=lambda item: item.value)
        ):
            raise InvalidResultMaterialization("policy.categories_not_canonical")
        if self.allowed_disclosures != tuple(
            sorted(set(self.allowed_disclosures), key=lambda item: item.value)
        ) or not self.allowed_disclosures:
            raise InvalidResultMaterialization("policy.disclosures_not_canonical")
        for value, code, maximum in (
            (self.max_items, "policy.max_items_invalid", 1024),
            (self.max_summary_bytes, "policy.max_summary_invalid", 4096),
            (self.max_total_estimated_bytes, "policy.max_total_invalid", 1_048_576),
            (self.max_diagnostics, "policy.max_diagnostics_invalid", 1024),
            (self.max_stdio_references, "policy.max_stdio_invalid", 16),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
                or value > maximum
            ):
                raise InvalidResultMaterialization(code)
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.policy_fingerprint:
            raise InvalidResultMaterialization("policy.fingerprint_mismatch")
        if derive_identity(SandboxEvidencePolicyId, expected) != self.policy_id:
            raise InvalidResultMaterialization("policy.identity_mismatch")

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        required_categories: tuple[SandboxEvidenceCategory, ...],
        max_items: int,
        max_summary_bytes: int,
        max_total_estimated_bytes: int,
        max_diagnostics: int,
        max_stdio_references: int,
        allowed_disclosures: tuple[SandboxEvidenceDisclosureLevel, ...],
        retention: SandboxEvidenceRetention,
    ) -> SandboxEvidencePolicy:
        categories = tuple(sorted(set(required_categories), key=lambda item: item.value))
        disclosures = tuple(sorted(set(allowed_disclosures), key=lambda item: item.value))
        semantic = (
            RESULT_MATERIALIZATION_FORMAT,
            version,
            categories,
            max_items,
            max_summary_bytes,
            max_total_estimated_bytes,
            max_diagnostics,
            max_stdio_references,
            disclosures,
            retention,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxEvidencePolicyId, fingerprint)
        return cls(
            SandboxEvidencePolicyId(identity.value),
            fingerprint,
            version,
            categories,
            max_items,
            max_summary_bytes,
            max_total_estimated_bytes,
            max_diagnostics,
            max_stdio_references,
            disclosures,
            retention,
        )


@dataclass(frozen=True, slots=True)
class SandboxEvidenceItem:
    category: SandboxEvidenceCategory
    reference: OpaqueReference
    checksum: SandboxArtifactFingerprint
    summary: str
    estimated_bytes: int
    redaction: SandboxEvidenceRedactionLevel
    disclosure: SandboxEvidenceDisclosureLevel

    def __post_init__(self) -> None:
        _safe_summary(self.summary, 4096)
        if (
            not isinstance(self.estimated_bytes, int)
            or isinstance(self.estimated_bytes, bool)
            or self.estimated_bytes <= 0
            or self.estimated_bytes > 1_048_576
        ):
            raise InvalidResultMaterialization("evidence.estimated_bytes_invalid")


@dataclass(frozen=True, slots=True)
class SandboxEvidenceProjection:
    projection_id: SandboxEvidenceProjectionId
    projection_fingerprint: SandboxArtifactFingerprint
    categories: tuple[SandboxEvidenceCategory, ...]
    item_bindings: tuple[tuple[OpaqueReference, SandboxArtifactFingerprint], ...]
    item_count: int
    estimated_total_bytes: int

    def semantic_content(self) -> tuple[object, ...]:
        return (
            RESULT_MATERIALIZATION_FORMAT,
            self.categories,
            self.item_bindings,
            self.item_count,
            self.estimated_total_bytes,
        )

    def __post_init__(self) -> None:
        if self.categories != tuple(sorted(set(self.categories), key=lambda item: item.value)):
            raise InvalidResultMaterialization("projection.categories_not_canonical")
        if self.item_bindings != tuple(
            sorted(self.item_bindings, key=lambda item: item[0].value)
        ):
            raise InvalidResultMaterialization("projection.bindings_not_canonical")
        if self.item_count != len(self.item_bindings):
            raise InvalidResultMaterialization("projection.count_mismatch")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.projection_fingerprint:
            raise InvalidResultMaterialization("projection.fingerprint_mismatch")
        if derive_identity(SandboxEvidenceProjectionId, expected) != self.projection_id:
            raise InvalidResultMaterialization("projection.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    result_id: SandboxExecutionResultId
    result_fingerprint: SandboxArtifactFingerprint
    admission_decision_id: SandboxAdmissionId
    admission_decision_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    attempt_id: SandboxAttemptId
    attempt_fingerprint: SandboxArtifactFingerprint
    materialization_id: SandboxMaterializationId
    materialization_fingerprint: SandboxArtifactFingerprint
    supervision_result_id: SandboxSupervisionResultId
    supervision_result_fingerprint: SandboxArtifactFingerprint
    cancellation_result_id: SandboxCancellationResultId | None
    cancellation_result_fingerprint: SandboxArtifactFingerprint | None
    outcome: SandboxExecutionResultOutcome
    functional_result: SandboxFunctionalResult
    supervision_state: SandboxSupervisionState
    termination_proof_ref: SandboxTerminationProofId | None
    stdout_stderr_refs: tuple[OpaqueReference, ...]
    cleanup_required: bool
    diagnostics: tuple[str, ...]
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            RESULT_MATERIALIZATION_FORMAT,
            self.admission_decision_id,
            self.admission_decision_fingerprint,
            self.plan_id,
            self.plan_fingerprint,
            self.attempt_id,
            self.attempt_fingerprint,
            self.materialization_id,
            self.materialization_fingerprint,
            self.supervision_result_id,
            self.supervision_result_fingerprint,
            self.cancellation_result_id,
            self.cancellation_result_fingerprint,
            self.outcome,
            self.functional_result,
            self.supervision_state,
            self.termination_proof_ref,
            self.stdout_stderr_refs,
            self.cleanup_required,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "result.occurred_at_invalid")
        _codes(self.diagnostics, "result.diagnostics_not_canonical")
        if self.stdout_stderr_refs != tuple(
            sorted(set(self.stdout_stderr_refs), key=lambda item: item.value)
        ):
            raise InvalidResultMaterialization("result.stdio_references_not_canonical")
        if self.outcome is SandboxExecutionResultOutcome.SUCCEEDED and (
            self.functional_result is not SandboxFunctionalResult.SUCCEEDED
            or self.supervision_state is not SandboxSupervisionState.COMPLETED
            or self.termination_proof_ref is None
        ):
            raise InvalidResultMaterialization("result.succeeded_incompatible")
        if self.outcome is SandboxExecutionResultOutcome.TERMINATION_UNVERIFIED and self.functional_result is SandboxFunctionalResult.SUCCEEDED:
            raise InvalidResultMaterialization("result.unverified_cannot_succeed")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.result_fingerprint:
            raise InvalidResultMaterialization("result.fingerprint_mismatch")
        if derive_identity(SandboxExecutionResultId, expected) != self.result_id:
            raise InvalidResultMaterialization("result.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxEvidenceBundle:
    evidence_id: SandboxEvidenceId
    evidence_fingerprint: SandboxArtifactFingerprint
    result_id: SandboxExecutionResultId
    result_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxEvidencePolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    projection_id: SandboxEvidenceProjectionId
    projection_fingerprint: SandboxArtifactFingerprint
    items: tuple[SandboxEvidenceItem, ...]
    retention: SandboxEvidenceRetention
    occurred_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            RESULT_MATERIALIZATION_FORMAT,
            self.result_id,
            self.result_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.projection_id,
            self.projection_fingerprint,
            self.items,
            self.retention,
        )

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "bundle.occurred_at_invalid")
        if self.items != tuple(
            sorted(self.items, key=lambda item: (item.category.value, item.reference.value))
        ):
            raise InvalidResultMaterialization("bundle.items_not_canonical")
        expected = SandboxArtifactFingerprint.from_content(self.semantic_content())
        if expected != self.evidence_fingerprint:
            raise InvalidResultMaterialization("bundle.fingerprint_mismatch")
        if derive_identity(SandboxEvidenceId, expected) != self.evidence_id:
            raise InvalidResultMaterialization("bundle.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxResultMaterializationRequest:
    admission: SandboxAdmissionDecision
    plan: SandboxExecutionPlan
    capabilities: SandboxCapabilityGrantSet
    filesystem: SandboxFilesystemSpecification
    network: SandboxNetworkSpecification
    process: SandboxProcessSpecification
    resources: SandboxResourceSpecification
    secrets: SandboxSecretLeaseSpecification | None
    materialization_plan: SandboxMaterializationPlan
    materialization: SandboxMaterializationRecord
    attempt: SandboxExecutionAttempt
    supervision: SandboxSupervisionResult
    cancellation: SandboxCancellationResult | None
    termination_proof: SandboxTerminationProof | None
    evidence_policy: SandboxEvidencePolicy
    evidence_items: tuple[SandboxEvidenceItem, ...]
    stdout_stderr_refs: tuple[OpaqueReference, ...]
    occurred_at: datetime

    def __post_init__(self) -> None:
        _aware(self.occurred_at, "request.occurred_at_invalid")


@dataclass(frozen=True, slots=True)
class SandboxResultMaterializationOutcome:
    status: SandboxResultMaterializationStatus
    result: SandboxExecutionResult | None
    bundle: SandboxEvidenceBundle | None
    projection: SandboxEvidenceProjection | None
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        _codes(self.diagnostics, "outcome.diagnostics_not_canonical")
        complete = self.result is not None and self.bundle is not None and self.projection is not None
        if (self.status is SandboxResultMaterializationStatus.MATERIALIZED) != complete:
            raise InvalidResultMaterialization("outcome.artifact_conflict")


class SandboxResultMaterializationService:
    @classmethod
    def materialize(
        cls, request: SandboxResultMaterializationRequest
    ) -> SandboxResultMaterializationOutcome:
        diagnostics = cls._binding_diagnostics(request)
        if diagnostics:
            return SandboxResultMaterializationOutcome(
                SandboxResultMaterializationStatus.MISMATCH,
                None,
                None,
                None,
                tuple(sorted(diagnostics)),
            )
        try:
            items = cls._validate_items(request)
        except InvalidResultMaterialization as error:
            if "evidence.required_category_absent" in error.diagnostics:
                status = (
                    SandboxResultMaterializationStatus.UNAVAILABLE
                    if not request.evidence_items
                    else SandboxResultMaterializationStatus.INCOMPLETE
                )
            elif any(
                "sensitive" in item or "path" in item for item in error.diagnostics
            ):
                status = SandboxResultMaterializationStatus.REDACTION_FAILED
            else:
                status = SandboxResultMaterializationStatus.LIMIT_EXCEEDED
            return SandboxResultMaterializationOutcome(
                status, None, None, None, tuple(sorted(error.diagnostics))
            )
        mapped = cls._map_outcome(request)
        if mapped is None:
            return SandboxResultMaterializationOutcome(
                SandboxResultMaterializationStatus.INCOMPLETE,
                None,
                None,
                None,
                ("result.supervision_incomplete",),
            )
        outcome, functional = mapped
        proof_ref = (
            request.termination_proof.proof_id
            if request.termination_proof is not None
            else None
        )
        cancellation_id = request.cancellation.result_id if request.cancellation else None
        cancellation_fp = (
            request.cancellation.result_fingerprint if request.cancellation else None
        )
        result_diagnostics = tuple(
            sorted(
                set(request.supervision.diagnostics)
                | (set(request.cancellation.diagnostics) if request.cancellation else set())
            )
        )
        if len(result_diagnostics) > request.evidence_policy.max_diagnostics:
            return SandboxResultMaterializationOutcome(
                SandboxResultMaterializationStatus.LIMIT_EXCEEDED,
                None,
                None,
                None,
                ("result.diagnostics_limit_exceeded",),
            )
        cleanup_required = request.supervision.cleanup_required or (
            request.cancellation.cleanup_required if request.cancellation else False
        )
        stdio_references = tuple(
            sorted(request.stdout_stderr_refs, key=lambda item: item.value)
        )
        semantic = (
            RESULT_MATERIALIZATION_FORMAT,
            request.admission.decision_id,
            request.admission.decision_fingerprint,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.attempt.attempt_id,
            request.attempt.attempt_fingerprint,
            request.materialization.materialization_id,
            request.materialization.materialization_fingerprint,
            request.supervision.result_id,
            request.supervision.result_fingerprint,
            cancellation_id,
            cancellation_fp,
            outcome,
            functional,
            request.supervision.final_state,
            proof_ref,
            stdio_references,
            cleanup_required,
            result_diagnostics,
        )
        result_fp = SandboxArtifactFingerprint.from_content(semantic)
        result_id = derive_identity(SandboxExecutionResultId, result_fp)
        result = SandboxExecutionResult(
            SandboxExecutionResultId(result_id.value),
            result_fp,
            request.admission.decision_id,
            request.admission.decision_fingerprint,
            request.plan.plan_id,
            request.plan.plan_fingerprint,
            request.attempt.attempt_id,
            request.attempt.attempt_fingerprint,
            request.materialization.materialization_id,
            request.materialization.materialization_fingerprint,
            request.supervision.result_id,
            request.supervision.result_fingerprint,
            cancellation_id,
            cancellation_fp,
            outcome,
            functional,
            request.supervision.final_state,
            proof_ref,
            stdio_references,
            cleanup_required,
            result_diagnostics,
            request.occurred_at,
        )
        projection = cls._projection(items)
        bundle_semantic = (
            RESULT_MATERIALIZATION_FORMAT,
            result.result_id,
            result.result_fingerprint,
            request.evidence_policy.policy_id,
            request.evidence_policy.policy_fingerprint,
            projection.projection_id,
            projection.projection_fingerprint,
            items,
            request.evidence_policy.retention,
        )
        bundle_fp = SandboxArtifactFingerprint.from_content(bundle_semantic)
        bundle_id = derive_identity(SandboxEvidenceId, bundle_fp)
        bundle = SandboxEvidenceBundle(
            SandboxEvidenceId(bundle_id.value),
            bundle_fp,
            result.result_id,
            result.result_fingerprint,
            request.evidence_policy.policy_id,
            request.evidence_policy.policy_fingerprint,
            projection.projection_id,
            projection.projection_fingerprint,
            items,
            request.evidence_policy.retention,
            request.occurred_at,
        )
        return SandboxResultMaterializationOutcome(
            SandboxResultMaterializationStatus.MATERIALIZED,
            result,
            bundle,
            projection,
            (),
        )

    @staticmethod
    def _binding_diagnostics(request: SandboxResultMaterializationRequest) -> set[str]:
        diagnostics: set[str] = set()
        plan = request.plan
        if request.admission.outcome is not SandboxAdmissionDecisionOutcome.ADMITTED:
            diagnostics.add("binding.admission_not_admitted")
        if plan.decision_id != request.admission.decision_id or plan.decision_fingerprint != request.admission.decision_fingerprint:
            diagnostics.add("binding.admission_plan_mismatch")
        for name, candidate_id, candidate_fp in (
            ("capabilities", request.capabilities.plan_id, request.capabilities.plan_fingerprint),
            ("filesystem", request.filesystem.plan_id, request.filesystem.plan_fingerprint),
            ("network", request.network.plan_id, request.network.plan_fingerprint),
            ("process", request.process.plan_id, request.process.plan_fingerprint),
            ("resources", request.resources.plan_id, request.resources.plan_fingerprint),
            ("materialization", request.materialization.plan_id, request.materialization.plan_fingerprint),
            ("attempt", request.attempt.plan_id, request.attempt.plan_fingerprint),
            ("supervision", request.supervision.plan_id, request.supervision.plan_fingerprint),
        ):
            if candidate_id != plan.plan_id:
                diagnostics.add(f"binding.{name}_plan_identity_mismatch")
            if candidate_fp != plan.plan_fingerprint:
                diagnostics.add(f"binding.{name}_plan_fingerprint_mismatch")
        if request.materialization.materialization_plan_id != request.materialization_plan.materialization_plan_id or request.materialization.materialization_plan_fingerprint != request.materialization_plan.materialization_plan_fingerprint:
            diagnostics.add("binding.materialization_plan_mismatch")
        for name, actual, expected in (
            (
                "capabilities",
                request.capabilities.grant_set_fingerprint,
                request.materialization_plan.capability_grant_set_fingerprint,
            ),
            (
                "filesystem",
                request.filesystem.specification_fingerprint,
                request.materialization_plan.filesystem_specification_fingerprint,
            ),
            (
                "network",
                request.network.specification_fingerprint,
                request.materialization_plan.network_specification_fingerprint,
            ),
            (
                "process",
                request.process.specification_fingerprint,
                request.materialization_plan.process_specification_fingerprint,
            ),
            (
                "resources",
                request.resources.specification_fingerprint,
                request.materialization_plan.resource_specification_fingerprint,
            ),
            (
                "secrets",
                request.secrets.specification_fingerprint if request.secrets else None,
                request.materialization_plan.secret_specification_fingerprint,
            ),
        ):
            if actual != expected:
                diagnostics.add(f"binding.materialized_{name}_mismatch")
        if (
            request.process.filesystem_specification_fingerprint
            != request.filesystem.specification_fingerprint
        ):
            diagnostics.add("binding.process_filesystem_mismatch")
        if (
            request.process.network_specification_fingerprint
            != request.network.specification_fingerprint
        ):
            diagnostics.add("binding.process_network_mismatch")
        if (
            request.resources.process_specification_fingerprint
            != request.process.specification_fingerprint
        ):
            diagnostics.add("binding.resources_process_mismatch")
        if request.secrets is not None and (
            request.secrets.plan_id != plan.plan_id
            or request.secrets.resource_specification_fingerprint
            != request.resources.specification_fingerprint
        ):
            diagnostics.add("binding.secrets_mismatch")
        if request.attempt.materialization_id != request.materialization.materialization_id or request.attempt.materialization_fingerprint != request.materialization.materialization_fingerprint:
            diagnostics.add("binding.attempt_materialization_mismatch")
        if request.supervision.attempt_id != request.attempt.attempt_id:
            diagnostics.add("binding.supervision_attempt_mismatch")
        if request.cancellation is not None and (
            request.cancellation.attempt_id != request.attempt.attempt_id
            or request.cancellation.attempt_fingerprint != request.attempt.attempt_fingerprint
        ):
            diagnostics.add("binding.cancellation_attempt_mismatch")
        if (
            request.cancellation is not None
            and request.cancellation.termination_proof_ref is not None
            and request.supervision.termination_proof_ref is not None
            and request.cancellation.termination_proof_ref
            != request.supervision.termination_proof_ref
        ):
            diagnostics.add("binding.termination_proof_conflict")
        expected_proof = request.supervision.termination_proof_ref
        if request.cancellation is not None and request.cancellation.termination_proof_ref is not None:
            expected_proof = request.cancellation.termination_proof_ref
        if expected_proof is not None and (
            request.termination_proof is None
            or request.termination_proof.proof_id != expected_proof
            or request.termination_proof.attempt_id != request.attempt.attempt_id
        ):
            diagnostics.add("binding.termination_proof_mismatch")
        if expected_proof is None and request.termination_proof is not None:
            diagnostics.add("binding.termination_proof_unexpected")
        return diagnostics

    @staticmethod
    def _validate_items(
        request: SandboxResultMaterializationRequest,
    ) -> tuple[SandboxEvidenceItem, ...]:
        items = tuple(
            sorted(request.evidence_items, key=lambda item: (item.category.value, item.reference.value))
        )
        policy = request.evidence_policy
        if len(items) > policy.max_items:
            raise InvalidResultMaterialization("evidence.item_limit_exceeded")
        if len(request.stdout_stderr_refs) > policy.max_stdio_references:
            raise InvalidResultMaterialization("evidence.stdio_limit_exceeded")
        if len(set(request.stdout_stderr_refs)) != len(request.stdout_stderr_refs):
            raise InvalidResultMaterialization("evidence.stdio_duplicate")
        if len({item.reference for item in items}) != len(items):
            raise InvalidResultMaterialization("evidence.reference_duplicate")
        categories = {item.category for item in items}
        dynamically_required: set[SandboxEvidenceCategory] = set()
        if request.cancellation is not None:
            dynamically_required.add(SandboxEvidenceCategory.CANCELLATION_TIMEOUT)
        if request.supervision.cleanup_required or (
            request.cancellation is not None and request.cancellation.cleanup_required
        ):
            dynamically_required.add(SandboxEvidenceCategory.CLEANUP_REQUIREMENT)
        if request.supervision.resource_usage:
            dynamically_required.add(SandboxEvidenceCategory.RESOURCE_USAGE)
        if request.supervision.diagnostics or (
            request.cancellation is not None and request.cancellation.diagnostics
        ):
            dynamically_required.add(SandboxEvidenceCategory.DIAGNOSTICS)
        for violation in request.supervision.violations:
            if violation.startswith("filesystem."):
                dynamically_required.add(SandboxEvidenceCategory.FILESYSTEM_VIOLATIONS)
            elif violation.startswith("network."):
                dynamically_required.add(SandboxEvidenceCategory.NETWORK_VIOLATIONS)
            elif violation.startswith(("process.", "isolation.", "descendant.")):
                dynamically_required.add(SandboxEvidenceCategory.PROCESS_VIOLATIONS)
        if not (set(policy.required_categories) | dynamically_required).issubset(categories):
            raise InvalidResultMaterialization("evidence.required_category_absent")
        total = 0
        for item in items:
            _safe_summary(item.summary, policy.max_summary_bytes)
            if item.disclosure not in policy.allowed_disclosures:
                raise InvalidResultMaterialization("evidence.disclosure_denied")
            total += item.estimated_bytes
        if total > policy.max_total_estimated_bytes:
            raise InvalidResultMaterialization("evidence.total_limit_exceeded")
        return items

    @staticmethod
    def _projection(items: tuple[SandboxEvidenceItem, ...]) -> SandboxEvidenceProjection:
        categories = tuple(sorted({item.category for item in items}, key=lambda item: item.value))
        bindings = tuple(sorted(((item.reference, item.checksum) for item in items), key=lambda item: item[0].value))
        total = sum(item.estimated_bytes for item in items)
        semantic = (RESULT_MATERIALIZATION_FORMAT, categories, bindings, len(items), total)
        fingerprint = SandboxArtifactFingerprint.from_content(semantic)
        identity = derive_identity(SandboxEvidenceProjectionId, fingerprint)
        return SandboxEvidenceProjection(
            SandboxEvidenceProjectionId(identity.value), fingerprint, categories, bindings, len(items), total
        )

    @staticmethod
    def _map_outcome(
        request: SandboxResultMaterializationRequest,
    ) -> tuple[SandboxExecutionResultOutcome, SandboxFunctionalResult] | None:
        supervision = request.supervision
        cancellation = request.cancellation
        if cancellation is not None:
            if cancellation.final_state is SandboxCancellationState.MANUAL_INTERVENTION:
                return SandboxExecutionResultOutcome.MANUAL_INTERVENTION, SandboxFunctionalResult.NOT_AVAILABLE
            if cancellation.final_state is SandboxCancellationState.TERMINATION_UNVERIFIED:
                return SandboxExecutionResultOutcome.TERMINATION_UNVERIFIED, SandboxFunctionalResult.NOT_AVAILABLE
            if cancellation.final_state is not SandboxCancellationState.COMPLETED:
                return None
            if cancellation.classification in {
                SandboxCancellationClassification.STARTUP_TIMEOUT,
                SandboxCancellationClassification.IDLE_TIMEOUT,
                SandboxCancellationClassification.WALL_CLOCK_TIMEOUT,
                SandboxCancellationClassification.TERMINATION_GRACE_TIMEOUT,
                SandboxCancellationClassification.CLEANUP_TIMEOUT,
            }:
                return SandboxExecutionResultOutcome.TIMED_OUT, SandboxFunctionalResult.NOT_AVAILABLE
            return SandboxExecutionResultOutcome.CANCELLED, SandboxFunctionalResult.NOT_AVAILABLE
        mapping = {
            SandboxSupervisionState.FAILED: (
                SandboxExecutionResultOutcome.INFRASTRUCTURE_FAILED,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
            SandboxSupervisionState.TIMED_OUT: (
                SandboxExecutionResultOutcome.TIMED_OUT,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
            SandboxSupervisionState.CANCELLED: (
                SandboxExecutionResultOutcome.CANCELLED,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
            SandboxSupervisionState.TERMINATED: (
                SandboxExecutionResultOutcome.TERMINATED,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
            SandboxSupervisionState.TERMINATION_UNVERIFIED: (
                SandboxExecutionResultOutcome.TERMINATION_UNVERIFIED,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
            SandboxSupervisionState.CLEANUP_REQUIRED: (
                SandboxExecutionResultOutcome.CLEANUP_REQUIRED,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
            SandboxSupervisionState.MANUAL_INTERVENTION: (
                SandboxExecutionResultOutcome.MANUAL_INTERVENTION,
                SandboxFunctionalResult.NOT_AVAILABLE,
            ),
        }
        if supervision.final_state is SandboxSupervisionState.COMPLETED:
            if supervision.exit_classification is SandboxExitClassification.SUCCEEDED:
                return SandboxExecutionResultOutcome.SUCCEEDED, SandboxFunctionalResult.SUCCEEDED
            return SandboxExecutionResultOutcome.FAILED, SandboxFunctionalResult.FAILED
        return mapping.get(supervision.final_state)
