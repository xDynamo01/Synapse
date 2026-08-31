from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from synapse.sandbox import (
    CapabilityDeclaration,
    FactCompleteness,
    InvalidCapabilityGrantSet,
    InvalidExecutionPlan,
    RequestedCapability,
    SandboxAdmissionDecisionOutcome,
    SandboxAdmissionDecisionService,
    SandboxAdmissionFactsAssessmentService,
    SandboxCapabilityConstraint,
    SandboxCapabilityDenialReason,
    SandboxCapabilityFact,
    SandboxCapabilityGrantService,
    SandboxCapabilityPermissionSnapshot,
    SandboxCapabilityScope,
    SandboxCapabilityScopeKind,
    SandboxExecutionPlanService,
    SandboxIsolationProfileId,
    SandboxPlanCapabilityPermission,
    SandboxPlanId,
)
from test_sandbox_admission_facts import NOW, ref, request, snapshot
from test_sandbox_admission_policy import policy
from test_sandbox_execution_plan import specification


def pipeline(*, admission_policy=None):
    admission_request = request()
    facts = snapshot(admission_request)
    evaluated = SandboxAdmissionFactsAssessmentService().assess(
        admission_request, facts, evaluated_at=NOW
    )
    selected_policy = admission_policy or policy()
    decision = SandboxAdmissionDecisionService().decide(
        admission_request, evaluated, selected_policy, occurred_at=NOW
    )
    plan = SandboxExecutionPlanService().build(
        admission_request,
        facts,
        evaluated,
        selected_policy,
        decision,
        specification(admission_request, facts),
        created_at=NOW,
    )
    return admission_request, facts, selected_policy, decision, plan


def permissions(inputs, *, completeness=FactCompleteness.COMPLETE, supplied=None, reverse=False):
    _, facts, _, _, plan = inputs
    source_facts = tuple(supplied if supplied is not None else facts.capability_facts)
    permission_facts = tuple(
        SandboxPlanCapabilityPermission(plan.plan_id, plan.plan_fingerprint, fact)
        for fact in source_facts
    )
    if reverse:
        permission_facts = tuple(reversed(permission_facts))
    return SandboxCapabilityPermissionSnapshot.create(
        observed_at=NOW,
        completeness=completeness,
        facts=permission_facts,
    )


def evaluate(inputs, permission_snapshot=None, *, evaluated_at=NOW, occurred_at=NOW):
    admission_request, _, admission_policy, decision, plan = inputs
    return SandboxCapabilityGrantService().evaluate(
        admission_request,
        permission_snapshot or permissions(inputs),
        admission_policy,
        decision,
        plan,
        evaluated_at=evaluated_at,
        occurred_at=occurred_at,
    )


def test_declaration_request_permission_and_effective_grant_remain_distinct() -> None:
    inputs = pipeline()
    admission_request, facts, _, _, _ = inputs
    grant_set = evaluate(inputs)
    grant = grant_set.grants[0]
    fact = facts.capability_facts[0]
    assert isinstance(admission_request.declared_capabilities[0], CapabilityDeclaration)
    assert isinstance(admission_request.requested_capabilities[0], RequestedCapability)
    assert isinstance(fact, SandboxCapabilityFact)
    assert grant.capability == fact.declaration.name
    assert grant.source_references == (fact.external_grant_ref,)
    assert not hasattr(grant, "authorized")


def test_unrequested_capability_never_receives_grant() -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    extra = replace(
        facts.capability_facts[0],
        declaration=CapabilityDeclaration("network"),
        external_grant_ref=ref("external-capability-grant:network"),
    )
    grant_set = evaluate(
        inputs,
        permissions(inputs, supplied=facts.capability_facts + (extra,), reverse=True),
    )
    assert tuple(item.capability for item in grant_set.grants) == ("python",)
    assert not any(item.capability == "network" for item in grant_set.denials)


