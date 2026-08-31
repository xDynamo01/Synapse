from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.sandbox import (
    SandboxAdmissionDecisionOutcome,
    SandboxArtifactKind,
    SandboxCancellationEventKind,
    SandboxCancellationService,
    SandboxCleanupState,
    SandboxCompleteness,
    SandboxEvidenceCategory,
    SandboxExecutionResultOutcome,
    SandboxExitClassification,
    SandboxMaterializationAction,
    SandboxMaterializationPlanService,
    SandboxMaterializationResultOutcome,
    SandboxOccurrenceMetadata,
    SandboxRecordDraft,
    SandboxRecoveryState,
    SandboxResultMaterializationStatus,
    SandboxRetentionMetadata,
    SandboxRuntimeEventKind,
    SandboxRuntimeSupervisionService,
    SandboxSQLiteConfig,
    SandboxSQLiteDatabase,
    SandboxStoreResponsibility,
    SandboxTerminationEscalationStage,
    SandboxWriteDisposition,
)
from synapse.sandbox.errors import (
    SandboxPersistenceConflict,
    SandboxPersistenceCorrupt,
    SandboxPersistenceVersionUnsupported,
)
from synapse.sandbox_composition import (
    SandboxRuntimeBuilder,
    SandboxRuntimeConfig,
    SandboxRuntimeFeatures,
    SandboxRuntimePorts,
)
from test_sandbox_admission_facts import NOW as ADMISSION_NOW
from test_sandbox_admission_facts import FactCompleteness, request, snapshot
from test_sandbox_admission_policy import policy, rebuild
from test_sandbox_cancellation import (
    decision as cancellation_decision,
)
from test_sandbox_cancellation import (
    event as cancellation_event,
)
from test_sandbox_cancellation import (
    policy as cancellation_policy,
)
from test_sandbox_capability_grants import evaluate as capability_evaluate
from test_sandbox_capability_grants import pipeline
from test_sandbox_execution_plan import specification as execution_specification
from test_sandbox_materialization import Custody, Verification, Workspace, materialization_request
from test_sandbox_result_materialization import (
    item as evidence_item,
)
from test_sandbox_result_materialization import (
    items as evidence_items,
)
from test_sandbox_result_materialization import (
    request as result_request,
)
from test_sandbox_runtime_supervision import (
    Ports,
    event,
    observation,
    proof,
    running_events,
    start_request,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def runtime_config(
    database_path: Path,
    *,
    materialization_ports: bool = False,
    supervision_ports: bool = False,
    workspace: Workspace | None = None,
) -> SandboxRuntimeConfig:
    ports = Ports()
    material_request = materialization_request()
    material_plan = SandboxMaterializationPlanService.build(material_request)
    selected_workspace = workspace or Workspace()
    return SandboxRuntimeConfig(
        database_path=database_path.resolve(),
        database_reference="sandbox-e2e:sqlite",
        migration_applied_at=NOW,
        admission_policy=policy(),
        features=SandboxRuntimeFeatures(
            materialization=materialization_ports,
            supervision=supervision_ports,
        ),
        ports=SandboxRuntimePorts(
            custody=Custody() if materialization_ports else None,
            workspace=selected_workspace if materialization_ports else None,
            materialization_verification=(
                Verification(material_plan) if materialization_ports else None
            ),
            workload_start=ports if supervision_ports else None,
            runtime_observation=ports if supervision_ports else None,
            runtime_termination=ports if supervision_ports else None,
            runtime_metrics=ports if supervision_ports else None,
            runtime_isolation=ports if supervision_ports else None,
        ),
    )


def record(
    responsibility: SandboxStoreResponsibility,
    kind: SandboxArtifactKind,
    identity: str,
    *,
    stream: str,
    sequence: int,
    expected: int,
    payload: object,
    lineage: tuple[str, ...] = (),
    completeness: SandboxCompleteness = SandboxCompleteness.COMPLETE,
    recovery: SandboxRecoveryState = SandboxRecoveryState.NONE,
) -> SandboxRecordDraft:
    return SandboxRecordDraft(
        responsibility=responsibility,
        artifact_kind=kind,
        semantic_identity=identity,
        stream_identity=stream,
        sequence=sequence,
        expected_stream_version=expected,
        idempotency_key=f"idempotency:{identity}",
        payload=payload,
        lineage_fingerprints=lineage,
        occurrence=SandboxOccurrenceMetadata(NOW, NOW, "sandbox-e2e"),
        retention=SandboxRetentionMetadata("retention:e2e"),
        completeness=completeness,
        recovery_state=recovery,
    )


def test_admitted_flow_reaches_persisted_result_and_evidence_through_runtime(
    tmp_path: Path,
) -> None:
    runtime = SandboxRuntimeBuilder().build(runtime_config(tmp_path / "happy.db"))
    inputs = pipeline()
    admission_request, facts, admission_policy, decision, plan = inputs
    assessment = runtime.services.admission_assessment.assess(
        admission_request, facts, evaluated_at=ADMISSION_NOW
    )
    grants = capability_evaluate(inputs)
    assert decision.outcome is SandboxAdmissionDecisionOutcome.ADMITTED
    assert runtime.services.execution_plans.build(
        admission_request,
        facts,
        assessment,
        admission_policy,
        decision,
        execution_specification(admission_request, facts),
        created_at=plan.created_at,
    ).plan_fingerprint == plan.plan_fingerprint
    assert grants.decision_id == decision.decision_id

    selected_result_request = result_request()
    materialized = runtime.services.results.materialize(selected_result_request)
    repeated = runtime.services.results.materialize(result_request())
    assert materialized.status is SandboxResultMaterializationStatus.MATERIALIZED
    assert materialized.result is not None and materialized.bundle is not None
    assert repeated.result is not None and repeated.bundle is not None
    assert materialized.result.outcome is SandboxExecutionResultOutcome.SUCCEEDED
    assert repeated.result.result_fingerprint == materialized.result.result_fingerprint
    assert repeated.bundle.evidence_fingerprint == materialized.bundle.evidence_fingerprint

    admission = runtime.stores.admission.append(
        record(
            SandboxStoreResponsibility.ADMISSION,
            SandboxArtifactKind.ADMISSION_DECISION,
            decision.decision_id.value,
            stream="admission:e2e",
            sequence=1,
            expected=0,
            payload=decision,
        )
    ).record
    persisted_plan = runtime.stores.admission.append(
        record(
            SandboxStoreResponsibility.ADMISSION,
            SandboxArtifactKind.EXECUTION_PLAN,
            plan.plan_id.value,
            stream="admission:e2e",
            sequence=2,
            expected=1,
            payload=plan,
            lineage=(admission.semantic_fingerprint,),
        )
    ).record
    persisted_grants = runtime.stores.admission.append(
        record(
            SandboxStoreResponsibility.ADMISSION,
            SandboxArtifactKind.CAPABILITY_GRANT_SET,
            selected_result_request.capabilities.grant_set_id.value,
            stream="admission:e2e",
            sequence=3,
            expected=2,
            payload=selected_result_request.capabilities,
            lineage=(persisted_plan.semantic_fingerprint,),
        )
    ).record
    persisted_materialization_plan = runtime.stores.admission.append(
        record(
            SandboxStoreResponsibility.ADMISSION,
            SandboxArtifactKind.MATERIALIZATION_PLAN,
            selected_result_request.materialization_plan.materialization_plan_id.value,
            stream="admission:e2e",
            sequence=4,
            expected=3,
            payload=selected_result_request.materialization_plan,
            lineage=(persisted_grants.semantic_fingerprint,),
        )
    ).record
    persisted_materialization = runtime.stores.lifecycle.append(
        record(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.MATERIALIZATION_RECORD,
            selected_result_request.materialization.materialization_id.value,
            stream="lifecycle:e2e",
            sequence=1,
            expected=0,
            payload=selected_result_request.materialization,
            lineage=(persisted_materialization_plan.semantic_fingerprint,),
        )
    ).record
    persisted_attempt = runtime.stores.lifecycle.append(
        record(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.EXECUTION_ATTEMPT,
            selected_result_request.attempt.attempt_id.value,
            stream="lifecycle:e2e",
            sequence=2,
            expected=1,
            payload=selected_result_request.attempt,
            lineage=(persisted_materialization.semantic_fingerprint,),
        )
    ).record
    assert selected_result_request.termination_proof is not None
    persisted_termination = runtime.stores.lifecycle.append(
        record(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.TERMINATION_PROOF,
            selected_result_request.termination_proof.proof_id.value,
            stream="lifecycle:e2e",
            sequence=3,
            expected=2,
            payload=selected_result_request.termination_proof,
            lineage=(persisted_attempt.semantic_fingerprint,),
        )
    ).record
    persisted_result = runtime.stores.results.append(
        record(
            SandboxStoreResponsibility.RESULT,
            SandboxArtifactKind.EXECUTION_RESULT,
            materialized.result.result_id.value,
            stream="result:e2e",
            sequence=1,
            expected=0,
            payload=materialized.result,
            lineage=(persisted_termination.semantic_fingerprint,),
        )
    ).record
    persisted_bundle = runtime.stores.results.append(
        record(
            SandboxStoreResponsibility.RESULT,
            SandboxArtifactKind.EVIDENCE_BUNDLE,
            materialized.bundle.evidence_id.value,
            stream="result:e2e",
            sequence=2,
            expected=1,
            payload=materialized.bundle,
            lineage=(persisted_result.semantic_fingerprint,),
        )
    ).record

    replay = runtime.stores.results.replay("result:e2e")
    assert runtime.stores.admission.replay("admission:e2e").complete
    assert runtime.stores.lifecycle.replay("lifecycle:e2e").complete
    assert replay.complete
    assert tuple(item.sequence for item in replay.records) == (1, 2)
    assert replay.records[-1].semantic_fingerprint == persisted_bundle.semantic_fingerprint
    assert runtime.health().real_execution_available is False
    runtime.close()


@pytest.mark.parametrize(
    ("facts", "expected"),
    (
        (FactCompleteness.INCOMPLETE, SandboxAdmissionDecisionOutcome.INCOMPLETE),
        (FactCompleteness.ABSENT, SandboxAdmissionDecisionOutcome.UNAVAILABLE),
        (FactCompleteness.UNKNOWN, SandboxAdmissionDecisionOutcome.UNAVAILABLE),
    ),
)
def test_denial_incomplete_stale_unavailable_and_artifact_mismatch_remain_distinct(
    tmp_path: Path,
    facts: FactCompleteness,
    expected: SandboxAdmissionDecisionOutcome,
) -> None:
    runtime = SandboxRuntimeBuilder().build(runtime_config(tmp_path / f"facts-{facts}.db"))
    selected_request = request(approval=False)
    selected_snapshot = snapshot(selected_request, approval_status=facts)
    assessed = runtime.services.admission_assessment.assess(
        selected_request, selected_snapshot, evaluated_at=ADMISSION_NOW
    )
    decision = runtime.services.admission_decisions.decide(
        selected_request,
        assessed,
        policy(approval_required=False, approval_not_required=True),
        occurred_at=ADMISSION_NOW,
    )
    assert decision.outcome is expected

    base = snapshot(request())
    mismatch = replace(
        base.artifact_facts[0],
        fingerprint=type(base.artifact_facts[0].fingerprint).from_content("mismatch"),
    )
    mismatched = rebuild(base, artifact_facts=(mismatch,))
    mismatch_assessment = runtime.services.admission_assessment.assess(
        request(), mismatched, evaluated_at=ADMISSION_NOW
    )
    mismatch_decision = runtime.services.admission_decisions.decide(
        request(), mismatch_assessment, runtime.policy, occurred_at=ADMISSION_NOW
    )
    assert mismatch_decision.outcome is SandboxAdmissionDecisionOutcome.DENIED

    stale_policy_fact = replace(
        base.policy_facts[0],
        valid_from=ADMISSION_NOW - timedelta(hours=2),
        valid_until=ADMISSION_NOW - timedelta(hours=1),
    )
    stale_snapshot = rebuild(base, policy_facts=(stale_policy_fact,))
    stale_assessment = runtime.services.admission_assessment.assess(
        request(), stale_snapshot, evaluated_at=ADMISSION_NOW
    )
    stale_decision = runtime.services.admission_decisions.decide(
        request(), stale_assessment, runtime.policy, occurred_at=ADMISSION_NOW
    )
    assert stale_decision.outcome is SandboxAdmissionDecisionOutcome.STALE
    runtime.close()


def test_controlled_materialization_exposes_partial_cleanup_without_real_io(tmp_path: Path) -> None:
    workspace = Workspace(
        fail_action=SandboxMaterializationAction.BIND_RUNTIME_ASSET,
        cleanup_fails=True,
    )
    runtime = SandboxRuntimeBuilder().build(
        runtime_config(
            tmp_path / "partial.db",
            materialization_ports=True,
            workspace=workspace,
        )
    )
    assert runtime.services.materialization is not None
    outcome = runtime.services.materialization.materialize(materialization_request())
    assert outcome.outcome is SandboxMaterializationResultOutcome.CLEANUP_REQUIRED
    assert outcome.cleanup_state is SandboxCleanupState.FAILED
    assert outcome.record is None
    assert [name for name, _ in workspace.calls][-1] == "cleanup"
    assert not runtime.health().real_execution_available
    runtime.close()


def test_timeout_descendant_and_cancellation_escalation_never_invent_proof(
    tmp_path: Path,
) -> None:
    runtime = SandboxRuntimeBuilder().build(runtime_config(tmp_path / "lifecycle.db"))
    start = start_request()
    attempt = SandboxRuntimeSupervisionService.create_attempt(start)
    timed_out = runtime.services.supervision_reducer.evaluate(
        start,
        (
            *running_events(attempt),
            event(
                4,
                SandboxRuntimeEventKind.RUNTIME_OBSERVED,
                attempt,
                observation=observation(
                    alive=False,
                    exit_classification=SandboxExitClassification.TIMED_OUT,
                    descendants=(type(start.attempt_ref)("child:active"),),
                ),
            ),
        ),
    )
    assert timed_out.termination_proof_ref is None
    assert timed_out.cleanup_required

    forced_policy = cancellation_policy(forced=True)
    current_attempt, _, _, selected = cancellation_decision(selected_policy=forced_policy)
    termination = proof(current_attempt)
    events = (
        cancellation_event(1, SandboxCancellationEventKind.CANCELLATION_REQUESTED, selected),
        cancellation_event(2, SandboxCancellationEventKind.CANCELLATION_ACKNOWLEDGED, selected),
        cancellation_event(3, SandboxCancellationEventKind.TERMINATION_REQUESTED, selected),
        cancellation_event(
            4,
            SandboxCancellationEventKind.TERMINATION_INITIATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.COOPERATIVE_CANCELLATION,
        ),
        cancellation_event(
            5,
            SandboxCancellationEventKind.ESCALATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.GRACEFUL_TERMINATION,
        ),
        cancellation_event(
            6,
            SandboxCancellationEventKind.ESCALATED,
            selected,
            escalation_stage=SandboxTerminationEscalationStage.FORCED_TERMINATION,
        ),
        cancellation_event(
            7,
            SandboxCancellationEventKind.TERMINATION_VERIFIED,
            selected,
            termination_proof=termination,
        ),
        cancellation_event(8, SandboxCancellationEventKind.CANCELLATION_COMPLETED, selected),
    )
    cancelled = SandboxCancellationService.reduce(selected, forced_policy, events, occurred_at=NOW)
    assert cancelled.escalation.applied_stage is SandboxTerminationEscalationStage.FORCED_TERMINATION
    runtime.close()


RESTART_CASES = (
    (SandboxArtifactKind.ADMISSION_DECISION, SandboxRecoveryState.NONE, SandboxCompleteness.COMPLETE),
    (SandboxArtifactKind.EXECUTION_PLAN, SandboxRecoveryState.NONE, SandboxCompleteness.COMPLETE),
    (
        SandboxArtifactKind.MATERIALIZATION_OUTCOME,
        SandboxRecoveryState.CLEANUP_REQUIRED,
        SandboxCompleteness.PARTIAL,
    ),
    (
        SandboxArtifactKind.EXECUTION_ATTEMPT,
        SandboxRecoveryState.ATTEMPT_INCOMPLETE,
        SandboxCompleteness.PARTIAL,
    ),
    (
        SandboxArtifactKind.CANCELLATION_REQUEST,
        SandboxRecoveryState.CANCELLATION_IN_PROGRESS,
        SandboxCompleteness.PARTIAL,
    ),
    (
        SandboxArtifactKind.TERMINATION_PROOF,
        SandboxRecoveryState.TERMINATION_UNVERIFIED,
        SandboxCompleteness.PARTIAL,
    ),
    (
        SandboxArtifactKind.EXECUTION_RESULT,
        SandboxRecoveryState.EVIDENCE_INCOMPLETE,
        SandboxCompleteness.PARTIAL,
    ),
    (
        SandboxArtifactKind.CANCELLATION_RESULT,
        SandboxRecoveryState.MANUAL_INTERVENTION,
        SandboxCompleteness.PARTIAL,
    ),
)


@pytest.mark.parametrize(("kind", "state", "completeness"), RESTART_CASES)
def test_restart_preserves_each_intermediate_fact_without_action(
    tmp_path: Path,
    kind: SandboxArtifactKind,
    state: SandboxRecoveryState,
    completeness: SandboxCompleteness,
) -> None:
    database_path = tmp_path / f"restart-{kind}.db"
    first = SandboxRuntimeBuilder().build(runtime_config(database_path))
    responsibility = (
        SandboxStoreResponsibility.ADMISSION
        if kind in {SandboxArtifactKind.ADMISSION_DECISION, SandboxArtifactKind.EXECUTION_PLAN}
        else (
            SandboxStoreResponsibility.RESULT
            if kind is SandboxArtifactKind.EXECUTION_RESULT
            else SandboxStoreResponsibility.LIFECYCLE
        )
    )
    store = {
        SandboxStoreResponsibility.ADMISSION: first.stores.admission,
        SandboxStoreResponsibility.LIFECYCLE: first.stores.lifecycle,
        SandboxStoreResponsibility.RESULT: first.stores.results,
    }[responsibility]
    persisted = store.append(
        record(
            responsibility,
            kind,
            f"{kind}:restart",
            stream=f"{kind}:restart",
            sequence=1,
            expected=0,
            payload={"kind": kind, "terminal": False},
            completeness=completeness,
            recovery=state,
        )
    ).record
    health_before = first.health()
    first.close()

    reopened = SandboxRuntimeBuilder().build(runtime_config(database_path))
    reopened_store = {
        SandboxStoreResponsibility.ADMISSION: reopened.stores.admission,
        SandboxStoreResponsibility.LIFECYCLE: reopened.stores.lifecycle,
        SandboxStoreResponsibility.RESULT: reopened.stores.results,
    }[responsibility]
    exact = reopened_store.get_exact(persisted.semantic_identity, persisted.semantic_fingerprint)
    findings = reopened.stores.recovery.findings()
    assert exact == persisted
    assert reopened.health().schema_valid == health_before.schema_valid
    assert not reopened.health().real_execution_available
    if state is SandboxRecoveryState.NONE:
        assert findings == ()
    else:
        assert [(finding.state, finding.completeness) for finding in findings] == [
            (state, completeness)
        ]
    assert reopened_store.append(
        replace(
            record(
                responsibility,
                kind,
                f"{kind}:restart",
                stream=f"{kind}:restart",
                sequence=1,
                expected=0,
                payload={"kind": kind, "terminal": False},
                completeness=completeness,
                recovery=state,
            ),
            occurrence=SandboxOccurrenceMetadata(NOW + timedelta(minutes=1), NOW, "restart"),
        )
    ).disposition is SandboxWriteDisposition.REPLAYED
    reopened.close()


def test_recovery_is_read_only_and_incomplete_evidence_never_becomes_bundle(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "read-only.db"
    first = SandboxRuntimeBuilder().build(runtime_config(database_path))
    first.stores.results.append(
        record(
            SandboxStoreResponsibility.RESULT,
            SandboxArtifactKind.EVIDENCE_BUNDLE,
            "evidence:incomplete",
            stream="evidence:incomplete",
            sequence=1,
            expected=0,
            payload={"bundle": None},
            completeness=SandboxCompleteness.INVALID,
            recovery=SandboxRecoveryState.EVIDENCE_INCOMPLETE,
        )
    )
    before = first.stores.results.replay("evidence:incomplete")
    first.close()

    reopened = SandboxRuntimeBuilder().build(runtime_config(database_path))
    assert reopened.stores.recovery.findings()[0].state is SandboxRecoveryState.EVIDENCE_INCOMPLETE
    after = reopened.stores.results.replay("evidence:incomplete")
    assert after == before
    incomplete = reopened.services.results.materialize(
        replace(result_request(), evidence_items=evidence_items()[1:])
    )
    assert incomplete.status is SandboxResultMaterializationStatus.INCOMPLETE
    assert incomplete.bundle is None
    assert evidence_item(SandboxEvidenceCategory.ADMISSION) not in evidence_items()[1:]
    reopened.close()


def test_corruption_unknown_version_lineage_gap_and_conflict_fail_closed(
    tmp_path: Path,
) -> None:
    runtime = SandboxRuntimeBuilder().build(runtime_config(tmp_path / "integrity.db"))
    first = runtime.stores.lifecycle.append(
        record(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.EXECUTION_ATTEMPT,
            "attempt:integrity",
            stream="attempt:integrity",
            sequence=1,
            expected=0,
            payload={"attempt": "started"},
        )
    ).record
    runtime.stores.lifecycle.append(
        record(
            SandboxStoreResponsibility.LIFECYCLE,
            SandboxArtifactKind.RUNTIME_EVENT,
            "event:integrity",
            stream="attempt:integrity",
            sequence=2,
            expected=1,
            payload={"event": "observed"},
            lineage=(first.semantic_fingerprint, "sha256:" + "f" * 64),
        )
    )
    replay = runtime.stores.lifecycle.replay("attempt:integrity")
    assert not replay.complete
    assert replay.missing_lineage_fingerprints == ("sha256:" + "f" * 64,)
    with pytest.raises(SandboxPersistenceConflict):
        runtime.stores.lifecycle.append(
            record(
                SandboxStoreResponsibility.LIFECYCLE,
                SandboxArtifactKind.EXECUTION_ATTEMPT,
                "attempt:integrity",
                stream="attempt:integrity",
                sequence=1,
                expected=0,
                payload={"attempt": "divergent"},
            )
        )

    database = SandboxSQLiteDatabase(SandboxSQLiteConfig((tmp_path / "integrity.db").resolve()))
    with database.connection() as connection:
        connection.execute("DROP TRIGGER sandbox_lifecycle_records_no_update")
        connection.execute(
            "UPDATE sandbox_lifecycle_records SET payload='{}' WHERE semantic_identity=?",
            (first.semantic_identity,),
        )
    with pytest.raises(SandboxPersistenceCorrupt):
        runtime.stores.lifecycle.get_exact(first.semantic_identity, first.semantic_fingerprint)
    runtime.close()

    versioned = SandboxRuntimeBuilder().build(runtime_config(tmp_path / "version.db"))
    version_record = versioned.stores.results.append(
        record(
            SandboxStoreResponsibility.RESULT,
            SandboxArtifactKind.EXECUTION_RESULT,
            "result:version",
            stream="result:version",
            sequence=1,
            expected=0,
            payload={"result": "unknown-version"},
        )
    ).record
    version_database = SandboxSQLiteDatabase(SandboxSQLiteConfig((tmp_path / "version.db").resolve()))
    with version_database.connection() as connection:
        connection.execute("DROP TRIGGER sandbox_result_records_no_update")
        connection.execute("UPDATE sandbox_result_records SET schema_version=2")
    with pytest.raises(SandboxPersistenceVersionUnsupported):
        versioned.stores.results.get_exact(
            version_record.semantic_identity, version_record.semantic_fingerprint
        )
    versioned.close()


def test_controlled_adapters_are_not_part_of_production_public_surface() -> None:
    import synapse.sandbox_composition as composition

    for test_adapter in ("Custody", "Workspace", "Verification", "Ports"):
        assert not hasattr(composition, test_adapter)
