from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from synapse.private_evals import (
    BaselineListFilter,
    ComparisonId,
    ComparisonListFilter,
    ComparisonResult,
    ContentChecksum,
    DatasetBindingListFilter,
    EvalAnalysisStore,
    EvalCatalogStore,
    EvalDuplicateRecord,
    EvalEvidenceStore,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalMaterializationStore,
    EvalRecordNotFound,
    EvalRunFinalizationFactory,
    EvalRunId,
    EvalRunManifestBuilder,
    EvalRunStore,
    EvalSchemaVersionMismatch,
    EvalStoreUnavailable,
    Fingerprint,
    IdempotencyKey,
    PageRequest,
    RegressionReportId,
    Revision,
    RunListFilter,
    ScoringDecisionFactory,
    StoreOrder,
    SuiteListFilter,
    WriteDisposition,
    content_checksum,
    evaluation_attempt_record,
)
from synapse.private_evals.analysis import EvalComparison, RegressionReport
from synapse.private_evals.sqlite_serialization import decode_record, encode_record
from synapse.private_evals.sqlite_stores import (
    SCHEMA_VERSION,
    SQLiteEvalAnalysisStore,
    SQLiteEvalCatalogStore,
    SQLiteEvalEvidenceStore,
    SQLiteEvalMaterializationStore,
    SQLiteEvalRunStore,
)
from synapse.private_evals.values import EvalResultId, UtcTimestamp
from test_private_evals_analysis import NOW as ANALYSIS_NOW
from test_private_evals_analysis import candidate, rule
from test_private_evals_case_evaluation import evaluation_request, evaluation_response
from test_private_evals_catalog_runtime import (
    CASE_ID,
    LATER,
    SUITE_ID,
    VERSION,
    binding,
    suite,
)
from test_private_evals_result_materialization import FACTORY, materialization
from test_private_evals_run_finalization import finalization_input
from test_private_evals_run_runtime import manifest_spec
from test_private_evals_run_scoring import scoring_input, with_result_change
from test_private_evals_sqlite_stores import (
    config,
    evidence_records,
    populate_catalog,
    seed_evidence_finalization,
)

METHOD_COVERAGE = {
    EvalCatalogStore: {
        "create_suite": "test_catalog_protocol_methods_and_every_family_restart",
        "get_suite": "test_catalog_protocol_methods_and_every_family_restart",
        "update_suite": "test_catalog_protocol_methods_and_every_family_restart",
        "list_suites": "test_catalog_protocol_methods_and_every_family_restart",
        "save_suite_version": "test_catalog_protocol_methods_and_every_family_restart",
        "get_suite_version": "test_catalog_protocol_methods_and_every_family_restart",
        "update_suite_version_status": "test_catalog_protocol_methods_and_every_family_restart",
        "list_suite_versions": "test_catalog_protocol_methods_and_every_family_restart",
        "save_case_version": "test_catalog_protocol_methods_and_every_family_restart",
        "get_case_version": "test_catalog_protocol_methods_and_every_family_restart",
        "update_case_version_status": "test_catalog_protocol_methods_and_every_family_restart",
        "list_case_versions": "test_catalog_protocol_methods_and_every_family_restart",
        "save_dataset_binding": "test_catalog_protocol_methods_and_every_family_restart",
        "get_dataset_binding": "test_catalog_protocol_methods_and_every_family_restart",
        "list_dataset_bindings": "test_catalog_protocol_methods_and_every_family_restart",
    },
    EvalRunStore: {
        "create_run": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_run": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "update_run": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "list_runs": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "save_manifest": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_manifest": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "save_result": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_result": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_result_for_execution": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "result_exists": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "list_results": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "save_evaluation_attempt": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_evaluation_attempt": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "save_finalization": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_finalization": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "get_finalization_for_run": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
        "finalization_exists": "test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization",
    },
    EvalAnalysisStore: {
        "save_scoring_decision": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "get_scoring_decision": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "get_scoring_decision_for_run": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "scoring_decision_exists": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "create_baseline": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "get_baseline": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "update_baseline_status": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "list_baselines": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "save_comparison": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "get_comparison": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "list_comparisons": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "save_regression_rule": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "get_regression_rule": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "save_regression_report": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
        "get_regression_report": "test_analysis_protocol_methods_are_persistence_only_and_restartable",
    },
    EvalMaterializationStore: {
        "save_materialized_output": "test_materialization_protocol_methods_replay_conflict_restart_and_corruption",
        "get_materialized_output": "test_materialization_protocol_methods_replay_conflict_restart_and_corruption",
        "get_materialized_output_for_execution": "test_materialization_protocol_methods_replay_conflict_restart_and_corruption",
        "materialized_output_exists": "test_materialization_protocol_methods_replay_conflict_restart_and_corruption",
    },
    EvalEvidenceStore: {
        "save_evidence_submission": "test_evidence_protocol_methods_require_complete_local_chain",
        "get_evidence_submission": "test_evidence_protocol_methods_require_complete_local_chain",
        "get_evidence_submission_for_run": "test_evidence_protocol_methods_require_complete_local_chain",
        "evidence_submission_exists": "test_evidence_protocol_methods_require_complete_local_chain",
        "save_evidence_submission_attempt": "test_evidence_protocol_methods_require_complete_local_chain",
        "list_evidence_submission_attempts": "test_evidence_protocol_methods_require_complete_local_chain",
        "save_evidence_submission_receipt": "test_evidence_protocol_methods_require_complete_local_chain",
        "list_evidence_submission_receipts": "test_evidence_protocol_methods_require_complete_local_chain",
    },
}


