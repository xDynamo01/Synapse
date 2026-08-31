from __future__ import annotations

import hashlib
from dataclasses import replace

from synapse.deployment import (
    AdapterBindingReference,
    ArtifactEligibilityOutcome,
    ArtifactEligibilityResultV1,
    ArtifactFingerprintReference,
    ArtifactMediaClass,
    ArtifactReference,
    AuthorizationReference,
    CapabilityAvailability,
    CapabilityReference,
    CorrelationReference,
    CustodyReference,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAttemptV1,
    DeploymentEnvironmentOperationalV1,
    DeploymentEnvironmentV1,
    DeploymentFencingAuthority,
    DeploymentFencingScopeKind,
    DeploymentFencingScopeV1,
    DeploymentFencingTransitionRequestV1,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentIdempotencyRequestV1,
    DeploymentIntentId,
    DeploymentMutationClass,
    DeploymentReleaseV1,
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
    LocalRevisionPreparationAuthorizationV1,
    LocalRevisionPreparationFailure,
    LocalRevisionPreparationOutcome,
    LocalRevisionPreparationRequestV1,
    OccurrenceReference,
    PolicyReference,
    ProvenanceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    SecretReference,
    SlotCapability,
    TargetCapabilityFactV1,
    TargetCapabilityKind,
    TargetCapabilityRequirementsV1,
    TargetCorrespondenceRequestV1,
    preparation_semantic_fingerprint,
)
from synapse.deployment_adapters import (
    DeploymentSQLiteConfig,
    LocalServiceAdapterBindingV1,
    LocalServicePreparationAdapter,
    SQLiteDeploymentAuthorityStore,
    SQLiteDeploymentJournalStore,
)
from synapse.deployment_integrations import DeploymentSandboxWindowsHandoffAdapter


