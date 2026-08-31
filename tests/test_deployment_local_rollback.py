from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from synapse.deployment import (
    ArtifactEligibilityOutcome,
    ArtifactFingerprintReference,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    DeploymentFencingScopeKind,
    DeploymentFencingScopeV1,
    DeploymentFencingTransitionRequestV1,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentIdempotencyRequestV1,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentMutationClass,
    DeploymentRollbackAttemptV1,
    EvidenceReference,
    LocalDeploymentVerifier,
    LocalObservationOutcome,
    LocalProcessObservationFactV1,
    LocalProcessState,
    LocalRollbackApplyRequestV1,
    LocalRollbackAuthorizationV1,
    LocalRollbackFailure,
    LocalRollbackOutcome,
    LocalRollbackPreparationOutcome,
    LocalRollbackPreparationRequestV1,
    LocalVerificationOutcome,
    LocalVerificationPolicyV1,
    OccurrenceReference,
    PolicyReference,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RollbackLifecycleState,
    SandboxLocalApplyCommandV1,
    SandboxLocalApplyOutcome,
    SandboxLocalApplyResultV1,
    content_fingerprint,
    local_rollback_apply_semantic_fingerprint,
    local_rollback_preparation_semantic_fingerprint,
)
from synapse.deployment_adapters import (
    LocalObservationConfigV1,
    LocalRollbackAdapterConfigV1,
    LocalRollbackPreparationAdapter,
    LocalRollbackStateAdapter,
    LocalTargetObserver,
)
from synapse.deployment_integrations import LocalRollbackOrchestrator
from test_deployment_local_apply import _apply_setup

NOW = datetime(2026, 8, 15, 15, tzinfo=timezone.utc)


class Sandbox:
    def __init__(self, outcome=SandboxLocalApplyOutcome.STARTED, codes=()) -> None:
        self.outcome = outcome
        self.codes = codes
        self.calls = 0

    def start(self, command: SandboxLocalApplyCommandV1) -> SandboxLocalApplyResultV1:
        self.calls += 1
        return SandboxLocalApplyResultV1(
            self.outcome,
            CapabilityReference("sandbox-execution:rollback")
            if self.outcome is not SandboxLocalApplyOutcome.FAILED
            else None,
            self.outcome is not SandboxLocalApplyOutcome.FAILED,
            self.outcome is SandboxLocalApplyOutcome.STARTED,
            self.codes,
        )


class ProcessFacts:
    def __init__(self, state=LocalProcessState.RUNNING) -> None:
        self.state = state
        self.calls = 0

    def observe(self, execution_reference: str | None) -> LocalProcessObservationFactV1:
        self.calls += 1
        return LocalProcessObservationFactV1(
            self.state,
            execution_reference,
            True if self.state is LocalProcessState.RUNNING else None,
        )


class CurrentAuthorization:
    def __init__(self, values=(True,)) -> None:
        self.values = values
        self.calls = 0

    def validate(self, request) -> bool:
        del request
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


