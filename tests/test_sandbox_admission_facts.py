from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from synapse.sandbox import (
    AdmissionFactDimension,
    AdmissionFactsOutcome,
    ArtifactAvailability,
    CapabilityDeclaration,
    DimensionCompleteness,
    FactCompleteness,
    FactCorrespondence,
    FactFreshness,
    HandoffReadiness,
    InvalidAdmissionFacts,
    OpaqueReference,
    RequestedCapability,
    ResourceLimit,
    ResourceRequest,
    SandboxAdmissionFactsAssessmentService,
    SandboxAdmissionFactsSnapshot,
    SandboxAdmissionRequest,
    SandboxApprovalFact,
    SandboxArtifactFact,
    SandboxArtifactFingerprint,
    SandboxCapabilityConstraint,
    SandboxCapabilityFact,
    SandboxCapabilityScope,
    SandboxCapabilityScopeKind,
    SandboxEvidenceRequirementFact,
    SandboxHandoffFact,
    SandboxIsolationProfileId,
    SandboxIsolationSupportFact,
    SandboxPolicyFact,
    SandboxPolicyVersion,
    SandboxResourceGrantFact,
    SandboxWorkloadId,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def ref(value: str) -> OpaqueReference:
    return OpaqueReference(value)


def request(*, approval: bool = True) -> SandboxAdmissionRequest:
    return SandboxAdmissionRequest(
        workload_id=SandboxWorkloadId("workload:1"),
        subject=ref("subject:1"),
        handoff_fingerprint=SandboxArtifactFingerprint.from_content({"handoff": 1}),
        actor_ref=ref("actor:1"),
        purpose="evaluate",
        correlation_ref=ref("correlation:1"),
        policy_refs=(ref("policy:1"),),
        approval_ref=ref("approval:1") if approval else None,
        declared_capabilities=(CapabilityDeclaration("python"),),
        requested_capabilities=(RequestedCapability("python"),),
        requested_resources=(ResourceRequest("cpu", 2, "cores"),),
        execution_profile=ref("intent:batch"),
        isolation_policy_version=SandboxPolicyVersion("policy:v1"),
        isolation_profile_id=SandboxIsolationProfileId("isolation:strict"),
        structurally_complete=True,
    )


def complete_statuses(*, approval: FactCompleteness = FactCompleteness.COMPLETE) -> tuple[DimensionCompleteness, ...]:
    return tuple(
        DimensionCompleteness(
            dimension,
            approval if dimension is AdmissionFactDimension.APPROVAL else FactCompleteness.COMPLETE,
        )
        for dimension in AdmissionFactDimension
    )


def snapshot(
    admission_request: SandboxAdmissionRequest,
    *,
    approval_status: FactCompleteness = FactCompleteness.COMPLETE,
    approval_fact: SandboxApprovalFact | None = None,
    policy_fact: SandboxPolicyFact | None = None,
    reverse: bool = False,
) -> SandboxAdmissionFactsSnapshot:
    artifact_fingerprint = SandboxArtifactFingerprint.from_content({"artifact": 1})
    handoff = SandboxHandoffFact(
        admission_request.subject,
        admission_request.handoff_fingerprint,
        artifact_fingerprint,
        admission_request.actor_ref,
        admission_request.purpose,
        admission_request.execution_profile,
        HandoffReadiness.READY,
    )
    artifact = SandboxArtifactFact(
        admission_request.subject,
        ref("artifact:1"),
        artifact_fingerprint,
        ArtifactAvailability.AVAILABLE,
    )
    policy = policy_fact or SandboxPolicyFact(
        ref("policy:1"),
        admission_request.subject,
        admission_request.isolation_policy_version,
        NOW - timedelta(hours=1),
        NOW + timedelta(hours=1),
    )
    approval = approval_fact
    if approval is None and admission_request.approval_ref is not None:
        approval = SandboxApprovalFact(
            admission_request.approval_ref,
            admission_request.subject,
            admission_request.actor_ref,
            admission_request.purpose,
            admission_request.execution_profile,
            (ref("scope:sandbox"),),
            NOW - timedelta(hours=1),
            NOW + timedelta(hours=1),
        )
    capabilities = (
        SandboxCapabilityFact(
            admission_request.subject,
            admission_request.actor_ref,
            admission_request.purpose,
            admission_request.execution_profile,
            CapabilityDeclaration("python"),
            ref("external-capability-grant:1"),
            True,
            (SandboxCapabilityScope(SandboxCapabilityScopeKind.EXACT, ref("scope:workspace")),),
            (SandboxCapabilityConstraint("calls", 10),),
            (admission_request.isolation_profile_id,),
            NOW - timedelta(hours=1),
            NOW + timedelta(hours=1),
        ),
    )
    resources = (
        SandboxResourceGrantFact(
            admission_request.subject,
            ref("external-resource-grant:1"),
            ResourceLimit("cpu", 2, "cores"),
        ),
    )
    isolation = (
        SandboxIsolationSupportFact(
            admission_request.isolation_profile_id,
            admission_request.isolation_policy_version,
            ref("isolation-support:1"),
            True,
        ),
    )
    evidence = (
        SandboxEvidenceRequirementFact(
            ref("evidence:scan"),
            admission_request.subject,
            True,
            True,
        ),
    )
    statuses = complete_statuses(approval=approval_status)
    if reverse:
        statuses = tuple(reversed(statuses))
    return SandboxAdmissionFactsSnapshot.create(
        observed_at=NOW - timedelta(minutes=1),
        handoff_facts=(handoff,),
        artifact_facts=(artifact,),
        policy_facts=(policy,),
        approval_facts=() if approval is None else (approval,),
        capability_facts=capabilities,
        resource_facts=resources,
        isolation_facts=isolation,
        evidence_facts=evidence,
        completeness=statuses,
    )


def assess(
    admission_request: SandboxAdmissionRequest,
    facts: SandboxAdmissionFactsSnapshot,
):
    return SandboxAdmissionFactsAssessmentService().assess(
        admission_request, facts, evaluated_at=NOW
    )


def dimension(assessment, target: AdmissionFactDimension):
    return next(item for item in assessment.dimensions if item.dimension is target)


def test_complete_corresponding_fresh_facts_are_factually_satisfied() -> None:
    admission_request = request()
    assessment = assess(admission_request, snapshot(admission_request))
    assert assessment.outcome is AdmissionFactsOutcome.SATISFIED
    assert all(
        item.correspondence in {FactCorrespondence.MATCH, FactCorrespondence.NOT_REQUIRED}
        for item in assessment.dimensions
    )
    assert not hasattr(assessment, "admitted")
    assert not hasattr(assessment, "authorized")
    assert not hasattr(assessment, "grants")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject", ref("subject:other")),
        ("actor_ref", ref("actor:other")),
        ("purpose", "deploy"),
        ("plan_intent_ref", ref("intent:other")),
    ],
)
def test_approval_correspondence_is_exact(field: str, value: object) -> None:
    admission_request = request()
    base = snapshot(admission_request).approval_facts[0]
    mismatched = replace(base, **{field: value})
    assessment = assess(admission_request, snapshot(admission_request, approval_fact=mismatched))
    assert assessment.outcome is AdmissionFactsOutcome.MISMATCH
    assert dimension(
        assessment, AdmissionFactDimension.APPROVAL
    ).correspondence is FactCorrespondence.MISMATCH


