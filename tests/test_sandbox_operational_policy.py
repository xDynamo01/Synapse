from dataclasses import replace

from synapse.bootstrap.adapters.sandbox_policy import (
    LOCAL_WINDOWS_JOB_ISOLATION_PROFILE,
    LOCAL_WINDOWS_SANDBOX_POLICY_VERSION,
    build_local_windows_sandbox_admission_policy,
)
from synapse.sandbox import (
    AdmissionFactDimension,
    DimensionCompleteness,
    FactCompleteness,
    SandboxAdmissionDecisionOutcome,
    SandboxAdmissionDecisionService,
    SandboxAdmissionFactsAssessmentService,
    SandboxAdmissionFactsSnapshot,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
)
from test_sandbox_admission_facts import NOW, request, snapshot


def decide(admission_request, facts):
    assessment = SandboxAdmissionFactsAssessmentService().assess(
        admission_request, facts, evaluated_at=NOW
    )
    return SandboxAdmissionDecisionService().decide(
        admission_request,
        assessment,
        build_local_windows_sandbox_admission_policy(),
        occurred_at=NOW,
    )


def rebuild(
    base: SandboxAdmissionFactsSnapshot,
    **changes: object,
) -> SandboxAdmissionFactsSnapshot:
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


def test_policy_is_canonical_exact_and_fail_closed() -> None:
    first = build_local_windows_sandbox_admission_policy()
    second = build_local_windows_sandbox_admission_policy()

    assert first == second
    assert first.version == LOCAL_WINDOWS_SANDBOX_POLICY_VERSION
    assert first.minimum_isolation_profiles == (LOCAL_WINDOWS_JOB_ISOLATION_PROFILE,)
    assert first.allowed_capabilities == ("python",)
    assert not first.allow_capability_wildcards
    assert first.require_approval_fact
    assert first.require_external_capability_grants
    assert first.require_external_resource_grants
    assert first.require_isolation_support
    assert all(item.required for item in first.dimension_requirements)
    assert all(
        item.allowed_completeness == (FactCompleteness.COMPLETE,)
        and not item.allow_not_required
        for item in first.dimension_requirements
    )
    assert {
        item.dimension for item in first.dimension_requirements if item.require_fresh
    } == {AdmissionFactDimension.POLICY, AdmissionFactDimension.APPROVAL}
    assert first.policy_fingerprint == SandboxArtifactFingerprint.from_content(
        first.semantic_content()
    )


def test_complete_corresponding_facts_are_admitted_but_not_authorized() -> None:
    admission_request = replace(
        request(), isolation_profile_id=LOCAL_WINDOWS_JOB_ISOLATION_PROFILE
    )
    decision = decide(admission_request, snapshot(admission_request))

    assert decision.outcome is SandboxAdmissionDecisionOutcome.ADMITTED
    assert not hasattr(decision, "authorized")
    assert not hasattr(decision, "executable")


def test_wrong_isolation_profile_is_denied() -> None:
    admission_request = replace(
        request(), isolation_profile_id=SandboxIsolationProfileId("profile:other")
    )
    decision = decide(admission_request, snapshot(admission_request))

    assert decision.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert "isolation.profile_disallowed" in decision.rationale_codes


def test_missing_approval_is_unavailable_and_not_admitted() -> None:
    admission_request = replace(
        request(approval=False),
        isolation_profile_id=LOCAL_WINDOWS_JOB_ISOLATION_PROFILE,
    )
    facts = snapshot(admission_request, approval_status=FactCompleteness.ABSENT)
    decision = decide(admission_request, facts)

    assert decision.outcome is SandboxAdmissionDecisionOutcome.UNAVAILABLE


def test_incomplete_facts_remain_incomplete() -> None:
    admission_request = replace(
        request(), isolation_profile_id=LOCAL_WINDOWS_JOB_ISOLATION_PROFILE
    )
    facts = snapshot(admission_request)
    incomplete = tuple(
        DimensionCompleteness(
            item.dimension,
            FactCompleteness.INCOMPLETE
            if item.dimension is AdmissionFactDimension.EVIDENCE
            else item.status,
        )
        for item in facts.completeness
    )
    decision = decide(admission_request, rebuild(facts, completeness=incomplete))

    assert decision.outcome is SandboxAdmissionDecisionOutcome.INCOMPLETE


def test_unsupported_isolation_is_denied() -> None:
    admission_request = replace(
        request(), isolation_profile_id=LOCAL_WINDOWS_JOB_ISOLATION_PROFILE
    )
    facts = snapshot(admission_request)
    unsupported = replace(
        facts.isolation_facts[0],
        supported=False,
    )
    changed = rebuild(facts, isolation_facts=(unsupported,))
    decision = decide(admission_request, changed)

    assert decision.outcome is SandboxAdmissionDecisionOutcome.DENIED
    assert "isolation.support_required" in decision.rationale_codes