def _rollback_setup(tmp_path, *, sandbox=None, eligibility_outcome=None, authorization=None):
    apply, deployment_request, fencing, _, _, _, journal = _apply_setup(tmp_path)
    applied = apply.apply(deployment_request)
    assert applied.receipt is not None
    source = tmp_path / "rollback-a.bin"
    content = b"explicit rollback revision A\n"
    source.write_bytes(content)
    artifact = ArtifactReference("artifact:local-service-rollback-a")
    artifact_fp = ArtifactFingerprintReference("sha256:" + hashlib.sha256(content).hexdigest())
    revision_a = RevisionId("deployment-revision:local-service-a")
    revision_b = applied.receipt.applied_revision
    rollback = DeploymentRollbackAttemptV1(
        RollbackAttemptId("deployment-rollback-attempt:local-a"),
        deployment_request.preparation_request.correspondence.attempt.release_id,
        deployment_request.preparation_request.correspondence.target.target.target_id,
        revision_b,
        revision_a,
        AuthorizationReference("authorization:rollback-local-a"),
        OccurrenceReference("occurrence:rollback-request"),
    )
    scope = DeploymentFencingScopeV1(
        DeploymentFencingScopeKind.ROLLBACK_ATTEMPT,
        release_id=rollback.release_id,
        target_id=rollback.target_id,
        rollback_attempt_id=rollback.rollback_attempt_id,
        source_revision=revision_b,
        intended_revision=revision_a,
    )
    revision_fp = DeploymentFingerprint(content_fingerprint((revision_a, artifact_fp)))
    target_fp = deployment_request.preparation_request.correspondence.target.configuration_fingerprint
    eligibility_semantic = DeploymentFingerprint("sha256:" + "a" * 64)
    eligibility = replace(
        deployment_request.preparation_request.eligibility,
        outcome=eligibility_outcome or ArtifactEligibilityOutcome.ELIGIBLE,
        artifact_reference=artifact.value,
        expected_fingerprint=artifact_fp,
        observed_fingerprint=artifact_fp,
        provenance_evidence_reference=EvidenceReference("evidence:rollback-provenance-a"),
        semantic_fingerprint=eligibility_semantic,
    )
    authority = deployment_request.deployment_fencing_authority
    requester = RequesterReference("subject:rollback-operator")
    command_entrypoint = CapabilityReference("command-entrypoint:service")
    resource_profile = CapabilityReference("resource-profile:local-small")
    semantic = local_rollback_preparation_semantic_fingerprint(
        rollback, applied.receipt.environment_reference, artifact, artifact_fp,
        revision_fp, target_fp, eligibility.policy_reference,
        command_entrypoint, resource_profile,
    )
    placeholder_auth = LocalRollbackAuthorizationV1(
        rollback.authorization_reference, requester, rollback.rollback_attempt_id.value,
        rollback.target_id.value, revision_b, revision_a,
        semantic, True,
    )
    placeholder_idem = DeploymentIdempotencyRequestV1(
        DeploymentMutationClass.ROLLBACK_REQUEST, scope,
        DeploymentIdempotencyKey("deployment-idempotency:rollback-prepare-a"),
        semantic,
        OccurrenceReference("occurrence:rollback-prepare-idempotency"),
    )
    provisional = LocalRollbackPreparationRequestV1(
        rollback, applied.receipt.environment_reference, artifact, artifact_fp,
        revision_fp, target_fp, eligibility, eligibility_semantic,
        eligibility.policy_reference, placeholder_auth, None, placeholder_idem,
        authority, command_entrypoint,
        resource_profile,
        OccurrenceReference("occurrence:rollback-prepare"),
    )
    auth = placeholder_auth
    token = fencing.transition(DeploymentFencingTransitionRequestV1(
        scope, requester, authority, 0,
        OccurrenceReference("occurrence:rollback-prep-fencing"), semantic,
    ))
    prep_request = replace(
        provisional,
        authorization=auth,
        fencing_token=token,
        idempotency=replace(placeholder_idem, semantic_fingerprint=semantic),
    )
    config = LocalRollbackAdapterConfigV1(
        tmp_path / "rollback-materialized",
        tmp_path / "deployment-root/active-state",
        ((artifact.value, source),),
    )
    prep_adapter = LocalRollbackPreparationAdapter(config, fencing)
    state = LocalRollbackStateAdapter(config)
    sandbox = sandbox or Sandbox()
    orchestrator = LocalRollbackOrchestrator(
        fencing,
        authorization or CurrentAuthorization(),
        prep_adapter,
        sandbox,
        state,
        journal,
    )
    return orchestrator, prep_request, fencing, state, sandbox, journal, config