def protocol_methods(protocol: type[object]) -> set[str]:
    return {
        name
        for name, value in protocol.__dict__.items()
        if inspect.isfunction(value) and name != "__init__"
    }


def baseline_with_revision(model, revision: Revision):
    changed = replace(model, revision=revision)
    semantic = {
        "baseline_id": changed.baseline_id,
        "scope": changed.scope,
        "source_run_id": changed.source_run_id,
        "source_run_verdict": changed.source_run_verdict,
        "run_fingerprint": changed.run_fingerprint,
        "finalization_checksum": changed.finalization_checksum,
        "protocol_fingerprint": changed.protocol_fingerprint,
        "subject_fingerprint": changed.subject_fingerprint,
        "decision_fingerprint": changed.decision_fingerprint,
        "compatibility_signature": changed.compatibility_signature,
        "summary_checksum": changed.summary_checksum,
        "status": changed.status,
        "aggregates": changed.aggregates,
        "compatibility": changed.compatibility,
        "compatibility_policy": changed.compatibility_policy,
        "eligibility_policy": changed.eligibility_policy,
        "revision": changed.revision,
        "governance_binding_reference": changed.governance_binding_reference,
    }
    return replace(changed, content_checksum=content_checksum(semantic))


def incompatible_comparison(baseline) -> EvalComparison:
    return EvalComparison(
        ComparisonId("comparison-sqlite"),
        EvalRunId("run-current"),
        baseline.baseline_id,
        baseline.source_run_id,
        baseline.scope,
        Fingerprint("1" * 64),
        Fingerprint("2" * 64),
        (),
        ComparisonResult.INCOMPATIBLE,
        (),
        ("protocol_mismatch",),
        ContentChecksum("3" * 64),
        ANALYSIS_NOW,
    )


def incompatible_report(comparison: EvalComparison, rule_model) -> RegressionReport:
    return RegressionReport(
        RegressionReportId("report-sqlite"),
        comparison.comparison_id,
        rule_model.rule_id,
        rule_model.version,
        rule_model.checksum,
        ComparisonResult.INCOMPATIBLE,
        (),
        ("comparison_incompatible",),
        ContentChecksum("4" * 64),
        ANALYSIS_NOW,
        baseline_id=comparison.baseline_id,
        current_run_id=comparison.current_run_id,
        comparison_fingerprint=Fingerprint(comparison.checksum.value),
    )


def test_method_coverage_manifest_exactly_matches_all_protocol_operations() -> None:
    concrete = {
        EvalCatalogStore: SQLiteEvalCatalogStore,
        EvalRunStore: SQLiteEvalRunStore,
        EvalAnalysisStore: SQLiteEvalAnalysisStore,
        EvalMaterializationStore: SQLiteEvalMaterializationStore,
        EvalEvidenceStore: SQLiteEvalEvidenceStore,
    }
    for protocol, coverage in METHOD_COVERAGE.items():
        assert set(coverage) == protocol_methods(protocol)
        assert all(callable(getattr(concrete[protocol], method)) for method in coverage)


