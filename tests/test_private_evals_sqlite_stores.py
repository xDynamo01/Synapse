from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from synapse.private_evals import (
    EvalAnalysisStore,
    EvalCatalogRuntime,
    EvalCatalogStore,
    EvalDuplicateRecord,
    EvalEvidenceStore,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalMaterializationStore,
    EvalRevisionConflict,
    EvalRunFinalizationFactory,
    EvalRunFinalizationId,
    EvalRunId,
    EvalRunManifestBuilder,
    EvalRunRuntime,
    EvalRunStore,
    EvalSchemaVersionMismatch,
    EvalStoreUnavailable,
    IdempotencyKey,
    PrivateEvalsPersistenceConfig,
    Revision,
    StoreOrder,
    SuiteListFilter,
    WriteDisposition,
)
from synapse.private_evals.evidence_submission_service import EvalEvidenceSubmissionService
from synapse.private_evals.sqlite_stores import (
    SQLiteEvalAnalysisStore,
    SQLiteEvalCatalogStore,
    SQLiteEvalEvidenceStore,
    SQLiteEvalMaterializationStore,
    SQLiteEvalRunStore,
)
from synapse.private_evals.store_models import PageRequest
from test_private_evals_analysis import candidate
from test_private_evals_catalog_runtime import (
    CASE_ID,
    LATER,
    SUITE_ID,
    VERSION,
    binding,
    case,
    suite,
    suite_version,
)
from test_private_evals_evidence_submission import (
    EvidenceStoreFake,
    GovernanceFake,
    identities,
    scorable_planning_input,
)
from test_private_evals_result_materialization import FACTORY, materialization
from test_private_evals_run_finalization import finalization_input
from test_private_evals_run_runtime import NOW, T1, manifest_spec


def config(path: Path, **changes: object) -> PrivateEvalsPersistenceConfig:
    return PrivateEvalsPersistenceConfig(path, **changes)


def populate_catalog(store: SQLiteEvalCatalogStore) -> EvalCatalogRuntime:
    runtime = EvalCatalogRuntime(store)
    suite_model = suite()
    case_model = case()
    binding_model = binding()
    runtime.create_suite(suite_model, idempotency_key=IdempotencyKey("suite-create"))
    runtime.register_case_version(case_model, idempotency_key=IdempotencyKey("case-create"))
    runtime.register_dataset_binding(
        binding_model, idempotency_key=IdempotencyKey("binding-create")
    )
    runtime.create_suite_version(
        suite_version(case_model, binding_model),
        idempotency_key=IdempotencyKey("suite-version-create"),
    )
    return runtime


def evidence_records():
    source = scorable_planning_input()
    fake = EvidenceStoreFake()
    result = EvalEvidenceSubmissionService(fake, GovernanceFake()).submit(
        source,
        submission_id="submission-1",
        governance_identities=identities(source),
    )
    assert result.record is not None
    return fake.attempts[0], fake.receipts[0], result.record, source.finalization


def seed_evidence_finalization(database: Path, finalization) -> None:
    store = SQLiteEvalRunStore(config(database))
    run = replace(finalization_input().run, revision=Revision(1))
    store.create_run(run, idempotency_key=IdempotencyKey("evidence-run"))
    store.save_finalization(
        finalization, idempotency_key=IdempotencyKey("evidence-finalization")
    )
    store.close()