def _apply_request(prep_request, prep_result, fencing):
    sandbox_auth = CapabilityReference("sandbox-authority:rollback")
    sandbox_fence = CapabilityReference("sandbox-fencing:rollback-generation-1")
    semantic = local_rollback_apply_semantic_fingerprint(
        prep_request, prep_result, sandbox_auth, sandbox_fence
    )
    auth = replace(prep_request.authorization, semantic_fingerprint=semantic)
    token = fencing.transition(DeploymentFencingTransitionRequestV1(
        prep_request.idempotency.scope, auth.requester, prep_request.fencing_authority,
        prep_request.fencing_token.generation.value,
        OccurrenceReference("occurrence:rollback-apply-fencing"), semantic,
    ))
    idem = DeploymentIdempotencyRequestV1(
        DeploymentMutationClass.ROLLBACK_APPLY, prep_request.idempotency.scope,
        DeploymentIdempotencyKey("deployment-idempotency:rollback-apply-a"), semantic,
        OccurrenceReference("occurrence:rollback-apply-idempotency"),
    )
    return LocalRollbackApplyRequestV1(
        prep_request, prep_result, auth, token, idem, prep_request.fencing_authority,
        sandbox_auth, sandbox_fence, OccurrenceReference("occurrence:rollback-apply"),
    )


def test_controlled_smoke_b_to_explicit_a_observed_and_verified(tmp_path) -> None:
    orchestrator, prep_request, fencing, _, sandbox, journal, config = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep_request)
    assert prepared.outcome is LocalRollbackPreparationOutcome.PREPARED
    apply_request = _apply_request(prep_request, prepared, fencing)
    result = orchestrator.apply(apply_request)
    assert result.outcome is LocalRollbackOutcome.ROLLED_BACK
    assert result.receipt is not None and not result.receipt.verified
    assert result.receipt.source_revision != result.receipt.intended_revision
    observer = LocalTargetObserver(
        LocalObservationConfigV1(config.active_state_root), ProcessFacts(), lambda: NOW
    )
    observation, verification = orchestrator.observe_and_verify(
        apply_request, result.receipt, observer, LocalDeploymentVerifier(),
        LocalVerificationPolicyV1(
            PolicyReference("policy:rollback-verification"), process_running_required=True
        ), NOW,
    )
    assert observation.outcome is LocalObservationOutcome.OBSERVED
    assert verification.outcome is LocalVerificationOutcome.VERIFIED
    assert sandbox.calls == 1
    active = json.loads((config.active_state_root / "active.json").read_text(encoding="utf-8"))
    assert active["desired_revision"] == prep_request.rollback.intended_revision.value
    machine = DeploymentMachineKey(DeploymentMachineKind.ROLLBACK, prep_request.rollback.rollback_attempt_id.value)
    assert [record.event.resulting_state for record in journal.history(machine)][-2:] == [
        RollbackLifecycleState.VERIFYING, RollbackLifecycleState.VERIFIED
    ]


@pytest.mark.parametrize("outcome", [ArtifactEligibilityOutcome.UNAVAILABLE, ArtifactEligibilityOutcome.STALE, ArtifactEligibilityOutcome.INELIGIBLE])
def test_unavailable_stale_or_ineligible_previous_revision_blocks_before_apply(tmp_path, outcome) -> None:
    orchestrator, request, _, _, sandbox, _, config = _rollback_setup(
        tmp_path, eligibility_outcome=outcome
    )
    result = orchestrator.prepare(request)
    assert result.failure is LocalRollbackFailure.ELIGIBILITY_INVALID
    assert sandbox.calls == 0
    assert not (config.revision_root / "revisions").exists()


def test_wrong_artifact_and_rollback_specific_authorization_fail_closed(tmp_path) -> None:
    orchestrator, request, _, _, sandbox, _, _ = _rollback_setup(tmp_path)
    wrong = replace(
        request,
        eligibility=replace(request.eligibility, artifact_reference="artifact:wrong"),
    )
    assert orchestrator.preparation.prepare(wrong).failure is LocalRollbackFailure.ELIGIBILITY_INVALID
    invalid_auth = replace(request, authorization=replace(request.authorization, current=False))
    assert orchestrator.prepare(invalid_auth).failure is LocalRollbackFailure.AUTHORIZATION_INVALID
    assert sandbox.calls == 0


def test_stale_fencing_has_zero_next_mutation(tmp_path) -> None:
    orchestrator, request, fencing, _, sandbox, _, config = _rollback_setup(tmp_path)
    token = request.fencing_token
    fencing.transition(DeploymentFencingTransitionRequestV1(
        request.idempotency.scope, RequesterReference("subject:new-owner"),
        request.fencing_authority, token.generation.value,
        OccurrenceReference("occurrence:rollback-transfer"), request.semantic_fingerprint,
    ))
    assert orchestrator.preparation.prepare(request).failure is LocalRollbackFailure.FENCING_INVALID
    assert sandbox.calls == 0
    assert not (config.revision_root / "revisions").exists()