def test_catalog_protocol_methods_and_every_family_restart(tmp_path: Path) -> None:
    database = tmp_path / "catalog.sqlite3"
    store = SQLiteEvalCatalogStore(config(database))
    runtime = populate_catalog(store)
    updated_suite = replace(suite(), revision=Revision(2), updated_at=LATER, name="updated")
    assert store.update_suite(
        updated_suite,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("suite-update-direct"),
    ).stored_revision == Revision(2)
    frozen_case = runtime.freeze_case_version(
        SUITE_ID,
        CASE_ID,
        VERSION,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("case-freeze-audit"),
    )
    frozen_version = runtime.freeze_suite_version(
        SUITE_ID,
        VERSION,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("version-freeze-audit"),
    )
    assert store.get_suite(SUITE_ID) == updated_suite
    assert store.get_suite_version(SUITE_ID, VERSION) == frozen_version
    assert store.get_case_version(SUITE_ID, CASE_ID, VERSION) == frozen_case
    assert store.get_dataset_binding(binding().binding_id, Revision(1)) == binding()
    assert store.list_suites(SuiteListFilter(), PageRequest()).items == (updated_suite,)
    assert store.list_suite_versions(SUITE_ID, PageRequest()).items == (frozen_version,)
    assert store.list_case_versions(SUITE_ID, VERSION, PageRequest()).items == (frozen_case,)
    assert store.list_dataset_bindings(
        DatasetBindingListFilter(asset_id=binding().asset_id), PageRequest()
    ).items == (binding(),)
    store.close()
    reopened = SQLiteEvalCatalogStore(config(database, create_if_missing=False))
    assert reopened.get_suite(SUITE_ID) == updated_suite
    assert reopened.get_suite_version(SUITE_ID, VERSION) == frozen_version
    assert reopened.get_case_version(SUITE_ID, CASE_ID, VERSION) == frozen_case
    assert reopened.get_dataset_binding(binding().binding_id, Revision(1)) == binding()


def test_run_protocol_methods_restart_slots_attempt_sequence_and_finalization(
    tmp_path: Path,
) -> None:
    database = tmp_path / "run.sqlite3"
    store = SQLiteEvalRunStore(config(database))
    source = finalization_input()
    run = replace(source.run, revision=Revision(1))
    store.create_run(run, idempotency_key=IdempotencyKey("run-create-audit"))
    updated = replace(run, revision=Revision(2), updated_at=UtcTimestamp("2026-07-19T12:00:02Z"))
    store.update_run(
        updated,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("run-update-audit"),
    )
    spec, _ = manifest_spec()
    manifest = EvalRunManifestBuilder().build(spec)
    store.save_manifest(manifest, idempotency_key=IdempotencyKey("manifest-audit"))
    result = scoring_input().results[0]
    store.save_result(result, idempotency_key=IdempotencyKey("result-audit"))
    divergent = with_result_change(result, result_id=EvalResultId("result-divergent"))
    with pytest.raises(EvalDuplicateRecord):
        store.save_result(divergent, idempotency_key=IdempotencyKey("result-divergent"))

    attempt_run = replace(run, run_id=EvalRunId("run-1"), revision=Revision(1))
    store.create_run(attempt_run, idempotency_key=IdempotencyKey("attempt-run"))
    request = evaluation_request()
    attempt_one = evaluation_attempt_record(request, evaluation_response(request), attempt=1)
    attempt_two = replace(attempt_one, attempt=2, fingerprint=None, checksum=None)
    attempt_three = replace(attempt_one, attempt=3, fingerprint=None, checksum=None)
    with pytest.raises(EvalIntegrityConflict):
        store.save_evaluation_attempt(
            attempt_two, idempotency_key=IdempotencyKey("attempt-gap-first")
        )
    store.save_evaluation_attempt(attempt_one, idempotency_key=IdempotencyKey("attempt-one"))
    with pytest.raises(EvalIntegrityConflict):
        store.save_evaluation_attempt(
            attempt_three, idempotency_key=IdempotencyKey("attempt-gap-third")
        )
    store.save_evaluation_attempt(attempt_two, idempotency_key=IdempotencyKey("attempt-two"))

    finalization = EvalRunFinalizationFactory().create(source)
    store.save_finalization(finalization, idempotency_key=IdempotencyKey("finalization-audit"))
    assert store.get_run(run.run_id) == updated
    assert store.list_runs(RunListFilter(), PageRequest(order=StoreOrder.ID_ASC)).total == 2
    assert store.get_manifest(manifest.manifest_id) == manifest
    assert store.get_result(result.result_id) == result
    assert store.get_result_for_execution(
        result.run_id, result.case_reference, result.repetition
    ) == result
    assert store.result_exists(result.run_id, result.case_reference, result.repetition)
    assert store.list_results(result.run_id, PageRequest()).items == (result,)
    assert store.get_evaluation_attempt(attempt_one.fingerprint) == attempt_one
    assert store.get_finalization(finalization.finalization_id) == finalization
    assert store.get_finalization_for_run(run.run_id) == finalization
    assert store.finalization_exists(run.run_id)
    store.close()
    reopened = SQLiteEvalRunStore(config(database, create_if_missing=False))
    assert reopened.get_result(result.result_id) == result
    assert reopened.get_evaluation_attempt(attempt_two.fingerprint) == attempt_two
    assert reopened.get_finalization(finalization.finalization_id) == finalization


