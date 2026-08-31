from dataclasses import replace

import pytest

from synapse.deployment import (
    ApplyReceiptReference,
    ArtifactReference,
    AuthorizationReference,
    CapabilityReference,
    CausationReference,
    ContradictoryDeploymentTransition,
    CorrelationReference,
    DeploymentAttemptId,
    DeploymentEventId,
    DeploymentLifecycleState,
    DeploymentStateMismatch,
    DeploymentStateProjection,
    DeploymentTargetId,
    DeploymentTransitionEventV1,
    InvalidDeploymentTransition,
    InvalidRollbackProgression,
    InvalidRolloutProgression,
    MissingDeploymentTransitionReference,
    ObservationReference,
    OccurrenceReference,
    PromotionId,
    PromotionLifecycleState,
    PromotionStateProjection,
    PromotionTransitionEventV1,
    ReleaseId,
    RevisionId,
    RollbackAttemptId,
    RollbackLifecycleState,
    RollbackReceiptReference,
    RollbackStateProjection,
    RollbackTransitionEventV1,
    RolloutId,
    RolloutLifecycleState,
    RolloutStageV1,
    RolloutStateProjection,
    RolloutTransitionEventV1,
    SlotId,
    StateTerminality,
    TransitionFailureClass,
    VerificationReference,
    reduce_deployment,
    reduce_rollback,
    reduce_rollout,
)

RELEASE = ReleaseId("deployment-release:state-machine")
ATTEMPT = DeploymentAttemptId("deployment-attempt:state-machine")
ROLLOUT = RolloutId("deployment-rollout:state-machine")
PROMOTION = PromotionId("deployment-promotion:state-machine")
ROLLBACK = RollbackAttemptId("deployment-rollback-attempt:state-machine")
TARGET = DeploymentTargetId("deployment-target:state-machine")
SOURCE_REVISION = RevisionId("deployment-revision:failed")
ROLLBACK_REVISION = RevisionId("deployment-revision:rollback")


def _event_id(number: int) -> DeploymentEventId:
    return DeploymentEventId(f"deployment-event:{number}")


def _deployment_event(
    number: int,
    prior: DeploymentLifecycleState,
    resulting: DeploymentLifecycleState,
    *,
    authorization: bool = False,
    receipt: bool = False,
    observation: bool = False,
    verification: bool = False,
    failure: TransitionFailureClass | None = None,
) -> DeploymentTransitionEventV1:
    return DeploymentTransitionEventV1(
        event_id=_event_id(number),
        release_id=RELEASE,
        attempt_id=ATTEMPT,
        prior_state=prior,
        resulting_state=resulting,
        correlation=CorrelationReference("correlation:deployment-state-machine"),
        causation=CausationReference(f"causation:{number}"),
        occurrence=OccurrenceReference(f"occurrence:{number}"),
        authorization_reference=(
            AuthorizationReference(f"authorization:{number}") if authorization else None
        ),
        apply_receipt_reference=(
            ApplyReceiptReference(f"apply-receipt:{number}") if receipt else None
        ),
        observation_reference=(
            ObservationReference(f"observation:{number}") if observation else None
        ),
        verification_reference=(
            VerificationReference(f"verification:{number}") if verification else None
        ),
        failure_class=failure,
    )


def _deployment_prefix() -> tuple[DeploymentTransitionEventV1, ...]:
    return (
        _deployment_event(1, DeploymentLifecycleState.PROPOSED, DeploymentLifecycleState.AUTHORIZATION_PENDING),
        _deployment_event(2, DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.AUTHORIZED, authorization=True),
        _deployment_event(3, DeploymentLifecycleState.AUTHORIZED, DeploymentLifecycleState.PREPARED),
        _deployment_event(4, DeploymentLifecycleState.PREPARED, DeploymentLifecycleState.APPLYING),
    )


