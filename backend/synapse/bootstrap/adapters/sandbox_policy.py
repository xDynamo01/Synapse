"""Canonical fail-closed Sandbox admission policy for local Windows composition."""

from synapse.sandbox import (
    ADMISSION_OUTCOME_PRECEDENCE,
    AdmissionDimensionRequirement,
    AdmissionFactDimension,
    AdmissionPolicyTreatments,
    FactCompleteness,
    SandboxAdmissionDecisionOutcome,
    SandboxAdmissionPolicy,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
)

LOCAL_WINDOWS_SANDBOX_POLICY_VERSION = SandboxPolicyVersion(
    "sandbox-admission-policy:local-windows-v1"
)
LOCAL_WINDOWS_JOB_ISOLATION_PROFILE = SandboxIsolationProfileId(
    "sandbox-profile:windows-job-contained-v1"
)


def build_local_windows_sandbox_admission_policy() -> SandboxAdmissionPolicy:
    """Build the immutable local policy without probing or activating host capabilities."""

    requirements = tuple(
        AdmissionDimensionRequirement(
            dimension=dimension,
            required=True,
            allowed_completeness=(FactCompleteness.COMPLETE,),
            allow_not_required=False,
            require_fresh=dimension
            in {AdmissionFactDimension.POLICY, AdmissionFactDimension.APPROVAL},
        )
        for dimension in AdmissionFactDimension
    )
    return SandboxAdmissionPolicy.create(
        version=LOCAL_WINDOWS_SANDBOX_POLICY_VERSION,
        dimension_requirements=requirements,
        treatments=AdmissionPolicyTreatments(
            mismatch=SandboxAdmissionDecisionOutcome.DENIED,
            stale=SandboxAdmissionDecisionOutcome.STALE,
            unavailable=SandboxAdmissionDecisionOutcome.UNAVAILABLE,
            incomplete=SandboxAdmissionDecisionOutcome.INCOMPLETE,
        ),
        minimum_isolation_profiles=(LOCAL_WINDOWS_JOB_ISOLATION_PROFILE,),
        require_isolation_support=True,
        require_approval_fact=True,
        require_external_capability_grants=True,
        require_external_resource_grants=True,
        allowed_capabilities=("python",),
        allow_capability_wildcards=False,
        outcome_precedence=ADMISSION_OUTCOME_PRECEDENCE,
    )