def test_analysis_protocol_methods_are_persistence_only_and_restartable(tmp_path: Path) -> None:
    database = tmp_path / "analysis.sqlite3"
    store = SQLiteEvalAnalysisStore(config(database))
    decision = ScoringDecisionFactory().create(scoring_input())
    baseline = candidate()
    updated_baseline = baseline_with_revision(baseline, Revision(2))
    comparison = incompatible_comparison(baseline)
    rule_model = rule()
    report = incompatible_report(comparison, rule_model)
    store.save_scoring_decision(decision, idempotency_key=IdempotencyKey("decision-audit"))
    store.create_baseline(baseline, idempotency_key=IdempotencyKey("baseline-audit"))
    store.update_baseline_status(
        updated_baseline,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("baseline-update-audit"),
    )
    store.save_comparison(comparison, idempotency_key=IdempotencyKey("comparison-audit"))
    store.save_regression_rule(rule_model, idempotency_key=IdempotencyKey("rule-audit"))
    store.save_regression_report(report, idempotency_key=IdempotencyKey("report-audit"))
    assert store.get_scoring_decision(decision.decision_id) == decision
    assert store.get_scoring_decision_for_run(decision.run_id) == decision
    assert store.scoring_decision_exists(decision.run_id)
    assert store.get_baseline(baseline.baseline_id) == updated_baseline
    assert store.list_baselines(BaselineListFilter(), PageRequest()).items == (
        updated_baseline,
    )
    assert store.get_comparison(comparison.comparison_id) == comparison
    assert store.list_comparisons(ComparisonListFilter(), PageRequest()).items == (
        comparison,
    )
    assert store.get_regression_rule(rule_model.rule_id, rule_model.version) == rule_model
    assert store.get_regression_report(report.report_id) == report
    assert store.save_comparison(
        comparison, idempotency_key=IdempotencyKey("comparison-replay")
    ).disposition is WriteDisposition.IDEMPOTENT_REPLAY
    store.close()
    reopened = SQLiteEvalAnalysisStore(config(database, create_if_missing=False))
    assert reopened.get_scoring_decision(decision.decision_id) == decision
    assert reopened.get_baseline(baseline.baseline_id) == updated_baseline
    assert reopened.get_comparison(comparison.comparison_id) == comparison
    assert reopened.get_regression_rule(rule_model.rule_id, rule_model.version) == rule_model
    assert reopened.get_regression_report(report.report_id) == report


