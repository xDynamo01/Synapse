from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.sandbox import (
    InvalidRuntimeSupervision,
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxExecutionStartRequest,
    SandboxExitClassification,
    SandboxProcessEnforcement,
    SandboxRuntimeDriverCapabilityFact,
    SandboxRuntimeEvent,
    SandboxRuntimeEventKind,
    SandboxRuntimeObservation,
    SandboxRuntimeSupervisionApplicationService,
    SandboxRuntimeSupervisionService,
    SandboxSupervisionState,
    SandboxTerminationMethod,
    SandboxTerminationProof,
    SandboxTerminationProofId,
    SandboxTerminationVerificationOutcome,
    derive_identity,
)
from test_sandbox_materialization import execute, materialization_request

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def ref(value: str) -> OpaqueReference:
    return OpaqueReference(value)


def start_request(*, occurred_at=NOW, available=True):
    material_request = materialization_request(occurred_at=occurred_at)
    material_plan, material_result, _, _, _ = execute(material_request)
    assert material_result.record is not None
    required = tuple(
        sorted(
            material_request.process.required_enforcements,
            key=lambda item: item.value,
        )
    )
    driver = SandboxRuntimeDriverCapabilityFact(
        ref("runtime-driver:abstract-v1"),
        material_request.plan.plan_id,
        material_request.plan.plan_fingerprint,
        material_request.plan.isolation_profile_id,
        required,
        available,
        NOW - timedelta(minutes=1),
        NOW + timedelta(minutes=10),
    )
    return SandboxExecutionStartRequest(
        material_request.plan,
        material_plan,
        material_result.record,
        material_request.capabilities,
        material_request.filesystem,
        material_request.network,
        material_request.process,
        material_request.resources,
        material_request.secrets,
        driver,
        ref("attempt:requested-1"),
        NOW,
        occurred_at,
    )


def attempt(request=None):
    return SandboxRuntimeSupervisionService.create_attempt(request or start_request())


def observation(*, alive=True, exit_classification=None, available=True, descendants=()):
    return SandboxRuntimeObservation(
        ref("process:initial"),
        alive,
        tuple(descendants),
        exit_classification,
        available,
    )


def proof(current_attempt, *, verified=True, descendants=(), occurred_at=NOW):
    outcome = (
        SandboxTerminationVerificationOutcome.VERIFIED
        if verified
        else SandboxTerminationVerificationOutcome.UNVERIFIED
    )
    semantic = (
        "sandbox-runtime-supervision-v1",
        current_attempt.attempt_id,
        ref("process:initial"),
        tuple(descendants),
        SandboxTerminationMethod.RUNTIME_EXIT,
        current_attempt.driver_ref,
        (
            SandboxProcessEnforcement.DESCENDANT_TRACKING,
            SandboxProcessEnforcement.VERIFIED_TERMINATION,
        ),
        verified,
        outcome,
    )
    fingerprint = SandboxArtifactFingerprint.from_content(semantic)
    identity = derive_identity(SandboxTerminationProofId, fingerprint)
    return SandboxTerminationProof(
        SandboxTerminationProofId(identity.value),
        fingerprint,
        current_attempt.attempt_id,
        ref("process:initial"),
        tuple(descendants),
        SandboxTerminationMethod.RUNTIME_EXIT,
        current_attempt.driver_ref,
        (
            SandboxProcessEnforcement.DESCENDANT_TRACKING,
            SandboxProcessEnforcement.VERIFIED_TERMINATION,
        ),
        verified,
        outcome,
        occurred_at,
    )


def event(sequence, kind, current_attempt, **changes):
    return SandboxRuntimeEvent(sequence, kind, current_attempt.attempt_id, **changes)


def running_events(current_attempt):
    return (
        event(1, SandboxRuntimeEventKind.START_REQUESTED, current_attempt),
        event(2, SandboxRuntimeEventKind.PROCESS_CREATED, current_attempt),
        event(
            3,
            SandboxRuntimeEventKind.RUNTIME_OBSERVED,
            current_attempt,
            observation=observation(),
        ),
    )


def test_verified_materialization_does_not_start_workload() -> None:
    request = start_request()
    created = attempt(request)
    assert created.state is SandboxSupervisionState.PENDING
    assert created.materialization_id == request.materialization.materialization_id


