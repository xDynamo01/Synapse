from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.sandbox import (
    InvalidCancellation,
    SandboxCancellationClassification,
    SandboxCancellationDecisionService,
    SandboxCancellationEvent,
    SandboxCancellationEventKind,
    SandboxCancellationRequest,
    SandboxCancellationService,
    SandboxCancellationState,
    SandboxDeadline,
    SandboxDeadlineKind,
    SandboxDeadlineService,
    SandboxDeadlineSet,
    SandboxDescendantsStatus,
    SandboxPolicyVersion,
    SandboxTerminationEscalation,
    SandboxTerminationEscalationService,
    SandboxTerminationEscalationStage,
    SandboxTimeoutPolicy,
)
from test_sandbox_runtime_supervision import attempt, proof, ref

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def policy(*, forced=False, acknowledgement=True):
    stages = (
        SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION,
        SandboxTerminationEscalationStage.GRACEFUL_TERMINATION,
        *((SandboxTerminationEscalationStage.FORCED_TERMINATION,) if forced else ()),
        SandboxTerminationEscalationStage.MANUAL_INTERVENTION,
    )
    return SandboxTimeoutPolicy.create(
        version=SandboxPolicyVersion("cancellation-policy:v1"),
        required_deadlines=tuple(SandboxDeadlineKind),
        escalation_order=stages,
        acknowledgement_required=acknowledgement,
        forced_termination_allowed=forced,
    )


def deadline_set(current_attempt, selected_policy=None, *, occurred_at=NOW):
    selected_policy = selected_policy or policy()
    return SandboxDeadlineSet.create(
        current_attempt,
        selected_policy,
        (
            SandboxDeadline(SandboxDeadlineKind.STARTUP, NOW + timedelta(seconds=5)),
            SandboxDeadline(SandboxDeadlineKind.IDLE, NOW + timedelta(seconds=10)),
            SandboxDeadline(SandboxDeadlineKind.WALL_CLOCK, NOW + timedelta(seconds=20)),
            SandboxDeadline(
                SandboxDeadlineKind.TERMINATION_GRACE,
                NOW + timedelta(seconds=25),
            ),
            SandboxDeadline(SandboxDeadlineKind.CLEANUP, NOW + timedelta(seconds=30)),
        ),
        occurred_at=occurred_at,
    )


def cancellation_request(current_attempt, selected_policy, deadlines, *, occurred_at=NOW):
    return SandboxCancellationRequest(
        current_attempt.attempt_id,
        current_attempt.attempt_fingerprint,
        ref("actor:operator-1"),
        "cancel-workload",
        "operator.requested",
        selected_policy.policy_id,
        selected_policy.policy_fingerprint,
        deadlines.deadline_set_id,
        deadlines.deadline_set_fingerprint,
        occurred_at,
    )


def decision(*, explicit=True, evaluated_at=NOW, occurred_at=NOW, selected_policy=None):
    current_attempt = attempt()
    selected_policy = selected_policy or policy()
    deadlines = deadline_set(current_attempt, selected_policy, occurred_at=occurred_at)
    evaluation = SandboxDeadlineService.evaluate(deadlines, evaluated_at=evaluated_at)
    request = (
        cancellation_request(
            current_attempt,
            selected_policy,
            deadlines,
            occurred_at=occurred_at,
        )
        if explicit
        else None
    )
    selected = SandboxCancellationDecisionService.decide(
        current_attempt,
        selected_policy,
        deadlines,
        request,
        evaluation,
        occurred_at=occurred_at,
    )
    return current_attempt, selected_policy, deadlines, selected


def event(sequence, kind, selected_decision, **changes):
    return SandboxCancellationEvent(
        sequence,
        kind,
        selected_decision.decision_id,
        **changes,
    )


def completed_events(current_attempt, selected_decision, *, occurred_at=None):
    termination = proof(current_attempt, occurred_at=occurred_at or NOW)
    stage = SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION
    return (
        event(
            1,
            SandboxCancellationEventKind.CANCELLATION_REQUESTED,
            selected_decision,
            occurred_at=occurred_at,
        ),
        event(
            2,
            SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED,
            selected_decision,
            occurred_at=occurred_at,
        ),
        event(
            3,
            SandboxCancellationEventKind.TERMINATION_REQUESTED,
            selected_decision,
            occurred_at=occurred_at,
        ),
        event(
            4,
            SandboxCancellationEventKind.TERMINATION_INITIATED,
            selected_decision,
            escalation_stage=stage,
            occurred_at=occurred_at,
        ),
        event(
            5,
            SandboxCancellationEventKind.TERMINATION_VERIFIED,
            selected_decision,
            termination_proof=termination,
            occurred_at=occurred_at,
        ),
        event(
            6,
            SandboxCancellationEventKind.CANCELLATION_COMPLETED,
            selected_decision,
            occurred_at=occurred_at,
        ),
    )


