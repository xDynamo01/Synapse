from __future__ import annotations

from dataclasses import dataclass

from synapse.project_governance.contracts import RFCEvidenceWritePort

from .canonical import fingerprint
from .contracts import EvalEvidenceStore
from .evidence_errors import GovernanceBindingMismatch
from .evidence_projection import EvalEvidenceEmitter, EvalEvidenceProjectionFactory
from .evidence_submission import EvalEvidencePlanningInput, EvalEvidenceSubmissionPlanner
from .evidence_submission_errors import (
    EvidencePersistenceUnavailable,
    EvidenceReconciliationRequired,
    EvidenceSubmissionContentConflict,
    EvidenceSubmissionIdempotencyConflict,
    GovernanceReferenceMismatch,
    GovernanceSubmissionUnavailable,
    PartialEvidenceRecoveryConflict,
)
from .evidence_submission_models import (
    EvalEvidenceSubmissionRecord,
    EvidenceSubmissionAttemptRecord,
    EvidenceSubmissionOutcome,
    EvidenceSubmissionReceiptRecord,
    EvidenceSubmissionResult,
    GovernanceEvidenceIdentity,
    GovernanceEvidenceReceipt,
    evidence_submission_attempt_checksum,
    evidence_submission_attempt_fingerprint,
    evidence_submission_receipt_checksum,
    evidence_submission_record_checksum,
)
from .store_errors import EvalIdempotencyConflict, EvalStoreError, EvalStoreUnavailable
from .store_models import IdempotencyKey
from .values import ContentChecksum

EVIDENCE_SUBMISSION_RETRY_POLICY_REFERENCE = "private-evals-evidence-submission:1.1.0"


