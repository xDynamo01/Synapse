from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from synapse.deployment import (
    AdapterBindingReference,
    ArtifactFingerprintReference,
    ArtifactMediaClass,
    ArtifactReference,
    CapabilityAvailability,
    CapabilityReference,
    CorrelationReference,
    CustodyReference,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAttemptV1,
    DeploymentEnvironmentOperationalV1,
    DeploymentEnvironmentV1,
    DeploymentFingerprint,
    DeploymentIntentId,
    DeploymentReleaseV1,
    DeploymentSlotV1,
    DeploymentTargetClass,
    DeploymentTargetId,
    DeploymentTargetKind,
    DeploymentTargetOperationalV1,
    DeploymentTargetV1,
    DeploymentTier,
    DesiredOperationalRevisionV1,
    DesiredRevisionV1,
    EnvironmentClassification,
    EnvironmentId,
    EnvironmentOperationalClass,
    InvalidDeploymentAttemptBinding,
    InvalidDeploymentEnvironment,
    InvalidDeploymentTarget,
    ObservationReference,
    ObservedOperationalRevisionV1,
    ObservedRevisionV1,
    OccurrenceReference,
    PolicyReference,
    ProvenanceReference,
    ReleaseId,
    RevisionCorrespondence,
    RevisionId,
    SecretReference,
    SlotActivity,
    SlotCapability,
    SlotId,
    TargetCapabilityFactV1,
    TargetCapabilityKind,
    TargetCapabilityRequirementsV1,
    TargetCompatibility,
    TargetCorrespondenceRequestV1,
    classify_revision_correspondence,
    classify_target_compatibility,
    validate_target_correspondence,
)


def _contracts() -> tuple[
    DeploymentEnvironmentOperationalV1,
    DeploymentTargetOperationalV1,
    DeploymentArtifactRefV1,
    DesiredOperationalRevisionV1,
    DeploymentReleaseV1,
    DeploymentAttemptV1,
]:
    policy = PolicyReference("policy:target-v1")
    environment = DeploymentEnvironmentOperationalV1(
        DeploymentEnvironmentV1(
            EnvironmentId("deployment-environment:local"), "Local Runtime",
            EnvironmentClassification.DEVELOPMENT, policy,
        ),
        EnvironmentOperationalClass.LOCAL,
        DeploymentTier.NON_CRITICAL,
        (TargetCapabilityKind.APPLY, TargetCapabilityKind.OBSERVE),
    )
    target = DeploymentTargetOperationalV1(
        DeploymentTargetV1(
            DeploymentTargetId("deployment-target:local-api"),
            environment.environment.environment_id,
            AdapterBindingReference("adapter-binding:local-service-v1"),
            DeploymentTargetClass.SERVICE,
            capability_references=(CapabilityReference("capability:single-host"),),
        ),
        DeploymentTargetKind.LOCAL_SERVICE,
        SlotCapability.SINGLE_SLOT,
        (
            TargetCapabilityFactV1(
                TargetCapabilityKind.APPLY, True, True, CapabilityAvailability.UNKNOWN
            ),
            TargetCapabilityFactV1(
                TargetCapabilityKind.OBSERVE, True, True, CapabilityAvailability.AVAILABLE,
                CapabilityReference("evidence:observation-capability"),
            ),
            TargetCapabilityFactV1(
                TargetCapabilityKind.VERIFY, True, False, CapabilityAvailability.UNKNOWN
            ),
        ),
        (CapabilityReference("configuration:service-unit-v1"),),
        CapabilityReference("capability:local-observation"),
        CapabilityReference("capability:immutable-rollback"),
        (SecretReference("secret-reference:service-account"),),
    )
    artifact = DeploymentArtifactRefV1(
        ArtifactReference("artifact:local-api-v8"),
        ArtifactFingerprintReference("sha256:" + "8" * 64),
        ProvenanceReference("provenance:build-v8"),
        ArtifactMediaClass.APPLICATION_BUNDLE,
        CustodyReference("custody:local-v8"),
        "application/zip",
    )
    desired = DesiredRevisionV1(
        RevisionId("deployment-revision:local-api-v8"), artifact.fingerprint
    )
    operational_revision = DesiredOperationalRevisionV1(
        desired,
        artifact,
        target.configuration_fingerprint,
        (CapabilityReference("configuration:runtime-v8"),),
        policy,
        "v8",
    )
    release = DeploymentReleaseV1(
        ReleaseId("deployment-release:v8"), DeploymentIntentId("deployment-intent:v8"),
        DeploymentFingerprint("sha256:" + "1" * 64), artifact,
        target.target.target_id, desired, policy,
    )
    attempt = DeploymentAttemptV1(
        DeploymentAttemptId("deployment-attempt:v8"), release.release_id,
        target.target.target_id, desired, artifact, 1, policy,
        target.configuration_fingerprint, OccurrenceReference("occurrence:attempt-v8"),
        CorrelationReference("correlation:attempt-v8"),
    )
    return environment, target, artifact, operational_revision, release, attempt


