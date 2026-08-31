from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Generic, TypeVar

from synapse.project_governance.models import RFCImplementationBinding

from ..case_evaluation import CaseEvaluationRequest
from ..catalog import EvalCaseVersion
from ..command_contracts import (
    EvaluationRecordResolver,
    EvidenceRecordResolver,
    FinalizationRecordResolver,
    MaterializationRecordResolver,
    RunManifestResolver,
    ScoringRecordResolver,
)
from ..command_errors import (
    ReferencedInputMismatch,
    ReferencedInputNotFound,
    ReferencedInputUnavailable,
)
from ..contracts import (
    EvalAnalysisStore,
    EvalCatalogStore,
    EvalMaterializationStore,
    EvalRunStore,
)
from ..evaluation_records import EvaluationAttemptRecord
from ..evidence_submission import EvidenceProjectionCandidate
from ..execution import CaseExecutionRequest
from ..execution_records import (
    ExecutionAccountingProjection,
    ExecutionAttemptRecord,
    LogicalExecutionProjection,
)
from ..result_models import MaterializedOutputRecord
from ..run_finalization_models import EvalRunFinalizationRecord, TerminalFailureProjection
from ..run_scoring import ExpectedExecutionMatrix, RunScoringDecision
from ..runs import EvalResult, EvalRun, EvalRunManifest
from ..scoring import ScoringProtocol
from ..store_errors import EvalRecordNotFound, EvalStoreError, EvalStoreUnavailable
from ..values import (
    EvalCaseId,
    EvalResultId,
    EvalRunFinalizationId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    MaterializedOutputId,
    ScoringDecisionId,
)

T = TypeVar("T")
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def _safe_reference(value: str) -> None:
    if not isinstance(value, str) or not _SAFE_REFERENCE.fullmatch(value):
        raise ValueError("resolver reference must be an opaque safe value")
    lowered = value.casefold()
    if any(term in lowered for term in ("token", "secret", "password", "credential")):
        raise ValueError("resolver reference contains a forbidden value")


@dataclass(frozen=True)
class ReferencedRecord(Generic[T]):
    reference: str
    record: T

    def __post_init__(self) -> None:
        _safe_reference(self.reference)

    def __repr__(self) -> str:
        return f"ReferencedRecord(reference={self.reference!r}, record_type={type(self.record).__name__!r})"


@dataclass(frozen=True)
class StoredCaseReference:
    reference: str
    suite_id: EvalSuiteId
    case_id: EvalCaseId
    version: EvalVersion

    def __post_init__(self) -> None:
        _safe_reference(self.reference)


@dataclass(frozen=True)
class ResolverRecordCatalog:
    """Immutable, non-owning bindings for inputs with no approved read store.

    This object is assembled explicitly by the future Composition Root for one
    command scope.  It is not a repository, performs no discovery, and must not
    contain records already owned by a Private Evals store.
    """

    case_references: tuple[StoredCaseReference, ...] = ()
    execution_requests: tuple[ReferencedRecord[CaseExecutionRequest], ...] = ()
    execution_attempts: tuple[ReferencedRecord[ExecutionAttemptRecord], ...] = ()
    logical_projections: tuple[ReferencedRecord[LogicalExecutionProjection], ...] = ()
    evaluation_requests: tuple[ReferencedRecord[CaseEvaluationRequest], ...] = ()
    scoring_protocols: tuple[ReferencedRecord[ScoringProtocol], ...] = ()
    expected_matrices: tuple[ReferencedRecord[ExpectedExecutionMatrix], ...] = ()
    terminal_failures: tuple[ReferencedRecord[TerminalFailureProjection], ...] = ()
    execution_accounting: tuple[ReferencedRecord[ExecutionAccountingProjection], ...] = ()
    implementations: tuple[ReferencedRecord[RFCImplementationBinding], ...] = ()
    projection_candidates: tuple[ReferencedRecord[EvidenceProjectionCandidate], ...] = ()

    def __post_init__(self) -> None:
        typed_groups = (
            (self.case_references, StoredCaseReference),
            (self.execution_requests, CaseExecutionRequest),
            (self.execution_attempts, ExecutionAttemptRecord),
            (self.logical_projections, LogicalExecutionProjection),
            (self.evaluation_requests, CaseEvaluationRequest),
            (self.scoring_protocols, ScoringProtocol),
            (self.expected_matrices, ExpectedExecutionMatrix),
            (self.terminal_failures, TerminalFailureProjection),
            (self.execution_accounting, ExecutionAccountingProjection),
            (self.implementations, RFCImplementationBinding),
            (self.projection_candidates, EvidenceProjectionCandidate),
        )
        for group, expected_type in typed_groups:
            if not isinstance(group, tuple):
                raise TypeError("resolver bindings must be immutable tuples")
            for item in group:
                if expected_type is StoredCaseReference:
                    if not isinstance(item, StoredCaseReference):
                        raise TypeError("resolver binding has an invalid record type")
                elif not isinstance(item, ReferencedRecord) or not isinstance(
                    item.record, expected_type
                ):
                    raise TypeError("resolver binding has an invalid record type")
        references = tuple(
            item.reference for group, _expected_type in typed_groups for item in group
        )
        if len(references) != len(set(references)):
            raise ValueError("resolver catalog references must be globally unique")


