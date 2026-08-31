from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from synapse.deployment import (
    LocalDeploymentVerifier,
    LocalObservationOutcome,
    LocalObservationRequestV1,
    LocalProcessObservationFactV1,
    LocalProcessState,
    LocalVerificationOutcome,
    LocalVerificationPolicyV1,
    LocalVerificationRequestV1,
    OccurrenceReference,
    PolicyReference,
)
from synapse.deployment_adapters import LocalObservationConfigV1, LocalTargetObserver
from synapse.deployment_integrations import LocalIndependentVerificationFlow
from test_deployment_local_apply import _apply_setup

NOW = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)


class RuntimeFacts:
    def __init__(self, fact: LocalProcessObservationFactV1) -> None:
        self.fact = fact
        self.calls = 0

    def observe(self, execution_reference: str | None) -> LocalProcessObservationFactV1:
        self.calls += 1
        assert execution_reference is None or execution_reference.startswith("sandbox-execution:")
        return self.fact


class UnavailableRuntime:
    def observe(self, execution_reference: str | None) -> LocalProcessObservationFactV1:
        del execution_reference
        raise OSError("controlled observer unavailable")


def _observed(tmp_path, runtime=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    orchestrator, apply_request, _, _, _, _, journal = _apply_setup(tmp_path)
    applied = orchestrator.apply(apply_request)
    assert applied.receipt is not None
    runtime = runtime or RuntimeFacts(
        LocalProcessObservationFactV1(LocalProcessState.RUNNING, "process:controlled", True)
    )
    observer = LocalTargetObserver(
        LocalObservationConfigV1(tmp_path / "deployment-root/active-state"),
        runtime,
        lambda: NOW,
    )
    correspondence = apply_request.preparation_request.correspondence
    request = LocalObservationRequestV1(
        applied.receipt.release_reference,
        applied.receipt.attempt_reference,
        applied.receipt.target_reference,
        applied.receipt.environment_reference,
        applied.receipt.applied_revision,
        apply_request.preparation_result.revision_fingerprint,
        applied.receipt.sandbox_execution_reference.value,
        correspondence.target.target.slot_id.value if correspondence.target.target.slot_id else None,
        PolicyReference("policy:local-verification"),
    )
    return observer, request, journal, runtime


def _policy(**changes):
    return replace(
        LocalVerificationPolicyV1(PolicyReference("policy:local-verification")),
        **changes,
    )


def test_controlled_smoke_applied_observed_verified_and_read_only(tmp_path) -> None:
    observer, request, journal, runtime = _observed(tmp_path)
    active = tmp_path / "deployment-root/active-state/active.json"
    before = active.read_bytes()
    observation, result = LocalIndependentVerificationFlow(
        observer, LocalDeploymentVerifier(), journal
    ).run(request, _policy(process_running_required=True), OccurrenceReference("occurrence:verify"), NOW)
    assert observation.outcome is LocalObservationOutcome.OBSERVED
    assert observation.observed_revision is not None
    assert result.outcome is LocalVerificationOutcome.VERIFIED
    assert result.verification_reference is not None
    assert active.read_bytes() == before
    assert runtime.calls == 1


def test_apply_receipt_alone_cannot_verify_and_observer_emits_no_verification(tmp_path) -> None:
    observer, request, _, _ = _observed(tmp_path)
    observation = observer.observe(request)
    assert not hasattr(observation, "verification_reference")
    assert observation.observation_reference is not None


@pytest.mark.parametrize(
    ("state", "expected", "reason"),
    [
        (LocalProcessState.RUNNING, LocalVerificationOutcome.VERIFIED, "required-facts-correspond"),
        (LocalProcessState.ABSENT, LocalVerificationOutcome.FAILED, "process-absent"),
        (LocalProcessState.UNAVAILABLE, LocalVerificationOutcome.UNAVAILABLE, "process-state-unavailable"),
        (LocalProcessState.INDETERMINATE, LocalVerificationOutcome.INDETERMINATE, "observation-indeterminate"),
    ],
)
def test_process_policy_preserves_running_absent_unavailable_and_indeterminate(
    tmp_path, state, expected, reason
) -> None:
    observer, request, _, _ = _observed(
        tmp_path, RuntimeFacts(LocalProcessObservationFactV1(state))
    )
    observation = observer.observe(request)
    result = LocalDeploymentVerifier().verify(LocalVerificationRequestV1(
        request.release_reference, request.attempt_reference, request.target_reference,
        request.environment_reference, request.desired_revision,
        request.desired_revision_fingerprint, request.slot_reference, observation,
        _policy(process_running_required=True), observer.current_fingerprint(), NOW,
    ))
    assert result.outcome is expected
    assert reason in result.reasons


def test_revision_mismatch_fails_but_revision_match_needs_required_runtime(tmp_path) -> None:
    observer, request, _, _ = _observed(
        tmp_path,
        RuntimeFacts(LocalProcessObservationFactV1(LocalProcessState.UNAVAILABLE)),
    )
    active = tmp_path / "deployment-root/active-state/active.json"
    payload = json.loads(active.read_text(encoding="utf-8"))
    payload["desired_revision"] = "deployment-revision:tampered"
    active.write_text(json.dumps(payload), encoding="utf-8")
    observation = observer.observe(request)
    verifier_request = LocalVerificationRequestV1(
        request.release_reference, request.attempt_reference, request.target_reference,
        request.environment_reference, request.desired_revision,
        request.desired_revision_fingerprint, request.slot_reference, observation,
        _policy(process_running_required=True), observer.current_fingerprint(), NOW,
    )
    result = LocalDeploymentVerifier().verify(verifier_request)
    assert result.outcome is LocalVerificationOutcome.FAILED
    assert "revision-mismatch" in result.reasons


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ({"target_reference": "deployment-target:other"}, "target-mismatch"),
        ({"environment_reference": "deployment-environment:other"}, "environment-mismatch"),
        ({"revision_fingerprint": "sha256:" + "0" * 64}, "revision-fingerprint-mismatch"),
    ],
)
def test_target_environment_and_fingerprint_mismatch_fail(tmp_path, mutation, expected_reason) -> None:
    observer, request, _, _ = _observed(tmp_path)
    active = tmp_path / "deployment-root/active-state/active.json"
    payload = json.loads(active.read_text(encoding="utf-8"))
    payload.update(mutation)
    active.write_text(json.dumps(payload), encoding="utf-8")
    observation = observer.observe(request)
    result = LocalDeploymentVerifier().verify(LocalVerificationRequestV1(
        request.release_reference, request.attempt_reference, request.target_reference,
        request.environment_reference, request.desired_revision,
        request.desired_revision_fingerprint, request.slot_reference, observation,
        _policy(), observer.current_fingerprint(), NOW,
    ))
    assert result.outcome is LocalVerificationOutcome.FAILED
    assert expected_reason in result.reasons