def test_preparation_unavailable_and_contradictory_idempotency_are_explicit(tmp_path) -> None:
    orchestrator, request, fencing, _, _, _, config = _rollback_setup(tmp_path)
    source = config.artifact_sources[0][1]
    source.unlink()
    assert orchestrator.preparation.prepare(request).outcome is LocalRollbackPreparationOutcome.UNAVAILABLE
    source.write_bytes(b"explicit rollback revision A\n")
    first = orchestrator.preparation.prepare(request)
    assert first.outcome is LocalRollbackPreparationOutcome.PREPARED
    alternate_resource = CapabilityReference("resource-profile:local-other")
    semantic = local_rollback_preparation_semantic_fingerprint(
        request.rollback, request.environment_reference, request.artifact,
        request.artifact_fingerprint, request.revision_fingerprint,
        request.target_configuration_fingerprint, request.eligibility_policy_reference,
        request.command_entrypoint, alternate_resource,
    )
    auth = replace(request.authorization, semantic_fingerprint=semantic)
    token = fencing.transition(DeploymentFencingTransitionRequestV1(
        request.idempotency.scope, auth.requester, request.fencing_authority,
        request.fencing_token.generation.value,
        OccurrenceReference("occurrence:rollback-contradiction-fencing"), semantic,
    ))
    contradictory = replace(
        request,
        resource_profile=alternate_resource,
        authorization=auth,
        fencing_token=token,
        idempotency=replace(request.idempotency, semantic_fingerprint=semantic),
    )
    assert orchestrator.preparation.prepare(contradictory).failure is LocalRollbackFailure.IDEMPOTENCY_CONTRADICTION


@pytest.mark.parametrize(
    ("sandbox_outcome", "codes", "expected"),
    [
        (SandboxLocalApplyOutcome.FAILED, ("sandbox-authority-invalid",), LocalRollbackOutcome.FAILED),
        (SandboxLocalApplyOutcome.FAILED, ("process-failed",), LocalRollbackOutcome.FAILED),
        (SandboxLocalApplyOutcome.PARTIAL, (), LocalRollbackOutcome.PARTIALLY_ROLLED_BACK),
        (SandboxLocalApplyOutcome.UNKNOWN, (), LocalRollbackOutcome.OUTCOME_UNKNOWN),
    ],
)
def test_apply_failures_partial_and_unknown_are_factual(tmp_path, sandbox_outcome, codes, expected) -> None:
    orchestrator, prep, fencing, _, _, _, _ = _rollback_setup(
        tmp_path, sandbox=Sandbox(sandbox_outcome, codes)
    )
    prepared = orchestrator.prepare(prep)
    result = orchestrator.apply(_apply_request(prep, prepared, fencing))
    assert result.outcome is expected
    assert not result.verified


def test_repeated_proven_rollback_is_idempotent_and_unknown_is_not_retried(tmp_path) -> None:
    orchestrator, prep, fencing, _, sandbox, _, _ = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep)
    request = _apply_request(prep, prepared, fencing)
    first = orchestrator.apply(request)
    second = orchestrator.apply(request)
    assert second.receipt == first.receipt
    assert sandbox.calls == 1


def test_authorization_invalidated_mid_flow_stops_next_effect(tmp_path) -> None:
    authorization = CurrentAuthorization((True, True, False))
    orchestrator, prep, fencing, _, sandbox, _, config = _rollback_setup(
        tmp_path, authorization=authorization
    )
    prepared = orchestrator.prepare(prep)
    result = orchestrator.apply(_apply_request(prep, prepared, fencing))
    assert result.outcome is LocalRollbackOutcome.OUTCOME_UNKNOWN
    assert sandbox.calls == 0
    active = json.loads((config.active_state_root / "active.json").read_text(encoding="utf-8"))
    assert active["desired_revision"] == prep.rollback.source_revision.value