def test_deployment_happy_path_requires_apply_verify_and_promotion_events() -> None:
    events = (
        *_deployment_prefix(),
        _deployment_event(5, DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLIED, receipt=True),
        _deployment_event(6, DeploymentLifecycleState.APPLIED, DeploymentLifecycleState.VERIFYING),
        _deployment_event(7, DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFIED, observation=True, verification=True),
        _deployment_event(8, DeploymentLifecycleState.VERIFIED, DeploymentLifecycleState.PROMOTION_PENDING),
        _deployment_event(9, DeploymentLifecycleState.PROMOTION_PENDING, DeploymentLifecycleState.PROMOTED),
    )
    applied = DeploymentStateProjection.replay(RELEASE, ATTEMPT, events[:5])
    verified = DeploymentStateProjection.replay(RELEASE, ATTEMPT, events[:7])
    assert applied.state is DeploymentLifecycleState.APPLIED
    assert applied.terminality is StateTerminality.NON_TERMINAL
    assert verified.state is DeploymentLifecycleState.VERIFIED
    assert verified.terminality is StateTerminality.NON_TERMINAL
    assert DeploymentStateProjection.replay(RELEASE, ATTEMPT, events).state is DeploymentLifecycleState.PROMOTED


@pytest.mark.parametrize(
    ("prior", "resulting", "failure", "receipt"),
    (
        (DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.DENIED, TransitionFailureClass.POLICY_DENIED, False),
        (DeploymentLifecycleState.AUTHORIZED, DeploymentLifecycleState.PREPARATION_FAILED, TransitionFailureClass.PRECONDITION_FAILED, False),
        (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLY_FAILED, TransitionFailureClass.EXTERNAL_FAILURE, False),
        (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.PARTIALLY_APPLIED, TransitionFailureClass.PARTIAL_EXTERNAL_EFFECT, True),
        (DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN, TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN, False),
        (DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFICATION_FAILED, TransitionFailureClass.VERIFICATION_MISMATCH, False),
        (DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFICATION_UNAVAILABLE, TransitionFailureClass.EVIDENCE_UNAVAILABLE, False),
        (DeploymentLifecycleState.PROMOTION_PENDING, DeploymentLifecycleState.ROLLBACK_REQUIRED, TransitionFailureClass.EXTERNAL_FAILURE, False),
    ),
)
def test_deployment_lateral_states_remain_factual(prior, resulting, failure, receipt) -> None:
    if prior in {DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.AUTHORIZED}:
        prefix = _deployment_prefix()[: 1 if prior is DeploymentLifecycleState.AUTHORIZATION_PENDING else 2]
    else:
        prefix = _deployment_prefix()
        if prior in {DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.PROMOTION_PENDING}:
            prefix += (
                _deployment_event(5, DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLIED, receipt=True),
                _deployment_event(6, DeploymentLifecycleState.APPLIED, DeploymentLifecycleState.VERIFYING),
            )
        if prior is DeploymentLifecycleState.PROMOTION_PENDING:
            prefix += (
                _deployment_event(7, DeploymentLifecycleState.VERIFYING, DeploymentLifecycleState.VERIFIED, observation=True, verification=True),
                _deployment_event(8, DeploymentLifecycleState.VERIFIED, DeploymentLifecycleState.PROMOTION_PENDING),
            )
    event = _deployment_event(20, prior, resulting, failure=failure, receipt=receipt)
    projection = DeploymentStateProjection.replay(RELEASE, ATTEMPT, (*prefix, event))
    assert projection.state is resulting


def test_deployment_unknown_can_only_record_reconciliation_not_infer_outcome() -> None:
    unknown = DeploymentStateProjection.replay(
        RELEASE,
        ATTEMPT,
        (*_deployment_prefix(), _deployment_event(5, DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN, failure=TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN)),
    )
    reconciled = reduce_deployment(
        unknown,
        _deployment_event(6, DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN, DeploymentLifecycleState.RECONCILIATION_REQUIRED),
    )
    assert unknown.state is DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN
    assert reconciled.state is DeploymentLifecycleState.RECONCILIATION_REQUIRED


