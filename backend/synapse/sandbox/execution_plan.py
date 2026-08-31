"""Canonical structural execution plan; no authorization or execution semantics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .admission_policy import (
    SandboxAdmissionDecision,
    SandboxAdmissionDecisionOutcome,
    SandboxAdmissionPolicy,
)
from .assessment import SandboxAdmissionFactsAssessment
from .errors import InvalidExecutionPlan
from .facts import SandboxAdmissionFactsSnapshot
from .identities import (
    OpaqueReference,
    SandboxAdmissionId,
    SandboxAdmissionPolicyId,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxWorkloadId,
    derive_identity,
)
from .models import (
    RequestedCapability,
    ResourceLimit,
    ResourceRequest,
    SandboxAdmissionRequest,
)

EXECUTION_PLAN_FORMAT = "sandbox-execution-plan-v1"
_LOGICAL_NAME = re.compile(r"^[a-z][a-z0-9_.:@-]{0,127}$")
_RUNTIME_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")


class SandboxRuntimeKind(StrEnum):
    PYTHON = "python"
    WASM = "wasm"


class SandboxRetentionKind(StrEnum):
    NONE = "none"
    BOUNDED = "bounded"


@dataclass(frozen=True, slots=True)
class SandboxRuntimeDescriptor:
    kind: SandboxRuntimeKind
    version: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SandboxRuntimeKind):
            raise InvalidExecutionPlan(("runtime.kind_unsupported",))
        if not _RUNTIME_VERSION.fullmatch(self.version):
            raise InvalidExecutionPlan(("runtime.version_invalid",))


@dataclass(frozen=True, slots=True)
class SandboxLogicalEntrypoint:
    value: str

    def __post_init__(self) -> None:
        if not _LOGICAL_NAME.fullmatch(self.value):
            raise InvalidExecutionPlan(("entrypoint.logical_name_invalid",))


@dataclass(frozen=True, slots=True)
class SandboxExternalCapabilityReference:
    capability: str
    reference: OpaqueReference

    def __post_init__(self) -> None:
        if not _LOGICAL_NAME.fullmatch(self.capability):
            raise InvalidExecutionPlan(("capability.reference_invalid",))


@dataclass(frozen=True, slots=True)
class SandboxExternalResourceReference:
    resource: str
    reference: OpaqueReference

    def __post_init__(self) -> None:
        if not _LOGICAL_NAME.fullmatch(self.resource):
            raise InvalidExecutionPlan(("resource.reference_invalid",))


@dataclass(frozen=True, slots=True)
class SandboxEvidenceRequirement:
    evidence_ref: OpaqueReference
    required: bool


@dataclass(frozen=True, slots=True)
class SandboxRetentionRequirement:
    kind: SandboxRetentionKind
    maximum_days: int | None

    def __post_init__(self) -> None:
        if self.kind is SandboxRetentionKind.NONE and self.maximum_days is not None:
            raise InvalidExecutionPlan(("retention.none_has_limit",))
        if self.kind is SandboxRetentionKind.BOUNDED and (
            not isinstance(self.maximum_days, int)
            or isinstance(self.maximum_days, bool)
            or not 1 <= self.maximum_days <= 3650
        ):
            raise InvalidExecutionPlan(("retention.limit_invalid",))


@dataclass(frozen=True, slots=True)
class SandboxExecutionPlanSpecification:
    handoff_ref: OpaqueReference
    handoff_fingerprint: SandboxArtifactFingerprint
    artifact_ref: OpaqueReference
    artifact_fingerprint: SandboxArtifactFingerprint
    runtime: SandboxRuntimeDescriptor
    entrypoint: SandboxLogicalEntrypoint
    requested_capabilities: tuple[RequestedCapability, ...]
    requested_resources: tuple[ResourceRequest, ...]
    external_capability_refs: tuple[SandboxExternalCapabilityReference, ...]
    external_resource_refs: tuple[SandboxExternalResourceReference, ...]
    isolation_profile_id: SandboxIsolationProfileId
    resource_limits: tuple[ResourceLimit, ...]
    evidence_requirements: tuple[SandboxEvidenceRequirement, ...]
    retention_requirement: SandboxRetentionRequirement
    correlation_ref: OpaqueReference
    purpose: str


@dataclass(frozen=True, slots=True)
class SandboxPlanDiagnostic:
    code: str


@dataclass(frozen=True, slots=True)
class SandboxExecutionPlan:
    format_version: str
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    workload_id: SandboxWorkloadId
    subject: OpaqueReference
    request_fingerprint: SandboxArtifactFingerprint
    snapshot_fingerprint: SandboxArtifactFingerprint
    assessment_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxAdmissionPolicyId
    policy_version: SandboxPolicyVersion
    policy_fingerprint: SandboxArtifactFingerprint
    decision_id: SandboxAdmissionId
    decision_fingerprint: SandboxArtifactFingerprint
    handoff_ref: OpaqueReference
    handoff_fingerprint: SandboxArtifactFingerprint
    artifact_ref: OpaqueReference
    artifact_fingerprint: SandboxArtifactFingerprint
    runtime: SandboxRuntimeDescriptor
    entrypoint: SandboxLogicalEntrypoint
    requested_capabilities: tuple[RequestedCapability, ...]
    requested_resources: tuple[ResourceRequest, ...]
    external_capability_refs: tuple[SandboxExternalCapabilityReference, ...]
    external_resource_refs: tuple[SandboxExternalResourceReference, ...]
    isolation_profile_id: SandboxIsolationProfileId
    resource_limits: tuple[ResourceLimit, ...]
    evidence_requirements: tuple[SandboxEvidenceRequirement, ...]
    retention_requirement: SandboxRetentionRequirement
    correlation_ref: OpaqueReference
    purpose: str
    execution_profile: OpaqueReference
    diagnostics: tuple[SandboxPlanDiagnostic, ...]
    created_at: datetime

    def semantic_content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.workload_id,
            self.subject,
            self.request_fingerprint,
            self.snapshot_fingerprint,
            self.assessment_fingerprint,
            self.policy_id,
            self.policy_version,
            self.policy_fingerprint,
            self.decision_id,
            self.decision_fingerprint,
            self.handoff_ref,
            self.handoff_fingerprint,
            self.artifact_ref,
            self.artifact_fingerprint,
            self.runtime,
            self.entrypoint,
            self.requested_capabilities,
            self.requested_resources,
            self.external_capability_refs,
            self.external_resource_refs,
            self.isolation_profile_id,
            self.resource_limits,
            self.evidence_requirements,
            self.retention_requirement,
            self.correlation_ref,
            self.purpose,
            self.execution_profile,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        if self.format_version != EXECUTION_PLAN_FORMAT:
            raise InvalidExecutionPlan(("plan.format_unsupported",))
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise InvalidExecutionPlan(("plan.created_at_invalid",))
        expected_fingerprint = SandboxPlanFingerprint.from_content(self.semantic_content())
        if self.plan_fingerprint != expected_fingerprint:
            raise InvalidExecutionPlan(("plan.fingerprint_mismatch",))
        expected_id = derive_identity(SandboxPlanId, self.plan_fingerprint)
        if self.plan_id != expected_id:
            raise InvalidExecutionPlan(("plan.identity_mismatch",))


class SandboxExecutionPlanService:
    """Build and validate a structural plan from an admitted decision."""

    def build(
        self,
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        assessment: SandboxAdmissionFactsAssessment,
        policy: SandboxAdmissionPolicy,
        decision: SandboxAdmissionDecision,
        specification: SandboxExecutionPlanSpecification,
        *,
        created_at: datetime,
    ) -> SandboxExecutionPlan:
        diagnostics = self._validate_bindings(request, snapshot, assessment, policy, decision)
        diagnostics.extend(self._validate_specification(request, snapshot, specification))
        ordered_diagnostics = tuple(sorted(set(diagnostics)))
        if ordered_diagnostics:
            raise InvalidExecutionPlan(ordered_diagnostics)

        requested_capabilities = tuple(
            sorted(specification.requested_capabilities, key=lambda item: item.name)
        )
        requested_resources = tuple(
            sorted(
                specification.requested_resources,
                key=lambda item: (item.resource, item.unit, item.amount),
            )
        )
        capability_refs = tuple(
            sorted(
                specification.external_capability_refs,
                key=lambda item: (item.capability, item.reference.value),
            )
        )
        resource_refs = tuple(
            sorted(
                specification.external_resource_refs,
                key=lambda item: (item.resource, item.reference.value),
            )
        )
        resource_limits = tuple(
            sorted(
                specification.resource_limits,
                key=lambda item: (item.resource, item.unit, item.maximum),
            )
        )
        evidence = tuple(
            sorted(
                specification.evidence_requirements,
                key=lambda item: (item.evidence_ref.value, item.required),
            )
        )
        plan_diagnostics: tuple[SandboxPlanDiagnostic, ...] = ()
        request_fingerprint = SandboxArtifactFingerprint.from_content(request)
        semantic_content: tuple[object, ...] = (
            EXECUTION_PLAN_FORMAT,
            request.workload_id,
            request.subject,
            request_fingerprint,
            snapshot.snapshot_fingerprint,
            assessment.assessment_fingerprint,
            policy.policy_id,
            policy.version,
            policy.policy_fingerprint,
            decision.decision_id,
            decision.decision_fingerprint,
            specification.handoff_ref,
            specification.handoff_fingerprint,
            specification.artifact_ref,
            specification.artifact_fingerprint,
            specification.runtime,
            specification.entrypoint,
            requested_capabilities,
            requested_resources,
            capability_refs,
            resource_refs,
            specification.isolation_profile_id,
            resource_limits,
            evidence,
            specification.retention_requirement,
            specification.correlation_ref,
            specification.purpose,
            request.execution_profile,
            plan_diagnostics,
        )
        fingerprint = SandboxPlanFingerprint.from_content(semantic_content)
        plan_id = derive_identity(SandboxPlanId, fingerprint)
        return SandboxExecutionPlan(
            format_version=EXECUTION_PLAN_FORMAT,
            plan_id=SandboxPlanId(plan_id.value),
            plan_fingerprint=fingerprint,
            workload_id=request.workload_id,
            subject=request.subject,
            request_fingerprint=request_fingerprint,
            snapshot_fingerprint=snapshot.snapshot_fingerprint,
            assessment_fingerprint=assessment.assessment_fingerprint,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            policy_fingerprint=policy.policy_fingerprint,
            decision_id=decision.decision_id,
            decision_fingerprint=decision.decision_fingerprint,
            handoff_ref=specification.handoff_ref,
            handoff_fingerprint=specification.handoff_fingerprint,
            artifact_ref=specification.artifact_ref,
            artifact_fingerprint=specification.artifact_fingerprint,
            runtime=specification.runtime,
            entrypoint=specification.entrypoint,
            requested_capabilities=requested_capabilities,
            requested_resources=requested_resources,
            external_capability_refs=capability_refs,
            external_resource_refs=resource_refs,
            isolation_profile_id=specification.isolation_profile_id,
            resource_limits=resource_limits,
            evidence_requirements=evidence,
            retention_requirement=specification.retention_requirement,
            correlation_ref=specification.correlation_ref,
            purpose=specification.purpose,
            execution_profile=request.execution_profile,
            diagnostics=plan_diagnostics,
            created_at=created_at,
        )

    @staticmethod
    def _validate_bindings(
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        assessment: SandboxAdmissionFactsAssessment,
        policy: SandboxAdmissionPolicy,
        decision: SandboxAdmissionDecision,
    ) -> list[str]:
        diagnostics: list[str] = []
        request_fingerprint = SandboxArtifactFingerprint.from_content(request)
        if decision.outcome is not SandboxAdmissionDecisionOutcome.ADMITTED:
            diagnostics.append("decision.not_admitted")
        if assessment.request_fingerprint != request_fingerprint:
            diagnostics.append("assessment.request_mismatch")
        if assessment.snapshot_fingerprint != snapshot.snapshot_fingerprint:
            diagnostics.append("assessment.snapshot_mismatch")
        if decision.request_fingerprint != request_fingerprint:
            diagnostics.append("decision.request_mismatch")
        if decision.assessment_fingerprint != assessment.assessment_fingerprint:
            diagnostics.append("decision.assessment_mismatch")
        if decision.policy_id != policy.policy_id:
            diagnostics.append("decision.policy_identity_mismatch")
        if decision.policy_fingerprint != policy.policy_fingerprint:
            diagnostics.append("decision.policy_fingerprint_mismatch")
        return diagnostics

    @staticmethod
    def _validate_specification(
        request: SandboxAdmissionRequest,
        snapshot: SandboxAdmissionFactsSnapshot,
        specification: SandboxExecutionPlanSpecification,
    ) -> list[str]:
        diagnostics: list[str] = []
        if specification.handoff_fingerprint != request.handoff_fingerprint:
            diagnostics.append("specification.handoff_mismatch")
        if set(specification.requested_capabilities) != set(request.requested_capabilities):
            diagnostics.append("specification.capabilities_mismatch")
        if set(specification.requested_resources) != set(request.requested_resources):
            diagnostics.append("specification.resources_mismatch")
        if specification.isolation_profile_id != request.isolation_profile_id:
            diagnostics.append("specification.isolation_mismatch")
        if specification.correlation_ref != request.correlation_ref:
            diagnostics.append("specification.correlation_mismatch")
        if specification.purpose != request.purpose:
            diagnostics.append("specification.purpose_mismatch")
        artifact_facts = set(snapshot.artifact_facts)
        if len(artifact_facts) != 1:
            diagnostics.append("specification.artifact_fact_ambiguous")
        elif (
            specification.artifact_ref != next(iter(artifact_facts)).artifact_ref
            or specification.artifact_fingerprint != next(iter(artifact_facts)).fingerprint
        ):
            diagnostics.append("specification.artifact_mismatch")

        requested_capabilities = {item.name for item in request.requested_capabilities}
        referenced_capabilities = {
            item.capability for item in specification.external_capability_refs
        }
        if len(referenced_capabilities) != len(specification.external_capability_refs):
            diagnostics.append("specification.capability_references_conflict")
        if not referenced_capabilities <= requested_capabilities:
            diagnostics.append("specification.capability_reference_unrequested")
        expected_capability_refs = {
            (fact.declaration.name, fact.external_grant_ref)
            for fact in snapshot.capability_facts
            if fact.external_grant_ref is not None
        }
        supplied_capability_refs = {
            (item.capability, item.reference) for item in specification.external_capability_refs
        }
        if supplied_capability_refs != expected_capability_refs:
            diagnostics.append("specification.capability_references_mismatch")

        requested_resources = {item.resource: item for item in request.requested_resources}
        referenced_resources = {item.resource for item in specification.external_resource_refs}
        if len(referenced_resources) != len(specification.external_resource_refs):
            diagnostics.append("specification.resource_references_conflict")
        if not referenced_resources <= set(requested_resources):
            diagnostics.append("specification.resource_reference_unrequested")
        expected_resource_refs = {
            (fact.limit.resource, fact.external_grant_ref) for fact in snapshot.resource_facts
        }
        supplied_resource_refs = {
            (item.resource, item.reference) for item in specification.external_resource_refs
        }
        if supplied_resource_refs != expected_resource_refs:
            diagnostics.append("specification.resource_references_mismatch")

        limits = {item.resource: item for item in specification.resource_limits}
        if len(limits) != len(specification.resource_limits):
            diagnostics.append("specification.resource_limits_conflict")
        for resource, requested in requested_resources.items():
            limit = limits.get(resource)
            if limit is None or limit.unit != requested.unit or limit.maximum < requested.amount:
                diagnostics.append("specification.resource_limit_invalid")
        expected_evidence = {(fact.evidence_ref, fact.required) for fact in snapshot.evidence_facts}
        supplied_evidence = {
            (item.evidence_ref, item.required) for item in specification.evidence_requirements
        }
        if supplied_evidence != expected_evidence:
            diagnostics.append("specification.evidence_requirements_mismatch")
        return diagnostics
