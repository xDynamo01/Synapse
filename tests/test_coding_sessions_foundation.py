from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from synapse.coding_sessions import (
    CANONICAL_FORMAT,
    CodingSessionActorReference,
    CodingSessionApprovalReference,
    CodingSessionArtifactReference,
    CodingSessionAuthorizationReference,
    CodingSessionCausalMetadata,
    CodingSessionCausalRevision,
    CodingSessionCheckoutReference,
    CodingSessionCheckpointIdentity,
    CodingSessionCorrelationReference,
    CodingSessionDeploymentCandidateReference,
    CodingSessionExternalReceiptIdentity,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionIntentIdentity,
    CodingSessionLeaseFactIdentity,
    CodingSessionLineage,
    CodingSessionPrivateEvalEvidenceReference,
    CodingSessionPrivateEvalResultReference,
    CodingSessionPrivateEvalRunReference,
    CodingSessionProjectReference,
    CodingSessionPurposeReference,
    CodingSessionRecoveryArtifactIdentity,
    CodingSessionRepositoryReference,
    CodingSessionSandboxAttemptReference,
    CodingSessionSandboxPlanReference,
    CodingSessionSandboxResultReference,
    CodingSessionTaskReference,
    CodingSessionVersionMismatch,
    CodingSessionWorkerAssignmentReference,
    CodingSessionWorkerAttemptReference,
    CodingSessionWorktreeReference,
    InvalidCodingSessionCausalRevision,
    InvalidCodingSessionIdentity,
    InvalidCodingSessionLineage,
    InvalidCodingSessionReference,
)
from synapse.coding_sessions.canonical import canonical_bytes


def test_session_identity_is_stable_and_independent_of_external_lifecycle_facts() -> None:
    first = CodingSessionIdentity.from_stable_key("project-1:task-1:session-1")
    after_worker_eval_and_deployment = CodingSessionIdentity.from_stable_key(
        "project-1:task-1:session-1"
    )
    assert first == after_worker_eval_and_deployment
    assert first.value.startswith("coding-session:")
    assert "worker" not in first.value
    assert "deployment" not in first.value


def test_semantically_distinct_identities_are_not_interchangeable() -> None:
    key = "session-1:artifact-1"
    identities = (
        CodingSessionIdentity.from_stable_key(key),
        CodingSessionFactIdentity.from_stable_key(key),
        CodingSessionCheckpointIdentity.from_stable_key(key),
        CodingSessionIntentIdentity.from_stable_key(key),
        CodingSessionExternalReceiptIdentity.from_stable_key(key),
        CodingSessionLeaseFactIdentity.from_stable_key(key),
        CodingSessionRecoveryArtifactIdentity.from_stable_key(key),
    )
    assert len(set(identities)) == len(identities)
    assert len({item.value.split(":", 1)[0] for item in identities}) == len(identities)


@pytest.mark.parametrize(
    "reference_type,value",
    (
        (CodingSessionActorReference, "actor:agent-1"),
        (CodingSessionProjectReference, "project:1"),
        (CodingSessionTaskReference, "task:1"),
        (CodingSessionPurposeReference, "purpose:change"),
        (CodingSessionCorrelationReference, "correlation:1"),
    ),
)
def test_local_references_are_opaque_and_immutable(reference_type, value: str) -> None:
    reference = reference_type(value)
    assert reference.value == value
    with pytest.raises(FrozenInstanceError):
        reference.value = "replacement"