def test_deployment_replay_is_deterministic_idempotent_and_detects_contradiction() -> None:
    event = _deployment_prefix()[0]
    once = DeploymentStateProjection.replay(RELEASE, ATTEMPT, (event,))
    twice = DeploymentStateProjection.replay(RELEASE, ATTEMPT, (event, event))
    assert once == twice
    assert once == DeploymentStateProjection.replay(RELEASE, ATTEMPT, (event,))
    contradictory = replace(event, resulting_state=DeploymentLifecycleState.DENIED)
    with pytest.raises(ContradictoryDeploymentTransition):
        reduce_deployment(once, contradictory)


def test_deployment_rejects_shortcuts_mismatch_and_missing_typed_evidence() -> None:
    projection = DeploymentStateProjection(RELEASE, ATTEMPT)
    with pytest.raises(InvalidDeploymentTransition):
        reduce_deployment(projection, _deployment_event(1, DeploymentLifecycleState.PROPOSED, DeploymentLifecycleState.APPLIED, receipt=True))
    with pytest.raises(DeploymentStateMismatch):
        reduce_deployment(projection, replace(_deployment_prefix()[0], release_id=ReleaseId("deployment-release:other")))
    pending = reduce_deployment(projection, _deployment_prefix()[0])
    with pytest.raises(MissingDeploymentTransitionReference):
        reduce_deployment(pending, _deployment_event(2, DeploymentLifecycleState.AUTHORIZATION_PENDING, DeploymentLifecycleState.AUTHORIZED))
    with pytest.raises(MissingDeploymentTransitionReference):
        replace(
            _deployment_event(
                3,
                DeploymentLifecycleState.VERIFYING,
                DeploymentLifecycleState.VERIFIED,
                observation=True,
                verification=True,
            ),
            verification_reference=ApplyReceiptReference("apply-receipt:wrong-type"),
        )


def _rollout_event(
    number: int,
    prior: RolloutLifecycleState,
    resulting: RolloutLifecycleState,
    *,
    authorization: bool = False,
    stage: RolloutStageV1 | None = None,
    failure: TransitionFailureClass | None = None,
) -> RolloutTransitionEventV1:
    return RolloutTransitionEventV1(
        _event_id(number), ROLLOUT, RELEASE, prior, resulting,
        CorrelationReference("correlation:rollout"), CausationReference(f"causation:rollout-{number}"),
        OccurrenceReference(f"occurrence:rollout-{number}"),
        AuthorizationReference(f"authorization:rollout-{number}") if authorization else None,
        stage, failure,
    )


def test_rollout_progresses_pauses_resumes_and_does_not_create_promotion() -> None:
    stage = RolloutStageV1(1, CapabilityReference("stage:first"), SlotId("deployment-slot:blue"), 10, CapabilityReference("gate:health"))
    events = (
        _rollout_event(31, RolloutLifecycleState.PLANNED, RolloutLifecycleState.AUTHORIZED, authorization=True),
        _rollout_event(32, RolloutLifecycleState.AUTHORIZED, RolloutLifecycleState.IN_PROGRESS, stage=stage),
        _rollout_event(33, RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.PAUSED),
        _rollout_event(34, RolloutLifecycleState.PAUSED, RolloutLifecycleState.IN_PROGRESS, stage=stage),
        _rollout_event(35, RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.COMPLETED, stage=replace(stage, sequence=2, abstract_percentage=100)),
    )
    projection = RolloutStateProjection.replay(ROLLOUT, RELEASE, events)
    assert projection.state is RolloutLifecycleState.COMPLETED
    assert not hasattr(projection, "promotion")
    assert PromotionStateProjection(PROMOTION, ROLLOUT).state is PromotionLifecycleState.PENDING


