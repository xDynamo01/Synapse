from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .command_error_mapping import EXPECTED_BOUNDARY_ERRORS, translate_expected_error
from .contracts import EvalAnalysisStore, EvalRunStore
from .query_models import (
    EvidenceLocalStateProjection,
    RunSummaryRequest,
    RunSummaryResponse,
)
from .run_finalization_errors import RunFinalizationError
from .run_finalization_models import (
    validate_finalization_record,
)
from .run_runtime import EvalRunRuntime
from .run_scoring import run_scoring_decision_checksum
from .values import EvalRunId


class EvidenceLocalStateReader(Protocol):
    """Read-only projection over attempts, receipts and completed local submissions."""

    def get_local_evidence_state(
        self, run_id: EvalRunId
    ) -> EvidenceLocalStateProjection: ...


@dataclass(frozen=True)
class PrivateEvalsRunSummaryQuery:
    """Minimized reference-only read model; it never mutates or recovers state."""

    run_runtime: EvalRunRuntime
    run_store: EvalRunStore
    analysis_store: EvalAnalysisStore
    evidence_reader: EvidenceLocalStateReader

    def execute(self, request: RunSummaryRequest) -> RunSummaryResponse:
        try:
            run_id = EvalRunId(request.run_id)
            run = self.run_runtime.get_run(run_id)
            decision = (
                self.analysis_store.get_scoring_decision_for_run(run_id)
                if self.analysis_store.scoring_decision_exists(run_id)
                else None
            )
            finalization = (
                self.run_store.get_finalization_for_run(run_id)
                if self.run_store.finalization_exists(run_id)
                else None
            )
            evidence = self.evidence_reader.get_local_evidence_state(run_id)
            reconciliation_required = False
            terminal_statuses = {
                "partially_failed",
                "completed",
                "failed",
                "cancelled",
                "invalid",
                "policy_denied",
            }
            if finalization is not None:
                try:
                    validate_finalization_record(finalization)
                except RunFinalizationError:
                    reconciliation_required = True
                reconciliation_required = reconciliation_required or (
                    finalization.run_id != run.run_id
                    or run.finalization_reference != finalization.record_reference
                    or run.status.value not in terminal_statuses
                )
            elif run.status.value in terminal_statuses or run.finalization_reference is not None:
                reconciliation_required = True
            if decision is not None:
                reconciliation_required = (
                    reconciliation_required
                    or decision.run_id != run.run_id
                    or decision.checksum != run_scoring_decision_checksum(decision)
                )
            reconciliation_required = reconciliation_required or (
                evidence.run_id != run.run_id.value
                or not evidence.integrity_valid
                or not evidence.chain_complete
                or (
                    evidence.finalization_reference is not None
                    and (
                        finalization is None
                        or evidence.finalization_reference
                        != finalization.record_reference
                    )
                )
            )
            return RunSummaryResponse(
                run_id=run.run_id.value,
                suite_id=run.suite_id.value,
                suite_version=str(run.suite_version),
                run_status=run.status.value,
                revision=run.revision.value,
                manifest_reference=(
                    run.manifest_id.value if run.manifest_id is not None else None
                ),
                accepted_result_count=run.accepted_result_count,
                failed_execution_count=run.failed_execution_count,
                scoring_verdict=(
                    decision.aggregate.verdict.value if decision is not None else None
                ),
                finalization_reference=(
                    finalization.record_reference if finalization is not None else None
                ),
                finalization_disposition=(
                    finalization.disposition.value if finalization is not None else None
                ),
                finalization_coverage=(
                    finalization.coverage.value if finalization is not None else None
                ),
                finalization_path=(
                    finalization.path.value if finalization is not None else None
                ),
                finalization_lifecycle_status=(
                    finalization.lifecycle_status.value
                    if finalization is not None
                    else None
                ),
                terminal_causes=(
                    tuple(item.value for item in finalization.terminal_causes)
                    if finalization is not None
                    else ()
                ),
                evidence_submission_reference=(
                    evidence.submission_reference
                ),
                evidence_receipt_count=(
                    evidence.receipt_count
                ),
                evidence_local_state=evidence.state.value,
                reconciliation_state=(
                    "reconciliation_required"
                    if reconciliation_required
                    else "not_required"
                ),
                correlation_reference=request.context.correlation_reference,
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, request.context.correlation_reference
            ) from exc
