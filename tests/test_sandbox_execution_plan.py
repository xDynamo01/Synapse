from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from synapse.sandbox import (
    InvalidExecutionPlan,
    OpaqueReference,
    SandboxAdmissionDecisionService,
    SandboxAdmissionFactsAssessmentService,
    SandboxEvidenceRequirement,
    SandboxExecutionPlanService,
    SandboxExecutionPlanSpecification,
    SandboxExternalCapabilityReference,
    SandboxExternalResourceReference,
    SandboxLogicalEntrypoint,
    SandboxRetentionKind,
    SandboxRetentionRequirement,
    SandboxRuntimeDescriptor,
    SandboxRuntimeKind,
)
from test_sandbox_admission_facts import NOW, ref, request, snapshot
from test_sandbox_admission_policy import policy, rebuild


def admitted_inputs():
    admission_request = request()
    facts = snapshot(admission_request)
    evaluated = SandboxAdmissionFactsAssessmentService().assess(
        admission_request, facts, evaluated_at=NOW
    )
    admission_policy = policy()
    decision = SandboxAdmissionDecisionService().decide(
        admission_request, evaluated, admission_policy, occurred_at=NOW
    )
    return admission_request, facts, evaluated, admission_policy, decision


def specification(admission_request, facts, *, reverse: bool = False):
    capabilities = tuple(
        SandboxExternalCapabilityReference(
            fact.declaration.name,
            fact.external_grant_ref,
        )
        for fact in facts.capability_facts
        if fact.external_grant_ref is not None
    )
    resources = tuple(
        SandboxExternalResourceReference(fact.limit.resource, fact.external_grant_ref)
        for fact in facts.resource_facts
    )
    limits = tuple(fact.limit for fact in facts.resource_facts)
    evidence = tuple(
        SandboxEvidenceRequirement(fact.evidence_ref, fact.required)
        for fact in facts.evidence_facts
    )
    if reverse:
        capabilities = tuple(reversed(capabilities))
        resources = tuple(reversed(resources))
        limits = tuple(reversed(limits))
        evidence = tuple(reversed(evidence))
    return SandboxExecutionPlanSpecification(
        handoff_ref=ref("handoff:1"),
        handoff_fingerprint=admission_request.handoff_fingerprint,
        artifact_ref=facts.artifact_facts[0].artifact_ref,
        artifact_fingerprint=facts.artifact_facts[0].fingerprint,
        runtime=SandboxRuntimeDescriptor(SandboxRuntimeKind.PYTHON, "3.12"),
        entrypoint=SandboxLogicalEntrypoint("package.module:main"),
        requested_capabilities=tuple(
            reversed(admission_request.requested_capabilities)
            if reverse
            else admission_request.requested_capabilities
        ),
        requested_resources=tuple(
            reversed(admission_request.requested_resources)
            if reverse
            else admission_request.requested_resources
        ),
        external_capability_refs=capabilities,
        external_resource_refs=resources,
        isolation_profile_id=admission_request.isolation_profile_id,
        resource_limits=limits,
        evidence_requirements=evidence,
        retention_requirement=SandboxRetentionRequirement(
            SandboxRetentionKind.BOUNDED, 30
        ),
        correlation_ref=admission_request.correlation_ref,
        purpose=admission_request.purpose,
    )


def build(inputs, spec=None, *, created_at=NOW):
    admission_request, facts, evaluated, admission_policy, decision = inputs
    return SandboxExecutionPlanService().build(
        admission_request,
        facts,
        evaluated,
        admission_policy,
        decision,
        spec or specification(admission_request, facts),
        created_at=created_at,
    )


def test_only_admitted_decision_can_generate_plan() -> None:
    admission_request, facts, _, admission_policy, _ = admitted_inputs()
    bad_approval = replace(facts.approval_facts[0], purpose="deploy")
    mismatch_facts = rebuild(facts, approval_facts=(bad_approval,))
    mismatch_assessment = SandboxAdmissionFactsAssessmentService().assess(
        admission_request, mismatch_facts, evaluated_at=NOW
    )
    denied = SandboxAdmissionDecisionService().decide(
        admission_request, mismatch_assessment, admission_policy, occurred_at=NOW
    )
    with pytest.raises(InvalidExecutionPlan) as captured:
        SandboxExecutionPlanService().build(
            admission_request,
            mismatch_facts,
            mismatch_assessment,
            admission_policy,
            denied,
            specification(admission_request, mismatch_facts),
            created_at=NOW,
        )
    assert "decision.not_admitted" in captured.value.diagnostics


def test_plan_binds_every_governed_input_without_operational_state() -> None:
    inputs = admitted_inputs()
    plan = build(inputs)
    admission_request, facts, evaluated, admission_policy, decision = inputs
    assert plan.workload_id == admission_request.workload_id
    assert plan.snapshot_fingerprint == facts.snapshot_fingerprint
    assert plan.assessment_fingerprint == evaluated.assessment_fingerprint
    assert plan.policy_id == admission_policy.policy_id
    assert plan.policy_version == admission_policy.version
    assert plan.decision_id == decision.decision_id
    assert not hasattr(plan, "authorized")
    assert not hasattr(plan, "materialized")
    assert not hasattr(plan, "executable")
    assert not hasattr(plan, "allocations")
    assert not hasattr(plan, "effective_grants")
    assert not hasattr(plan, "run")
    assert not hasattr(plan, "execute")