def _setup(tmp_path):
    payload = b"immutable local service revision\n"
    source = tmp_path / "artifact.bin"
    source.write_bytes(payload)
    artifact_fingerprint = ArtifactFingerprintReference(
        "sha256:" + hashlib.sha256(payload).hexdigest()
    )
    policy = PolicyReference("policy:local-service-v1")
    environment = DeploymentEnvironmentOperationalV1(
        DeploymentEnvironmentV1(
            EnvironmentId("deployment-environment:local"),
            "Local",
            EnvironmentClassification.DEVELOPMENT,
            policy,
        ),
        EnvironmentOperationalClass.LOCAL,
        DeploymentTier.NON_CRITICAL,
        (TargetCapabilityKind.PREPARE,),
    )
    binding_ref = AdapterBindingReference("adapter-binding:local-service-v1")
    target = DeploymentTargetOperationalV1(
        DeploymentTargetV1(
            DeploymentTargetId("deployment-target:local-service"),
            environment.environment.environment_id,
            binding_ref,
            DeploymentTargetClass.SERVICE,
        ),
        DeploymentTargetKind.LOCAL_SERVICE,
        SlotCapability.SINGLE_SLOT,
        (
            TargetCapabilityFactV1(
                TargetCapabilityKind.PREPARE,
                True,
                True,
                CapabilityAvailability.AVAILABLE,
                CapabilityReference("capability:local-prepare"),
            ),
        ),
        (CapabilityReference("configuration:local-service-v1"),),
        secret_requirements=(SecretReference("secret-reference:service-account"),),
    )
    artifact = DeploymentArtifactRefV1(
        ArtifactReference("artifact:local-service-v1"),
        artifact_fingerprint,
        ProvenanceReference("provenance:local-build-v1"),
        ArtifactMediaClass.APPLICATION_BUNDLE,
        CustodyReference("custody:local-service-v1"),
        "application/octet-stream",
    )
    desired_revision = DesiredRevisionV1(
        RevisionId("deployment-revision:local-service-v1"), artifact.fingerprint
    )
    desired = DesiredOperationalRevisionV1(
        desired_revision,
        artifact,
        target.configuration_fingerprint,
        (CapabilityReference("configuration:command-v1"),),
        policy,
        "v1",
    )
    release = DeploymentReleaseV1(
        ReleaseId("deployment-release:local-service-v1"),
        DeploymentIntentId("deployment-intent:local-service-v1"),
        DeploymentFingerprint("sha256:" + "1" * 64),
        artifact,
        target.target.target_id,
        desired_revision,
        policy,
    )
    attempt = DeploymentAttemptV1(
        DeploymentAttemptId("deployment-attempt:local-service-v1"),
        release.release_id,
        target.target.target_id,
        desired_revision,
        artifact,
        1,
        policy,
        target.configuration_fingerprint,
        OccurrenceReference("occurrence:local-attempt"),
        CorrelationReference("correlation:local-attempt"),
    )
    correspondence = TargetCorrespondenceRequestV1(
        environment,
        target,
        None,
        desired,
        attempt,
        TargetCapabilityRequirementsV1(
            release.release_id,
            attempt.attempt_id,
            policy,
            (TargetCapabilityKind.PREPARE,),
        ),
        binding_ref,
        target.configuration_fingerprint,
    )
    entrypoint = CapabilityReference("command-entrypoint:service")
    resources = CapabilityReference("resource-profile:local-small")
    network = CapabilityReference("network-profile:local-loopback")
    semantic = preparation_semantic_fingerprint(correspondence, entrypoint, resources, None)
    eligibility = ArtifactEligibilityResultV1(
        ArtifactEligibilityOutcome.ELIGIBLE,
        (),
        release.release_id.value,
        attempt.attempt_id.value,
        artifact.artifact.value,
        artifact.fingerprint,
        artifact.fingerprint,
        artifact.custody,
        None,
        None,
        policy,
        attempt.semantic_fingerprint,
        DeploymentFingerprint("sha256:" + "2" * 64),
    )
    owner = RequesterReference("subject:local-operator")
    authority_ref = CapabilityReference("authority:deployment-fencing")
    scope = DeploymentFencingScopeV1(
        DeploymentFencingScopeKind.TARGET, target_id=target.target.target_id
    )
    sqlite = DeploymentSQLiteConfig((tmp_path / "deployment.sqlite3").resolve())
    authority_store = SQLiteDeploymentAuthorityStore(sqlite)
    authority_store.initialize()
    authority = DeploymentFencingAuthority(authority_store)
    token = authority.transition(
        DeploymentFencingTransitionRequestV1(
            scope,
            owner,
            authority_ref,
            0,
            OccurrenceReference("occurrence:preparation-fencing"),
            semantic,
        )
    )
    idempotency = DeploymentIdempotencyRequestV1(
        DeploymentMutationClass.REVISION_PREPARATION,
        scope,
        DeploymentIdempotencyKey("deployment-idempotency:local-preparation"),
        semantic,
        OccurrenceReference("occurrence:preparation-idempotency"),
    )
    request = LocalRevisionPreparationRequestV1(
        correspondence,
        eligibility,
        LocalRevisionPreparationAuthorizationV1(
            AuthorizationReference("authorization:local-preparation"),
            owner,
            release.release_id,
            attempt.attempt_id,
            environment.environment.environment_id,
            target.target.target_id,
            artifact.artifact.value,
            artifact.fingerprint.value,
            desired.desired_revision.revision_id,
            policy,
            semantic,
            True,
        ),
        token,
        idempotency,
        authority_ref,
        entrypoint,
        resources,
        None,
        True,
        OccurrenceReference("occurrence:preparation"),
    )
    adapter = LocalServicePreparationAdapter(
        LocalServiceAdapterBindingV1(
            binding_ref,
            (tmp_path / "deployment-root").resolve(),
            ((artifact.artifact.value, source.resolve()),),
            entrypoint,
            resources,
            (network,),
        ),
        authority,
        SQLiteDeploymentJournalStore(sqlite),
    )
    return adapter, request, authority, source