@pytest.mark.parametrize("state", [RolloutLifecycleState.BLOCKED, RolloutLifecycleState.FAILED, RolloutLifecycleState.ROLLBACK_REQUIRED])
def test_rollout_lateral_states_are_explicit(state) -> None:
    stage = RolloutStageV1(1, CapabilityReference("stage:first"))
    events = (
        _rollout_event(41, RolloutLifecycleState.PLANNED, RolloutLifecycleState.AUTHORIZED, authorization=True),
        _rollout_event(42, RolloutLifecycleState.AUTHORIZED, RolloutLifecycleState.IN_PROGRESS, stage=stage),
        _rollout_event(43, RolloutLifecycleState.IN_PROGRESS, state, failure=TransitionFailureClass.EXTERNAL_FAILURE),
    )
    assert RolloutStateProjection.replay(ROLLOUT, RELEASE, events).state is state


def test_rollout_rejects_non_advancing_stage() -> None:
    stage = RolloutStageV1(1, CapabilityReference("stage:first"))
    projection = RolloutStateProjection.replay(ROLLOUT, RELEASE, (
        _rollout_event(51, RolloutLifecycleState.PLANNED, RolloutLifecycleState.AUTHORIZED, authorization=True),
        _rollout_event(52, RolloutLifecycleState.AUTHORIZED, RolloutLifecycleState.IN_PROGRESS, stage=stage),
    ))
    with pytest.raises(InvalidRolloutProgression):
        reduce_rollout(projection, _rollout_event(53, RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.IN_PROGRESS, stage=stage))


def test_rollout_rollback_requirement_can_only_record_reconciliation() -> None:
    stage = RolloutStageV1(1, CapabilityReference("stage:first"))
    required = RolloutStateProjection.replay(
        ROLLOUT,
        RELEASE,
        (
            _rollout_event(54, RolloutLifecycleState.PLANNED, RolloutLifecycleState.AUTHORIZED, authorization=True),
            _rollout_event(55, RolloutLifecycleState.AUTHORIZED, RolloutLifecycleState.IN_PROGRESS, stage=stage),
            _rollout_event(56, RolloutLifecycleState.IN_PROGRESS, RolloutLifecycleState.ROLLBACK_REQUIRED, failure=TransitionFailureClass.EXTERNAL_FAILURE),
        ),
    )
    reconciled = reduce_rollout(
        required,
        _rollout_event(57, RolloutLifecycleState.ROLLBACK_REQUIRED, RolloutLifecycleState.RECONCILIATION_REQUIRED),
    )
    assert reconciled.state is RolloutLifecycleState.RECONCILIATION_REQUIRED


def _promotion_event(number, prior, resulting, *, authorization=False, receipt=False, failure=None):
    return PromotionTransitionEventV1(
        _event_id(number), PROMOTION, ROLLOUT, prior, resulting,
        CorrelationReference("correlation:promotion"), CausationReference(f"causation:promotion-{number}"),
        OccurrenceReference(f"occurrence:promotion-{number}"),
        AuthorizationReference(f"authorization:promotion-{number}") if authorization else None,
        ApplyReceiptReference(f"apply-receipt:promotion-{number}") if receipt else None,
        failure,
    )


def test_promotion_is_explicit_authorized_and_receipted() -> None:
    events = (
        _promotion_event(61, PromotionLifecycleState.PENDING, PromotionLifecycleState.AUTHORIZED, authorization=True),
        _promotion_event(62, PromotionLifecycleState.AUTHORIZED, PromotionLifecycleState.APPLIED, receipt=True),
    )
    assert PromotionStateProjection.replay(PROMOTION, ROLLOUT, events).state is PromotionLifecycleState.APPLIED
    assert PromotionStateProjection(PROMOTION, ROLLOUT).state is PromotionLifecycleState.PENDING


