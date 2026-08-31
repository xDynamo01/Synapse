from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError

import pytest

from synapse.intelligence_boundary.models import DataClassification, InformationOwnership
from synapse.private_evals import (
    BaselineListFilter,
    ComparisonListFilter,
    ConflictMetadata,
    ContentChecksum,
    CreationInterval,
    DatasetBindingListFilter,
    EvalAnalysisStore,
    EvalCatalogStore,
    EvalEvidenceStore,
    EvalInvalidCursor,
    EvalInvalidStoreQuery,
    EvalMaterializationStore,
    EvalRevisionConflict,
    EvalRunId,
    EvalRunStore,
    EvalSuiteId,
    EvalVersion,
    IdempotencyKey,
    PageRequest,
    Revision,
    RunListFilter,
    RunStatus,
    StoreCursor,
    StoreOrder,
    StorePage,
    StoreWriteOutcome,
    SuiteListFilter,
    SuiteStatus,
    UtcTimestamp,
    WriteDisposition,
)

CHECKSUM = ContentChecksum("a" * 64)
NOW = UtcTimestamp("2026-07-17T18:00:00+00:00")


def test_cursor_and_idempotency_tokens_are_opaque_immutable_and_validated() -> None:
    cursor = StoreCursor("cursor_01")
    key = IdempotencyKey("run:create:01")
    assert "cursor_01" not in repr(cursor) and str(cursor) == "<opaque-cursor>"
    assert "run:create:01" not in repr(key) and str(key) == "<idempotency-key>"
    with pytest.raises(FrozenInstanceError):
        cursor.value = "changed"  # type: ignore[misc]
    for invalid in ("", "has whitespace", "x" * 513):
        with pytest.raises(EvalInvalidCursor):
            StoreCursor(invalid)
    for invalid in ("", "unsafe key", "x" * 129):
        with pytest.raises(EvalInvalidStoreQuery):
            IdempotencyKey(invalid)


@pytest.mark.parametrize("limit", [False, 0, -1, 501, "100"])
def test_page_request_rejects_invalid_limits_and_types(limit: object) -> None:
    with pytest.raises(EvalInvalidStoreQuery):
        PageRequest(limit=limit)  # type: ignore[arg-type]


def test_page_request_and_result_model_stable_deterministic_ordering() -> None:
    request = PageRequest(StoreCursor("cursor-1"), 50, StoreOrder.CREATED_AT_DESC)
    assert request.order is StoreOrder.CREATED_AT_DESC
    page = StorePage(("a", "b"), StoreCursor("cursor-2"), total=5)
    assert page.items == ("a", "b") and page.total == 5
    with pytest.raises(EvalInvalidStoreQuery):
        PageRequest(order="created_at_desc")  # type: ignore[arg-type]
    with pytest.raises(EvalInvalidStoreQuery):
        StorePage(("a", "b"), total=1)
    with pytest.raises(EvalInvalidStoreQuery):
        StorePage(["a"])  # type: ignore[arg-type]
    assert StoreCursor("url-safe-cursor-").value.endswith("-")


def test_explicit_filters_accept_safe_dimensions_and_reject_invalid_combinations() -> None:
    assert SuiteListFilter(
        SuiteStatus.ACTIVE,
        InformationOwnership.PROJECT,
        DataClassification.INTERNAL,
    ).status is SuiteStatus.ACTIVE
    assert DatasetBindingListFilter(asset_id="asset-1").asset_id == "asset-1"
    assert RunListFilter(
        EvalSuiteId("suite-1"),
        RunStatus.COMPLETED,
        CreationInterval(NOW, NOW),
    ).status is RunStatus.COMPLETED
    assert BaselineListFilter(
        EvalSuiteId("suite-1"), EvalVersion("1.0.0")
    ).suite_version == EvalVersion("1.0.0")
    assert ComparisonListFilter(current_run_id=EvalRunId("run-1")).current_run_id

    with pytest.raises(EvalInvalidStoreQuery):
        DatasetBindingListFilter(asset_id=" ")
    with pytest.raises(EvalInvalidStoreQuery):
        BaselineListFilter(suite_version=EvalVersion("1.0.0"))
    with pytest.raises(EvalInvalidStoreQuery):
        ComparisonListFilter(suite_version=EvalVersion("1.0.0"))
    with pytest.raises(EvalInvalidStoreQuery):
        CreationInterval(
            UtcTimestamp("2026-07-18T00:00:00+00:00"),
            UtcTimestamp("2026-07-17T00:00:00+00:00"),
        )
    with pytest.raises(EvalInvalidStoreQuery):
        SuiteListFilter(status="active")  # type: ignore[arg-type]


def test_write_outcomes_model_create_update_and_idempotent_replay() -> None:
    created = StoreWriteOutcome(
        "suite:suite-1",
        None,
        Revision(1),
        WriteDisposition.CREATED,
        CHECKSUM,
    )
    updated = StoreWriteOutcome(
        "suite:suite-1",
        Revision(1),
        Revision(2),
        WriteDisposition.UPDATED,
        CHECKSUM,
    )
    replay = StoreWriteOutcome(
        "suite:suite-1",
        Revision(1),
        Revision(1),
        WriteDisposition.IDEMPOTENT_REPLAY,
        CHECKSUM,
    )
    assert created.previous_revision is None
    assert updated.stored_revision == Revision(2)
    assert replay.disposition is WriteDisposition.IDEMPOTENT_REPLAY
    with pytest.raises(EvalInvalidStoreQuery):
        StoreWriteOutcome(
            "suite:suite-1",
            Revision(2),
            Revision(2),
            WriteDisposition.UPDATED,
            CHECKSUM,
        )
    with pytest.raises(EvalInvalidStoreQuery):
        StoreWriteOutcome(
            "suite:suite-1",
            Revision(1),
            Revision(2),
            WriteDisposition.CREATED,
            CHECKSUM,
        )
    with pytest.raises(EvalInvalidStoreQuery):
        StoreWriteOutcome(
            "suite:suite-1",
            None,
            Revision(2),
            WriteDisposition.CREATED,
            CHECKSUM,
        )


