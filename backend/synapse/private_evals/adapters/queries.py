from __future__ import annotations

from dataclasses import dataclass, replace

from ..contracts import EvalEvidenceStore
from ..evidence_submission_models import (
    evidence_submission_attempt_checksum,
    evidence_submission_attempt_fingerprint,
    evidence_submission_receipt_checksum,
    evidence_submission_record_checksum,
)
from ..query_handler import EvidenceLocalStateReader
from ..query_models import EvidenceLocalState, EvidenceLocalStateProjection
from ..values import EvalRunId, Fingerprint


@dataclass(frozen=True)
class EvidenceCoordinationReference:
    run_id: EvalRunId
    logical_submission_fingerprint: Fingerprint
    expected_receipt_count: int
    finalization_reference: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.expected_receipt_count, bool)
            or not isinstance(self.expected_receipt_count, int)
            or self.expected_receipt_count < 1
            or not self.finalization_reference
        ):
            raise ValueError("Evidence coordination reference is invalid")


@dataclass(frozen=True)
class SQLiteEvidenceLocalStateReader(EvidenceLocalStateReader):
    """Project only local facts; the optional index is explicit and read-only."""

    store: EvalEvidenceStore
    coordination: tuple[EvidenceCoordinationReference, ...] = ()

    def __post_init__(self) -> None:
        run_ids = tuple(item.run_id for item in self.coordination)
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("Evidence coordination references must be unique by run")

    def get_local_evidence_state(
        self, run_id: EvalRunId
    ) -> EvidenceLocalStateProjection:
        if self.store.evidence_submission_exists(run_id):
            submission = self.store.get_evidence_submission_for_run(run_id)
            try:
                submission_valid = replace(submission) == submission
            except Exception:
                submission_valid = False
            if not submission_valid or submission.run_id != run_id:
                return self._reconciliation(run_id)
            reference = next(
                (item for item in self.coordination if item.run_id == run_id), None
            )
            if reference is not None and (
                reference.logical_submission_fingerprint
                != submission.semantic_fingerprint
                or reference.expected_receipt_count
                != len(submission.projection_fingerprints)
                or reference.finalization_reference
                != submission.finalization_reference
            ):
                return self._reconciliation(run_id)
            return self._project(
                run_id=run_id,
                fingerprint=submission.semantic_fingerprint,
                expected=len(submission.projection_fingerprints),
                finalization_reference=submission.finalization_reference,
                submission_reference=submission.submission_id,
                submitted_checksum_valid=(
                    submission.checksum == evidence_submission_record_checksum(submission)
                ),
            )
        reference = next(
            (item for item in self.coordination if item.run_id == run_id), None
        )
        if reference is None:
            return EvidenceLocalStateProjection(
                run_id.value,
                None,
                None,
                0,
                EvidenceLocalState.ABSENT,
                True,
                True,
            )
        return self._project(
            run_id=run_id,
            fingerprint=reference.logical_submission_fingerprint,
            expected=reference.expected_receipt_count,
            finalization_reference=reference.finalization_reference,
            submission_reference=None,
            submitted_checksum_valid=True,
        )

    def _project(
        self,
        *,
        run_id: EvalRunId,
        fingerprint: Fingerprint,
        expected: int,
        finalization_reference: str,
        submission_reference: str | None,
        submitted_checksum_valid: bool,
    ) -> EvidenceLocalStateProjection:
        attempts = self.store.list_evidence_submission_attempts(fingerprint)
        receipts = self.store.list_evidence_submission_receipts(fingerprint)
        attempt_by_fingerprint = {
            item.fingerprint: item for item in attempts if item.fingerprint is not None
        }
        attempt_projections = tuple(item.projection_fingerprint for item in attempts)
        receipt_attempts = tuple(item.attempt_fingerprint for item in receipts)
        receipt_projections = tuple(item.projection_fingerprint for item in receipts)
        try:
            valid = (
                submitted_checksum_valid
                and expected > 0
                and len(attempt_by_fingerprint) == len(attempts)
                and len(attempt_projections) == len(set(attempt_projections))
                and len(receipt_attempts) == len(set(receipt_attempts))
                and len(receipt_projections) == len(set(receipt_projections))
                and len(attempts) <= expected
                and len(receipts) <= expected
                and all(
                    replace(item) == item
                    and item.fingerprint == evidence_submission_attempt_fingerprint(item)
                    and item.checksum == evidence_submission_attempt_checksum(item)
                    and item.logical_submission_fingerprint == fingerprint
                    and item.attempt_number == 1
                    for item in attempts
                )
                and all(
                    replace(item) == item
                    and item.checksum == evidence_submission_receipt_checksum(item)
                    and item.logical_submission_fingerprint == fingerprint
                    and item.attempt_fingerprint in attempt_by_fingerprint
                    and item.attempt_number
                    == attempt_by_fingerprint[item.attempt_fingerprint].attempt_number
                    and attempt_by_fingerprint[
                        item.attempt_fingerprint
                    ].projection_fingerprint
                    == item.projection_fingerprint
                    and attempt_by_fingerprint[
                        item.attempt_fingerprint
                    ].projection_kind
                    is item.projection_kind
                    for item in receipts
                )
            )
        except Exception:
            valid = False
        if submission_reference is not None:
            complete = valid and len(attempts) == expected and len(receipts) == expected
            state = (
                EvidenceLocalState.SUBMITTED
                if complete
                else EvidenceLocalState.RECONCILIATION_REQUIRED
            )
        elif not valid or len(receipts) > len(attempts):
            complete = False
            state = EvidenceLocalState.RECONCILIATION_REQUIRED
        elif not attempts:
            complete = False
            state = EvidenceLocalState.ABSENT
        elif not receipts:
            complete = False
            state = EvidenceLocalState.ATTEMPT_STARTED
        elif len(receipts) < expected:
            complete = False
            state = EvidenceLocalState.RECEIPT_RECORDED
        else:
            complete = len(attempts) == expected
            state = (
                EvidenceLocalState.RECEIPTS_COMPLETE
                if complete
                else EvidenceLocalState.RECONCILIATION_REQUIRED
            )
        return EvidenceLocalStateProjection(
            run_id.value,
            finalization_reference,
            submission_reference,
            len(receipts),
            state,
            complete,
            valid,
        )

    @staticmethod
    def _reconciliation(run_id: EvalRunId) -> EvidenceLocalStateProjection:
        return EvidenceLocalStateProjection(
            run_id.value,
            None,
            None,
            0,
            EvidenceLocalState.RECONCILIATION_REQUIRED,
            False,
            False,
        )