def test_process_created_needs_valid_runtime_observation_to_be_running() -> None:
    request = start_request()
    created = attempt(request)
    result = SandboxRuntimeSupervisionService.evaluate(
        request,
        (
            event(1, SandboxRuntimeEventKind.START_REQUESTED, created),
            event(2, SandboxRuntimeEventKind.PROCESS_CREATED, created),
        ),
    )
    assert result.final_state is SandboxSupervisionState.STARTING


def test_timeout_does_not_claim_termination() -> None:
    request = start_request()
    created = attempt(request)
    events = (
        *running_events(created),
        event(
            4,
            SandboxRuntimeEventKind.RUNTIME_OBSERVED,
            created,
            observation=observation(
                alive=False,
                exit_classification=SandboxExitClassification.TIMED_OUT,
            ),
        ),
    )
    result = SandboxRuntimeSupervisionService.evaluate(request, events)
    assert result.final_state is SandboxSupervisionState.TIMED_OUT
    assert result.termination_proof_ref is None
    assert result.cleanup_required


def test_process_exit_without_proof_is_termination_unverified() -> None:
    request = start_request()
    created = attempt(request)
    result = SandboxRuntimeSupervisionService.evaluate(
        request,
        (
            *running_events(created),
            event(4, SandboxRuntimeEventKind.RUNTIME_EXITED, created),
        ),
    )
    assert result.final_state is SandboxSupervisionState.TERMINATION_UNVERIFIED
    assert result.exit_classification is SandboxExitClassification.UNKNOWN


def test_verified_exit_requires_proof_of_no_active_descendants() -> None:
    request = start_request()
    created = attempt(request)
    termination = proof(created)
    result = SandboxRuntimeSupervisionService.evaluate(
        request,
        (
            *running_events(created),
            event(
                4,
                SandboxRuntimeEventKind.RUNTIME_EXITED,
                created,
                termination_proof=termination,
            ),
        ),
    )
    assert result.final_state is SandboxSupervisionState.COMPLETED
    assert result.termination_proof_ref == termination.proof_id
    with pytest.raises(InvalidRuntimeSupervision):
        replace(termination, no_active_descendants=False)


@pytest.mark.parametrize(
    "events_factory",
    [
        lambda created: (
            event(1, SandboxRuntimeEventKind.START_REQUESTED, created),
            event(2, SandboxRuntimeEventKind.START_REQUESTED, created),
        ),
        lambda created: (event(1, SandboxRuntimeEventKind.PROCESS_CREATED, created),),
        lambda created: (
            event(1, SandboxRuntimeEventKind.START_REQUESTED, created),
            event(3, SandboxRuntimeEventKind.PROCESS_CREATED, created),
        ),
    ],
)
def test_duplicate_start_and_out_of_order_events_fail_closed(events_factory) -> None:
    request = start_request()
    created = attempt(request)
    with pytest.raises(InvalidRuntimeSupervision):
        SandboxRuntimeSupervisionService.evaluate(
            request,
            events_factory(created),
        )


def test_lost_observation_preserves_uncertainty() -> None:
    request = start_request()
    created = attempt(request)
    result = SandboxRuntimeSupervisionService.evaluate(
        request,
        (
            *running_events(created),
            event(
                4,
                SandboxRuntimeEventKind.RUNTIME_OBSERVED,
                created,
                observation=observation(available=False),
            ),
        ),
    )
    assert result.final_state is SandboxSupervisionState.TERMINATION_UNVERIFIED


def test_termination_request_failure_never_claims_termination() -> None:
    request = start_request()
    created = attempt(request)
    unverified = proof(created, verified=False)
    result = SandboxRuntimeSupervisionService.evaluate(
        request,
        (
            *running_events(created),
            event(4, SandboxRuntimeEventKind.TERMINATION_REQUESTED, created),
            event(
                5,
                SandboxRuntimeEventKind.TERMINATION_UNVERIFIED,
                created,
                termination_proof=unverified,
                diagnostics=("termination.request_failed",),
            ),
        ),
    )
    assert result.final_state is SandboxSupervisionState.TERMINATION_UNVERIFIED
    assert result.termination_proof_ref == unverified.proof_id
    assert result.cleanup_required


