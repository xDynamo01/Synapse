from dataclasses import replace

from tests.test_coding_sessions_intents import _contract, _intent

from synapse.coding_sessions import (
    CodingSessionArtifactReference,
    CodingSessionFingerprint,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
)
from synapse.coding_sessions_integrations import (
    CodingSessionMissionTaskExecutionRequest,
    CodingSessionWorkContext,
    CodingSessionWorkDiagnosticCode,
    CodingSessionWorkerAssistanceRequest,
    CodingSessionWorkerBindingProjectionState,
    CodingSessionWorkerReceipt,
    CodingSessionWorkerReceiptState,
    CodingSessionWorkersMissionsCompatibilityAdapter,
)
from synapse.missions.models import MissionTask, TaskAttempt
from synapse.workers import InboxProcessResult


def _context(state: CodingSessionLifecycleState = CodingSessionLifecycleState.ACTIVE):
    contract = _contract(capability=CodingSessionRequestedCapability.WORKER_ASSISTANCE)
    intent = _intent(
        contract,
        category=CodingSessionIntentCategory.WORKER_ASSISTANCE_REQUEST,
        authority=CodingSessionTargetAuthority.WORKERS,
        capability=CodingSessionRequestedCapability.WORKER_ASSISTANCE,
        write=False,
    )
    artifact = CodingSessionArtifactReference.create("artifact-authority", "v1", "input:one")
    return CodingSessionWorkContext(
        contract=contract,
        lifecycle=CodingSessionStateProjection(contract.session_identity, lifecycle=state),
        intent=intent,
        mission_identity="mission:one",
        mission_fingerprint=CodingSessionFingerprint.from_content("mission"),
        mission_task_identity="mission-task:one",
        mission_task_fingerprint=CodingSessionFingerprint.from_content("mission-task"),
        requested_capability="coding-assistance",
        artifact_references=(artifact,),
        authorization_references=(),
        policy_id="work-policy",
        policy_version="v1",
    )


def _task() -> MissionTask:
    return MissionTask(
        mission_id="mission:one",
        task_id="mission-task:one",
        title="implement",
        objective="implement bounded change",
    )


def _attempt(**changes) -> TaskAttempt:
    base = TaskAttempt(
        mission_id="mission:one",
        task_id="mission-task:one",
        worker_id="worker:producer-selected",
        agent_id="agent:worker",
        attempt_number=1,
        attempt_id="attempt:one",
        metadata={"assignment_identity": "assignment:one"},
    )
    return replace(base, **changes)


def _receipt(context, **changes) -> CodingSessionWorkerReceipt:
    binding = context.contract.binding
    base = CodingSessionWorkerReceipt(
        producer="missions",
        producer_version="v1",
        receipt_identity="receipt:one",
        receipt_fingerprint=CodingSessionFingerprint.from_content("receipt"),
        session_identity=context.contract.session_identity.value,
        intent_identity=context.intent.intent_identity.value,
        actor=context.contract.actor.value,
        project=context.contract.project.value,
        purpose=context.contract.purpose.purpose.value,
        correlation=context.contract.correlation.value,
        mission_identity=context.mission_identity,
        mission_task_identity=context.mission_task_identity,
        assignment_identity="assignment:one",
        assignment_fingerprint=CodingSessionFingerprint.from_content("assignment"),
        attempt_identity="attempt:one",
        attempt_fingerprint=CodingSessionFingerprint.from_content("attempt"),
        assignment_for_attempt="assignment:one",
        requested_capability=context.requested_capability,
        repository_binding=(
            binding.repository.identity if binding.repository else None,
            binding.checkout.identity if binding.checkout else None,
            binding.worktree.identity if binding.worktree else None,
        ),
        external_reference_fingerprints=tuple(
            item.fingerprint for item in context.artifact_references if item.fingerprint
        ),
        state=CodingSessionWorkerReceiptState.ATTEMPT_STARTED,
        causal_revision=1,
        parent_receipt_identity=None,
    )
    return replace(base, **changes)


def test_assistance_is_neutral_and_contains_no_worker_choice_or_scheduler_order() -> None:
    result = CodingSessionWorkersMissionsCompatibilityAdapter.worker_assistance(_context())

    assert isinstance(result.request, CodingSessionWorkerAssistanceRequest)
    assert result.request.worker_selection is None
    assert result.request.scheduling_directive is None
    assert not result.worker_selected
    assert not result.scheduling_ordered
    assert not result.execution_started
    assert not result.mission_created


def test_mission_task_mapping_references_existing_owned_task_without_mutation() -> None:
    result = CodingSessionWorkersMissionsCompatibilityAdapter.mission_task_execution(
        _context(), _task()
    )

    assert isinstance(result.request, CodingSessionMissionTaskExecutionRequest)
    assert not result.request.create_mission
    assert not result.request.mutate_task


def test_mission_task_and_assignment_attempt_mismatch_fail_closed() -> None:
    context = _context()
    wrong_task = replace(_task(), mission_id="mission:other")
    mission_result = CodingSessionWorkersMissionsCompatibilityAdapter.mission_task_execution(
        context, wrong_task
    )
    attempt_result = CodingSessionWorkersMissionsCompatibilityAdapter.observe_attempt(
        context,
        assignment_identity="assignment:other",
        assignment_fingerprint=CodingSessionFingerprint.from_content("assignment-other"),
        attempt=_attempt(),
        attempt_fingerprint=CodingSessionFingerprint.from_content("attempt"),
    )

    assert mission_result.request is None
    assert attempt_result.request is None
    assert CodingSessionWorkDiagnosticCode.MISSION_TASK_MISMATCH in {
        item.code for item in mission_result.diagnostics
    }
    assert CodingSessionWorkDiagnosticCode.ASSIGNMENT_ATTEMPT_MISMATCH in {
        item.code for item in attempt_result.diagnostics
    }