def test_requested_but_undeclared_fails_closed_before_plan() -> None:
    admission_request = replace(request(), declared_capabilities=())
    facts = snapshot(admission_request)
    evaluated = SandboxAdmissionFactsAssessmentService().assess(
        admission_request, facts, evaluated_at=NOW
    )
    admission_policy = policy()
    decision = SandboxAdmissionDecisionService().decide(
        admission_request, evaluated, admission_policy, occurred_at=NOW
    )
    assert decision.outcome is SandboxAdmissionDecisionOutcome.DENIED
    with pytest.raises(InvalidExecutionPlan):
        SandboxExecutionPlanService().build(
            admission_request,
            facts,
            evaluated,
            admission_policy,
            decision,
            specification(admission_request, facts),
            created_at=NOW,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject", ref("subject:other")),
        ("actor_ref", ref("actor:other")),
        ("purpose", "deploy"),
        ("plan_intent_ref", ref("intent:other")),
    ],
)
def test_external_fact_correspondence_is_integral(field: str, value: object) -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    mismatched = replace(facts.capability_facts[0], **{field: value})
    grant_set = evaluate(inputs, permissions(inputs, supplied=(mismatched,)))
    assert not grant_set.grants
    assert grant_set.denials[0].reason is SandboxCapabilityDenialReason.MISMATCH


def test_external_fact_for_another_plan_does_not_grant() -> None:
    inputs = pipeline()
    permission_snapshot = permissions(inputs)
    wrong_plan = replace(
        permission_snapshot.facts[0], plan_id=SandboxPlanId("plan:other")
    )
    mismatched = SandboxCapabilityPermissionSnapshot.create(
        observed_at=NOW,
        completeness=FactCompleteness.COMPLETE,
        facts=(wrong_plan,),
    )
    grant_set = evaluate(inputs, mismatched)
    assert not grant_set.grants
    assert grant_set.denials[0].reason is SandboxCapabilityDenialReason.MISMATCH


@pytest.mark.parametrize(
    ("completeness", "reason"),
    [
        (FactCompleteness.ABSENT, SandboxCapabilityDenialReason.ABSENT),
        (FactCompleteness.INCOMPLETE, SandboxCapabilityDenialReason.INCOMPLETE),
        (FactCompleteness.UNKNOWN, SandboxCapabilityDenialReason.UNAVAILABLE),
    ],
)
def test_absent_incomplete_and_unavailable_are_distinct(
    completeness: FactCompleteness, reason: SandboxCapabilityDenialReason
) -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    grant_set = evaluate(
        inputs,
        permissions(inputs, completeness=completeness, supplied=()),
    )
    assert grant_set.denials[0].reason is reason


def test_stale_permission_does_not_grant() -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    grant_set = evaluate(
        inputs,
        permissions(inputs),
        evaluated_at=NOW + timedelta(hours=2),
    )
    assert not grant_set.grants
    assert grant_set.denials[0].reason is SandboxCapabilityDenialReason.STALE


def test_grant_preserves_or_narrows_scope_constraints_and_validity() -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    fact = facts.capability_facts[0]
    grant = evaluate(inputs).grants[0]
    assert grant.scopes == fact.scopes
    assert grant.constraints == fact.constraints
    assert grant.valid_from == NOW
    assert grant.valid_until == fact.valid_until
    assert set(grant.scopes) <= set(fact.scopes)
    assert set(grant.constraints) <= set(fact.constraints)


def test_wildcard_requires_explicit_fact_and_policy_permission() -> None:
    wildcard_policy = policy(capability_wildcards=True)
    allowed_inputs = pipeline(admission_policy=wildcard_policy)
    _, facts, _, _, _ = allowed_inputs
    wildcard_fact = replace(
        facts.capability_facts[0],
        scopes=(SandboxCapabilityScope(SandboxCapabilityScopeKind.WILDCARD, None),),
    )
    allowed = evaluate(
        allowed_inputs, permissions(allowed_inputs, supplied=(wildcard_fact,))
    )
    assert allowed.grants[0].scopes[0].kind is SandboxCapabilityScopeKind.WILDCARD

    denied_inputs = pipeline(admission_policy=policy(capability_wildcards=False))
    _, denied_facts, _, _, _ = denied_inputs
    denied_fact = replace(
        denied_facts.capability_facts[0],
        scopes=(SandboxCapabilityScope(SandboxCapabilityScopeKind.WILDCARD, None),),
    )
    denied = evaluate(
        denied_inputs, permissions(denied_inputs, supplied=(denied_fact,))
    )
    assert denied.denials[0].reason is SandboxCapabilityDenialReason.POLICY_DENIED