@dataclass(frozen=True)
class EvalEvidenceSubmissionService:
    store: EvalEvidenceStore
    governance: RFCEvidenceWritePort
    planner: EvalEvidenceSubmissionPlanner = EvalEvidenceSubmissionPlanner()

    def submit(
        self,
        source: EvalEvidencePlanningInput,
        *,
        submission_id: str,
        governance_identities: tuple[GovernanceEvidenceIdentity, ...],
    ) -> EvidenceSubmissionResult:
        plan = self.planner.create(source)
        if not plan.specifications:
            if governance_identities:
                raise GovernanceReferenceMismatch()
            return EvidenceSubmissionResult(EvidenceSubmissionOutcome.NOT_APPLICABLE, plan, None)
        identities = self._validate_identities(plan, governance_identities)
        assert plan.semantic_fingerprint is not None
        existing = self._existing_for_run(plan.run_id)
        if existing is not None:
            self._validate_existing(existing, plan, identities)
            attempts, receipt_records = self._load_coordination(plan.semantic_fingerprint)
            receipts = self._validate_coordination(plan, identities, attempts, receipt_records)
            if set(receipts) != set(plan.expected_projection_fingerprints):
                raise PartialEvidenceRecoveryConflict()
            ordered = tuple(receipts[item] for item in plan.expected_projection_fingerprints)
            if ordered != existing.governance_receipts:
                raise PartialEvidenceRecoveryConflict()
            return EvidenceSubmissionResult(
                EvidenceSubmissionOutcome.IDEMPOTENT_REPLAY, plan, existing
            )

        projections = self.planner.construct_projections(source, plan)
        attempts, receipt_records = self._load_coordination(plan.semantic_fingerprint)
        recovered = bool(receipt_records)
        receipts = self._validate_coordination(plan, identities, attempts, receipt_records)
        for projection in projections:
            if projection.fingerprint in receipts:
                continue
            identity = identities[projection.fingerprint]
            governance_record = EvalEvidenceProjectionFactory.governance_record(
                projection,
                evidence_id=identity.evidence_id,
                created_at=source.created_at,
            )
            request_fingerprint = fingerprint(
                {
                    "logical_submission_fingerprint": plan.semantic_fingerprint,
                    "projection_fingerprint": projection.fingerprint,
                    "institutional_evidence_reference": identity.evidence_id,
                    "evidence_checksum": governance_record.checksum,
                }
            )
            attempt = EvidenceSubmissionAttemptRecord(
                plan.semantic_fingerprint,
                1,
                projection.fingerprint,
                projection.binding.projection_kind,
                request_fingerprint,
                source.created_at,
                EVIDENCE_SUBMISSION_RETRY_POLICY_REFERENCE,
            )
            claimed_receipt = self._save_attempt_claim(
                source.idempotency_key, attempt, plan, identities
            )
            if claimed_receipt is not None:
                receipts[projection.fingerprint] = claimed_receipt
                recovered = True
                continue
            try:
                recorded = EvalEvidenceEmitter(self.governance).emit(governance_record)
            except GovernanceBindingMismatch as exc:
                raise GovernanceReferenceMismatch() from exc
            except (EvidenceReconciliationRequired, GovernanceSubmissionUnavailable):
                raise
            except Exception as exc:
                raise EvidenceReconciliationRequired() from exc
            try:
                receipt = GovernanceEvidenceReceipt(
                    projection.binding.projection_kind,
                    projection.fingerprint,
                    recorded.evidence_id,
                    ContentChecksum(recorded.checksum),
                )
            except (ValueError, GovernanceReferenceMismatch) as exc:
                raise GovernanceReferenceMismatch() from exc
            assert attempt.fingerprint is not None
            receipt_record = EvidenceSubmissionReceiptRecord(
                plan.semantic_fingerprint,
                attempt.fingerprint,
                attempt.attempt_number,
                projection.fingerprint,
                projection.binding.projection_kind,
                receipt,
                source.created_at,
            )
            self._save_receipt(source.idempotency_key, receipt_record, plan, identities)
            receipts[projection.fingerprint] = receipt

        ordered_receipts = tuple(receipts[item] for item in plan.expected_projection_fingerprints)
        record = EvalEvidenceSubmissionRecord(
            submission_id=submission_id,
            run_id=plan.run_id,
            finalization_reference=plan.finalization_reference,
            finalization_fingerprint=plan.finalization_fingerprint,
            implementation=plan.implementation,
            implementation_binding_reference=plan.implementation_binding_reference,
            projection_fingerprints=plan.expected_projection_fingerprints,
            governance_receipts=ordered_receipts,
            submitted_at=source.created_at,
            producer_id=plan.producer_id,
            producer_version=plan.producer_version,
            semantic_fingerprint=plan.semantic_fingerprint,
        )
        stored = self._save_submission(source.idempotency_key, record, plan, identities)
        outcome = (
            EvidenceSubmissionOutcome.PARTIAL_RECOVERY
            if recovered
            else EvidenceSubmissionOutcome.CREATED
        )
        if stored is not record:
            outcome = EvidenceSubmissionOutcome.IDEMPOTENT_REPLAY
        return EvidenceSubmissionResult(outcome, plan, stored)

    @staticmethod
    def _validate_identities(plan, values):
        if len(values) != len(plan.specifications):
            raise GovernanceReferenceMismatch()
        expected = {
            (item.projection_kind, item.expected_projection_fingerprint)
            for item in plan.specifications
        }
        actual = {(item.projection_kind, item.projection_fingerprint) for item in values}
        if actual != expected or len(actual) != len(values):
            raise GovernanceReferenceMismatch()
        return {item.projection_fingerprint: item for item in values}

    def _existing_for_run(self, run_id):
        try:
            if not self.store.evidence_submission_exists(run_id):
                return None
            record = self.store.get_evidence_submission_for_run(run_id)
        except EvalStoreUnavailable as exc:
            raise EvidencePersistenceUnavailable() from exc
        except EvalStoreError as exc:
            raise EvidenceSubmissionContentConflict() from exc
        if record.checksum != evidence_submission_record_checksum(record):
            raise EvidenceSubmissionContentConflict()
        return record

    @staticmethod
    def _validate_existing(record, plan, identities):
        expected_ids = tuple(
            identities[item].evidence_id for item in plan.expected_projection_fingerprints
        )
        if (
            record.semantic_fingerprint != plan.semantic_fingerprint
            or record.finalization_fingerprint != plan.finalization_fingerprint
            or record.implementation != plan.implementation
            or record.projection_fingerprints != plan.expected_projection_fingerprints
            or tuple(item.evidence_id for item in record.governance_receipts) != expected_ids
        ):
            raise EvidenceSubmissionContentConflict()

    def _load_coordination(self, semantic_fingerprint):
        try:
            return (
                self.store.list_evidence_submission_attempts(semantic_fingerprint),
                self.store.list_evidence_submission_receipts(semantic_fingerprint),
            )
        except EvalStoreError as exc:
            raise EvidencePersistenceUnavailable() from exc

    @staticmethod
    def _validate_coordination(plan, identities, attempts, receipt_records):
        specifications = {
            item.expected_projection_fingerprint: item.projection_kind
            for item in plan.specifications
        }
        attempt_by_projection = {}
        for attempt in attempts:
            expected_kind = specifications.get(attempt.projection_fingerprint)
            if (
                attempt.checksum != evidence_submission_attempt_checksum(attempt)
                or attempt.fingerprint != evidence_submission_attempt_fingerprint(attempt)
                or attempt.logical_submission_fingerprint != plan.semantic_fingerprint
                or expected_kind is not attempt.projection_kind
                or attempt.attempt_number != 1
                or attempt.projection_fingerprint not in identities
                or attempt.projection_fingerprint in attempt_by_projection
            ):
                raise PartialEvidenceRecoveryConflict()
            attempt_by_projection[attempt.projection_fingerprint] = attempt
        receipts = {}
        for receipt_record in receipt_records:
            attempt = attempt_by_projection.get(receipt_record.projection_fingerprint)
            identity = identities.get(receipt_record.projection_fingerprint)
            if (
                receipt_record.checksum != evidence_submission_receipt_checksum(receipt_record)
                or receipt_record.logical_submission_fingerprint != plan.semantic_fingerprint
                or attempt is None
                or receipt_record.attempt_fingerprint != attempt.fingerprint
                or receipt_record.attempt_number != attempt.attempt_number
                or receipt_record.projection_kind is not attempt.projection_kind
                or identity is None
                or receipt_record.governance_receipt.evidence_id != identity.evidence_id
                or receipt_record.projection_fingerprint in receipts
            ):
                raise PartialEvidenceRecoveryConflict()
            receipts[receipt_record.projection_fingerprint] = receipt_record.governance_receipt
        if set(attempt_by_projection) - set(receipts):
            raise EvidenceReconciliationRequired()
        return receipts

    def _save_attempt_claim(self, key, attempt, plan, identities):
        attempt_key = IdempotencyKey(
            f"{key.value}.{attempt.projection_kind.value}-attempt-{attempt.attempt_number}"
        )
        try:
            self.store.save_evidence_submission_attempt(attempt, idempotency_key=attempt_key)
            return None
        except EvalIdempotencyConflict as exc:
            raise EvidenceSubmissionIdempotencyConflict() from exc
        except EvalStoreUnavailable as exc:
            raise EvidencePersistenceUnavailable() from exc
        except EvalStoreError as exc:
            attempts, receipt_records = self._load_coordination(plan.semantic_fingerprint)
            recovered = self._validate_coordination(plan, identities, attempts, receipt_records)
            receipt = recovered.get(attempt.projection_fingerprint)
            if receipt is None:
                raise EvidenceReconciliationRequired() from exc
            return receipt

    def _save_receipt(self, key, receipt, plan, identities):
        receipt_key = IdempotencyKey(
            f"{key.value}.{receipt.projection_kind.value}-receipt-{receipt.attempt_number}"
        )
        try:
            self.store.save_evidence_submission_receipt(receipt, idempotency_key=receipt_key)
        except EvalIdempotencyConflict as exc:
            raise EvidenceSubmissionIdempotencyConflict() from exc
        except EvalStoreUnavailable as exc:
            raise EvidencePersistenceUnavailable() from exc
        except EvalStoreError as exc:
            attempts, receipt_records = self._load_coordination(plan.semantic_fingerprint)
            recovered = self._validate_coordination(plan, identities, attempts, receipt_records)
            if recovered.get(receipt.projection_fingerprint) != receipt.governance_receipt:
                raise PartialEvidenceRecoveryConflict() from exc

    def _save_submission(self, key, record, plan, identities):
        try:
            self.store.save_evidence_submission(record, idempotency_key=key)
            return record
        except EvalIdempotencyConflict as exc:
            raise EvidenceSubmissionIdempotencyConflict() from exc
        except EvalStoreUnavailable as exc:
            raise EvidencePersistenceUnavailable() from exc
        except EvalStoreError as exc:
            existing = self._existing_for_run(plan.run_id)
            if existing is None:
                raise EvidencePersistenceUnavailable() from exc
            self._validate_existing(existing, plan, identities)
            return existing
