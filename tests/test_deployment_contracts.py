from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.deployment import (
    AdapterBindingReference,
    ApplyReceiptReference,
    ArtifactFingerprintReference,
    ArtifactMediaClass,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    CausationReference,
    CorrelationReference,
    CustodyReference,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAttemptV1,
    DeploymentEnvironmentV1,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentIntentId,
    DeploymentIntentV1,
    DeploymentMetadataEntry,
    DeploymentPromotionV1,
    DeploymentReleaseV1,
    DeploymentRollbackAttemptV1,
    DeploymentRolloutV1,
    DeploymentTargetClass,
    DeploymentTargetId,
    DeploymentTargetV1,
    DesiredRevisionV1,
    EnvironmentClassification,
    EnvironmentId,
    EvidenceReference,
    InvalidDeploymentArtifactReference,
    InvalidDeploymentAttemptBinding,
    InvalidDeploymentEnvironment,
    InvalidDeploymentIdentity,
    InvalidDeploymentIntent,
    InvalidDeploymentMetadata,
    InvalidDeploymentReference,
    InvalidDeploymentRevision,
    ObservationReference,
    ObservedRevisionV1,
    OccurrenceReference,
    PolicyReference,
    PromotionId,
    ProvenanceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RolloutId,
    RolloutStageClass,
    SecretReference,
    SlotId,
    VerificationReference,
    canonical_json,
)


def _facts() -> tuple[
    DeploymentEnvironmentV1,
    DeploymentTargetV1,
    DeploymentArtifactRefV1,
    DesiredRevisionV1,
]:
    environment = DeploymentEnvironmentV1(
        EnvironmentId("deployment-environment:test"),
        "Test",
        EnvironmentClassification.TEST,
        PolicyReference("policy:deployment-v1"),
        (
            DeploymentMetadataEntry("synapse", "region-class", "local"),
            DeploymentMetadataEntry("deployment", "risk-tier", "low"),
        ),
    )
    target = DeploymentTargetV1(
        DeploymentTargetId("deployment-target:api-test"),
        environment.environment_id,
        AdapterBindingReference("adapter-binding:local-service"),
        DeploymentTargetClass.SERVICE,
        capability_references=(CapabilityReference("capability:process-supervision"),),
    )
    artifact = DeploymentArtifactRefV1(
        ArtifactReference("artifact:synapse-api-v1"),
        ArtifactFingerprintReference("fingerprint:sha256-release-001"),
        ProvenanceReference("provenance:build-001"),
        ArtifactMediaClass.APPLICATION_BUNDLE,
        CustodyReference("custody:local-approved"),
        "application/zip",
    )
    revision = DesiredRevisionV1(
        RevisionId("deployment-revision:release-001"), artifact.fingerprint
    )
    return environment, target, artifact, revision


def _intent() -> DeploymentIntentV1:
    environment, target, artifact, revision = _facts()
    return DeploymentIntentV1(
        DeploymentIntentId("deployment-intent:req-001"),
        artifact,
        environment,
        target,
        revision,
        RequesterReference("subject:operator"),
        PolicyReference("policy:deployment-v1"),
        DeploymentIdempotencyKey("deployment-idempotency:request-001"),
        CorrelationReference("correlation:001"),
        CausationReference("causation:001"),
        OccurrenceReference("occurrence:001"),
    )


def test_identities_are_typed_immutable_hashable_and_validate_prefixes() -> None:
    left = DeploymentIntentId("deployment-intent:one")
    assert left == DeploymentIntentId("deployment-intent:one")
    assert len({left, DeploymentIntentId("deployment-intent:one")}) == 1
    assert left != ReleaseId("deployment-release:one")
    assert DeploymentIdempotencyKey("deployment-idempotency:one") != left
    with pytest.raises(InvalidDeploymentIdentity):
        DeploymentIntentId("deployment-release:one")
    with pytest.raises(FrozenInstanceError):
        setattr(left, "value", "deployment-intent:two")


def test_environment_metadata_is_namespaced_bounded_immutable_and_canonical() -> None:
    environment, _, _, _ = _facts()
    assert [item.namespace for item in environment.metadata] == ["deployment", "synapse"]
    assert canonical_json(environment) == canonical_json(environment)
    with pytest.raises(InvalidDeploymentEnvironment):
        replace(environment, logical_name="")
    with pytest.raises(InvalidDeploymentMetadata):
        DeploymentMetadataEntry("Not Namespaced", "key", "value")
    with pytest.raises(InvalidDeploymentMetadata):
        replace(
            environment,
            metadata=(
                DeploymentMetadataEntry("synapse", "key", "one"),
                DeploymentMetadataEntry("synapse", "key", "two"),
            ),
        )


def test_target_environment_correspondence_and_optional_slot_are_explicit() -> None:
    environment, target, _, _ = _facts()
    assert target.slot_id is None
    slotted = replace(target, slot_id=SlotId("deployment-slot:blue"))
    assert slotted != target
    with pytest.raises(InvalidDeploymentIntent):
        replace(
            _intent(),
            target=replace(
                target, environment_id=EnvironmentId("deployment-environment:other")
            ),
        )
    assert environment.environment_id == target.environment_id