def test_subject_and_handoff_fingerprint_must_match_exactly() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    bad_handoff = replace(
        base.handoff_facts[0],
        handoff_fingerprint=SandboxArtifactFingerprint.from_content({"other": 1}),
    )
    facts = SandboxAdmissionFactsSnapshot.create(
        observed_at=base.observed_at,
        handoff_facts=(bad_handoff,),
        artifact_facts=base.artifact_facts,
        policy_facts=base.policy_facts,
        approval_facts=base.approval_facts,
        capability_facts=base.capability_facts,
        resource_facts=base.resource_facts,
        isolation_facts=base.isolation_facts,
        evidence_facts=base.evidence_facts,
        completeness=base.completeness,
    )
    assert assess(admission_request, facts).outcome is AdmissionFactsOutcome.MISMATCH


def test_expired_fact_is_stale_not_unavailable() -> None:
    admission_request = request()
    expired = SandboxPolicyFact(
        ref("policy:1"),
        admission_request.subject,
        admission_request.isolation_policy_version,
        NOW - timedelta(hours=2),
        NOW - timedelta(hours=1),
    )
    assessment = assess(admission_request, snapshot(admission_request, policy_fact=expired))
    assert assessment.outcome is AdmissionFactsOutcome.STALE
    assert dimension(
        assessment, AdmissionFactDimension.POLICY
    ).freshness is FactFreshness.STALE


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (FactCompleteness.ABSENT, AdmissionFactsOutcome.UNAVAILABLE),
        (FactCompleteness.UNKNOWN, AdmissionFactsOutcome.UNAVAILABLE),
        (FactCompleteness.INCOMPLETE, AdmissionFactsOutcome.INCOMPLETE),
    ],
)
def test_completeness_states_remain_distinct(
    status: FactCompleteness, outcome: AdmissionFactsOutcome
) -> None:
    admission_request = request(approval=False)
    facts = snapshot(admission_request, approval_status=status)
    assessment = assess(admission_request, facts)
    assert dimension(assessment, AdmissionFactDimension.APPROVAL).completeness is status
    assert assessment.outcome is outcome