def test_policy_denial_and_isolation_incompatibility_are_explicit() -> None:
    denied_inputs = pipeline(admission_policy=policy(allowed_capabilities=()))
    policy_denial = evaluate(denied_inputs)
    assert policy_denial.denials[0].reason is SandboxCapabilityDenialReason.POLICY_DENIED

    inputs = pipeline()
    _, facts, _, _, _ = inputs
    incompatible = replace(
        facts.capability_facts[0],
        isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
    )
    isolation_denial = evaluate(
        inputs, permissions(inputs, supplied=(incompatible,))
    )
    assert isolation_denial.denials[0].reason is SandboxCapabilityDenialReason.UNSUPPORTED


def test_input_order_does_not_change_grant_set_or_fingerprint() -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    extra = replace(
        facts.capability_facts[0],
        declaration=CapabilityDeclaration("network"),
        external_grant_ref=ref("external-capability-grant:network"),
    )
    left = evaluate(
        inputs, permissions(inputs, supplied=(facts.capability_facts[0], extra))
    )
    right = evaluate(
        inputs,
        permissions(
            inputs, supplied=(extra, facts.capability_facts[0]), reverse=True
        ),
    )
    assert left == right
    assert left.grant_set_fingerprint == right.grant_set_fingerprint


def test_semantic_change_changes_fingerprint_but_occurrence_does_not() -> None:
    inputs = pipeline()
    _, facts, _, _, _ = inputs
    first = evaluate(inputs)
    changed_fact = replace(
        facts.capability_facts[0],
        constraints=(SandboxCapabilityConstraint("calls", 5),),
    )
    changed = evaluate(inputs, permissions(inputs, supplied=(changed_fact,)))
    later_occurrence = evaluate(inputs, occurred_at=NOW + timedelta(minutes=5))
    assert first.grant_set_fingerprint != changed.grant_set_fingerprint
    assert first.grant_set_id == later_occurrence.grant_set_id
    assert first.grant_set_fingerprint == later_occurrence.grant_set_fingerprint
    assert first.occurred_at != later_occurrence.occurred_at


def test_complete_denial_does_not_revoke_admission_or_create_global_authorization() -> None:
    inputs = pipeline(admission_policy=policy(allowed_capabilities=()))
    grant_set = evaluate(inputs)
    _, _, _, decision, _ = inputs
    assert decision.outcome is SandboxAdmissionDecisionOutcome.ADMITTED
    assert not grant_set.grants
    assert grant_set.denials
    assert not hasattr(grant_set, "authorized")
    assert not hasattr(grant_set, "materialized")
    assert not hasattr(grant_set, "executable")


def test_exact_replay_integrity_and_binding_are_deterministic() -> None:
    inputs = pipeline()
    first = evaluate(inputs)
    replay = evaluate(inputs)
    assert replay == first
    with pytest.raises(FrozenInstanceError):
        first.grants = ()  # type: ignore[misc]
    with pytest.raises(InvalidCapabilityGrantSet):
        replace(
            first,
            grant_set_fingerprint=type(first.grant_set_fingerprint).from_content(
                {"tampered": 1}
            ),
        )

    admission_request, facts, admission_policy, decision, plan = inputs
    other_policy = policy(version="admission-policy:v2")
    with pytest.raises(InvalidCapabilityGrantSet):
        SandboxCapabilityGrantService().evaluate(
            admission_request,
            permissions(inputs),
            other_policy,
            decision,
            plan,
            evaluated_at=NOW,
            occurred_at=NOW,
        )