def test_desired_and_observed_revisions_are_distinct_contracts() -> None:
    _, _, _, desired = _facts()
    observed = ObservedRevisionV1(
        desired.revision_id,
        ObservationReference("observation:target-001"),
        desired.artifact_fingerprint,
    )
    assert type(desired) is not type(observed)
    assert desired != observed


def test_artifact_reference_is_safe_immutable_and_does_not_prove_availability() -> None:
    _, _, artifact, _ = _facts()
    assert not hasattr(artifact, "bytes")
    assert not hasattr(artifact, "available")
    assert not hasattr(artifact, "deployable")
    with pytest.raises(FrozenInstanceError):
        setattr(artifact, "media_type", "text/plain")
    with pytest.raises(InvalidDeploymentReference):
        ArtifactReference("C:\\build\\artifact.zip")
    with pytest.raises(InvalidDeploymentReference):
        ArtifactReference("https://registry.invalid/image")
    with pytest.raises(InvalidDeploymentArtifactReference):
        replace(artifact, media_type="invalid")


def test_intent_is_not_authorization_and_semantics_exclude_occurrence_context() -> None:
    intent = _intent()
    changed_context = replace(
        intent,
        intent_id=DeploymentIntentId("deployment-intent:req-002"),
        idempotency_key=DeploymentIdempotencyKey("deployment-idempotency:request-002"),
        correlation=CorrelationReference("correlation:002"),
        causation=None,
        occurrence=OccurrenceReference("occurrence:002"),
    )
    assert intent.semantic_fingerprint == changed_context.semantic_fingerprint
    assert not hasattr(intent, "authorized")
    authorization = AuthorizationReference("authorization:approval-001")
    assert not hasattr(authorization, "authorized")


def test_release_and_attempt_are_distinct_and_attempt_binding_is_semantic() -> None:
    intent = _intent()
    release = DeploymentReleaseV1(
        ReleaseId("deployment-release:001"),
        intent.intent_id,
        intent.semantic_fingerprint,
        intent.artifact,
        intent.target.target_id,
        intent.desired_revision,
        intent.policy_reference,
    )
    attempt = DeploymentAttemptV1(
        DeploymentAttemptId("deployment-attempt:001"),
        release.release_id,
        release.target_id,
        release.desired_revision,
        release.artifact,
        1,
        release.policy_reference,
        DeploymentFingerprint("sha256:" + "1" * 64),
        OccurrenceReference("occurrence:attempt-001"),
        CorrelationReference("correlation:attempt-001"),
    )
    assert type(release) is not type(attempt)
    assert attempt.semantic_fingerprint == replace(
        attempt,
        attempt_id=DeploymentAttemptId("deployment-attempt:002"),
        occurrence=OccurrenceReference("occurrence:attempt-002"),
        correlation=CorrelationReference("correlation:attempt-002"),
    ).semantic_fingerprint
    with pytest.raises(InvalidDeploymentAttemptBinding):
        replace(attempt, attempt_number=0)


def test_receipt_observation_verification_and_secret_are_opaque_distinct_refs() -> None:
    receipt = ApplyReceiptReference("apply-receipt:001")
    observation = ObservationReference("observation:001")
    verification = VerificationReference("verification:001")
    evidence = EvidenceReference("evidence:001")
    secret = SecretReference("secret-reference:deployment-credential")
    assert len({receipt, observation, verification, evidence, secret}) == 5
    assert not hasattr(receipt, "verified")
    assert not hasattr(secret, "value_material")
    with pytest.raises(InvalidDeploymentReference):
        SecretReference("vault://deployment/credential")


def test_rollout_promotion_and_rollback_contracts_preserve_distinctions() -> None:
    release_id = ReleaseId("deployment-release:001")
    target_id = DeploymentTargetId("deployment-target:api-test")
    rollout = DeploymentRolloutV1(
        RolloutId("deployment-rollout:001"),
        release_id,
        target_id,
        CapabilityReference("stage:initial"),
        RolloutStageClass.INITIAL,
        SlotId("deployment-slot:blue"),
    )
    promotion = DeploymentPromotionV1(
        PromotionId("deployment-promotion:001"),
        rollout.rollout_id,
        SlotId("deployment-slot:blue"),
        SlotId("deployment-slot:green"),
        PolicyReference("policy:promotion-v1"),
    )
    rollback = DeploymentRollbackAttemptV1(
        RollbackAttemptId("deployment-rollback-attempt:001"),
        release_id,
        target_id,
        RevisionId("deployment-revision:release-002"),
        RevisionId("deployment-revision:release-001"),
        AuthorizationReference("authorization:rollback-001"),
        OccurrenceReference("occurrence:rollback-001"),
    )
    assert rollout.rollout_id != promotion.promotion_id
    assert not hasattr(rollback, "applied")
    with pytest.raises(InvalidDeploymentRevision):
        replace(rollback, intended_revision=rollback.source_revision)