@pytest.mark.parametrize("state", [PromotionLifecycleState.DENIED, PromotionLifecycleState.FAILED])
def test_promotion_denial_and_failure_are_not_applied(state) -> None:
    prefix = () if state is PromotionLifecycleState.DENIED else (
        _promotion_event(71, PromotionLifecycleState.PENDING, PromotionLifecycleState.AUTHORIZED, authorization=True),
    )
    prior = PromotionLifecycleState.PENDING if state is PromotionLifecycleState.DENIED else PromotionLifecycleState.AUTHORIZED
    result = PromotionStateProjection.replay(PROMOTION, ROLLOUT, (*prefix, _promotion_event(72, prior, state, failure=TransitionFailureClass.EXTERNAL_FAILURE)))
    assert result.state is state


def test_promotion_unknown_outcome_requires_reconciliation() -> None:
    events = (
        _promotion_event(73, PromotionLifecycleState.PENDING, PromotionLifecycleState.AUTHORIZED, authorization=True),
        _promotion_event(74, PromotionLifecycleState.AUTHORIZED, PromotionLifecycleState.OUTCOME_UNKNOWN, failure=TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN),
        _promotion_event(75, PromotionLifecycleState.OUTCOME_UNKNOWN, PromotionLifecycleState.RECONCILIATION_REQUIRED),
    )
    projection = PromotionStateProjection.replay(PROMOTION, ROLLOUT, events)
    assert projection.state is PromotionLifecycleState.RECONCILIATION_REQUIRED


def _rollback_event(
    number: int,
    prior: RollbackLifecycleState,
    resulting: RollbackLifecycleState,
    *, authorization=False, receipt=False, observation=False, verification=False,
    failure: TransitionFailureClass | None = None,
) -> RollbackTransitionEventV1:
    return RollbackTransitionEventV1(
        _event_id(number), ROLLBACK, RELEASE, TARGET, SOURCE_REVISION, ROLLBACK_REVISION,
        ArtifactReference("artifact:rollback") if resulting is RollbackLifecycleState.ROLLED_BACK else None,
        prior, resulting, CorrelationReference("correlation:rollback"),
        CausationReference(f"causation:rollback-{number}"), OccurrenceReference(f"occurrence:rollback-{number}"),
        AuthorizationReference(f"authorization:rollback-{number}") if authorization else None,
        RollbackReceiptReference(f"rollback-receipt:rollback-{number}") if receipt else None,
        ObservationReference(f"observation:rollback-{number}") if observation else None,
        VerificationReference(f"verification:rollback-{number}") if verification else None,
        failure,
    )


def _rollback_prefix() -> tuple[RollbackTransitionEventV1, ...]:
    return (
        _rollback_event(81, RollbackLifecycleState.REQUESTED, RollbackLifecycleState.AUTHORIZATION_PENDING),
        _rollback_event(82, RollbackLifecycleState.AUTHORIZATION_PENDING, RollbackLifecycleState.AUTHORIZED, authorization=True),
        _rollback_event(83, RollbackLifecycleState.AUTHORIZED, RollbackLifecycleState.PREPARING),
        _rollback_event(84, RollbackLifecycleState.PREPARING, RollbackLifecycleState.ROLLING_BACK),
    )


def test_rollback_happy_path_keeps_explicit_revision_and_evidence_bindings() -> None:
    events = (
        *_rollback_prefix(),
        _rollback_event(85, RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLED_BACK, receipt=True),
        _rollback_event(86, RollbackLifecycleState.ROLLED_BACK, RollbackLifecycleState.VERIFYING),
        _rollback_event(87, RollbackLifecycleState.VERIFYING, RollbackLifecycleState.VERIFIED, observation=True, verification=True),
    )
    projection = RollbackStateProjection.replay(ROLLBACK, RELEASE, TARGET, SOURCE_REVISION, ROLLBACK_REVISION, events)
    assert projection.state is RollbackLifecycleState.VERIFIED
    assert projection.source_revision is SOURCE_REVISION
    assert projection.intended_revision is ROLLBACK_REVISION


