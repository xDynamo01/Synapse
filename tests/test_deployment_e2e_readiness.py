from __future__ import annotations

import json

from synapse.deployment import (
    DeploymentLifecycleState,
    DeploymentMachineKey,
    DeploymentMachineKind,
    LocalDeploymentVerifier,
    LocalObservationOutcome,
    LocalVerificationOutcome,
    LocalVerificationPolicyV1,
    OccurrenceReference,
    PolicyReference,
    RollbackLifecycleState,
)
from synapse.deployment_adapters import LocalObservationConfigV1, LocalTargetObserver
from synapse.deployment_integrations import LocalIndependentVerificationFlow
from test_deployment_local_rollback import (
    NOW as ROLLBACK_NOW,
)
from test_deployment_local_rollback import (
    ProcessFacts,
    _apply_request,
    _rollback_setup,
)
from test_deployment_local_verification import NOW, _observed, _policy


def test_local_v1_prepare_apply_observe_verify_journey_is_factual(tmp_path) -> None:
    observer, request, journal, runtime = _observed(tmp_path)

    observation, verification = LocalIndependentVerificationFlow(
        observer,
        LocalDeploymentVerifier(),
        journal,
    ).run(
        request,
        _policy(process_running_required=True),
        OccurrenceReference("occurrence:e2e-readiness-verify"),
        NOW,
    )

    assert observation.outcome is LocalObservationOutcome.OBSERVED
    assert observation.observation_reference is not None
    assert verification.outcome is LocalVerificationOutcome.VERIFIED
    assert verification.verification_reference is not None
    assert observation.observation_reference.value != verification.verification_reference.value
    assert runtime.calls == 1

    machine = DeploymentMachineKey(
        DeploymentMachineKind.DEPLOYMENT,
        request.attempt_reference,
    )
    states = [record.event.resulting_state for record in journal.history(machine)]
    assert states[-3:] == [
        DeploymentLifecycleState.APPLIED,
        DeploymentLifecycleState.VERIFYING,
        DeploymentLifecycleState.VERIFIED,
    ]


def test_local_v1_explicit_rollback_reaches_independent_verification(tmp_path) -> None:
    orchestrator, preparation_request, fencing, _, sandbox, journal, config = (
        _rollback_setup(tmp_path)
    )
    preparation = orchestrator.prepare(preparation_request)
    apply_request = _apply_request(preparation_request, preparation, fencing)
    applied = orchestrator.apply(apply_request)
    assert applied.receipt is not None
    assert not applied.receipt.verified

    observer = LocalTargetObserver(
        LocalObservationConfigV1(config.active_state_root),
        ProcessFacts(),
        lambda: ROLLBACK_NOW,
    )
    observation, verification = orchestrator.observe_and_verify(
        apply_request,
        applied.receipt,
        observer,
        LocalDeploymentVerifier(),
        LocalVerificationPolicyV1(
            PolicyReference("policy:rollback-verification"),
            process_running_required=True,
        ),
        ROLLBACK_NOW,
    )

    assert observation.outcome is LocalObservationOutcome.OBSERVED
    assert verification.outcome is LocalVerificationOutcome.VERIFIED
    assert observation.observation_reference is not None
    assert verification.verification_reference is not None
    assert observation.observation_reference.value != verification.verification_reference.value
    assert sandbox.calls == 1

    active = json.loads(
        (config.active_state_root / "active.json").read_text(encoding="utf-8")
    )
    assert active["desired_revision"] == preparation_request.rollback.intended_revision.value
    machine = DeploymentMachineKey(
        DeploymentMachineKind.ROLLBACK,
        preparation_request.rollback.rollback_attempt_id.value,
    )
    states = [record.event.resulting_state for record in journal.history(machine)]
    assert states[-3:] == [
        RollbackLifecycleState.ROLLED_BACK,
        RollbackLifecycleState.VERIFYING,
        RollbackLifecycleState.VERIFIED,
    ]