def test_comparison_filters_are_applied_before_pagination(tmp_path: Path) -> None:
    store = SQLiteEvalAnalysisStore(config(tmp_path / "comparison-volume.sqlite3"))
    baseline = candidate()
    source = incompatible_comparison(baseline)
    target_run = EvalRunId("run-target-after-500")
    target = None
    for index in range(501):
        current = replace(
            source,
            comparison_id=ComparisonId(f"comparison-volume-{index:03d}"),
            current_run_id=target_run if index == 500 else EvalRunId(f"run-{index:03d}"),
        )
        store.save_comparison(
            current, idempotency_key=IdempotencyKey(f"comparison-volume-{index:03d}")
        )
        if index == 500:
            target = current
    page = store.list_comparisons(
        ComparisonListFilter(current_run_id=target_run), PageRequest(limit=1)
    )
    assert page.items == (target,)
    assert page.total == 1


def test_materialization_protocol_methods_replay_conflict_restart_and_corruption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "materialization.sqlite3"
    record = FACTORY.create(materialization())
    store = SQLiteEvalMaterializationStore(config(database))
    store.save_materialized_output(record, idempotency_key=IdempotencyKey("output-audit"))
    assert store.get_materialized_output(record.output_id) == record
    assert store.get_materialized_output_for_execution(
        record.run_id, record.case_reference, record.repetition
    ) == record
    assert store.materialized_output_exists(
        record.run_id, record.case_reference, record.repetition
    )
    assert store.save_materialized_output(
        record, idempotency_key=IdempotencyKey("output-replay-audit")
    ).disposition is WriteDisposition.IDEMPOTENT_REPLAY
    divergent = replace(record, output_id=type(record.output_id)("output-divergent"))
    with pytest.raises(EvalDuplicateRecord):
        store.save_materialized_output(
            divergent, idempotency_key=IdempotencyKey("output-divergent-audit")
        )
    store.close()
    reopened = SQLiteEvalMaterializationStore(config(database, create_if_missing=False))
    assert reopened.get_materialized_output(record.output_id) == record


def test_slice_16_schema_v1_row_survives_store_write_outcome_translation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "slice-16-v1.sqlite3"
    record = FACTORY.create(materialization())
    store = SQLiteEvalMaterializationStore(config(database))
    created = store.save_materialized_output(
        record, idempotency_key=IdempotencyKey("slice-16-create")
    )
    with sqlite3.connect(database) as connection:
        schema_version = connection.execute(
            "SELECT schema_version FROM private_evals_schema"
        ).fetchone()[0]
        payload, persisted_payload_checksum = connection.execute(
            """SELECT payload, payload_checksum
               FROM eval_materialized_outputs WHERE record_key = ?""",
            (record.output_id.value,),
        ).fetchone()
    assert schema_version == 1
    assert hashlib.sha256(payload.encode()).hexdigest() == persisted_payload_checksum
    assert created.checksum == record.checksum

    store.close()
    reopened = SQLiteEvalMaterializationStore(config(database, create_if_missing=False))
    assert reopened.get_materialized_output(record.output_id) == record
    replay = reopened.save_materialized_output(
        record, idempotency_key=IdempotencyKey("slice-16-replay")
    )
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    assert replay.checksum == record.checksum


