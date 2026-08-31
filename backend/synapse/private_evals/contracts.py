"""Typed persistence contracts owned by Private Evals.

Every create/save method is create-only for its logical identity. Repeating the same
idempotency key with the same semantic identity returns ``IDEMPOTENT_REPLAY``; reusing
the key for different content raises ``EvalIdempotencyConflict``. Existing identities
with different content raise duplicate or integrity conflicts. A materialized output
uses its content fingerprint for replay equivalence and its checksum for record
integrity. Mutable aggregate roots use mandatory expected revisions and one-record
compare-and-set writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .analysis import EvalBaseline, EvalComparison, RegressionReport, RegressionRule
from .catalog import (
    DatasetBinding,
    EvalCaseVersion,
    EvalCaseVersionRef,
    EvalSuite,
    EvalSuiteVersion,
)
from .result_models import MaterializedOutputRecord
from .runs import EvalResult, EvalRun, EvalRunManifest
from .store_models import (
    BaselineListFilter,
    ComparisonListFilter,
    DatasetBindingListFilter,
    IdempotencyKey,
    PageRequest,
    RunListFilter,
    StorePage,
    StoreWriteOutcome,
    SuiteListFilter,
)
from .values import (
    BaselineId,
    ComparisonId,
    DatasetBindingId,
    EvalCaseId,
    EvalResultId,
    EvalRunFinalizationId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    MaterializedOutputId,
    RegressionReportId,
    RegressionRuleId,
    Revision,
    ScoringDecisionId,
)

if TYPE_CHECKING:
    from .evaluation_records import EvaluationAttemptRecord
    from .evidence_submission_models import (
        EvalEvidenceSubmissionRecord,
        EvidenceSubmissionAttemptRecord,
        EvidenceSubmissionReceiptRecord,
    )
    from .run_finalization import EvalRunFinalizationRecord
    from .run_scoring import RunScoringDecision


@runtime_checkable
class EvalCatalogStore(Protocol):
    """Persistence boundary for Suite, Case Version and Dataset Binding records."""

    def create_suite(
        self, suite: EvalSuite, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_suite(self, suite_id: EvalSuiteId) -> EvalSuite: ...

    def update_suite(
        self,
        suite: EvalSuite,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def list_suites(self, filters: SuiteListFilter, page: PageRequest) -> StorePage[EvalSuite]: ...

    def save_suite_version(
        self, version: EvalSuiteVersion, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_suite_version(
        self, suite_id: EvalSuiteId, version: EvalVersion
    ) -> EvalSuiteVersion: ...

    def update_suite_version_status(
        self,
        version: EvalSuiteVersion,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome:
        """Compare-and-set a definition status without changing semantic content."""
        ...

    def list_suite_versions(
        self, suite_id: EvalSuiteId, page: PageRequest
    ) -> StorePage[EvalSuiteVersion]: ...

    def save_case_version(
        self, case: EvalCaseVersion, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_case_version(
        self,
        suite_id: EvalSuiteId,
        case_id: EvalCaseId,
        version: EvalVersion,
    ) -> EvalCaseVersion: ...

    def update_case_version_status(
        self,
        case: EvalCaseVersion,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome:
        """Compare-and-set a definition status without changing semantic content."""
        ...

    def list_case_versions(
        self,
        suite_id: EvalSuiteId,
        suite_version: EvalVersion,
        page: PageRequest,
    ) -> StorePage[EvalCaseVersion]: ...

    def save_dataset_binding(
        self, binding: DatasetBinding, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_dataset_binding(
        self, binding_id: DatasetBindingId, revision: Revision
    ) -> DatasetBinding: ...

    def list_dataset_bindings(
        self, filters: DatasetBindingListFilter, page: PageRequest
    ) -> StorePage[DatasetBinding]: ...


@runtime_checkable
class EvalRunStore(Protocol):
    """Persistence boundary for the Run aggregate and unique accepted Results."""

    def create_run(self, run: EvalRun, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome: ...

    def get_run(self, run_id: EvalRunId) -> EvalRun: ...

    def update_run(
        self,
        run: EvalRun,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome:
        """Atomically compare-and-set one Run record, including terminal state."""
        ...

    def list_runs(self, filters: RunListFilter, page: PageRequest) -> StorePage[EvalRun]: ...

    def save_manifest(
        self, manifest: EvalRunManifest, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_manifest(self, manifest_id: EvalRunManifestId) -> EvalRunManifest: ...

    def save_result(
        self, result: EvalResult, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome:
        """Create one logical run/case/repetition result exactly once and idempotently."""
        ...

    def get_result(self, result_id: EvalResultId) -> EvalResult: ...

    def get_result_for_execution(
        self,
        run_id: EvalRunId,
        case_reference: EvalCaseVersionRef,
        repetition: int,
    ) -> EvalResult: ...

    def result_exists(
        self,
        run_id: EvalRunId,
        case_reference: EvalCaseVersionRef,
        repetition: int,
    ) -> bool: ...

    def list_results(self, run_id: EvalRunId, page: PageRequest) -> StorePage[EvalResult]: ...

    def save_evaluation_attempt(
        self,
        record: EvaluationAttemptRecord,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def get_evaluation_attempt(
        self, attempt_fingerprint: Fingerprint
    ) -> EvaluationAttemptRecord: ...

    def save_finalization(
        self,
        record: EvalRunFinalizationRecord,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome:
        """Create the run's sole immutable finalization record."""
        ...

    def get_finalization(
        self, finalization_id: EvalRunFinalizationId
    ) -> EvalRunFinalizationRecord: ...

    def get_finalization_for_run(self, run_id: EvalRunId) -> EvalRunFinalizationRecord: ...

    def finalization_exists(self, run_id: EvalRunId) -> bool: ...