def test_environment_descriptor_is_provider_neutral_and_not_authorization() -> None:
    environment, _, _, _, _, _ = _contracts()
    assert environment.operational_class is EnvironmentOperationalClass.LOCAL
    assert environment.tier is DeploymentTier.NON_CRITICAL
    assert environment.required_capabilities == (
        TargetCapabilityKind.APPLY,
        TargetCapabilityKind.OBSERVE,
    )
    assert not hasattr(environment, "authorization_reference")
    assert not hasattr(environment, "endpoint")


@pytest.mark.parametrize("classification", tuple(EnvironmentOperationalClass))
def test_environment_operational_taxonomy_is_canonical(
    classification: EnvironmentOperationalClass,
) -> None:
    environment, _, _, _, _, _ = _contracts()
    assert replace(environment, operational_class=classification).operational_class is classification


def test_concrete_host_provider_and_secret_metadata_are_rejected() -> None:
    environment, target, _, _, _, _ = _contracts()
    from synapse.deployment import DeploymentMetadataEntry

    with pytest.raises(InvalidDeploymentEnvironment):
        replace(
            environment,
            environment=replace(
                environment.environment,
                metadata=(DeploymentMetadataEntry("deployment", "endpoint", "https://host"),),
            ),
        )
    with pytest.raises(InvalidDeploymentTarget):
        replace(
            target,
            target=replace(
                target.target,
                metadata=(DeploymentMetadataEntry("deployment", "host-path", "C:\\service"),),
            ),
        )


@pytest.mark.parametrize("kind", tuple(DeploymentTargetKind))
def test_target_kind_is_provider_neutral_and_descriptor_can_be_unsupported(
    kind: DeploymentTargetKind,
) -> None:
    _, target, _, _, _, _ = _contracts()
    descriptor = replace(target, kind=kind)
    assert descriptor.kind is kind
    unsupported = replace(
        descriptor,
        slot_capability=SlotCapability.UNSUPPORTED,
        capability_facts=(),
        verification_capability_reference=None,
        rollback_capability_reference=None,
    )
    assert unsupported.capability_facts == ()


def test_adapter_binding_and_configuration_fingerprint_are_factual_and_deterministic() -> None:
    _, target, _, _, _, _ = _contracts()
    assert target.configuration_fingerprint == replace(target).configuration_fingerprint
    changed = replace(
        target,
        configuration_references=(CapabilityReference("configuration:service-unit-v2"),),
    )
    assert changed.configuration_fingerprint != target.configuration_fingerprint
    assert not target.adapter_available
    assert not hasattr(target.target.adapter_binding, "available")


def test_no_slot_single_slot_and_multi_slot_are_distinct_capabilities() -> None:
    _, target, _, _, _, _ = _contracts()
    assert target.target.slot_id is None
    assert target.slot_capability is SlotCapability.SINGLE_SLOT
    multi = replace(target, slot_capability=SlotCapability.MULTI_SLOT)
    assert multi.slot_capability is SlotCapability.MULTI_SLOT
    with pytest.raises(InvalidDeploymentTarget):
        replace(
            target,
            target=replace(target.target, slot_id=SlotId("deployment-slot:primary")),
            slot_capability=SlotCapability.UNSUPPORTED,
        )


def test_slot_identity_target_and_observed_activity_are_separate() -> None:
    _, target, _, desired, _, _ = _contracts()
    observation = ObservationReference("observation:slot-primary")
    observed = ObservedRevisionV1(
        desired.desired_revision.revision_id, observation, desired.artifact.fingerprint
    )
    slot = DeploymentSlotV1(
        SlotId("deployment-slot:primary"), target.target.target_id, "primary",
        SlotActivity.ACTIVE, observed, observation,
    )
    assert slot.slot_id != target.target.target_id
    assert slot.activity is SlotActivity.ACTIVE
    assert replace(
        slot, target_id=DeploymentTargetId("deployment-target:other")
    ).target_id != target.target.target_id


def test_desired_revision_fingerprint_changes_with_artifact_config_and_policy_not_occurrence() -> None:
    _, _, artifact, desired, _, attempt = _contracts()
    assert desired.revision_fingerprint == replace(desired).revision_fingerprint
    changed_artifact = replace(
        artifact, fingerprint=ArtifactFingerprintReference("sha256:" + "9" * 64)
    )
    changed_desired = replace(
        desired.desired_revision, artifact_fingerprint=changed_artifact.fingerprint
    )
    assert replace(
        desired, desired_revision=changed_desired, artifact=changed_artifact
    ).revision_fingerprint != desired.revision_fingerprint
    assert replace(
        desired, target_configuration_fingerprint=DeploymentFingerprint("sha256:" + "3" * 64)
    ).revision_fingerprint != desired.revision_fingerprint
    changed_occurrence = replace(attempt, occurrence=OccurrenceReference("occurrence:other"))
    assert changed_occurrence.configuration_fingerprint == attempt.configuration_fingerprint
    assert desired.revision_fingerprint == replace(desired).revision_fingerprint