def test_concrete_stores_implement_only_the_approved_protocols(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    stores = (
        SQLiteEvalCatalogStore(config(database)),
        SQLiteEvalRunStore(config(database)),
        SQLiteEvalAnalysisStore(config(database)),
        SQLiteEvalMaterializationStore(config(database)),
        SQLiteEvalEvidenceStore(config(database)),
    )
    assert isinstance(stores[0], EvalCatalogStore)
    assert isinstance(stores[1], EvalRunStore)
    assert isinstance(stores[2], EvalAnalysisStore)
    assert isinstance(stores[3], EvalMaterializationStore)
    assert isinstance(stores[4], EvalEvidenceStore)
    for store in stores:
        store.close()


def test_catalog_restart_replay_cas_children_and_pagination(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    first = SQLiteEvalCatalogStore(config(database))
    runtime = populate_catalog(first)
    frozen_case = runtime.freeze_case_version(
        SUITE_ID,
        CASE_ID,
        VERSION,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("freeze-case"),
    )
    runtime.freeze_suite_version(
        SUITE_ID,
        VERSION,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("freeze-version"),
    )
    first.close()

    second = SQLiteEvalCatalogStore(config(database, create_if_missing=False))
    assert second.get_suite(SUITE_ID) == suite()
    assert second.get_case_version(SUITE_ID, CASE_ID, VERSION) == frozen_case
    assert second.get_dataset_binding(binding().binding_id, Revision(1)) == binding()
    assert second.list_case_versions(SUITE_ID, VERSION, PageRequest()).items == (frozen_case,)
    replay = second.create_suite(suite(), idempotency_key=IdempotencyKey("restart-replay"))
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    with pytest.raises(EvalDuplicateRecord):
        second.create_suite(
            replace(suite(), name="divergent"),
            idempotency_key=IdempotencyKey("restart-divergent"),
        )
    with pytest.raises(EvalRevisionConflict):
        second.update_suite(
            replace(suite(), revision=Revision(2), updated_at=LATER),
            expected_revision=Revision(2),
            idempotency_key=IdempotencyKey("stale"),
        )
    assert (
        second.list_suites(SuiteListFilter(), PageRequest(limit=1, order=StoreOrder.ID_ASC)).total
        == 1
    )


def test_run_manifest_and_lifecycle_cas_survive_restart(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    spec, catalog = manifest_spec()
    manifest = EvalRunManifestBuilder().build(spec)
    first = SQLiteEvalRunStore(config(database))
    runtime = EvalRunRuntime(first, catalog)
    run = runtime.prepare_run(
        EvalRunId("run-sqlite"),
        manifest,
        created_at=NOW,
        idempotency_key=IdempotencyKey("prepare-sqlite"),
    )
    first.close()

    second = SQLiteEvalRunStore(config(database, create_if_missing=False))
    assert second.get_manifest(manifest.manifest_id) == manifest
    assert second.get_run(run.run_id) == run
    validating = EvalRunRuntime(second, catalog).begin_validation(
        run.run_id,
        timestamp=T1,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("validate-sqlite"),
    )
    assert validating.revision == Revision(2)
    with pytest.raises(EvalRevisionConflict):
        second.update_run(
            replace(validating, revision=Revision(3)),
            expected_revision=Revision(1),
            idempotency_key=IdempotencyKey("stale-run"),
        )


def test_analysis_and_materialization_are_create_only_and_restartable(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    analysis = SQLiteEvalAnalysisStore(config(database))
    baseline = candidate()
    analysis.create_baseline(baseline, idempotency_key=IdempotencyKey("baseline-create"))
    assert analysis.get_baseline(baseline.baseline_id) == baseline
    materialized = FACTORY.create(materialization())
    outputs = SQLiteEvalMaterializationStore(config(database))
    outputs.save_materialized_output(materialized, idempotency_key=IdempotencyKey("output-create"))
    outputs.close()

    reopened = SQLiteEvalMaterializationStore(config(database, create_if_missing=False))
    assert reopened.get_materialized_output(materialized.output_id) == materialized
    assert (
        reopened.get_materialized_output_for_execution(
            materialized.run_id,
            materialized.case_reference,
            materialized.repetition,
        )
        == materialized
    )
    assert (
        reopened.save_materialized_output(
            materialized, idempotency_key=IdempotencyKey("output-replay")
        ).disposition
        is WriteDisposition.IDEMPOTENT_REPLAY
    )


def test_evidence_chain_restart_orphan_rejection_and_replay(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    attempt, receipt, submission, finalization = evidence_records()
    seed_evidence_finalization(database, finalization)
    store = SQLiteEvalEvidenceStore(config(database))
    store.save_evidence_submission_attempt(
        attempt, idempotency_key=IdempotencyKey("attempt-create")
    )
    store.save_evidence_submission_receipt(
        receipt, idempotency_key=IdempotencyKey("receipt-create")
    )
    store.save_evidence_submission(submission, idempotency_key=IdempotencyKey("submission-create"))
    store.close()

    reopened = SQLiteEvalEvidenceStore(config(database, create_if_missing=False))
    assert reopened.list_evidence_submission_attempts(attempt.logical_submission_fingerprint) == (
        attempt,
    )
    assert reopened.list_evidence_submission_receipts(attempt.logical_submission_fingerprint) == (
        receipt,
    )
    assert reopened.get_evidence_submission_for_run(submission.run_id) == submission
    assert (
        reopened.save_evidence_submission_attempt(
            attempt, idempotency_key=IdempotencyKey("attempt-replay")
        ).disposition
        is WriteDisposition.IDEMPOTENT_REPLAY
    )
    orphan = replace(receipt, attempt_fingerprint=receipt.projection_fingerprint, checksum=None)
    with pytest.raises(EvalIntegrityConflict):
        reopened.save_evidence_submission_receipt(
            orphan, idempotency_key=IdempotencyKey("orphan-receipt")
        )


def test_equivalent_and_divergent_concurrent_writers(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    writers = (
        SQLiteEvalCatalogStore(config(database)),
        SQLiteEvalCatalogStore(config(database)),
    )

    def write(store: SQLiteEvalCatalogStore, name: str, key: str):
        return store.create_suite(
            replace(suite(), name=name), idempotency_key=IdempotencyKey(key)
        ).disposition

    with ThreadPoolExecutor(max_workers=2) as executor:
        equivalent = tuple(
            executor.map(
                lambda item: write(*item),
                (
                    (writers[0], "Catalog", "writer-1"),
                    (writers[1], "Catalog", "writer-2"),
                ),
            )
        )
    assert set(equivalent) == {
        WriteDisposition.CREATED,
        WriteDisposition.IDEMPOTENT_REPLAY,
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(write, writers[0], "Catalog", "writer-3"),
            executor.submit(write, writers[1], "different", "writer-4"),
        )
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except EvalDuplicateRecord:
                outcomes.append("conflict")
    assert "conflict" in outcomes
    for store in writers:
        store.close()


def test_schema_busy_unavailable_corruption_and_idempotency_rollback(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    store = SQLiteEvalCatalogStore(config(database, timeout_seconds=0.05))
    store.create_suite(suite(), idempotency_key=IdempotencyKey("original"))
    with pytest.raises(EvalIdempotencyConflict):
        store.create_suite(
            replace(suite(), name="bad replay"),
            idempotency_key=IdempotencyKey("original"),
        )
    assert store.get_suite(SUITE_ID) == suite()

    blocker = sqlite3.connect(database, isolation_level=None)
    blocker.execute("PRAGMA journal_mode = WAL")
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(EvalStoreUnavailable):
            store.create_suite(
                replace(suite(), suite_id=type(SUITE_ID)("suite.locked")),
                idempotency_key=IdempotencyKey("locked"),
            )
    finally:
        blocker.rollback()
        blocker.close()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE eval_suites SET payload = payload || ' ' WHERE record_key = ?",
            (SUITE_ID.value,),
        )
    with pytest.raises(EvalIntegrityConflict):
        store.get_suite(SUITE_ID)

    missing = tmp_path / "missing" / "private-evals.sqlite3"
    with pytest.raises(EvalStoreUnavailable):
        SQLiteEvalCatalogStore(config(missing, create_if_missing=False))


def test_concurrent_cas_allows_exactly_one_revision_winner(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    stores = (
        SQLiteEvalCatalogStore(config(database)),
        SQLiteEvalCatalogStore(config(database)),
    )
    stores[0].create_suite(suite(), idempotency_key=IdempotencyKey("create"))

    def update(store: SQLiteEvalCatalogStore, name: str, key: str):
        try:
            return store.update_suite(
                replace(suite(), name=name, revision=Revision(2), updated_at=LATER),
                expected_revision=Revision(1),
                idempotency_key=IdempotencyKey(key),
            ).disposition
        except EvalRevisionConflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda item: update(*item),
                (
                    (stores[0], "winner-a", "cas-a"),
                    (stores[1], "winner-b", "cas-b"),
                ),
            )
        )
    assert set(outcomes) == {WriteDisposition.UPDATED, "stale"}
    assert stores[0].get_suite(SUITE_ID).revision == Revision(2)


def test_concurrent_evidence_claim_receipt_and_final_envelope_races(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    attempt, receipt, submission, finalization = evidence_records()
    seed_evidence_finalization(database, finalization)
    stores = (
        SQLiteEvalEvidenceStore(config(database)),
        SQLiteEvalEvidenceStore(config(database)),
    )

    def race(call):
        with ThreadPoolExecutor(max_workers=2) as executor:
            return tuple(executor.map(call, range(2)))

    attempts = race(
        lambda index: (
            stores[index]
            .save_evidence_submission_attempt(
                attempt, idempotency_key=IdempotencyKey(f"attempt-{index}")
            )
            .disposition
        )
    )
    assert set(attempts) == {WriteDisposition.CREATED, WriteDisposition.IDEMPOTENT_REPLAY}
    receipts = race(
        lambda index: (
            stores[index]
            .save_evidence_submission_receipt(
                receipt, idempotency_key=IdempotencyKey(f"receipt-{index}")
            )
            .disposition
        )
    )
    assert set(receipts) == {WriteDisposition.CREATED, WriteDisposition.IDEMPOTENT_REPLAY}
    submissions = race(
        lambda index: (
            stores[index]
            .save_evidence_submission(
                submission, idempotency_key=IdempotencyKey(f"submission-{index}")
            )
            .disposition
        )
    )
    assert set(submissions) == {
        WriteDisposition.CREATED,
        WriteDisposition.IDEMPOTENT_REPLAY,
    }
    divergent = replace(
        attempt,
        retry_policy_reference="evidence-retry-policy-2",
        fingerprint=None,
        checksum=None,
    )
    with pytest.raises(EvalDuplicateRecord):
        stores[0].save_evidence_submission_attempt(
            divergent, idempotency_key=IdempotencyKey("attempt-divergent")
        )


def test_concurrent_finalization_is_single_create_only_fact(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    source = finalization_input()
    source = replace(source, run=replace(source.run, revision=Revision(1)))
    record = EvalRunFinalizationFactory().create(source)
    stores = (
        SQLiteEvalRunStore(config(database)),
        SQLiteEvalRunStore(config(database)),
    )
    stores[0].create_run(source.run, idempotency_key=IdempotencyKey("run-create"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda index: (
                    stores[index]
                    .save_finalization(
                        record, idempotency_key=IdempotencyKey(f"finalization-{index}")
                    )
                    .disposition
                ),
                range(2),
            )
        )
    assert set(outcomes) == {WriteDisposition.CREATED, WriteDisposition.IDEMPOTENT_REPLAY}
    divergent_source = replace(
        source, finalization_id=EvalRunFinalizationId("finalization-divergent")
    )
    divergent = EvalRunFinalizationFactory().create(divergent_source)
    with pytest.raises(EvalDuplicateRecord):
        stores[0].save_finalization(
            divergent, idempotency_key=IdempotencyKey("finalization-divergent")
        )


def test_tampered_identity_and_incompatible_schema_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    store = SQLiteEvalCatalogStore(config(database))
    store.create_suite(suite(), idempotency_key=IdempotencyKey("create"))
    store.close()
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload FROM eval_suites WHERE record_key = ?", (SUITE_ID.value,)
        ).fetchone()
        payload = row[0]
        connection.execute(
            "UPDATE eval_suites SET record_key = ?, payload_checksum = ? WHERE record_key = ?",
            ("forged-key", hashlib.sha256(payload.encode()).hexdigest(), SUITE_ID.value),
        )
    forged = SQLiteEvalCatalogStore(config(database, create_if_missing=False))
    with pytest.raises(EvalIntegrityConflict):
        forged.list_suites(SuiteListFilter(), PageRequest())
    forged.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE private_evals_schema SET schema_version = 99 WHERE singleton = 1"
        )
    with pytest.raises(EvalSchemaVersionMismatch):
        SQLiteEvalCatalogStore(config(database, create_if_missing=False))


def test_unknown_serialized_fields_and_enum_values_are_rejected(tmp_path: Path) -> None:
    database = tmp_path / "private-evals.sqlite3"
    store = SQLiteEvalCatalogStore(config(database))
    second_id = type(SUITE_ID)("suite.enum")
    store.create_suite(suite(), idempotency_key=IdempotencyKey("first"))
    store.create_suite(
        replace(suite(), suite_id=second_id), idempotency_key=IdempotencyKey("second")
    )
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT record_key, payload FROM eval_suites ORDER BY record_key"
        ).fetchall()
        for record_key, payload in rows:
            data = json.loads(payload)
            fields = data["record"]["$fields"]
            if record_key == SUITE_ID.value:
                fields["unknown_field"] = "rejected"
            else:
                fields["classification"]["value"] = "not-a-classification"
            changed = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            connection.execute(
                "UPDATE eval_suites SET payload = ?, payload_checksum = ? WHERE record_key = ?",
                (changed, hashlib.sha256(changed.encode()).hexdigest(), record_key),
            )
    with pytest.raises(EvalIntegrityConflict):
        store.get_suite(SUITE_ID)
    with pytest.raises(EvalIntegrityConflict):
        store.get_suite(second_id)