def test_evidence_protocol_methods_require_complete_local_chain(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite3"
    attempt, receipt, submission, finalization = evidence_records()
    seed_evidence_finalization(database, finalization)
    store = SQLiteEvalEvidenceStore(config(database))
    store.save_evidence_submission_attempt(attempt, idempotency_key=IdempotencyKey("attempt"))
    with pytest.raises(EvalIntegrityConflict):
        store.save_evidence_submission(submission, idempotency_key=IdempotencyKey("incomplete"))
    store.save_evidence_submission_receipt(receipt, idempotency_key=IdempotencyKey("receipt"))
    store.save_evidence_submission(submission, idempotency_key=IdempotencyKey("submission"))
    assert store.list_evidence_submission_attempts(submission.semantic_fingerprint) == (attempt,)
    assert store.list_evidence_submission_receipts(submission.semantic_fingerprint) == (receipt,)
    assert store.get_evidence_submission(submission.submission_id) == submission
    assert store.get_evidence_submission_for_run(submission.run_id) == submission
    assert store.evidence_submission_exists(submission.run_id)
    assert store.save_evidence_submission_attempt(
        attempt, idempotency_key=IdempotencyKey("attempt")
    ).disposition is WriteDisposition.IDEMPOTENT_REPLAY
    late_attempt = replace(attempt, attempt_number=2, fingerprint=None, checksum=None)
    with pytest.raises(EvalIntegrityConflict):
        store.save_evidence_submission_attempt(
            late_attempt, idempotency_key=IdempotencyKey("late-attempt")
        )
    divergent_receipt = replace(
        receipt,
        governance_receipt=replace(
            receipt.governance_receipt, evidence_checksum=ContentChecksum("9" * 64)
        ),
        checksum=None,
    )
    with pytest.raises(EvalDuplicateRecord):
        store.save_evidence_submission_receipt(
            divergent_receipt, idempotency_key=IdempotencyKey("receipt-divergent")
        )
    divergent_submission = replace(
        submission, producer_version="14.0.1", checksum=None
    )
    with pytest.raises(EvalDuplicateRecord):
        store.save_evidence_submission(
            divergent_submission, idempotency_key=IdempotencyKey("submission-divergent")
        )
    store.close()
    reopened = SQLiteEvalEvidenceStore(config(database, create_if_missing=False))
    assert reopened.get_evidence_submission(submission.submission_id) == submission


def test_evidence_tuple_lists_do_not_truncate_after_500_records(tmp_path: Path) -> None:
    store = SQLiteEvalEvidenceStore(config(tmp_path / "evidence-volume.sqlite3"))
    source_attempt, source_receipt, _, _ = evidence_records()
    expected_attempts = []
    expected_receipts = []
    for index in range(1, 502):
        projection = Fingerprint(f"{index:064x}")
        attempt = replace(
            source_attempt,
            attempt_number=index,
            projection_fingerprint=projection,
            fingerprint=None,
            checksum=None,
        )
        governance_receipt = replace(
            source_receipt.governance_receipt,
            projection_fingerprint=projection,
        )
        receipt = replace(
            source_receipt,
            attempt_fingerprint=attempt.fingerprint,
            attempt_number=index,
            projection_fingerprint=projection,
            governance_receipt=governance_receipt,
            checksum=None,
        )
        store.save_evidence_submission_attempt(
            attempt, idempotency_key=IdempotencyKey(f"volume-attempt-{index}")
        )
        store.save_evidence_submission_receipt(
            receipt, idempotency_key=IdempotencyKey(f"volume-receipt-{index}")
        )
        expected_attempts.append(attempt)
        expected_receipts.append(receipt)
    assert store.list_evidence_submission_attempts(
        source_attempt.logical_submission_fingerprint
    ) == tuple(expected_attempts)
    assert store.list_evidence_submission_receipts(
        source_attempt.logical_submission_fingerprint
    ) == tuple(expected_receipts)


@pytest.mark.parametrize("version", [0, SCHEMA_VERSION + 1])
def test_schema_rejects_lower_and_higher_versions(tmp_path: Path, version: int) -> None:
    database = tmp_path / f"schema-{version}.sqlite3"
    SQLiteEvalCatalogStore(config(database)).close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE private_evals_schema SET schema_version = ? WHERE singleton = 1",
            (version,),
        )
    with pytest.raises(EvalSchemaVersionMismatch):
        SQLiteEvalCatalogStore(config(database, create_if_missing=False))


@pytest.mark.parametrize(
    "mutation",
    [
        "DROP TABLE private_evals_schema",
        "DROP TABLE eval_comparisons",
        "CREATE TABLE unexpected_table(value TEXT)",
        "DROP INDEX eval_results_semantic_identity_uq",
    ],
)
def test_schema_rejects_missing_metadata_table_index_and_unknown_table(
    tmp_path: Path, mutation: str
) -> None:
    database = tmp_path / "schema-mutated.sqlite3"
    SQLiteEvalCatalogStore(config(database)).close()
    with sqlite3.connect(database) as connection:
        connection.execute(mutation)
    with pytest.raises(EvalSchemaVersionMismatch):
        SQLiteEvalCatalogStore(config(database, create_if_missing=False))


