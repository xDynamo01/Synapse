from __future__ import annotations

from dataclasses import dataclass

from .contracts import EvalAnalysisStore
from .run_scoring import (
    RunScoringDecision,
    RunScoringInput,
    ScoringDecisionFactory,
    run_scoring_decision_checksum,
)
from .run_scoring_errors import (
    RunScoringIdempotencyConflict,
    RunScoringInputInvalid,
    RunScoringPersistenceUnavailable,
    ScoringDecisionAlreadyExists,
)
from .store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidStoreQuery,
    EvalRecordNotFound,
    EvalStoreUnavailable,
)
from .store_models import StoreWriteOutcome, WriteDisposition


@dataclass(frozen=True)
class RunScoringWriteResult:
    decision: RunScoringDecision
    disposition: WriteDisposition
    store_outcome: StoreWriteOutcome | None


@dataclass(frozen=True)
class RunScoringService:
    """Create-only persistence coordination for a pure run-scoring decision."""

    store: EvalAnalysisStore
    factory: ScoringDecisionFactory = ScoringDecisionFactory()

    def score_run(self, source: RunScoringInput) -> RunScoringWriteResult:
        candidate = self.factory.create(source)
        try:
            if self.store.scoring_decision_exists(candidate.run_id):
                existing = self.store.get_scoring_decision_for_run(candidate.run_id)
                return self._replay_or_conflict(existing, candidate)
            outcome = self.store.save_scoring_decision(
                candidate,
                idempotency_key=source.idempotency_key,
            )
            if outcome.disposition is WriteDisposition.UPDATED:
                raise ScoringDecisionAlreadyExists()
            if outcome.disposition is WriteDisposition.IDEMPOTENT_REPLAY:
                existing = self.store.get_scoring_decision_for_run(candidate.run_id)
                return self._replay_or_conflict(existing, candidate, outcome)
            if outcome.checksum != candidate.checksum:
                raise ScoringDecisionAlreadyExists()
            return RunScoringWriteResult(candidate, WriteDisposition.CREATED, outcome)
        except EvalDuplicateRecord:
            return self._recover_duplicate(candidate)
        except EvalIntegrityConflict as exc:
            raise ScoringDecisionAlreadyExists() from exc
        except EvalIdempotencyConflict as exc:
            raise RunScoringIdempotencyConflict() from exc
        except EvalStoreUnavailable as exc:
            raise RunScoringPersistenceUnavailable() from exc
        except EvalInvalidStoreQuery as exc:
            raise RunScoringInputInvalid() from exc
        except EvalRecordNotFound as exc:
            raise RunScoringPersistenceUnavailable() from exc

    def _recover_duplicate(self, candidate: RunScoringDecision) -> RunScoringWriteResult:
        try:
            existing = self.store.get_scoring_decision_for_run(candidate.run_id)
        except EvalStoreUnavailable as exc:
            raise RunScoringPersistenceUnavailable() from exc
        except EvalRecordNotFound as exc:
            raise RunScoringPersistenceUnavailable() from exc
        return self._replay_or_conflict(existing, candidate)

    @staticmethod
    def _replay_or_conflict(
        existing: RunScoringDecision,
        candidate: RunScoringDecision,
        outcome: StoreWriteOutcome | None = None,
    ) -> RunScoringWriteResult:
        if (
            existing.run_id != candidate.run_id
            or existing.decision_fingerprint != candidate.decision_fingerprint
            or existing.result_set_fingerprint != candidate.result_set_fingerprint
            or existing.expected_result_count != candidate.expected_result_count
            or existing.aggregate != candidate.aggregate
            or existing.result_references != candidate.result_references
            or existing.observation_fingerprints
            != candidate.observation_fingerprints
            or existing.checksum != run_scoring_decision_checksum(existing)
        ):
            raise ScoringDecisionAlreadyExists()
        return RunScoringWriteResult(
            existing,
            WriteDisposition.IDEMPOTENT_REPLAY,
            outcome,
        )