def test_semantic_change_changes_plan_fingerprint() -> None:
    inputs = admitted_inputs()
    admission_request, facts, *_ = inputs
    first = build(inputs)
    changed = replace(
        specification(admission_request, facts),
        entrypoint=SandboxLogicalEntrypoint("package.module:alternate"),
    )
    second = build(inputs, changed)
    assert first.plan_id != second.plan_id
    assert first.plan_fingerprint != second.plan_fingerprint


def test_occurrence_metadata_does_not_change_semantic_identity() -> None:
    inputs = admitted_inputs()
    first = build(inputs, created_at=NOW)
    second = build(inputs, created_at=NOW + timedelta(minutes=1))
    assert first.plan_id == second.plan_id
    assert first.plan_fingerprint == second.plan_fingerprint
    assert first.created_at != second.created_at


def test_collection_order_does_not_change_plan_or_fingerprint() -> None:
    inputs = admitted_inputs()
    admission_request, facts, *_ = inputs
    first = build(inputs, specification(admission_request, facts))
    reordered = build(inputs, specification(admission_request, facts, reverse=True))
    assert first == reordered


@pytest.mark.parametrize(
    "field",
    ["request", "snapshot", "assessment", "policy"],
)
def test_binding_mismatches_fail_closed_with_safe_diagnostics(field: str) -> None:
    inputs = admitted_inputs()
    admission_request, facts, evaluated, admission_policy, decision = inputs
    other_request = replace(admission_request, purpose="deploy")
    other_facts = snapshot(other_request)
    other_assessment = SandboxAdmissionFactsAssessmentService().assess(
        other_request, other_facts, evaluated_at=NOW
    )
    other_policy = policy(version="admission-policy:v2")
    if field == "request":
        args = (other_request, facts, evaluated, admission_policy, decision)
    elif field == "snapshot":
        args = (admission_request, other_facts, evaluated, admission_policy, decision)
    elif field == "assessment":
        args = (admission_request, facts, other_assessment, admission_policy, decision)
    else:
        args = (admission_request, facts, evaluated, other_policy, decision)
    with pytest.raises(InvalidExecutionPlan) as captured:
        SandboxExecutionPlanService().build(
            *args,
            specification(admission_request, facts),
            created_at=NOW,
        )
    assert "secret" not in repr(captured.value).lower()


@pytest.mark.parametrize(
    "entrypoint",
    ["/absolute/path", "../escape", "python -c code", "module;rm", "module|pipe"],
)
def test_entrypoint_rejects_paths_shell_and_command_strings(entrypoint: str) -> None:
    with pytest.raises(InvalidExecutionPlan):
        SandboxLogicalEntrypoint(entrypoint)


def test_unsupported_runtime_fails_structurally() -> None:
    with pytest.raises(InvalidExecutionPlan):
        SandboxRuntimeDescriptor("ruby", "3.3")  # type: ignore[arg-type]
    with pytest.raises(InvalidExecutionPlan):
        SandboxRuntimeDescriptor(SandboxRuntimeKind.PYTHON, "latest")


def test_requests_and_external_references_do_not_become_grants_or_allocations() -> None:
    plan = build(admitted_inputs())
    assert plan.requested_capabilities
    assert plan.external_capability_refs
    assert plan.requested_resources
    assert plan.external_resource_refs
    assert plan.resource_limits
    assert not hasattr(plan.external_capability_refs[0], "effective")
    assert not hasattr(plan.external_resource_refs[0], "allocated")
    assert not hasattr(plan.isolation_profile_id, "available")


def test_structural_inconsistencies_return_complete_ordered_diagnostics() -> None:
    inputs = admitted_inputs()
    admission_request, facts, *_ = inputs
    bad = replace(
        specification(admission_request, facts),
        handoff_fingerprint=type(admission_request.handoff_fingerprint).from_content(
            {"other": 1}
        ),
        correlation_ref=OpaqueReference("correlation:other"),
        purpose="deploy",
        resource_limits=(),
    )
    with pytest.raises(InvalidExecutionPlan) as captured:
        build(inputs, bad)
    assert captured.value.diagnostics == tuple(sorted(captured.value.diagnostics))
    assert {
        "specification.handoff_mismatch",
        "specification.correlation_mismatch",
        "specification.purpose_mismatch",
        "specification.resource_limit_invalid",
    } <= set(captured.value.diagnostics)
    assert "correlation:other" not in repr(captured.value)


def test_exact_replay_and_plan_integrity_are_deterministic() -> None:
    inputs = admitted_inputs()
    first = build(inputs)
    replay = build(inputs)
    assert replay == first
    with pytest.raises(FrozenInstanceError):
        first.purpose = "changed"  # type: ignore[misc]
    with pytest.raises(InvalidExecutionPlan):
        replace(
            first,
            plan_fingerprint=type(first.plan_fingerprint).from_content({"tampered": 1}),
        )