def test_empty_database_policy_and_read_only_mode(tmp_path: Path) -> None:
    empty = tmp_path / "empty.sqlite3"
    sqlite3.connect(empty).close()
    with pytest.raises(EvalSchemaVersionMismatch):
        SQLiteEvalCatalogStore(config(empty, create_if_missing=False))
    initialized = SQLiteEvalCatalogStore(config(empty))
    initialized.create_suite(suite(), idempotency_key=IdempotencyKey("read-only-source"))
    initialized.close()
    read_only = SQLiteEvalCatalogStore(
        config(empty, create_if_missing=False, read_only=True)
    )
    assert read_only.get_suite(SUITE_ID) == suite()
    with pytest.raises(EvalStoreUnavailable):
        read_only.create_suite(suite(), idempotency_key=IdempotencyKey("read-only-write"))


def test_partial_database_and_inaccessible_path_fail_typed(tmp_path: Path) -> None:
    partial = tmp_path / "partial.sqlite3"
    with sqlite3.connect(partial) as connection:
        connection.execute("CREATE TABLE only_one(value TEXT)")
    with pytest.raises(EvalSchemaVersionMismatch):
        SQLiteEvalCatalogStore(config(partial))
    directory_as_database = tmp_path / "directory.sqlite3"
    directory_as_database.mkdir()
    with pytest.raises(EvalStoreUnavailable):
        SQLiteEvalCatalogStore(config(directory_as_database))


def test_real_connection_pragmas_close_and_idempotency_failure_rollback(tmp_path: Path) -> None:
    database = tmp_path / "failure.sqlite3"
    store = SQLiteEvalCatalogStore(config(database, timeout_seconds=0.05))
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        connection.execute(
            """CREATE TRIGGER fail_idempotency BEFORE INSERT ON private_evals_idempotency
               BEGIN SELECT RAISE(ABORT, 'idempotency failure'); END"""
        )
    with pytest.raises(EvalIdempotencyConflict):
        store.create_suite(suite(), idempotency_key=IdempotencyKey("rollback"))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM eval_suites").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_idempotency")
    store.close()
    with pytest.raises(EvalStoreUnavailable):
        store.get_suite(SUITE_ID)