@runtime_checkable
class EvalEvidenceStore(Protocol):
    """Create-only local coordination facts for institutional Evidence submission.

    Saving one attempt is the atomic claim for that logical projection. Attempts,
    receipts and the final envelope are deliberately separate writes; no transaction
    across them is assumed.
    """

    def save_evidence_submission(
        self,
        record: EvalEvidenceSubmissionRecord,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def get_evidence_submission(self, submission_id: str) -> EvalEvidenceSubmissionRecord: ...

    def get_evidence_submission_for_run(
        self, run_id: EvalRunId
    ) -> EvalEvidenceSubmissionRecord: ...

    def evidence_submission_exists(self, run_id: EvalRunId) -> bool: ...

    def save_evidence_submission_attempt(
        self,
        record: EvidenceSubmissionAttemptRecord,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def list_evidence_submission_attempts(
        self, logical_submission_fingerprint: Fingerprint
    ) -> tuple[EvidenceSubmissionAttemptRecord, ...]: ...

    def save_evidence_submission_receipt(
        self,
        record: EvidenceSubmissionReceiptRecord,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def list_evidence_submission_receipts(
        self, logical_submission_fingerprint: Fingerprint
    ) -> tuple[EvidenceSubmissionReceiptRecord, ...]: ...


@runtime_checkable
class EvalMaterializationStore(Protocol):
    """Create-only boundary for execution outputs before evaluator scoring."""

    def save_materialized_output(
        self,
        record: MaterializedOutputRecord,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def get_materialized_output(
        self, output_id: MaterializedOutputId
    ) -> MaterializedOutputRecord: ...

    def get_materialized_output_for_execution(
        self,
        run_id: EvalRunId,
        case_reference: EvalCaseVersionRef,
        repetition: int,
    ) -> MaterializedOutputRecord: ...

    def materialized_output_exists(
        self,
        run_id: EvalRunId,
        case_reference: EvalCaseVersionRef,
        repetition: int,
    ) -> bool: ...


@runtime_checkable
class EvalAnalysisStore(Protocol):
    """Create-only scoring/analysis records plus revisioned baseline authority."""

    def save_scoring_decision(
        self,
        decision: RunScoringDecision,
        *,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def get_scoring_decision(
        self,
        decision_id: ScoringDecisionId,
    ) -> RunScoringDecision: ...

    def get_scoring_decision_for_run(
        self,
        run_id: EvalRunId,
    ) -> RunScoringDecision: ...

    def scoring_decision_exists(self, run_id: EvalRunId) -> bool: ...

    def create_baseline(
        self, baseline: EvalBaseline, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_baseline(self, baseline_id: BaselineId) -> EvalBaseline: ...

    def update_baseline_status(
        self,
        baseline: EvalBaseline,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> StoreWriteOutcome: ...

    def list_baselines(
        self, filters: BaselineListFilter, page: PageRequest
    ) -> StorePage[EvalBaseline]: ...

    def save_comparison(
        self, comparison: EvalComparison, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_comparison(self, comparison_id: ComparisonId) -> EvalComparison: ...

    def list_comparisons(
        self, filters: ComparisonListFilter, page: PageRequest
    ) -> StorePage[EvalComparison]: ...

    def save_regression_rule(
        self, rule: RegressionRule, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_regression_rule(
        self, rule_id: RegressionRuleId, version: EvalVersion
    ) -> RegressionRule: ...

    def save_regression_report(
        self, report: RegressionReport, *, idempotency_key: IdempotencyKey
    ) -> StoreWriteOutcome: ...

    def get_regression_report(self, report_id: RegressionReportId) -> RegressionReport: ...
