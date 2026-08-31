from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.sandbox import (
    CapabilityDeclaration,
    InvalidSandboxIdentity,
    InvalidSandboxModel,
    OpaqueReference,
    RequestedCapability,
    ResourceRequest,
    SandboxAdmissionId,
    SandboxAdmissionRequest,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxCanonicalizationError,
    SandboxCleanupResult,
    SandboxCleanupState,
    SandboxEvidenceId,
    SandboxIsolationProfileId,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxRollbackResult,
    SandboxRollbackState,
    SandboxWorkloadId,
    UnsupportedSandboxFormat,
    canonical_bytes,
    content_fingerprint,
    derive_identity,
)


def ref(value: str) -> OpaqueReference:
    return OpaqueReference(value)


def admission_request() -> SandboxAdmissionRequest:
    return SandboxAdmissionRequest(
        workload_id=SandboxWorkloadId("workload:1"),
        subject=ref("skill:demo@1"),
        handoff_fingerprint=SandboxArtifactFingerprint.from_content({"handoff": 1}),
        actor_ref=ref("actor:agent-1"),
        purpose="evaluate",
        correlation_ref=ref("correlation:1"),
        policy_refs=(ref("policy:1"),),
        approval_ref=None,
        declared_capabilities=(CapabilityDeclaration("python"),),
        requested_capabilities=(RequestedCapability("python"),),
        requested_resources=(ResourceRequest("cpu", 2, "cores"),),
        execution_profile=ref("profile:batch"),
        isolation_policy_version=SandboxPolicyVersion("policy:v1"),
        isolation_profile_id=SandboxIsolationProfileId("isolation:strict"),
        secret_refs=(ref("secret-ref:vault-1"),),
        structurally_complete=True,
    )


@pytest.mark.parametrize(
    ("factory", "bad"),
    [
        (OpaqueReference, "/private/path"),
        (SandboxWorkloadId, "../escape"),
        (SandboxAdmissionId, "contains space"),
        (SandboxPlanId, ""),
        (SandboxAttemptId, "x" * 256),
        (SandboxEvidenceId, r"C:\private"),
        (SandboxPolicyVersion, "../policy"),
        (SandboxIsolationProfileId, "\\server"),
    ],
)
def test_identities_reject_paths_and_unbounded_values(factory: object, bad: str) -> None:
    with pytest.raises(InvalidSandboxIdentity):
        factory(bad)  # type: ignore[operator]


def test_canonical_encoding_is_stable_versioned_and_semantic() -> None:
    left = content_fingerprint({"b": (2, 3), "a": 1})
    right = content_fingerprint({"a": 1, "b": [2, 3]})
    changed = content_fingerprint({"a": 1, "b": [2, 4]})
    assert left == right
    assert changed != left
    with pytest.raises(UnsupportedSandboxFormat):
        canonical_bytes({}, format_version="sandbox-json-v2")
    with pytest.raises(SandboxCanonicalizationError):
        canonical_bytes(object())


def test_content_identity_excludes_occurrence_metadata() -> None:
    first = derive_identity(SandboxAttemptId, "plan:1", "attempt:1")
    same = derive_identity(SandboxAttemptId, "plan:1", "attempt:1")
    changed = derive_identity(SandboxAttemptId, "plan:1", "attempt:2")
    assert first == same
    assert first != changed


def test_models_are_frozen_and_deeply_immutable() -> None:
    request = admission_request()
    with pytest.raises(FrozenInstanceError):
        request.purpose = "changed"  # type: ignore[misc]
    assert isinstance(request.policy_refs, tuple)
    assert isinstance(request.requested_capabilities, tuple)


def test_declarations_do_not_create_effective_grants() -> None:
    request = admission_request()
    assert request.declared_capabilities[0].name == "python"
    assert request.requested_capabilities[0].name == "python"
    assert not hasattr(request, "effective_grants")


def test_cleanup_and_rollback_require_bounded_references() -> None:
    assert SandboxCleanupResult(
        SandboxAttemptId("attempt:1"), SandboxCleanupState.VERIFIED, ref("verify:1")
    )
    assert SandboxRollbackResult(
        SandboxAttemptId("attempt:1"), SandboxRollbackState.COMPLETED, ref("rollback:1")
    )


@pytest.mark.parametrize(
    "value",
    ["password=hunter2", "token=abc", "/home/user/output", "../output"],
)
def test_sensitive_values_and_paths_are_rejected_without_echo(value: str) -> None:
    with pytest.raises(InvalidSandboxModel) as captured:
        replace(admission_request(), purpose=value)
    assert value not in repr(captured.value)