def test_worker_completion_failure_and_cancellation_are_facts_not_session_outcomes() -> None:
    context = _context()
    adapter = CodingSessionWorkersMissionsCompatibilityAdapter()
    states = (
        CodingSessionWorkerReceiptState.ATTEMPT_COMPLETED,
        CodingSessionWorkerReceiptState.ATTEMPT_FAILED,
        CodingSessionWorkerReceiptState.ATTEMPT_CANCELLED,
    )

    projections = tuple(
        adapter.project_receipt(context, _receipt(context, state=state)) for state in states
    )

    assert all(item.state is CodingSessionWorkerBindingProjectionState.RELEASED for item in projections)
    assert all(not item.session_completed for item in projections)
    assert all(not item.session_cancelled for item in projections)
    assert all(not item.session_lifecycle_changed for item in projections)
    assert all(not item.recovery_started for item in projections)


def test_assignment_is_not_running_and_running_does_not_activate_session() -> None:
    context = _context(CodingSessionLifecycleState.PREPARED)
    assigned = CodingSessionWorkersMissionsCompatibilityAdapter.project_receipt(
        context,
        _receipt(context, state=CodingSessionWorkerReceiptState.ASSIGNMENT_CREATED),
    )
    running = CodingSessionWorkersMissionsCompatibilityAdapter.project_receipt(
        context,
        _receipt(context, state=CodingSessionWorkerReceiptState.ATTEMPT_STARTED),
    )

    assert assigned.state is CodingSessionWorkerBindingProjectionState.ASSIGNED
    assert running.state is CodingSessionWorkerBindingProjectionState.ACTIVE
    assert not assigned.session_lifecycle_changed
    assert not running.session_lifecycle_changed


def test_orphan_contradiction_and_stale_assignment_remain_explicit() -> None:
    context = _context()
    completed = _receipt(context, state=CodingSessionWorkerReceiptState.ATTEMPT_COMPLETED)
    contradictory = _receipt(
        context,
        receipt_identity="receipt:two",
        state=CodingSessionWorkerReceiptState.ATTEMPT_FAILED,
        causal_revision=2,
        parent_receipt_identity="receipt:one",
    )
    contradiction = CodingSessionWorkersMissionsCompatibilityAdapter.project_receipt(
        context, contradictory, known_receipts=(completed,)
    )
    orphan = CodingSessionWorkersMissionsCompatibilityAdapter.project_receipt(
        context,
        _receipt(context, state=CodingSessionWorkerReceiptState.ORPHANED, stale=True),
    )

    assert CodingSessionWorkDiagnosticCode.CONTRADICTORY_OUTCOME in {
        item.code for item in contradiction.diagnostics
    }
    assert contradiction.attempt_reference is None
    assert orphan.state is CodingSessionWorkerBindingProjectionState.ORPHANED
    assert {item.code for item in orphan.diagnostics} >= {
        CodingSessionWorkDiagnosticCode.ORPHAN_WORKER,
        CodingSessionWorkDiagnosticCode.STALE_ASSIGNMENT,
    }


def test_late_result_does_not_reopen_terminal_session() -> None:
    context = _context(CodingSessionLifecycleState.TERMINAL)
    result = CodingSessionWorkersMissionsCompatibilityAdapter.project_receipt(
        context, _receipt(context, state=CodingSessionWorkerReceiptState.LATE_RESULT)
    )

    assert CodingSessionWorkDiagnosticCode.LATE_RESULT in {
        item.code for item in result.diagnostics
    }
    assert not result.reopens_terminal_session
    assert not result.session_completed


def test_external_reference_and_causal_revision_mismatch_fail_closed() -> None:
    context = _context()
    receipt = _receipt(
        context,
        external_reference_fingerprints=(CodingSessionFingerprint.from_content("other"),),
        causal_revision=0,
    )

    result = CodingSessionWorkersMissionsCompatibilityAdapter.project_receipt(
        context, receipt
    )

    assert result.assignment_reference is None
    assert {item.code for item in result.diagnostics} >= {
        CodingSessionWorkDiagnosticCode.BINDING_MISMATCH,
        CodingSessionWorkDiagnosticCode.CAUSAL_REVISION_MISMATCH,
    }


def test_cancellation_request_does_not_infer_worker_or_session_cancelled() -> None:
    context = _context()
    result = CodingSessionWorkersMissionsCompatibilityAdapter.cancellation_reconciliation(
        context,
        assignment_identity="assignment:one",
        assignment_fingerprint=CodingSessionFingerprint.from_content("assignment"),
        attempt_identity="attempt:one",
        attempt_fingerprint=CodingSessionFingerprint.from_content("attempt"),
    )

    assert result.request is not None
    assert not result.request.termination_inferred
    assert not result.request.session_cancellation_inferred


def test_worker_public_result_is_reduced_to_opaque_reference() -> None:
    result = InboxProcessResult(
        agent_id="agent:worker",
        message_id="message:one",
        status="completed",
        response="private payload",
        tool_results=[{"secret": "not projected"}],
    )

    reference = CodingSessionWorkersMissionsCompatibilityAdapter.inbox_receipt_reference(result)

    assert reference.producer == "workers"
    assert reference.identity == "inbox-result:message:one"
    assert "private" not in reference.identity


def test_same_canonical_input_produces_same_translation() -> None:
    context = _context()
    first = CodingSessionWorkersMissionsCompatibilityAdapter.worker_assistance(context)
    second = CodingSessionWorkersMissionsCompatibilityAdapter.worker_assistance(context)

    assert first == second
