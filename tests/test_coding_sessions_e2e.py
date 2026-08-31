from pathlib import Path

from tests.test_coding_sessions_composition import _config
from tests.test_coding_sessions_control import (
    _journal_checkpoint,
    _lifecycle,
    _resume_request,
)
from tests.test_coding_sessions_deployment_reference import (
    _facts as deployment_facts,
)
from tests.test_coding_sessions_deployment_reference import (
    _receipt as deployment_receipt,
)
from tests.test_coding_sessions_governance_compatibility import (
    _context as governance_context,
)
from tests.test_coding_sessions_governance_compatibility import (
    _receipt as governance_receipt,
)
from tests.test_coding_sessions_leases import _contract, _issue
from tests.test_coding_sessions_private_evals_compatibility import (
    _context as eval_context,
)
from tests.test_coding_sessions_private_evals_compatibility import (
    _receipt as eval_receipt,
)
from tests.test_coding_sessions_repository_compatibility import _facts as repository_facts
from tests.test_coding_sessions_sandbox_compatibility import (
    _context as sandbox_context,
)
from tests.test_coding_sessions_sandbox_compatibility import (
    _receipt as sandbox_receipt,
)
from tests.test_coding_sessions_sqlite import _append_request, _record, _session
from tests.test_coding_sessions_workers_missions_compatibility import (
    _context as worker_context,
)
from tests.test_coding_sessions_workers_missions_compatibility import (
    _receipt as worker_receipt,
)

from synapse.coding_sessions import (
    CodingSessionCancellationState,
    CodingSessionCausalRangeReadRequest,
    CodingSessionCoordinationState,
    CodingSessionExactRecordReadRequest,
    CodingSessionLeaseCapability,
    CodingSessionLeaseMode,
    CodingSessionLeasePolicy,
    CodingSessionLifecycleState,
    CodingSessionOwnershipProjection,
    CodingSessionPersistenceStream,
    CodingSessionRecordAppendStatus,
    CodingSessionRecoveryState,
    CodingSessionRepositoryCorrespondenceState,
    CodingSessionResumeAssessment,
    CodingSessionStateProjection,
)
from synapse.coding_sessions_composition import (
    CodingSessionsCapability,
    CodingSessionsCapabilityState,
    CodingSessionsRuntimeBuilder,
)
from synapse.coding_sessions_integrations import (
    CodingSessionAuthorizationStatus,
    CodingSessionDeploymentProjectionState,
    CodingSessionEvalReceiptState,
    CodingSessionExecutionBindingProjectionState,
    CodingSessionSandboxReceiptState,
    CodingSessionWorkerBindingProjectionState,
    CodingSessionWorkerReceiptState,
)

ALL_REFERENCES = frozenset(
    {
        CodingSessionsCapability.REPOSITORY_RUNTIME,
        CodingSessionsCapability.GOVERNANCE_APPROVALS,
        CodingSessionsCapability.WORKERS_MISSIONS,
        CodingSessionsCapability.SANDBOX_REFERENCES,
        CodingSessionsCapability.PRIVATE_EVALS,
        CodingSessionsCapability.DEPLOYMENT_REFERENCES,
    }
)


def _runtime(tmp_path: Path):
    return CodingSessionsRuntimeBuilder().build(
        _config(tmp_path, enabled_integrations=ALL_REFERENCES)
    )


