from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import EvalRunStore
from .run_errors import (
    EvalRunLifecycleError,
    RunLifecycleUnavailable,
    RunRevisionConflict,
    TerminalRunMutation,
)
from .run_finalization import (
    EvalRunFinalizationFactory,
    RunFinalizationInput,
)
from .run_finalization_errors import (
    FinalizationAlreadyExists,
    FinalizationLifecycleConflict,
    FinalizationPersistenceUnavailable,
    FinalizationRecoveryRequired,
)
from .run_finalization_models import (
    EvalRunFinalizationRecord,
    validate_finalization_record,
)
from .run_finalization_policy import validate_finalization_policy
from .run_runtime import EvalRunRuntime
from .store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalRecordNotFound,
    EvalStoreError,
    EvalStoreUnavailable,
)
from .store_models import WriteDisposition


class FinalizationWriteDisposition(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class RunFinalizationServiceResult:
    finalization: EvalRunFinalizationRecord
    disposition: FinalizationWriteDisposition


@dataclass(frozen=True)
class EvalRunFinalizationService:
    store: EvalRunStore
    runtime: EvalRunRuntime
    factory: EvalRunFinalizationFactory = EvalRunFinalizationFactory()

    def finalize(self, source: RunFinalizationInput) -> RunFinalizationServiceResult:
        candidate = self.factory.create(source)
        existing = self._existing(candidate)
        created = existing is None
        newly_saved = False
        stable = candidate if existing is None else existing
        if existing is not None:
            self._validate_stable(existing)
            if existing.fingerprint != candidate.fingerprint:
                raise FinalizationAlreadyExists()
        current = self.runtime.get_run(candidate.run_id)
        if created:
            if current.status in EvalRunRuntime._TERMINAL:
                if current.finalization_reference is None:
                    raise FinalizationRecoveryRequired()
                raise FinalizationLifecycleConflict()
            if current.revision != source.run.revision:
                raise FinalizationLifecycleConflict()
        if created:
            stable, newly_saved = self._save_or_recover_race(candidate, source)
            if stable.fingerprint != candidate.fingerprint:
                raise FinalizationAlreadyExists()
        self._validate_stable(stable)
        current = self.runtime.get_run(stable.run_id)
        if current.status in EvalRunRuntime._TERMINAL:
            if current.finalization_reference is None:
                raise FinalizationRecoveryRequired()
            if (
                current.status is stable.lifecycle_status
                and current.finalization_reference == stable.record_reference
            ):
                return RunFinalizationServiceResult(
                    stable, FinalizationWriteDisposition.IDEMPOTENT_REPLAY
                )
            raise FinalizationLifecycleConflict()
        try:
            assert stable.fingerprint is not None
            self.runtime.apply_finalization(
                stable.run_id,
                stable.lifecycle_status,
                stable.record_reference,
                stable.fingerprint,
                accepted_result_count=stable.accepted_result_count,
                failed_execution_count=(
                    stable.expected_result_count - stable.accepted_result_count
                ),
                timestamp=source.created_at,
                expected_revision=(
                    source.run.revision if newly_saved else current.revision
                ),
                idempotency_key=source.idempotency_key,
            )
        except RunRevisionConflict as error:
            latest = self.runtime.get_run(stable.run_id)
            if (
                latest.status is stable.lifecycle_status
                and latest.finalization_reference == stable.record_reference
            ):
                return RunFinalizationServiceResult(
                    stable, FinalizationWriteDisposition.IDEMPOTENT_REPLAY
                )
            if latest.status in EvalRunRuntime._TERMINAL:
                raise FinalizationLifecycleConflict() from error
            raise FinalizationRecoveryRequired() from error
        except RunLifecycleUnavailable as error:
            raise FinalizationRecoveryRequired() from error
        except (TerminalRunMutation, EvalRunLifecycleError) as error:
            raise FinalizationLifecycleConflict() from error
        return RunFinalizationServiceResult(
            stable,
            FinalizationWriteDisposition.CREATED
            if newly_saved
            else FinalizationWriteDisposition.RECOVERED,
        )

    @staticmethod
    def _validate_stable(record: EvalRunFinalizationRecord) -> None:
        validate_finalization_record(record)
        validate_finalization_policy(record)

    def _existing(
        self, candidate: EvalRunFinalizationRecord
    ) -> EvalRunFinalizationRecord | None:
        try:
            if not self.store.finalization_exists(candidate.run_id):
                return None
            return self.store.get_finalization_for_run(candidate.run_id)
        except EvalRecordNotFound:
            return None
        except EvalStoreUnavailable as error:
            raise FinalizationPersistenceUnavailable() from error
        except EvalStoreError as error:
            raise FinalizationPersistenceUnavailable() from error

    def _save_or_recover_race(
        self,
        candidate: EvalRunFinalizationRecord,
        source: RunFinalizationInput,
    ) -> tuple[EvalRunFinalizationRecord, bool]:
        try:
            outcome = self.store.save_finalization(
                candidate, idempotency_key=source.idempotency_key
            )
            if outcome.disposition is WriteDisposition.IDEMPOTENT_REPLAY:
                return self.store.get_finalization_for_run(candidate.run_id), False
            return candidate, True
        except (EvalDuplicateRecord, EvalIdempotencyConflict, EvalIntegrityConflict):
            try:
                return self.store.get_finalization_for_run(candidate.run_id), False
            except EvalStoreError as error:
                raise FinalizationPersistenceUnavailable() from error
        except EvalStoreUnavailable as error:
            raise FinalizationPersistenceUnavailable() from error
        except EvalStoreError as error:
            raise FinalizationPersistenceUnavailable() from error