def _rebind(request, correspondence, authority, suffix: str):
    assert request.fencing_token is not None
    semantic = preparation_semantic_fingerprint(
        correspondence,
        request.command_entrypoint,
        request.resource_profile,
        request.network_profile,
    )
    token = authority.transition(
        DeploymentFencingTransitionRequestV1(
            request.idempotency.scope,
            request.authorization.requester,
            request.fencing_authority,
            request.fencing_token.generation.value,
            OccurrenceReference(f"occurrence:rebind-{suffix}"),
            semantic,
        )
    )
    return replace(
        request,
        correspondence=correspondence,
        authorization=replace(request.authorization, semantic_fingerprint=semantic),
        fencing_token=token,
        idempotency=replace(
            request.idempotency,
            idempotency_key=DeploymentIdempotencyKey(f"deployment-idempotency:{suffix}"),
            semantic_fingerprint=semantic,
        ),
    )


def test_controlled_local_smoke_prepares_atomic_revision_and_dry_sandbox_handoff(tmp_path) -> None:
    adapter, request, _, _ = _setup(tmp_path)
    result = adapter.prepare(request)
    assert result.outcome is LocalRevisionPreparationOutcome.PREPARED
    assert result.preparation_reference is not None
    assert result.prepared_revision_reference is not None
    assert not result.active
    assert not result.sandbox_executed
    root = tmp_path / "deployment-root"
    assert (root / "revisions/local-service-v1/content/artifact").is_file()
    assert (root / "runtime-state/local-service-v1").is_dir()
    assert (root / "logs/local-service-v1").is_dir()
    assert not (root / "temporary/local-service-v1.preparing").exists()
    handoff = DeploymentSandboxWindowsHandoffAdapter().translate(result)
    assert handoff is not None
    assert handoff.sandbox_fencing_required
    assert handoff.sandbox_fencing_reference is None
    assert not handoff.execution_requested
    assert not handoff.target_activation_requested
    assert tuple(item.value for item in handoff.secret_references) == (
        "secret-reference:service-account",
    )
    assert not any(hasattr(item, "secret_value") for item in handoff.secret_references)


def test_same_preparation_is_idempotent_and_replay_only_inspects(tmp_path) -> None:
    adapter, request, _, _ = _setup(tmp_path)
    assert adapter.prepare(request).outcome is LocalRevisionPreparationOutcome.PREPARED
    assert adapter.prepare(request).outcome is LocalRevisionPreparationOutcome.ALREADY_PREPARED
    assert adapter.inspect(request).outcome is LocalRevisionPreparationOutcome.ALREADY_PREPARED


def test_unsupported_target_wrong_binding_and_stale_eligibility_make_zero_mutation(
    tmp_path,
) -> None:
    adapter, request, authority, _ = _setup(tmp_path)
    unsupported_correspondence = replace(
        request.correspondence,
        target=replace(request.correspondence.target, kind=DeploymentTargetKind.REMOTE_SERVICE),
    )
    unsupported = _rebind(request, unsupported_correspondence, authority, "unsupported")
    assert (
        adapter.prepare(unsupported).failure is LocalRevisionPreparationFailure.UNSUPPORTED_TARGET
    )
    wrong_binding = replace(
        request.correspondence,
        expected_adapter_binding=AdapterBindingReference("adapter-binding:other"),
    )
    mismatched = _rebind(unsupported, wrong_binding, authority, "wrong-binding")
    assert adapter.prepare(mismatched).failure is LocalRevisionPreparationFailure.REVISION_MISMATCH
    stale_base = _rebind(mismatched, request.correspondence, authority, "stale")
    stale = replace(
        stale_base,
        eligibility=replace(stale_base.eligibility, outcome=ArtifactEligibilityOutcome.STALE),
    )
    assert adapter.prepare(stale).failure is LocalRevisionPreparationFailure.ELIGIBILITY_STALE
    assert not (tmp_path / "deployment-root").exists()


