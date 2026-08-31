from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from synapse.sandbox import (
    ADMISSION_OUTCOME_PRECEDENCE,
    AdmissionDimensionRequirement,
    AdmissionFactDimension,
    AdmissionPolicyTreatments,
    FactCompleteness,
    InvalidAdmissionDecision,
    InvalidAdmissionPolicy,
    SandboxAdmissionDecisionOutcome,
    SandboxAdmissionDecisionService,
    SandboxAdmissionFactsAssessmentService,
    SandboxAdmissionFactsSnapshot,
    SandboxAdmissionPolicy,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
)
from test_sandbox_admission_facts import NOW, request, snapshot


def policy(
    *,
    approval_required: bool = True,
    approval_not_required: bool = False,
    capability_grants: bool = True,
    resource_grants: bool = True,
    allowed_capabilities: tuple[str, ...] = ("python",),
    capability_wildcards: bool = False,
    version: str = "admission-policy:v1",
    reverse: bool = False,
) -> SandboxAdmissionPolicy:
    requirements = tuple(
        AdmissionDimensionRequirement(
            dimension=dimension,
            required=not (
                dimension is AdmissionFactDimension.APPROVAL and approval_not_required
            ),
            allowed_completeness=(
                (FactCompleteness.COMPLETE, FactCompleteness.NOT_REQUIRED)
                if dimension is AdmissionFactDimension.APPROVAL and approval_not_required
                else (FactCompleteness.COMPLETE,)
            ),
            allow_not_required=(
                dimension is AdmissionFactDimension.APPROVAL and approval_not_required
            ),
            require_fresh=dimension
            in {AdmissionFactDimension.POLICY, AdmissionFactDimension.APPROVAL}
            and not (
                dimension is AdmissionFactDimension.APPROVAL and approval_not_required
            ),
        )
        for dimension in AdmissionFactDimension
    )
    if reverse:
        requirements = tuple(reversed(requirements))
    return SandboxAdmissionPolicy.create(
        version=SandboxPolicyVersion(version),
        dimension_requirements=requirements,
        treatments=AdmissionPolicyTreatments(
            mismatch=SandboxAdmissionDecisionOutcome.DENIED,
            stale=SandboxAdmissionDecisionOutcome.STALE,
            unavailable=SandboxAdmissionDecisionOutcome.UNAVAILABLE,
            incomplete=SandboxAdmissionDecisionOutcome.INCOMPLETE,
        ),
        minimum_isolation_profiles=(SandboxIsolationProfileId("isolation:strict"),),
        require_isolation_support=True,
        require_approval_fact=approval_required,
        require_external_capability_grants=capability_grants,
        require_external_resource_grants=resource_grants,
        allowed_capabilities=allowed_capabilities,
        allow_capability_wildcards=capability_wildcards,
        outcome_precedence=ADMISSION_OUTCOME_PRECEDENCE,
    )


def assessment(admission_request, facts):
    return SandboxAdmissionFactsAssessmentService().assess(
        admission_request, facts, evaluated_at=NOW
    )


def decide(admission_request, facts, admission_policy, *, occurred_at=NOW):
    return SandboxAdmissionDecisionService().decide(
        admission_request,
        assessment(admission_request, facts),
        admission_policy,
        occurred_at=occurred_at,
    )


def rebuild(base: SandboxAdmissionFactsSnapshot, **changes: object) -> SandboxAdmissionFactsSnapshot:
    values = {
        "observed_at": base.observed_at,
        "handoff_facts": base.handoff_facts,
        "artifact_facts": base.artifact_facts,
        "policy_facts": base.policy_facts,
        "approval_facts": base.approval_facts,
        "capability_facts": base.capability_facts,
        "resource_facts": base.resource_facts,
        "isolation_facts": base.isolation_facts,
        "evidence_facts": base.evidence_facts,
        "completeness": base.completeness,
    }
    values.update(changes)
    return SandboxAdmissionFactsSnapshot.create(**values)  # type: ignore[arg-type]