def test_wrong_binding_stale_and_target_change_never_verify(tmp_path) -> None:
    observer, request, _, _ = _observed(tmp_path)
    observation = observer.observe(request)
    base = LocalVerificationRequestV1(
        request.release_reference, request.attempt_reference, request.target_reference,
        request.environment_reference, request.desired_revision,
        request.desired_revision_fingerprint, request.slot_reference, observation,
        _policy(), observer.current_fingerprint(), NOW,
    )
    assert LocalDeploymentVerifier().verify(replace(base, target_reference="deployment-target:other")).outcome is LocalVerificationOutcome.INDETERMINATE
    assert LocalDeploymentVerifier().verify(replace(base, attempt_reference="deployment-attempt:other")).outcome is LocalVerificationOutcome.INDETERMINATE
    assert LocalDeploymentVerifier().verify(replace(base, release_reference="deployment-release:other")).outcome is LocalVerificationOutcome.INDETERMINATE
    stale = replace(base, verified_at=NOW + timedelta(seconds=61))
    assert LocalDeploymentVerifier().verify(stale).outcome is LocalVerificationOutcome.INDETERMINATE
    changed = replace(base, current_target_fingerprint=None)
    assert LocalDeploymentVerifier().verify(changed).outcome is LocalVerificationOutcome.INDETERMINATE
    incompatible = replace(
        base,
        policy=replace(base.policy, policy_reference=PolicyReference("policy:other")),
    )
    assert LocalDeploymentVerifier().verify(incompatible).outcome is LocalVerificationOutcome.INDETERMINATE