@pytest.mark.parametrize(
    "reference_type",
    (
        CodingSessionRepositoryReference,
        CodingSessionCheckoutReference,
        CodingSessionWorktreeReference,
        CodingSessionWorkerAssignmentReference,
        CodingSessionWorkerAttemptReference,
        CodingSessionSandboxPlanReference,
        CodingSessionSandboxAttemptReference,
        CodingSessionSandboxResultReference,
        CodingSessionAuthorizationReference,
        CodingSessionApprovalReference,
        CodingSessionPrivateEvalRunReference,
        CodingSessionPrivateEvalResultReference,
        CodingSessionPrivateEvalEvidenceReference,
        CodingSessionArtifactReference,
        CodingSessionDeploymentCandidateReference,
    ),
)
def test_external_references_preserve_producer_version_identity_and_fingerprint(
    reference_type,
) -> None:
    fingerprint = CodingSessionFingerprint.from_content(("external", "fact"))
    reference = reference_type.create("producer:v1", "v1", "opaque:identity", fingerprint)
    assert reference.producer == "producer:v1"
    assert reference.version == "v1"
    assert reference.identity == "opaque:identity"
    assert reference.fingerprint == fingerprint
    assert not hasattr(reference, "authorized")
    assert not hasattr(reference, "status")
    assert not hasattr(reference, "payload")


def test_external_reference_type_cannot_be_forged_or_cross_assigned() -> None:
    with pytest.raises(InvalidCodingSessionReference):
        CodingSessionRepositoryReference("producer", "approval", "v1", "opaque")
    assert CodingSessionRepositoryReference.create(
        "repository-runtime", "v1", "repository:opaque"
    ) != CodingSessionApprovalReference.create("approvals", "v1", "approval:opaque")


def test_canonical_fingerprint_is_deterministic_for_semantically_unordered_values() -> None:
    left = {"facts": frozenset({"b", "a"}), "binding": {"worktree": "w", "repo": "r"}}
    right = {"binding": {"repo": "r", "worktree": "w"}, "facts": frozenset({"a", "b"})}
    assert CodingSessionFingerprint.from_content(left) == CodingSessionFingerprint.from_content(
        right
    )
    assert CodingSessionFingerprint.from_content(left) != CodingSessionFingerprint.from_content(
        {"binding": {"repo": "different", "worktree": "w"}, "facts": frozenset({"a", "b"})}
    )


def test_unknown_canonical_version_and_mutable_collection_fail_closed() -> None:
    assert CANONICAL_FORMAT == "coding-sessions-json-v1"
    with pytest.raises(CodingSessionVersionMismatch):
        canonical_bytes(("fact",), format_version="coding-sessions-json-v2")
    from synapse.coding_sessions import CodingSessionCanonicalizationError

    with pytest.raises(CodingSessionCanonicalizationError):
        CodingSessionFingerprint.from_content(["mutable", "sequence"])


def test_occurrence_metadata_does_not_change_semantic_identity_or_fingerprint() -> None:
    identity = CodingSessionFactIdentity.from_stable_key("session-1:fact-1")
    lineage = CodingSessionLineage()
    first = CodingSessionCausalMetadata(
        identity,
        CodingSessionCausalRevision(1),
        lineage,
        (("observed-at", "100"), ("trace", "a")),
    )
    second = CodingSessionCausalMetadata(
        identity,
        CodingSessionCausalRevision(1),
        lineage,
        (("trace", "b"), ("observed-at", "200")),
    )
    assert first.semantic_identity == second.semantic_identity
    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_causal_revision_and_lineage_are_validated_and_canonical() -> None:
    with pytest.raises(InvalidCodingSessionCausalRevision):
        CodingSessionCausalRevision(0)
    with pytest.raises(InvalidCodingSessionCausalRevision):
        CodingSessionCausalRevision(True)
    parent = CodingSessionFingerprint.from_content("parent")
    reference = CodingSessionFingerprint.from_content("reference")
    assert CodingSessionLineage((parent,), (reference,)) == CodingSessionLineage(
        (parent,), (reference,)
    )
    with pytest.raises(InvalidCodingSessionLineage):
        CodingSessionLineage((parent, parent), ())
    with pytest.raises(InvalidCodingSessionLineage):
        CodingSessionLineage((parent,), (parent,))


def test_errors_are_redacted_and_invalid_values_are_not_echoed() -> None:
    secret = "secret-token-value"
    with pytest.raises(InvalidCodingSessionIdentity) as identity_error:
        CodingSessionIdentity(secret)
    with pytest.raises(InvalidCodingSessionReference) as reference_error:
        CodingSessionActorReference(f"C:\\private\\{secret}")
    assert secret not in str(identity_error.value)
    assert secret not in str(reference_error.value)