def test_invalid_authorization_and_stale_fencing_make_zero_mutation(tmp_path) -> None:
    adapter, request, authority, _ = _setup(tmp_path)
    invalid = replace(
        request,
        authorization=replace(request.authorization, current=False),
    )
    assert adapter.prepare(invalid).failure is LocalRevisionPreparationFailure.AUTHORIZATION_INVALID
    authority.transition(
        DeploymentFencingTransitionRequestV1(
            request.idempotency.scope,
            RequesterReference("subject:other-owner"),
            request.fencing_authority,
            1,
            OccurrenceReference("occurrence:fencing-transfer"),
            request.semantic_fingerprint,
        )
    )
    assert (
        adapter.prepare(request).failure
        is LocalRevisionPreparationFailure.FENCING_STALE_OR_UNAVAILABLE
    )
    assert not (tmp_path / "deployment-root").exists()


def test_fingerprint_mismatch_leaves_reconciliation_fact_not_prepared(tmp_path) -> None:
    adapter, request, _, source = _setup(tmp_path)
    source.write_bytes(b"tampered")
    result = adapter.prepare(request)
    assert result.outcome is LocalRevisionPreparationOutcome.OUTCOME_UNKNOWN
    assert result.failure is LocalRevisionPreparationFailure.FINGERPRINT_VERIFICATION_FAILED
    assert (tmp_path / "deployment-root/temporary/local-service-v1.preparing").exists()
    assert not (tmp_path / "deployment-root/revisions/local-service-v1").exists()


def test_same_idempotency_key_with_changed_preparation_is_contradiction(tmp_path) -> None:
    adapter, request, authority, _ = _setup(tmp_path)
    assert adapter.prepare(request).outcome is LocalRevisionPreparationOutcome.PREPARED
    network = CapabilityReference("network-profile:local-loopback")
    semantic = preparation_semantic_fingerprint(
        request.correspondence,
        request.command_entrypoint,
        request.resource_profile,
        network,
    )
    assert request.fencing_token is not None
    token = authority.transition(
        DeploymentFencingTransitionRequestV1(
            request.idempotency.scope,
            request.authorization.requester,
            request.fencing_authority,
            request.fencing_token.generation.value,
            OccurrenceReference("occurrence:network-rebind"),
            semantic,
        )
    )
    contradictory = replace(
        request,
        authorization=replace(request.authorization, semantic_fingerprint=semantic),
        fencing_token=token,
        idempotency=replace(request.idempotency, semantic_fingerprint=semantic),
        network_profile=network,
    )
    result = adapter.prepare(contradictory)
    assert result.failure is LocalRevisionPreparationFailure.PREPARATION_CONFLICT


def test_cleanup_requires_current_authority_and_no_repository_mutation(tmp_path) -> None:
    adapter, request, authority, source = _setup(tmp_path)
    source.write_bytes(b"tampered")
    adapter.prepare(request)
    authority.transition(
        DeploymentFencingTransitionRequestV1(
            request.idempotency.scope,
            RequesterReference("subject:other-owner"),
            request.fencing_authority,
            1,
            OccurrenceReference("occurrence:cleanup-transfer"),
            request.semantic_fingerprint,
        )
    )
    assert not adapter.cleanup_temporary(request)
    assert not hasattr(adapter, "repository")
    assert not hasattr(adapter, "activate")


def test_current_authority_can_cleanup_residual_without_replay(tmp_path) -> None:
    adapter, request, _, source = _setup(tmp_path)
    source.write_bytes(b"tampered")
    adapter.prepare(request)
    assert adapter.cleanup_temporary(request)
    assert not (tmp_path / "deployment-root/temporary/local-service-v1.preparing").exists()