def test_negative_smoke_target_changed_after_observation_never_succeeds(tmp_path) -> None:
    observer, request, _, _ = _observed(tmp_path)
    observation = observer.observe(request)
    active = tmp_path / "deployment-root/active-state/active.json"
    payload = json.loads(active.read_text(encoding="utf-8"))
    payload["desired_revision"] = "deployment-revision:changed-after-observation"
    active.write_text(json.dumps(payload), encoding="utf-8")
    result = LocalDeploymentVerifier().verify(LocalVerificationRequestV1(
        request.release_reference, request.attempt_reference, request.target_reference,
        request.environment_reference, request.desired_revision,
        request.desired_revision_fingerprint, request.slot_reference, observation,
        _policy(), observer.current_fingerprint(), NOW,
    ))
    assert result.outcome is LocalVerificationOutcome.INDETERMINATE
    assert "target-changed-after-observation" in result.reasons


def test_unavailable_incomplete_and_inconsistent_observation_are_explicit(tmp_path) -> None:
    runtime = RuntimeFacts(LocalProcessObservationFactV1(LocalProcessState.RUNNING))
    root = tmp_path / "active"
    observer = LocalTargetObserver(LocalObservationConfigV1(root), runtime, lambda: NOW)
    _, request, _, _ = _observed(tmp_path / "source")
    assert observer.observe(request).outcome is LocalObservationOutcome.UNAVAILABLE
    root.mkdir(parents=True)
    (root / "active.json").write_text("{}", encoding="utf-8")
    assert observer.observe(request).outcome is LocalObservationOutcome.INDETERMINATE
    (root / "active.json").write_text('{"desired_revision": 1}', encoding="utf-8")
    assert observer.observe(request).outcome is LocalObservationOutcome.INDETERMINATE
    full_invalid = {
        "desired_revision": 1,
        "revision_fingerprint": "invalid",
        "target_reference": request.target_reference,
        "environment_reference": request.environment_reference,
        "semantic_fingerprint": "invalid",
    }
    (root / "active.json").write_text(json.dumps(full_invalid), encoding="utf-8")
    assert observer.observe(request).outcome is LocalObservationOutcome.INCONSISTENT


def test_observer_unavailable_is_not_verification_failure(tmp_path) -> None:
    _, request, _, _ = _observed(tmp_path)
    observer = LocalTargetObserver(
        LocalObservationConfigV1(tmp_path / "deployment-root/active-state"),
        UnavailableRuntime(),
        lambda: NOW,
    )
    observation = observer.observe(request)
    result = LocalDeploymentVerifier().verify(LocalVerificationRequestV1(
        request.release_reference, request.attempt_reference, request.target_reference,
        request.environment_reference, request.desired_revision,
        request.desired_revision_fingerprint, request.slot_reference, observation,
        _policy(process_running_required=True), observer.current_fingerprint(), NOW,
    ))
    assert observation.outcome is LocalObservationOutcome.UNAVAILABLE
    assert result.outcome is LocalVerificationOutcome.UNAVAILABLE


def test_replay_is_passive_and_does_not_reobserve_or_reverify(tmp_path) -> None:
    observer, request, journal, runtime = _observed(tmp_path)
    LocalIndependentVerificationFlow(observer, LocalDeploymentVerifier(), journal).run(
        request, _policy(), OccurrenceReference("occurrence:verify-replay"), NOW
    )
    calls = runtime.calls
    from synapse.deployment import DeploymentMachineKey, DeploymentMachineKind

    machine = DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, request.attempt_reference)
    history = journal.history(machine)
    assert len(history) >= 4
    assert runtime.calls == calls