def test_observed_revision_is_distinct_and_does_not_have_to_match_desired() -> None:
    _, _, _, desired, _, _ = _contracts()
    observation = ObservationReference("observation:target-v8")
    observed = ObservedOperationalRevisionV1(
        ObservedRevisionV1(
            RevisionId("deployment-revision:other"), observation,
            ArtifactFingerprintReference("sha256:" + "0" * 64),
        )
    )
    assert observed.observed_revision.revision_id != desired.desired_revision.revision_id
    assert not observed.verified


def test_revision_correspondence_has_four_factual_outcomes_and_never_verifies() -> None:
    _, _, _, desired, _, _ = _contracts()
    observation = ObservationReference("observation:revision-v8")
    matching = ObservedOperationalRevisionV1(
        ObservedRevisionV1(
            desired.desired_revision.revision_id, observation, desired.artifact.fingerprint
        ),
        desired.target_configuration_fingerprint,
    )
    mismatch = replace(
        matching,
        observed_revision=replace(
            matching.observed_revision,
            artifact_fingerprint=ArtifactFingerprintReference("sha256:" + "0" * 64),
        ),
    )
    indeterminate = replace(
        matching,
        observed_revision=replace(matching.observed_revision, artifact_fingerprint=None),
    )
    assert classify_revision_correspondence(desired, matching) is RevisionCorrespondence.MATCH
    assert classify_revision_correspondence(desired, mismatch) is RevisionCorrespondence.MISMATCH
    assert classify_revision_correspondence(desired, None) is RevisionCorrespondence.UNAVAILABLE
    assert classify_revision_correspondence(desired, indeterminate) is RevisionCorrespondence.INDETERMINATE
    assert not matching.verified


def test_declared_required_and_available_capabilities_remain_distinct() -> None:
    environment, target, _, _, _, _ = _contracts()
    assert classify_target_compatibility(
        target, environment.required_capabilities
    ) is TargetCompatibility.INDETERMINATE
    available = replace(
        target,
        capability_facts=tuple(
            replace(fact, availability=CapabilityAvailability.AVAILABLE)
            for fact in target.capability_facts
        ),
    )
    assert classify_target_compatibility(
        available, environment.required_capabilities
    ) is TargetCompatibility.COMPATIBLE
    assert next(
        fact for fact in target.capability_facts if fact.capability is TargetCapabilityKind.APPLY
    ).declared
    assert next(
        fact for fact in target.capability_facts if fact.capability is TargetCapabilityKind.APPLY
    ).availability is CapabilityAvailability.UNKNOWN


def test_external_egress_requirement_does_not_authorize_egress() -> None:
    _, target, _, _, _, _ = _contracts()
    requiring = replace(target, requires_external_egress=True)
    assert requiring.requires_external_egress
    assert not requiring.egress_authorized
    assert not hasattr(requiring, "egress_authorization_reference")


def test_target_correspondence_accepts_exact_binding_and_rejects_every_mismatch() -> None:
    environment, target, _, desired, _, attempt = _contracts()
    slot = DeploymentSlotV1(
        SlotId("deployment-slot:primary"), target.target.target_id, "primary"
    )
    request = TargetCorrespondenceRequestV1(
        environment,
        target,
        slot,
        desired,
        attempt,
        TargetCapabilityRequirementsV1(
            attempt.release_id,
            attempt.attempt_id,
            attempt.policy_reference,
            environment.required_capabilities,
        ),
        target.target.adapter_binding,
        target.configuration_fingerprint,
    )
    validate_target_correspondence(request)
    with pytest.raises(InvalidDeploymentTarget):
        validate_target_correspondence(
            replace(request, slot=replace(slot, target_id=DeploymentTargetId("deployment-target:other")))
        )
    with pytest.raises(InvalidDeploymentAttemptBinding):
        validate_target_correspondence(
            replace(request, expected_adapter_binding=AdapterBindingReference("adapter-binding:other"))
        )
    with pytest.raises(InvalidDeploymentAttemptBinding):
        validate_target_correspondence(
            replace(request, expected_target_configuration=DeploymentFingerprint("sha256:" + "0" * 64))
        )
    with pytest.raises(InvalidDeploymentTarget):
        validate_target_correspondence(
            replace(
                request,
                requirements=replace(
                    request.requirements,
                    required_capabilities=(TargetCapabilityKind.ROLLBACK,),
                ),
            )
        )


def test_local_service_future_contract_has_no_provider_or_execution_surface() -> None:
    _, target, _, _, _, _ = _contracts()
    assert target.kind is DeploymentTargetKind.LOCAL_SERVICE
    assert not hasattr(target, "host_path")
    assert not hasattr(target, "port")
    assert not hasattr(target, "provider_payload")
    assert not hasattr(target, "apply")
    with pytest.raises(FrozenInstanceError):
        setattr(target, "kind", DeploymentTargetKind.APPLICATION)