@pytest.mark.parametrize(
    ("prior", "state"),
    (
        (RollbackLifecycleState.AUTHORIZATION_PENDING, RollbackLifecycleState.DENIED),
        (RollbackLifecycleState.PREPARING, RollbackLifecycleState.PREPARATION_FAILED),
        (RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLBACK_FAILED),
        (RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN),
    ),
)
def test_rollback_lateral_states_are_explicit(prior, state) -> None:
    prefix = _rollback_prefix()
    if prior is RollbackLifecycleState.AUTHORIZATION_PENDING:
        prefix = prefix[:1]
    elif prior is RollbackLifecycleState.PREPARING:
        prefix = prefix[:3]
    result = RollbackStateProjection.replay(
        ROLLBACK, RELEASE, TARGET, SOURCE_REVISION, ROLLBACK_REVISION,
        (*prefix, _rollback_event(90, prior, state, failure=TransitionFailureClass.EXTERNAL_FAILURE)),
    )
    assert result.state is state


def test_rollback_unverified_reconciles_without_changing_deployment_history() -> None:
    deployment = DeploymentStateProjection.replay(RELEASE, ATTEMPT, _deployment_prefix())
    rolled_back = RollbackStateProjection.replay(
        ROLLBACK, RELEASE, TARGET, SOURCE_REVISION, ROLLBACK_REVISION,
        (*_rollback_prefix(), _rollback_event(91, RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLED_BACK, receipt=True)),
    )
    unverified = reduce_rollback(rolled_back, _rollback_event(92, RollbackLifecycleState.ROLLED_BACK, RollbackLifecycleState.ROLLBACK_UNVERIFIED, failure=TransitionFailureClass.EVIDENCE_UNAVAILABLE))
    reconciled = reduce_rollback(unverified, _rollback_event(93, RollbackLifecycleState.ROLLBACK_UNVERIFIED, RollbackLifecycleState.RECONCILIATION_REQUIRED))
    assert reconciled.state is RollbackLifecycleState.RECONCILIATION_REQUIRED
    assert deployment == DeploymentStateProjection.replay(RELEASE, ATTEMPT, _deployment_prefix())


def test_rollback_rejects_wrong_revision_and_illegal_shortcut() -> None:
    projection = RollbackStateProjection(ROLLBACK, RELEASE, TARGET, SOURCE_REVISION, ROLLBACK_REVISION)
    with pytest.raises(InvalidRollbackProgression):
        reduce_rollback(projection, replace(_rollback_prefix()[0], intended_revision=RevisionId("deployment-revision:wrong")))
    with pytest.raises(InvalidRollbackProgression):
        reduce_rollback(projection, _rollback_event(99, RollbackLifecycleState.REQUESTED, RollbackLifecycleState.VERIFIED, observation=True, verification=True))


def test_rollback_unknown_reconciles_then_requires_manual_intervention_fact() -> None:
    unknown = RollbackStateProjection.replay(
        ROLLBACK,
        RELEASE,
        TARGET,
        SOURCE_REVISION,
        ROLLBACK_REVISION,
        (
            *_rollback_prefix(),
            _rollback_event(101, RollbackLifecycleState.ROLLING_BACK, RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN, failure=TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN),
        ),
    )
    reconciled = reduce_rollback(
        unknown,
        _rollback_event(102, RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN, RollbackLifecycleState.RECONCILIATION_REQUIRED),
    )
    manual = reduce_rollback(
        reconciled,
        _rollback_event(103, RollbackLifecycleState.RECONCILIATION_REQUIRED, RollbackLifecycleState.MANUAL_INTERVENTION_REQUIRED, failure=TransitionFailureClass.MANUAL_INTERVENTION),
    )
    assert manual.state is RollbackLifecycleState.MANUAL_INTERVENTION_REQUIRED
    assert manual.terminality is StateTerminality.RECONCILIATION_REQUIRED