def test_admitted_is_only_admission_and_has_exact_bindings() -> None:
    admission_request = request()
    admission_policy = policy()
    evaluated = assessment(admission_request, snapshot(admission_request))
    decision = SandboxAdmissionDecisionService().decide(
        admission_request, evaluated, admission_policy, occurred_at=NOW
    )
    assert decision.outcome is SandboxAdmissionDecisionOutcome.ADMITTED
    assert decision.request_fingerprint == SandboxArtifactFingerprint.from_content(
        admission_request
    )
    assert decision.assessment_fingerprint == evaluated.assessment_fingerprint
    assert decision.policy_id == admission_policy.policy_id
    assert decision.policy_fingerprint == admission_policy.policy_fingerprint
    assert not hasattr(decision, "authorized")
    assert not hasattr(decision, "materialized")
    assert not hasattr(decision, "executable")
    assert not hasattr(decision, "effective_grants")


def test_policy_input_order_is_canonical() -> None:
    assert policy() == policy(reverse=True)


def test_policy_semantic_change_changes_policy_and_decision_fingerprints() -> None:
    admission_request = request()
    facts = snapshot(admission_request)
    first_policy = policy(version="admission-policy:v1")
    second_policy = policy(version="admission-policy:v2")
    first = decide(admission_request, facts, first_policy)
    second = decide(admission_request, facts, second_policy)
    assert first_policy.policy_id != second_policy.policy_id
    assert first_policy.policy_fingerprint != second_policy.policy_fingerprint
    assert first.decision_fingerprint != second.decision_fingerprint


def test_occurrence_timestamp_does_not_change_semantic_identity() -> None:
    admission_request = request()
    facts = snapshot(admission_request)
    admission_policy = policy()
    first = decide(admission_request, facts, admission_policy, occurred_at=NOW)
    second = decide(
        admission_request,
        facts,
        admission_policy,
        occurred_at=NOW + timedelta(minutes=5),
    )
    assert first.decision_id == second.decision_id
    assert first.decision_fingerprint == second.decision_fingerprint
    assert first.occurred_at != second.occurred_at


def test_assessment_mismatch_is_denied_and_never_admitted() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    bad = replace(base.approval_facts[0], purpose="deploy")
    decision = decide(
        admission_request,
        rebuild(base, approval_facts=(bad,)),
        policy(),
    )
    assert decision.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert "approval.mismatch" in decision.rationale_codes


def test_stale_is_not_unavailable() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    stale = replace(
        base.policy_facts[0],
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW - timedelta(hours=1),
    )
    decision = decide(
        admission_request,
        rebuild(base, policy_facts=(stale,)),
        policy(),
    )
    assert decision.outcome is SandboxAdmissionDecisionOutcome.STALE


@pytest.mark.parametrize(
    ("completeness", "expected"),
    [
        (FactCompleteness.ABSENT, SandboxAdmissionDecisionOutcome.UNAVAILABLE),
        (FactCompleteness.UNKNOWN, SandboxAdmissionDecisionOutcome.UNAVAILABLE),
        (FactCompleteness.INCOMPLETE, SandboxAdmissionDecisionOutcome.INCOMPLETE),
    ],
)
def test_non_decisive_fact_states_are_not_denied(
    completeness: FactCompleteness, expected: SandboxAdmissionDecisionOutcome
) -> None:
    admission_request = request(approval=False)
    facts = snapshot(admission_request, approval_status=completeness)
    decision = decide(
        admission_request,
        facts,
        policy(approval_required=False, approval_not_required=True),
    )
    assert decision.outcome is expected


def test_not_required_only_satisfies_when_policy_explicitly_allows_it() -> None:
    admission_request = request(approval=False)
    facts = snapshot(admission_request, approval_status=FactCompleteness.NOT_REQUIRED)
    allowed = decide(
        admission_request,
        facts,
        policy(approval_required=False, approval_not_required=True),
    )
    assert allowed.outcome is SandboxAdmissionDecisionOutcome.ADMITTED

    disallowed_policy = policy(approval_required=True, approval_not_required=False)
    disallowed = decide(admission_request, facts, disallowed_policy)
    assert disallowed.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert "approval.not_required_disallowed" in disallowed.rationale_codes