def test_idempotency_equivalence_divergence_cross_identity_and_altered_record(
    tmp_path: Path,
) -> None:
    database = tmp_path / "idempotency.sqlite3"
    store = SQLiteEvalCatalogStore(config(database))
    key = IdempotencyKey("stable-key")
    created = store.create_suite(suite(), idempotency_key=key)
    replay = store.create_suite(suite(), idempotency_key=key)
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    assert replace(replay, disposition=WriteDisposition.CREATED) == created
    assert store.create_suite(
        suite(), idempotency_key=IdempotencyKey("equivalent-new-key")
    ).disposition is WriteDisposition.IDEMPOTENT_REPLAY
    with pytest.raises(EvalIdempotencyConflict):
        store.create_suite(replace(suite(), name="changed"), idempotency_key=key)
    with pytest.raises(EvalIdempotencyConflict):
        store.create_suite(
            replace(suite(), suite_id=type(SUITE_ID)("suite.other")),
            idempotency_key=key,
        )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE private_evals_idempotency SET payload_checksum = ?
               WHERE operation = ? AND idempotency_key = ?""",
            ("0" * 64, "eval_suites:create", key.value),
        )
    with pytest.raises(EvalIdempotencyConflict):
        store.create_suite(suite(), idempotency_key=key)


def test_serialization_round_trip_and_manual_payload_rejections() -> None:
    spec, _ = manifest_spec()
    manifest = EvalRunManifestBuilder().build(spec)
    payload = encode_record(manifest)
    assert decode_record(payload, type(manifest)) == manifest
    raw = json.loads(payload)
    fields = raw["record"]["$fields"]
    missing = json.loads(payload)
    missing["record"]["$fields"].pop("model_provider")
    unknown_type = json.loads(payload)
    unknown_type["record"]["$type"] = "caller.controlled.Type"
    noncanonical = payload + " "
    duplicate = payload.replace('"format_version":1', '"format_version":1,"format_version":1')
    for changed in (missing, unknown_type):
        with pytest.raises(EvalIntegrityConflict):
            decode_record(
                json.dumps(changed, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                type(manifest),
            )
    assert "$tuple" in payload and "$decimal" in payload and "$enum" in payload
    result = scoring_input().results[0]
    assert any(value is None for value in result.__dict__.values())
    assert decode_record(encode_record(result), type(result)) == result
    assert fields
    with pytest.raises(EvalIntegrityConflict):
        decode_record(noncanonical, type(manifest))
    with pytest.raises(EvalIntegrityConflict):
        decode_record(duplicate, type(manifest))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("parent_a", "forged-suite"),
        ("status", "deprecated"),
        ("revision", 99),
        ("payload_checksum", "0" * 64),
    ],
)
def test_row_identity_parent_status_revision_and_payload_checksum_corruption(
    tmp_path: Path, column: str, value: object
) -> None:
    database = tmp_path / f"corrupt-{column}.sqlite3"
    store = SQLiteEvalCatalogStore(config(database))
    populate_catalog(store)
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"UPDATE eval_suite_versions SET {column} = ? WHERE record_key = ?",
            (value, f"{SUITE_ID.value}:{VERSION.value}"),
        )
    with pytest.raises(EvalIntegrityConflict):
        store.get_suite_version(SUITE_ID, VERSION)


def test_record_checksum_semantic_fingerprint_and_missing_parent_corruption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "semantic-corruption.sqlite3"
    source = finalization_input()
    run = replace(source.run, revision=Revision(1))
    result = scoring_input().results[0]
    store = SQLiteEvalRunStore(config(database))
    store.create_run(run, idempotency_key=IdempotencyKey("run"))
    store.save_result(result, idempotency_key=IdempotencyKey("result"))
    with sqlite3.connect(database) as connection:
        payload = connection.execute(
            "SELECT payload FROM eval_results WHERE record_key = ?", (result.result_id.value,)
        ).fetchone()[0]
        data = json.loads(payload)
        data["record"]["$fields"]["checksum"]["$fields"]["value"] = "0" * 64
        changed = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        connection.execute(
            "UPDATE eval_results SET payload = ?, payload_checksum = ? WHERE record_key = ?",
            (changed, hashlib.sha256(changed.encode()).hexdigest(), result.result_id.value),
        )
    with pytest.raises(EvalIntegrityConflict):
        store.get_result(result.result_id)
    with pytest.raises(EvalIntegrityConflict):
        store.result_exists(result.run_id, result.case_reference, result.repetition)

    attempt_run = replace(run, run_id=EvalRunId("run-1"), revision=Revision(1))
    store.create_run(attempt_run, idempotency_key=IdempotencyKey("attempt-run"))
    request = evaluation_request()
    attempt = evaluation_attempt_record(request, evaluation_response(request), attempt=1)
    store.save_evaluation_attempt(attempt, idempotency_key=IdempotencyKey("attempt"))
    forged = "f" * 64
    with sqlite3.connect(database) as connection:
        payload = connection.execute(
            "SELECT payload FROM eval_evaluation_attempts WHERE record_key = ?",
            (attempt.fingerprint.value,),
        ).fetchone()[0]
        data = json.loads(payload)
        data["record"]["$fields"]["fingerprint"]["$fields"]["value"] = forged
        changed = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        connection.execute(
            """UPDATE eval_evaluation_attempts
               SET record_key = ?, payload = ?, payload_checksum = ?
               WHERE record_key = ?""",
            (
                forged,
                changed,
                hashlib.sha256(changed.encode()).hexdigest(),
                attempt.fingerprint.value,
            ),
        )
    with pytest.raises(EvalIntegrityConflict):
        store.get_evaluation_attempt(Fingerprint(forged))

    finalization = EvalRunFinalizationFactory().create(source)
    store.save_finalization(finalization, idempotency_key=IdempotencyKey("finalization"))
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM eval_runs WHERE record_key = ?", (run.run_id.value,))
    with pytest.raises(EvalIntegrityConflict):
        store.get_finalization(finalization.finalization_id)


def test_safe_errors_and_config_repr_do_not_leak_database_path(tmp_path: Path) -> None:
    database = tmp_path / "private-secret-name.sqlite3"
    store = SQLiteEvalCatalogStore(config(database))
    with pytest.raises(EvalRecordNotFound) as caught:
        store.get_suite(SUITE_ID)
    assert str(database) not in str(caught.value)
    assert str(database) not in repr(caught.value)