def test_not_required_is_explicit_and_neutral_only_when_declared() -> None:
    admission_request = request(approval=False)
    facts = snapshot(admission_request, approval_status=FactCompleteness.NOT_REQUIRED)
    assessment = assess(admission_request, facts)
    approval = dimension(assessment, AdmissionFactDimension.APPROVAL)
    assert approval.correspondence is FactCorrespondence.NOT_REQUIRED
    assert approval.freshness is FactFreshness.NOT_REQUIRED
    assert assessment.outcome is AdmissionFactsOutcome.SATISFIED


def test_not_required_fails_closed_when_request_requires_the_dimension() -> None:
    admission_request = request()
    facts = snapshot(admission_request, approval_status=FactCompleteness.NOT_REQUIRED)
    assessment = assess(admission_request, facts)
    assert assessment.outcome is AdmissionFactsOutcome.MISMATCH
    assert any(
        item.code == "not_required.contradiction" for item in assessment.diagnostics
    )


def test_capability_and_resource_facts_do_not_mutate_requests_or_create_effective_grants() -> None:
    admission_request = request()
    facts = snapshot(admission_request)
    assessment = assess(admission_request, facts)
    assert admission_request.requested_capabilities == (RequestedCapability("python"),)
    assert admission_request.requested_resources == (ResourceRequest("cpu", 2, "cores"),)
    assert facts.capability_facts[0].external_grant_ref is not None
    assert not hasattr(assessment, "effective_grants")
    assert not hasattr(assessment, "resource_limits")


def test_artifact_availability_does_not_imply_materialization_or_executability() -> None:
    fact = snapshot(request()).artifact_facts[0]
    assert fact.availability is ArtifactAvailability.AVAILABLE
    assert not hasattr(fact, "materialized")
    assert not hasattr(fact, "executable")


def test_conflicting_multiple_facts_fail_closed() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    conflict = replace(base.handoff_facts[0], purpose="deploy")
    facts = SandboxAdmissionFactsSnapshot.create(
        observed_at=base.observed_at,
        handoff_facts=base.handoff_facts + (conflict,),
        artifact_facts=base.artifact_facts,
        policy_facts=base.policy_facts,
        approval_facts=base.approval_facts,
        capability_facts=base.capability_facts,
        resource_facts=base.resource_facts,
        isolation_facts=base.isolation_facts,
        evidence_facts=base.evidence_facts,
        completeness=base.completeness,
    )
    assessment = assess(admission_request, facts)
    assert assessment.outcome is AdmissionFactsOutcome.MISMATCH
    assert any(item.code == "handoff.correspondence" for item in assessment.diagnostics)


def test_input_order_does_not_change_snapshot_assessment_or_fingerprint() -> None:
    admission_request = request()
    left = snapshot(admission_request)
    right = snapshot(admission_request, reverse=True)
    left_assessment = assess(admission_request, left)
    right_assessment = assess(admission_request, right)
    assert left == right
    assert left_assessment == right_assessment
    assert left_assessment.assessment_fingerprint == right_assessment.assessment_fingerprint


def test_diagnostics_are_safe_codes_without_external_references() -> None:
    admission_request = request()
    mismatched = replace(
        snapshot(admission_request).approval_facts[0],
        subject=ref("sensitive-reference:customer-123456"),
    )
    assessment = assess(admission_request, snapshot(admission_request, approval_fact=mismatched))
    rendered = repr(assessment.diagnostics)
    assert "customer-123456" not in rendered
    assert "approval.correspondence" in rendered


def test_snapshots_assessments_and_timestamps_are_validated_and_immutable() -> None:
    admission_request = request()
    facts = snapshot(admission_request)
    with pytest.raises(FrozenInstanceError):
        facts.observed_at = NOW  # type: ignore[misc]
    with pytest.raises(InvalidAdmissionFacts):
        SandboxAdmissionFactsSnapshot.create(
            observed_at=NOW.replace(tzinfo=None),
            completeness=complete_statuses(),
        )
    with pytest.raises(InvalidAdmissionFacts):
        SandboxAdmissionFactsAssessmentService().assess(
            admission_request, facts, evaluated_at=NOW.replace(tzinfo=None)
        )