def test_deadlines_use_only_explicit_clock_and_remain_distinct() -> None:
    current_attempt = attempt()
    deadlines = deadline_set(current_attempt)
    before = SandboxDeadlineService.evaluate(
        deadlines,
        evaluated_at=NOW + timedelta(seconds=4),
    )
    startup = SandboxDeadlineService.evaluate(
        deadlines,
        evaluated_at=NOW + timedelta(seconds=6),
    )
    idle = SandboxDeadlineService.evaluate(
        deadlines,
        evaluated_at=NOW + timedelta(seconds=11),
    )
    wall = SandboxDeadlineService.evaluate(
        deadlines,
        evaluated_at=NOW + timedelta(seconds=21),
    )
    assert before.expired == ()
    assert startup.expired == (SandboxDeadlineKind.STARTUP,)
    assert set(idle.expired) == {
        SandboxDeadlineKind.STARTUP,
        SandboxDeadlineKind.IDLE,
    }
    assert SandboxDeadlineKind.WALL_CLOCK in wall.expired
    assert SandboxDeadlineKind.TERMINATION_GRACE not in wall.expired


def test_grace_does_not_extend_wall_clock_deadline() -> None:
    _, _, _, selected = decision(
        explicit=False,
        evaluated_at=NOW + timedelta(seconds=21),
    )
    assert selected.classification is SandboxCancellationClassification.WALL_CLOCK_TIMEOUT
    assert selected.diagnostics == ("deadline.wall_clock_timeout",)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (6, SandboxCancellationClassification.STARTUP_TIMEOUT),
        (11, SandboxCancellationClassification.IDLE_TIMEOUT),
        (21, SandboxCancellationClassification.WALL_CLOCK_TIMEOUT),
        (26, SandboxCancellationClassification.TERMINATION_GRACE_TIMEOUT),
        (31, SandboxCancellationClassification.CLEANUP_TIMEOUT),
    ],
)
def test_each_explicit_deadline_has_a_distinct_classification(seconds, expected) -> None:
    _, _, _, selected = decision(
        explicit=False,
        evaluated_at=NOW + timedelta(seconds=seconds),
    )
    assert selected.classification is expected


def test_explicit_request_binds_actor_purpose_reason_policy_and_attempt() -> None:
    current_attempt, selected_policy, deadlines, first = decision()
    changed_request = replace(
        cancellation_request(current_attempt, selected_policy, deadlines),
        actor_ref=ref("actor:operator-2"),
    )
    evaluation = SandboxDeadlineService.evaluate(deadlines, evaluated_at=NOW)
    changed = SandboxCancellationDecisionService.decide(
        current_attempt,
        selected_policy,
        deadlines,
        changed_request,
        evaluation,
        occurred_at=NOW,
    )
    assert first.cause_fingerprint != changed.cause_fingerprint
    assert first.decision_fingerprint != changed.decision_fingerprint


@pytest.mark.parametrize(
    "events",
    [
        (SandboxCancellationEventKind.CANCELLATION_REQUESTED,),
        (
            SandboxCancellationEventKind.CANCELLATION_REQUESTED,
            SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED,
        ),
        (
            SandboxCancellationEventKind.CANCELLATION_REQUESTED,
            SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED,
            SandboxCancellationEventKind.TERMINATION_REQUESTED,
        ),
    ],
)
def test_request_acknowledgement_or_termination_request_do_not_prove_exit(events) -> None:
    _, selected_policy, _, selected = decision()
    stream = tuple(event(index, kind, selected) for index, kind in enumerate(events, 1))
    with pytest.raises(InvalidCancellation, match="structurally invalid"):
        SandboxCancellationService.reduce(
            selected,
            selected_policy,
            stream,
            occurred_at=NOW,
        )


def test_completed_cancellation_requires_verified_termination_and_clear_descendants() -> None:
    current_attempt, selected_policy, _, selected = decision()
    result = SandboxCancellationService.reduce(
        selected,
        selected_policy,
        completed_events(current_attempt, selected),
        occurred_at=NOW,
    )
    assert result.final_state is SandboxCancellationState.COMPLETED
    assert result.termination_proof_ref is not None
    assert result.descendants_status is SandboxDescendantsStatus.CLEAR
    assert not result.cleanup_required


def test_unverified_termination_requires_cleanup() -> None:
    current_attempt, selected_policy, _, selected = decision()
    unverified = proof(current_attempt, verified=False)
    events = (
        event(1, SandboxCancellationEventKind.CANCELLATION_REQUESTED, selected),
        event(2, SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED, selected),
        event(3, SandboxCancellationEventKind.TERMINATION_REQUESTED, selected),
        event(
            4,
            SandboxCancellationEventKind.TERMINATION_INITIATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION,
        ),
        event(
            5,
            SandboxCancellationEventKind.TERMINATION_UNVERIFIED,
            selected,
            termination_proof=unverified,
        ),
    )
    result = SandboxCancellationService.reduce(
        selected,
        selected_policy,
        events,
        occurred_at=NOW,
    )
    assert result.final_state is SandboxCancellationState.TERMINATION_UNVERIFIED
    assert result.cleanup_required
    assert result.descendants_status is SandboxDescendantsStatus.ACTIVE