def test_descendant_escape_and_limit_are_factual_violations_not_policy_denials() -> None:
    request = start_request()
    created = attempt(request)
    termination = proof(created)
    result = SandboxRuntimeSupervisionService.evaluate(
        request,
        (
            *running_events(created),
            event(
                4,
                SandboxRuntimeEventKind.DESCENDANT_OBSERVED,
                created,
                violations=("isolation.descendant_escape",),
            ),
            event(
                5,
                SandboxRuntimeEventKind.LIMIT_TRIGGERED,
                created,
                violations=("resource.limit_triggered",),
            ),
            event(
                6,
                SandboxRuntimeEventKind.RUNTIME_EXITED,
                created,
                termination_proof=termination,
            ),
        ),
    )
    assert result.violations == (
        "isolation.descendant_escape",
        "resource.limit_triggered",
    )
    assert all("policy" not in code and "denied" not in code for code in result.violations)


def test_occurrence_metadata_does_not_change_attempt_proof_or_result_identity() -> None:
    first_request = start_request()
    replay_request = replace(
        first_request,
        occurred_at=NOW + timedelta(minutes=5),
    )
    first_attempt = attempt(first_request)
    replay_attempt = attempt(replay_request)
    assert first_attempt.attempt_id == replay_attempt.attempt_id
    first_proof = proof(first_attempt)
    replay_proof = proof(
        replay_attempt,
        occurred_at=NOW + timedelta(minutes=5),
    )
    assert first_proof.proof_id == replay_proof.proof_id
    first_events = (
        *running_events(first_attempt),
        event(
            4,
            SandboxRuntimeEventKind.RUNTIME_EXITED,
            first_attempt,
            termination_proof=first_proof,
            occurred_at=NOW,
        ),
    )
    replay_events = tuple(
        replace(item, occurred_at=NOW + timedelta(minutes=5))
        for item in (
            *running_events(replay_attempt),
            event(
                4,
                SandboxRuntimeEventKind.RUNTIME_EXITED,
                replay_attempt,
                termination_proof=replay_proof,
            ),
        )
    )
    first = SandboxRuntimeSupervisionService.evaluate(first_request, first_events)
    replay = SandboxRuntimeSupervisionService.evaluate(replay_request, replay_events)
    assert first.result_id == replay.result_id
    assert first.result_fingerprint == replay.result_fingerprint
    assert first.occurred_at != replay.occurred_at


class Ports:
    def __init__(self):
        self.calls = []

    def start(self, command):
        self.calls.append("start")
        return event(2, SandboxRuntimeEventKind.PROCESS_CREATED, command.attempt)

    def observe(self, current_attempt):
        self.calls.append("observe")
        return (
            event(
                3,
                SandboxRuntimeEventKind.RUNTIME_OBSERVED,
                current_attempt,
                observation=observation(),
            ),
        )

    def observe_descendants(self, current_attempt):
        self.calls.append("descendants")
        return ()

    def request_termination(self, current_attempt):
        self.calls.append("terminate")
        return event(4, SandboxRuntimeEventKind.TERMINATION_REQUESTED, current_attempt)

    def confirm_termination(self, current_attempt):
        self.calls.append("confirm")
        return event(
            5,
            SandboxRuntimeEventKind.TERMINATION_CONFIRMED,
            current_attempt,
            termination_proof=proof(current_attempt),
        )

    def collect(self, current_attempt):
        self.calls.append("metrics")
        return ()

    def verify(self, current_attempt):
        self.calls.append("isolation")
        return ()


def test_invalid_binding_or_unavailable_driver_fails_before_any_port_call() -> None:
    ports = Ports()
    service = SandboxRuntimeSupervisionApplicationService(
        ports,
        ports,
        ports,
        ports,
        ports,
    )
    with pytest.raises(InvalidRuntimeSupervision):
        service.supervise(start_request(available=False))
    assert ports.calls == []


def test_public_ports_are_abstract_and_never_start_real_processes() -> None:
    ports = Ports()
    result = SandboxRuntimeSupervisionApplicationService(
        ports,
        ports,
        ports,
        ports,
        ports,
    ).supervise(start_request())
    assert result.final_state is SandboxSupervisionState.RUNNING
    assert ports.calls == [
        "start",
        "observe",
        "descendants",
        "metrics",
        "isolation",
    ]
    assert not hasattr(result, "process")
    assert not hasattr(result, "authorized")
    assert not hasattr(result, "cleanup_completed")