def test_fencing_changes_after_sandbox_start_prevent_active_pointer_mutation(tmp_path) -> None:
    orchestrator, prep, fencing, _, _, journal, config = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep)
    request = _apply_request(prep, prepared, fencing)

    class TransferOnStart(Sandbox):
        def start(self, command):
            result = super().start(command)
            fencing.transition(DeploymentFencingTransitionRequestV1(
                request.idempotency.scope, RequesterReference("subject:rollback-new-owner"),
                request.fencing_authority, request.fencing_token.generation.value,
                OccurrenceReference("occurrence:rollback-midflow-transfer"),
                request.semantic_fingerprint,
            ))
            return result

    raced = LocalRollbackOrchestrator(
        fencing, CurrentAuthorization(), orchestrator.preparation,
        TransferOnStart(), orchestrator.active_state, journal,
    )
    result = raced.apply(request)
    assert result.outcome is LocalRollbackOutcome.PARTIALLY_ROLLED_BACK
    active = json.loads((config.active_state_root / "active.json").read_text(encoding="utf-8"))
    assert active["desired_revision"] == prep.rollback.source_revision.value


def test_restart_during_rolling_back_requires_reconciliation_without_retry(tmp_path) -> None:
    orchestrator, prep, fencing, state, sandbox, journal, _ = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep)
    request = _apply_request(prep, prepared, fencing)
    state.stage(request)
    restarted = LocalRollbackOrchestrator(
        fencing, CurrentAuthorization(), orchestrator.preparation, sandbox, state, journal
    )
    result = restarted.apply(request)
    assert result.outcome is LocalRollbackOutcome.OUTCOME_UNKNOWN
    assert result.reconciliation_required
    assert sandbox.calls == 0


def test_negative_smoke_tampered_a_fails_observation_verification(tmp_path) -> None:
    orchestrator, prep, fencing, _, _, _, config = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep)
    request = _apply_request(prep, prepared, fencing)
    result = orchestrator.apply(request)
    assert result.receipt is not None
    active = config.active_state_root / "active.json"
    payload = json.loads(active.read_text(encoding="utf-8"))
    payload["desired_revision"] = "deployment-revision:tampered"
    active.write_text(json.dumps(payload), encoding="utf-8")
    observer = LocalTargetObserver(LocalObservationConfigV1(config.active_state_root), ProcessFacts(), lambda: NOW)
    _, verification = orchestrator.observe_and_verify(
        request, result.receipt, observer, LocalDeploymentVerifier(),
        LocalVerificationPolicyV1(PolicyReference("policy:rollback-verification")), NOW,
    )
    assert verification.outcome is LocalVerificationOutcome.FAILED


def test_rollback_verification_unavailable_is_never_success(tmp_path) -> None:
    orchestrator, prep, fencing, _, _, _, config = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep)
    request = _apply_request(prep, prepared, fencing)
    result = orchestrator.apply(request)
    assert result.receipt is not None
    observer = LocalTargetObserver(
        LocalObservationConfigV1(config.active_state_root),
        ProcessFacts(LocalProcessState.UNAVAILABLE), lambda: NOW,
    )
    _, verification = orchestrator.observe_and_verify(
        request, result.receipt, observer, LocalDeploymentVerifier(),
        LocalVerificationPolicyV1(
            PolicyReference("policy:rollback-verification"), process_running_required=True
        ), NOW,
    )
    assert verification.outcome is LocalVerificationOutcome.UNAVAILABLE


def test_journal_replay_and_history_reads_do_not_reapply_reobserve_or_reverify(tmp_path) -> None:
    orchestrator, prep, fencing, _, sandbox, journal, _ = _rollback_setup(tmp_path)
    prepared = orchestrator.prepare(prep)
    request = _apply_request(prep, prepared, fencing)
    orchestrator.apply(request)
    calls = sandbox.calls
    machine = DeploymentMachineKey(DeploymentMachineKind.ROLLBACK, prep.rollback.rollback_attempt_id.value)
    projection = journal.replay(machine)
    assert projection.state is RollbackLifecycleState.ROLLED_BACK
    assert sandbox.calls == calls