def test_nominal_durable_journey_and_restart_preserve_all_seven_streams(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    categories = {
        CodingSessionPersistenceStream.CONTRACT_BINDINGS: "contract-created",
        CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: "lifecycle-prepared",
        CodingSessionPersistenceStream.INTENTS_RECEIPTS: "intent-pending",
        CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS: "checkpoint-persisted",
        CodingSessionPersistenceStream.CONTROL_CANCELLATION: "pause-requested",
        CodingSessionPersistenceStream.RESTART_RECONCILIATION: "reconciliation-incomplete",
        CodingSessionPersistenceStream.RECOVERY_OUTCOME: "recovery-required",
    }
    stores = {
        CodingSessionPersistenceStream.CONTRACT_BINDINGS: runtime.persistence.contracts,
        CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: runtime.persistence.lifecycle,
        CodingSessionPersistenceStream.INTENTS_RECEIPTS: runtime.persistence.intents,
        CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS: runtime.persistence.journal,
        CodingSessionPersistenceStream.CONTROL_CANCELLATION: runtime.persistence.control,
        CodingSessionPersistenceStream.RESTART_RECONCILIATION: runtime.persistence.restart,
        CodingSessionPersistenceStream.RECOVERY_OUTCOME: runtime.persistence.recovery,
    }
    records = {}
    for stream, category in categories.items():
        record = _record(1, stream=stream, category=category)
        records[stream] = record
        appended = stores[stream].append(_append_request(record))
        repeated = stores[stream].append(_append_request(record))
        assert appended.status is CodingSessionRecordAppendStatus.APPENDED
        assert repeated.status is CodingSessionRecordAppendStatus.IDEMPOTENT
    runtime.close()

    restarted = _runtime(tmp_path)
    restarted_stores = {
        CodingSessionPersistenceStream.CONTRACT_BINDINGS: restarted.persistence.contracts,
        CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: restarted.persistence.lifecycle,
        CodingSessionPersistenceStream.INTENTS_RECEIPTS: restarted.persistence.intents,
        CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS: restarted.persistence.journal,
        CodingSessionPersistenceStream.CONTROL_CANCELLATION: restarted.persistence.control,
        CodingSessionPersistenceStream.RESTART_RECONCILIATION: restarted.persistence.restart,
        CodingSessionPersistenceStream.RECOVERY_OUTCOME: restarted.persistence.recovery,
    }
    for stream, record in records.items():
        exact = restarted_stores[stream].read_exact(
            CodingSessionExactRecordReadRequest(
                _session(), stream, record.record_identity, record.record_fingerprint
            )
        )
        causal = restarted_stores[stream].read_range(
            CodingSessionCausalRangeReadRequest(_session(), stream, 1, 1)
        )
        assert exact.record == record
        assert causal == (record,)
    assert not hasattr(restarted, "resume_automatically")
    assert not hasattr(restarted, "recover_automatically")


def test_crash_restart_matrix_preserves_intermediate_states_without_promotion(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    states = (
        "contract-created",
        "lifecycle-prepared",
        "lease-issued",
        "intent-pending",
        "receipt-received",
        "checkpoint-pending",
        "checkpoint-durable-ready",
        "checkpoint-persisted",
        "pause-requested",
        "cancellation-requested",
        "cancellation-acknowledged",
        "reconciliation-incomplete",
        "recovery-reconciling",
        "recovery-partial",
        "manual-intervention",
    )
    streams = tuple(CodingSessionPersistenceStream)
    latest = {}
    records = []
    for index, category in enumerate(states):
        stream = streams[index % len(streams)]
        parent = latest.get(stream)
        revision = 1 if parent is None else parent.causal_revision + 1
        record = _record(revision, stream=stream, category=category, parent=parent)
        store = {
            CodingSessionPersistenceStream.CONTRACT_BINDINGS: runtime.persistence.contracts,
            CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: runtime.persistence.lifecycle,
            CodingSessionPersistenceStream.INTENTS_RECEIPTS: runtime.persistence.intents,
            CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS: runtime.persistence.journal,
            CodingSessionPersistenceStream.CONTROL_CANCELLATION: runtime.persistence.control,
            CodingSessionPersistenceStream.RESTART_RECONCILIATION: runtime.persistence.restart,
            CodingSessionPersistenceStream.RECOVERY_OUTCOME: runtime.persistence.recovery,
        }[stream]
        assert (
            store.append(_append_request(record, parent)).status
            is CodingSessionRecordAppendStatus.APPENDED
        )
        latest[stream] = record
        records.append(record)
    runtime.close()
    restarted = _runtime(tmp_path)
    for record in records:
        store = {
            CodingSessionPersistenceStream.CONTRACT_BINDINGS: restarted.persistence.contracts,
            CodingSessionPersistenceStream.LIFECYCLE_COORDINATION: restarted.persistence.lifecycle,
            CodingSessionPersistenceStream.INTENTS_RECEIPTS: restarted.persistence.intents,
            CodingSessionPersistenceStream.JOURNAL_CHECKPOINTS: restarted.persistence.journal,
            CodingSessionPersistenceStream.CONTROL_CANCELLATION: restarted.persistence.control,
            CodingSessionPersistenceStream.RESTART_RECONCILIATION: restarted.persistence.restart,
            CodingSessionPersistenceStream.RECOVERY_OUTCOME: restarted.persistence.recovery,
        }[record.stream]
        assert (
            store.read_exact(
                CodingSessionExactRecordReadRequest(
                    _session(), record.stream, record.record_identity, record.record_fingerprint
                )
            ).record.category
            == record.category
        )


def test_concurrent_leases_fail_closed_without_implicit_winner() -> None:
    writes = (_issue(_contract("session:one")), _issue(_contract("session:two")))
    conflict = CodingSessionOwnershipProjection.project(
        writes, observation_time=15, policy=CodingSessionLeasePolicy()
    )
    reads = (
        _issue(
            _contract("session:read-one", write=False),
            capability=CodingSessionLeaseCapability.READ,
            mode=CodingSessionLeaseMode.SHARED,
        ),
        _issue(
            _contract("session:read-two", write=False),
            capability=CodingSessionLeaseCapability.READ,
            mode=CodingSessionLeaseMode.SHARED,
        ),
    )
    shared = CodingSessionOwnershipProjection.project(
        reads, observation_time=15, policy=CodingSessionLeasePolicy()
    )
    different = (
        _issue(_contract("session:worktree-one", worktree="worktree:one")),
        _issue(_contract("session:worktree-two", worktree="worktree:other")),
    )
    separate = CodingSessionOwnershipProjection.project(
        different, observation_time=15, policy=CodingSessionLeasePolicy()
    )
    assert conflict.state is CodingSessionCoordinationState.CONFLICTED
    assert len(conflict.active_leases) == 2
    assert shared.state is CodingSessionCoordinationState.READ_OWNED
    assert separate.state is CodingSessionCoordinationState.WRITE_OWNED


def test_pause_resume_prerequisites_and_duplicate_resume_remain_explicit() -> None:
    journal, checkpoint = _journal_checkpoint()
    request = _resume_request(checkpoint)
    eligible = CodingSessionResumeAssessment.assess(
        request,
        _lifecycle(CodingSessionLifecycleState.SUSPENDED),
        checkpoint,
        journal,
        None,
    )
    blocked_lifecycle = _lifecycle(CodingSessionLifecycleState.SUSPENDED)
    blocked_lifecycle = blocked_lifecycle.__class__(
        blocked_lifecycle.session_identity,
        lifecycle=blocked_lifecycle.lifecycle,
        repository_correspondence=CodingSessionRepositoryCorrespondenceState.STALE,
        cancellation=CodingSessionCancellationState.REQUESTED,
        recovery=CodingSessionRecoveryState.REQUIRED,
    )
    blocked = CodingSessionResumeAssessment.assess(
        request,
        blocked_lifecycle,
        checkpoint,
        journal,
        None,
        frozenset({request.fingerprint}),
    )
    assert eligible.eligible
    assert not blocked.eligible
    assert blocked.lifecycle_fact is None


def test_all_reference_adapters_preserve_authority_and_late_facts(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    assert runtime.integrations.repository is not None
    contract, lease, lifecycle, binding = repository_facts()
    repository = runtime.integrations.repository.project(
        contract, lifecycle, lease, binding, observation_time=15
    )
    assert repository.contract is not None
    assert not hasattr(repository.lease, "authorization")

    governance = governance_context(CodingSessionLifecycleState.TERMINAL)
    governance_projection = runtime.integrations.governance.project_receipt(
        governance,
        governance_receipt(governance, status=CodingSessionAuthorizationStatus.GRANTED),
        observed_at=15,
    )
    assert not governance_projection.grants_authority
    assert not governance_projection.reopens_session

    worker = worker_context(CodingSessionLifecycleState.TERMINAL)
    worker_projection = runtime.integrations.workers_missions.project_receipt(
        worker, worker_receipt(worker, state=CodingSessionWorkerReceiptState.LATE_RESULT)
    )
    assert worker_projection.state is CodingSessionWorkerBindingProjectionState.UNKNOWN
    assert not worker_projection.session_completed

    sandbox = sandbox_context(CodingSessionLifecycleState.TERMINAL)
    sandbox_projection = runtime.integrations.sandbox.project_receipt(
        sandbox,
        sandbox_receipt(sandbox, state=CodingSessionSandboxReceiptState.EXITED, exit_code=0),
    )
    assert (
        sandbox_projection.state is CodingSessionExecutionBindingProjectionState.EXITED_UNVERIFIED
    )
    assert not sandbox_projection.session_completed
    assert not sandbox_projection.reopens_terminal_session

    evaluation = eval_context(CodingSessionLifecycleState.TERMINAL)
    eval_projection = runtime.integrations.private_evals.project_receipt(
        evaluation, eval_receipt(evaluation, state=CodingSessionEvalReceiptState.LATE)
    )
    assert not eval_projection.session_completed
    assert not eval_projection.reopens_terminal_session

    session, _, candidate, assessment, handoff = deployment_facts()
    deployment_projection = runtime.integrations.deployment.assess_handoff(
        candidate,
        handoff,
        candidate_assessment=assessment,
        lifecycle=CodingSessionStateProjection(
            session.session_identity, lifecycle=CodingSessionLifecycleState.TERMINAL
        ),
        receipt=deployment_receipt(session, candidate, handoff),
    )
    assert deployment_projection.state is CodingSessionDeploymentProjectionState.HANDED_OFF
    assert not deployment_projection.rollout_executed
    assert not deployment_projection.session_completed
    assert not deployment_projection.reopens_terminal_session

    capability_states = {item.capability: item.state for item in runtime.health().integrations}
    assert (
        capability_states[CodingSessionsCapability.SANDBOX_CONCRETE_EXECUTION]
        is CodingSessionsCapabilityState.UNAVAILABLE
    )
    assert (
        capability_states[CodingSessionsCapability.DEPLOYMENT_RUNTIME]
        is CodingSessionsCapabilityState.UNAVAILABLE
    )