@dataclass(frozen=True)
class PrivateEvalsCommandResolverAdapter(
    RunManifestResolver,
    MaterializationRecordResolver,
    EvaluationRecordResolver,
    ScoringRecordResolver,
    FinalizationRecordResolver,
    EvidenceRecordResolver,
):
    catalog_store: EvalCatalogStore
    run_store: EvalRunStore
    analysis_store: EvalAnalysisStore
    materialization_store: EvalMaterializationStore
    records: ResolverRecordCatalog = ResolverRecordCatalog()

    @staticmethod
    def _lookup(reference: str, values: tuple[ReferencedRecord[T], ...]) -> T:
        _safe_reference(reference)
        matches = tuple(item.record for item in values if item.reference == reference)
        if not matches:
            raise ReferencedInputNotFound()
        if len(matches) != 1:
            raise ReferencedInputMismatch()
        return matches[0]

    @staticmethod
    def _store_call(call):
        try:
            return call()
        except EvalRecordNotFound:
            raise ReferencedInputNotFound() from None
        except EvalStoreUnavailable:
            raise ReferencedInputUnavailable() from None
        except EvalStoreError:
            raise ReferencedInputMismatch() from None
        except (TypeError, ValueError):
            raise ReferencedInputMismatch() from None

    def resolve_manifest(self, reference: str) -> EvalRunManifest:
        return self._store_call(lambda: self.run_store.get_manifest(EvalRunManifestId(reference)))

    def resolve_execution_request(self, reference: str) -> CaseExecutionRequest:
        return self._lookup(reference, self.records.execution_requests)

    def resolve_execution_attempt(self, reference: str) -> ExecutionAttemptRecord:
        return self._lookup(reference, self.records.execution_attempts)

    def resolve_logical_projection(self, reference: str) -> LogicalExecutionProjection:
        return self._lookup(reference, self.records.logical_projections)

    def resolve_case(self, reference: str) -> EvalCaseVersion:
        _safe_reference(reference)
        matches = tuple(item for item in self.records.case_references if item.reference == reference)
        if len(matches) != 1:
            raise ReferencedInputNotFound() if not matches else ReferencedInputMismatch()
        identity = matches[0]
        record = self._store_call(
            lambda: self.catalog_store.get_case_version(
                identity.suite_id, identity.case_id, identity.version
            )
        )
        if record.reference.case_id != identity.case_id or record.reference.version != identity.version:
            raise ReferencedInputMismatch()
        return record

    def resolve_materialized_output(self, reference: str) -> MaterializedOutputRecord:
        return self._store_call(
            lambda: self.materialization_store.get_materialized_output(
                MaterializedOutputId(reference)
            )
        )

    def resolve_evaluation_request(self, reference: str) -> CaseEvaluationRequest:
        return self._lookup(reference, self.records.evaluation_requests)

    def resolve_scoring_protocol(self, reference: str) -> ScoringProtocol:
        return self._lookup(reference, self.records.scoring_protocols)

    def resolve_expected_matrix(self, reference: str) -> ExpectedExecutionMatrix:
        return self._lookup(reference, self.records.expected_matrices)

    def resolve_result(self, reference: str) -> EvalResult:
        return self._store_call(lambda: self.run_store.get_result(EvalResultId(reference)))

    def resolve_run(self, reference: str) -> EvalRun:
        return self._store_call(lambda: self.run_store.get_run(EvalRunId(reference)))

    def resolve_scoring_decision(self, reference: str) -> RunScoringDecision:
        return self._store_call(
            lambda: self.analysis_store.get_scoring_decision(ScoringDecisionId(reference))
        )

    def resolve_terminal_failure(self, reference: str) -> TerminalFailureProjection:
        return self._lookup(reference, self.records.terminal_failures)

    def resolve_execution_accounting(self, reference: str) -> ExecutionAccountingProjection:
        return self._lookup(reference, self.records.execution_accounting)

    def resolve_execution_projection(self, reference: str) -> LogicalExecutionProjection:
        return self._lookup(reference, self.records.logical_projections)

    def resolve_evaluation_attempt(self, reference: str) -> EvaluationAttemptRecord:
        return self._store_call(
            lambda: self.run_store.get_evaluation_attempt(Fingerprint(reference))
        )

    def resolve_finalization(self, reference: str) -> EvalRunFinalizationRecord:
        return self._store_call(
            lambda: self.run_store.get_finalization(EvalRunFinalizationId(reference))
        )

    def resolve_implementation(self, reference: str) -> RFCImplementationBinding:
        return self._lookup(reference, self.records.implementations)

    def resolve_projection_candidate(self, reference: str) -> EvidenceProjectionCandidate:
        return self._lookup(reference, self.records.projection_candidates)