def test_conflict_metadata_and_errors_do_not_expose_idempotency_or_unsafe_messages() -> None:
    conflict = ConflictMetadata(
        "run:run-1",
        Revision(2),
        Revision(3),
        IdempotencyKey("secret-looking-key"),
    )
    assert "secret-looking-key" not in repr(conflict)
    error = EvalRevisionConflict("token=must-not-leak", details={"kind": "revision"})
    assert str(error) == "Private Evals record revision conflict"
    assert "must-not-leak" not in repr(error)
    with pytest.raises(EvalInvalidStoreQuery):
        ConflictMetadata("run:run-1", Revision(2), Revision(2))


CATALOG_METHODS = {
    "create_suite",
    "get_suite",
    "update_suite",
    "list_suites",
    "save_suite_version",
    "get_suite_version",
    "update_suite_version_status",
    "list_suite_versions",
    "save_case_version",
    "get_case_version",
    "update_case_version_status",
    "list_case_versions",
    "save_dataset_binding",
    "get_dataset_binding",
    "list_dataset_bindings",
}
RUN_METHODS = {
    "create_run",
    "get_run",
    "update_run",
    "list_runs",
    "save_manifest",
    "get_manifest",
    "save_result",
    "get_result",
    "get_result_for_execution",
    "result_exists",
    "list_results",
    "save_evaluation_attempt",
    "get_evaluation_attempt",
    "save_finalization",
    "get_finalization",
    "get_finalization_for_run",
    "finalization_exists",
}
ANALYSIS_METHODS = {
    "save_scoring_decision",
    "get_scoring_decision",
    "get_scoring_decision_for_run",
    "scoring_decision_exists",
    "create_baseline",
    "get_baseline",
    "update_baseline_status",
    "list_baselines",
    "save_comparison",
    "get_comparison",
    "list_comparisons",
    "save_regression_rule",
    "get_regression_rule",
    "save_regression_report",
    "get_regression_report",
}
MATERIALIZATION_METHODS = {
    "save_materialized_output",
    "get_materialized_output",
    "get_materialized_output_for_execution",
    "materialized_output_exists",
}
EVIDENCE_METHODS = {
    "save_evidence_submission",
    "get_evidence_submission",
    "get_evidence_submission_for_run",
    "evidence_submission_exists",
    "save_evidence_submission_attempt",
    "list_evidence_submission_attempts",
    "save_evidence_submission_receipt",
    "list_evidence_submission_receipts",
}


def _public_methods(protocol: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(protocol, inspect.isfunction)
        if not name.startswith("_")
    }


def _structural_fake(name: str, methods: set[str]) -> object:
    def structural_stub(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("structural fake must not execute persistence")

    return type(name, (), {method: structural_stub for method in methods})()


def test_store_protocols_are_cohesive_structural_and_have_no_generic_crud() -> None:
    expected = (
        (EvalCatalogStore, CATALOG_METHODS),
        (EvalRunStore, RUN_METHODS),
        (EvalMaterializationStore, MATERIALIZATION_METHODS),
        (EvalAnalysisStore, ANALYSIS_METHODS),
        (EvalEvidenceStore, EVIDENCE_METHODS),
    )
    for protocol, methods in expected:
        assert _public_methods(protocol) == methods
        assert isinstance(_structural_fake(f"Fake{protocol.__name__}", methods), protocol)
        assert not ({"put", "get", "list", "delete", "query", "execute"} & methods)


def test_mutable_roots_require_revision_and_writes_require_idempotency() -> None:
    for protocol, method_name in (
        (EvalCatalogStore, "update_suite"),
        (EvalCatalogStore, "update_suite_version_status"),
        (EvalCatalogStore, "update_case_version_status"),
        (EvalRunStore, "update_run"),
        (EvalAnalysisStore, "update_baseline_status"),
    ):
        signature = inspect.signature(getattr(protocol, method_name))
        assert signature.parameters["expected_revision"].default is inspect.Parameter.empty
        assert signature.parameters["idempotency_key"].default is inspect.Parameter.empty
    for protocol, method_name in (
        (EvalCatalogStore, "save_suite_version"),
        (EvalCatalogStore, "save_case_version"),
        (EvalRunStore, "save_manifest"),
        (EvalRunStore, "save_result"),
        (EvalMaterializationStore, "save_materialized_output"),
        (EvalAnalysisStore, "save_comparison"),
        (EvalAnalysisStore, "save_scoring_decision"),
        (EvalAnalysisStore, "save_regression_report"),
        (EvalEvidenceStore, "save_evidence_submission"),
        (EvalEvidenceStore, "save_evidence_submission_attempt"),
        (EvalEvidenceStore, "save_evidence_submission_receipt"),
    ):
        signature = inspect.signature(getattr(protocol, method_name))
        assert signature.parameters["idempotency_key"].default is inspect.Parameter.empty