def test_forced_termination_requires_policy_and_cannot_skip_stages() -> None:
    denied_policy = policy(forced=False)
    current = SandboxTerminationEscalation(
        denied_policy.escalation_order,
        SandboxTerminationEscalationStage.GRACEFUL_TERMINATION,
    )
    advanced = SandboxTerminationEscalationService.advance(denied_policy, current)
    assert advanced.applied_stage is SandboxTerminationEscalationStage.MANUAL_INTERVENTION

    allowed_policy = policy(forced=True)
    current_attempt, _, _, selected = decision(selected_policy=allowed_policy)
    termination = proof(current_attempt)
    events = (
        event(1, SandboxCancellationEventKind.CANCELLATION_REQUESTED, selected),
        event(2, SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED, selected),
        event(3, SandboxCancellationEventKind.TERMINATION_REQUESTED, selected),
        event(
            4,
            SandboxCancellationEventKind.TERMINATION_INITIATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION,
        ),
        event(
            5,
            SandboxCancellationEventKind.ESCALATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.FORCED_TERMINATION,
        ),
        event(
            6,
            SandboxCancellationEventKind.TERMINATION_VERIFIED,
            selected,
            termination_proof=termination,
        ),
        event(7, SandboxCancellationEventKind.CANCELLATION_COMPLETED, selected),
    )
    with pytest.raises(InvalidCancellation):
        SandboxCancellationService.reduce(
            selected,
            allowed_policy,
            events,
            occurred_at=NOW,
        )

    valid_events = (
        *events[:4],
        event(
            5,
            SandboxCancellationEventKind.ESCALATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.GRACEFUL_TERMINATION,
        ),
        event(
            6,
            SandboxCancellationEventKind.ESCALATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.FORCED_TERMINATION,
        ),
        event(
            7,
            SandboxCancellationEventKind.TERMINATION_VERIFIED,
            selected,
            termination_proof=termination,
        ),
        event(8, SandboxCancellationEventKind.CANCELLATION_COMPLETED, selected),
    )
    result = SandboxCancellationService.reduce(
        selected,
        allowed_policy,
        valid_events,
        occurred_at=NOW,
    )
    assert result.escalation.applied_stage is SandboxTerminationEscalationStage.FORCED_TERMINATION


def test_duplicate_and_out_of_order_events_fail_closed() -> None:
    _, selected_policy, _, selected = decision()
    duplicate = (
        event(1, SandboxCancellationEventKind.CANCELLATION_REQUESTED, selected),
        event(2, SandboxCancellationEventKind.CANCELLATION_REQUESTED, selected),
    )
    with pytest.raises(InvalidCancellation):
        SandboxCancellationService.reduce(
            selected,
            selected_policy,
            duplicate,
            occurred_at=NOW,
        )
    out_of_order = (
        event(1, SandboxCancellationEventKind.CANCELLATION_REQUESTED, selected),
        event(
            2,
            SandboxCancellationEventKind.TERMINATION_VERIFIED,
            selected,
            termination_proof=proof(attempt()),
        ),
    )
    with pytest.raises(InvalidCancellation):
        SandboxCancellationService.reduce(
            selected,
            selected_policy,
            out_of_order,
            occurred_at=NOW,
        )


def test_replay_and_occurrence_metadata_do_not_change_semantic_result() -> None:
    current_attempt, selected_policy, _, selected = decision()
    replay_decision = replace(selected, occurred_at=NOW + timedelta(minutes=1))
    first = SandboxCancellationService.reduce(
        selected,
        selected_policy,
        completed_events(current_attempt, selected, occurred_at=NOW),
        occurred_at=NOW,
    )
    replay = SandboxCancellationService.reduce(
        replay_decision,
        selected_policy,
        completed_events(
            current_attempt,
            replay_decision,
            occurred_at=NOW + timedelta(minutes=1),
        ),
        occurred_at=NOW + timedelta(minutes=1),
    )
    assert first.result_id == replay.result_id
    assert first.result_fingerprint == replay.result_fingerprint
    assert first.occurred_at != replay.occurred_at


def test_contracts_expose_no_timer_signal_driver_or_io_operation() -> None:
    _, _, _, selected = decision()
    for forbidden in (
        "sleep",
        "timer",
        "signal",
        "kill",
        "subprocess",
        "popen",
        "filesystem",
    ):
        assert not hasattr(selected, forbidden)