def test_external_capability_grant_is_required_only_when_policy_says_so() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    without_grant = replace(base.capability_facts[0], external_grant_ref=None)
    facts = rebuild(base, capability_facts=(without_grant,))
    required = decide(admission_request, facts, policy(capability_grants=True))
    optional = decide(admission_request, facts, policy(capability_grants=False))
    assert required.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert optional.outcome is SandboxAdmissionDecisionOutcome.ADMITTED


def test_resource_request_without_grant_fact_is_not_admitted() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    facts = rebuild(base, resource_facts=())
    decision = decide(admission_request, facts, policy(resource_grants=True))
    assert decision.outcome is SandboxAdmissionDecisionOutcome.UNAVAILABLE
    assert "resources.external_grants_required" in decision.rationale_codes


def test_unsupported_or_disallowed_isolation_prevents_admission() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    unsupported = replace(base.isolation_facts[0], supported=False)
    unsupported_decision = decide(
        admission_request,
        rebuild(base, isolation_facts=(unsupported,)),
        policy(),
    )
    assert unsupported_decision.outcome is SandboxAdmissionDecisionOutcome.DENIED

    other_profile_policy = SandboxAdmissionPolicy.create(
        version=SandboxPolicyVersion("admission-policy:other"),
        dimension_requirements=policy().dimension_requirements,
        treatments=policy().treatments,
        minimum_isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
        require_isolation_support=True,
        require_approval_fact=True,
        require_external_capability_grants=True,
        require_external_resource_grants=True,
        allowed_capabilities=("python",),
        allow_capability_wildcards=False,
        outcome_precedence=ADMISSION_OUTCOME_PRECEDENCE,
    )
    disallowed = decide(admission_request, base, other_profile_policy)
    assert disallowed.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert "isolation.profile_disallowed" in disallowed.rationale_codes


def test_multiple_violations_produce_complete_ordered_safe_rationale() -> None:
    admission_request = request()
    base = snapshot(admission_request)
    bad_approval = replace(base.approval_facts[0], actor_ref=type(base.approval_facts[0].actor_ref)("actor:other"))
    unsupported = replace(base.isolation_facts[0], supported=False)
    decision = decide(
        admission_request,
        rebuild(
            base,
            approval_facts=(bad_approval,),
            capability_facts=(
                replace(base.capability_facts[0], external_grant_ref=None),
            ),
            isolation_facts=(unsupported,),
        ),
        policy(),
    )
    assert decision.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert decision.rationale_codes == tuple(sorted(decision.rationale_codes))
    assert {
        "approval.mismatch",
        "capabilities.external_grants_required",
        "isolation.mismatch",
        "isolation.support_required",
    } <= set(decision.rationale_codes)
    assert "actor:other" not in repr(decision.diagnostics)


def test_exact_replay_is_semantically_identical() -> None:
    admission_request = request()
    facts = snapshot(admission_request)
    admission_policy = policy()
    first = decide(admission_request, facts, admission_policy)
    replay = decide(admission_request, facts, admission_policy)
    assert replay == first
    assert replay.decision_id == first.decision_id


def test_request_assessment_binding_is_exact() -> None:
    first_request = request()
    evaluated = assessment(first_request, snapshot(first_request))
    other_request = replace(first_request, purpose="deploy")
    with pytest.raises(InvalidAdmissionDecision):
        SandboxAdmissionDecisionService().decide(
            other_request, evaluated, policy(), occurred_at=NOW
        )


def test_policy_and_decision_artifacts_validate_integrity_and_are_frozen() -> None:
    admission_policy = policy()
    with pytest.raises(FrozenInstanceError):
        admission_policy.require_approval_fact = False  # type: ignore[misc]
    with pytest.raises(InvalidAdmissionPolicy):
        replace(
            admission_policy,
            policy_fingerprint=SandboxArtifactFingerprint.from_content({"tampered": 1}),
        )
    admission_request = request()
    decision = decide(admission_request, snapshot(admission_request), admission_policy)
    with pytest.raises(InvalidAdmissionDecision):
        replace(
            decision,
            decision_fingerprint=SandboxArtifactFingerprint.from_content({"tampered": 1}),
        )
