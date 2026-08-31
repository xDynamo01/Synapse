from __future__ import annotations

from dataclasses import dataclass

from .case_evaluation import EvalResultCreationInput
from .command_contracts import PrivateEvalsCommandDependencies
from .command_error_mapping import EXPECTED_BOUNDARY_ERRORS, translate_expected_error
from .command_errors import PublicErrorCategory, public_error
from .command_models import (
    CreateEvalResultCommand,
    CreateRunCommand,
    CreateScoringDecisionCommand,
    EvidenceSubmissionResponse,
    FinalizationResponse,
    FinalizeRunCommand,
    PublicWriteOutcome,
    RecordMaterializedOutputCommand,
    RecordWriteResponse,
    RecoverFinalizationCommand,
    RunMutationResponse,
    ScoringDecisionResponse,
    StartRunCommand,
    SubmitEvidenceCommand,
)
from .evidence_submission import EvalEvidencePlanningInput
from .evidence_submission_models import EvidenceSubmissionOutcome
from .result_materialization import MaterializationInput
from .run_finalization import RunFinalizationInput
from .run_finalization_service import FinalizationWriteDisposition
from .run_scoring import RunScoringInput
from .runs import EvalRun
from .store_models import WriteDisposition
from .values import (
    EvalResultId,
    EvalRunFinalizationId,
    EvalRunId,
    Fingerprint,
    MaterializedOutputId,
    Revision,
    ScoringDecisionId,
)


def _write_outcome(value: WriteDisposition) -> PublicWriteOutcome:
    return (
        PublicWriteOutcome.CREATED
        if value is WriteDisposition.CREATED
        else PublicWriteOutcome.IDEMPOTENT_REPLAY
    )


@dataclass(frozen=True)
class PrivateEvalsCommandHandlers:
    dependencies: PrivateEvalsCommandDependencies

    def create_run(self, command: CreateRunCommand) -> RunMutationResponse:
        try:
            manifest = self.dependencies.manifest_resolver.resolve_manifest(
                command.manifest_reference
            )
            run = self.dependencies.run_runtime.prepare_run(
                EvalRunId(command.run_id),
                manifest,
                created_at=command.context.timestamp,
                idempotency_key=command.context.internal_idempotency_key,
            )
            return self._run_response(
                run, PublicWriteOutcome.CREATED, command.context.correlation_reference
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    def start_run(self, command: StartRunCommand) -> RunMutationResponse:
        try:
            run = self.dependencies.run_runtime.start_run(
                EvalRunId(command.run_id),
                timestamp=command.context.timestamp,
                expected_revision=Revision(command.expected_revision),
                idempotency_key=command.context.internal_idempotency_key,
            )
            return self._run_response(
                run, PublicWriteOutcome.APPLIED, command.context.correlation_reference
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    def record_materialized_output(
        self, command: RecordMaterializedOutputCommand
    ) -> RecordWriteResponse:
        try:
            resolver = self.dependencies.materialization_resolver
            request = resolver.resolve_execution_request(
                command.execution_request_reference
            )
            source = MaterializationInput(
                request=request,
                attempt=resolver.resolve_execution_attempt(
                    command.execution_attempt_reference
                ),
                logical_projection=resolver.resolve_logical_projection(
                    command.logical_projection_reference
                ),
                manifest=resolver.resolve_manifest(command.manifest_reference),
                case=resolver.resolve_case(command.case_reference),
                output_id=MaterializedOutputId(command.output_reference),
                producer_id=command.producer_id,
                producer_version=command.producer_version,
                created_at=command.context.timestamp,
                idempotency_key=command.context.internal_idempotency_key,
            )
            if request.logical_execution.run_id.value != command.run_id:
                raise public_error(
                    PublicErrorCategory.CONFLICT,
                    command.context.correlation_reference,
                )
            result = self.dependencies.materialization_service.materialize(source)
            return RecordWriteResponse(
                result.record.output_id.value,
                result.record.materialization_fingerprint.value,
                result.record.checksum.value,
                _write_outcome(result.disposition),
                command.context.correlation_reference,
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    def create_eval_result(self, command: CreateEvalResultCommand) -> RecordWriteResponse:
        try:
            resolver = self.dependencies.evaluation_resolver
            request = resolver.resolve_evaluation_request(
                command.evaluation_request_reference
            )
            source = EvalResultCreationInput(
                materialized=resolver.resolve_materialized_output(
                    command.materialized_output_reference
                ),
                request=request,
                response=command.evaluation_response,
                manifest=resolver.resolve_manifest(command.manifest_reference),
                case=resolver.resolve_case(command.case_reference),
                protocol=resolver.resolve_scoring_protocol(
                    command.scoring_protocol_reference
                ),
                result_id=EvalResultId(command.result_reference),
                producer_id=command.producer_id,
                producer_version=command.producer_version,
                created_at=command.context.timestamp,
                idempotency_key=command.context.internal_idempotency_key,
            )
            if request.run_id.value != command.run_id:
                raise public_error(
                    PublicErrorCategory.CONFLICT,
                    command.context.correlation_reference,
                )
            result = self.dependencies.result_service.create_result(source)
            assert result.result.result_fingerprint is not None
            return RecordWriteResponse(
                result.result.result_id.value,
                result.result.result_fingerprint.value,
                result.result.checksum.value,
                _write_outcome(result.disposition),
                command.context.correlation_reference,
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    def create_scoring_decision(
        self, command: CreateScoringDecisionCommand
    ) -> ScoringDecisionResponse:
        try:
            resolver = self.dependencies.scoring_resolver
            manifest = resolver.resolve_manifest(command.manifest_reference)
            source = RunScoringInput(
                run_id=EvalRunId(command.run_id),
                manifest_id=manifest.manifest_id,
                manifest_fingerprint=Fingerprint(command.manifest_fingerprint),
                suite_id=manifest.suite_id,
                suite_version=manifest.suite_version,
                protocol=resolver.resolve_scoring_protocol(
                    command.scoring_protocol_reference
                ),
                scoring_protocol_fingerprint=Fingerprint(
                    command.scoring_protocol_fingerprint
                ),
                expected_matrix=resolver.resolve_expected_matrix(
                    command.expected_matrix_reference
                ),
                results=tuple(
                    resolver.resolve_result(reference)
                    for reference in command.result_references
                ),
                decision_id=ScoringDecisionId(command.decision_reference),
                producer_id=command.producer_id,
                producer_version=command.producer_version,
                created_at=command.context.timestamp,
                idempotency_key=command.context.internal_idempotency_key,
                correlation_reference=command.context.correlation_reference,
            )
            if source.run_id.value != command.run_id:
                raise public_error(
                    PublicErrorCategory.CONFLICT,
                    command.context.correlation_reference,
                )
            result = self.dependencies.scoring_service.score_run(source)
            decision = result.decision
            return ScoringDecisionResponse(
                decision.decision_id.value,
                decision.run_id.value,
                decision.aggregate.verdict.value,
                decision.decision_fingerprint.value,
                decision.checksum.value,
                _write_outcome(result.disposition),
                command.context.correlation_reference,
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    def finalize_run(self, command: FinalizeRunCommand) -> FinalizationResponse:
        return self._finalize(command, recovery=False)

    def recover_finalization(
        self, command: RecoverFinalizationCommand
    ) -> FinalizationResponse:
        return self._finalize(command, recovery=True)

    def submit_evidence(
        self, command: SubmitEvidenceCommand
    ) -> EvidenceSubmissionResponse:
        try:
            resolver = self.dependencies.evidence_submission_resolver
            finalization = resolver.resolve_finalization(
                command.finalization_reference
            )
            source = EvalEvidencePlanningInput(
                finalization=finalization,
                implementation=resolver.resolve_implementation(
                    command.implementation_reference
                ),
                implementation_binding_reference=(
                    command.context.implementation_binding_reference
                ),
                candidates=tuple(
                    resolver.resolve_projection_candidate(reference)
                    for reference in command.projection_candidate_references
                ),
                scoring_decision=(
                    resolver.resolve_scoring_decision(
                        command.scoring_decision_reference
                    )
                    if command.scoring_decision_reference is not None
                    else None
                ),
                idempotency_key=command.context.internal_idempotency_key,
                correlation_reference=command.context.correlation_reference,
                producer_id=command.producer_id,
                producer_version=command.producer_version,
                created_at=command.context.timestamp,
            )
            if (
                finalization.run_id.value != command.run_id
                or source.implementation_binding_reference
                != command.context.implementation_binding_reference
            ):
                raise public_error(
                    PublicErrorCategory.CONFLICT,
                    command.context.correlation_reference,
                )
            result = self.dependencies.evidence_submission_service.submit(
                source,
                submission_id=command.submission_id,
                governance_identities=command.governance_identities,
            )
            outcome = {
                EvidenceSubmissionOutcome.CREATED: PublicWriteOutcome.SUBMITTED,
                EvidenceSubmissionOutcome.IDEMPOTENT_REPLAY: PublicWriteOutcome.LOCAL_REPLAY,
                EvidenceSubmissionOutcome.PARTIAL_RECOVERY: (
                    PublicWriteOutcome.RECEIPT_RECORDED
                ),
                EvidenceSubmissionOutcome.NOT_APPLICABLE: (
                    PublicWriteOutcome.NOT_APPLICABLE
                ),
            }[result.outcome]
            record = result.record
            return EvidenceSubmissionResponse(
                record.submission_id if record is not None else None,
                result.plan.run_id.value,
                tuple(item.value for item in result.plan.projection_kinds),
                (
                    tuple(item.evidence_id for item in record.governance_receipts)
                    if record is not None
                    else ()
                ),
                outcome,
                command.context.correlation_reference,
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    def _finalize(
        self,
        command: FinalizeRunCommand | RecoverFinalizationCommand,
        *,
        recovery: bool,
    ) -> FinalizationResponse:
        try:
            resolver = self.dependencies.finalization_resolver
            if recovery:
                assert isinstance(command, RecoverFinalizationCommand)
                persisted = resolver.resolve_finalization(
                    command.persisted_finalization_reference
                )
                finalization_reference = command.persisted_finalization_reference
                if persisted.record_reference != finalization_reference:
                    raise public_error(
                        PublicErrorCategory.CONFLICT,
                        command.context.correlation_reference,
                    )
            else:
                assert isinstance(command, FinalizeRunCommand)
                finalization_reference = command.finalization_reference
            run = resolver.resolve_run(command.run_reference)
            source = RunFinalizationInput(
                finalization_id=EvalRunFinalizationId(finalization_reference),
                run=run,
                manifest=resolver.resolve_manifest(command.manifest_reference),
                expected_matrix=resolver.resolve_expected_matrix(
                    command.expected_matrix_reference
                ),
                results=tuple(
                    resolver.resolve_result(reference)
                    for reference in command.result_references
                ),
                scoring_decision=(
                    resolver.resolve_scoring_decision(
                        command.scoring_decision_reference
                    )
                    if command.scoring_decision_reference is not None
                    else None
                ),
                terminal_failures=tuple(
                    resolver.resolve_terminal_failure(reference)
                    for reference in command.terminal_failure_references
                ),
                execution_accounting=resolver.resolve_execution_accounting(
                    command.execution_accounting_reference
                ),
                execution_projections=tuple(
                    resolver.resolve_execution_projection(reference)
                    for reference in command.execution_projection_references
                ),
                evaluation_attempts=tuple(
                    resolver.resolve_evaluation_attempt(reference)
                    for reference in command.evaluation_attempt_references
                ),
                security_snapshot_reference=command.security_snapshot_reference,
                security_snapshot_fingerprint=Fingerprint(
                    command.security_snapshot_fingerprint
                ),
                producer_id=command.producer_id,
                producer_version=command.producer_version,
                created_at=command.context.timestamp,
                idempotency_key=command.context.internal_idempotency_key,
                correlation_reference=command.context.correlation_reference,
            )
            if source.run.run_id.value != command.run_id:
                raise public_error(
                    PublicErrorCategory.CONFLICT,
                    command.context.correlation_reference,
                )
            result = self.dependencies.finalization_service.finalize(source)
            outcome = {
                FinalizationWriteDisposition.CREATED: PublicWriteOutcome.CREATED,
                FinalizationWriteDisposition.IDEMPOTENT_REPLAY: (
                    PublicWriteOutcome.IDEMPOTENT_REPLAY
                ),
                FinalizationWriteDisposition.RECOVERED: PublicWriteOutcome.RECOVERED,
            }[result.disposition]
            record = result.finalization
            return FinalizationResponse(
                record.record_reference,
                record.run_id.value,
                record.lifecycle_status.value,
                (
                    source.scoring_decision.verdict.value
                    if source.scoring_decision is not None
                    else None
                ),
                record.disposition.value,
                record.coverage.value,
                record.path.value,
                outcome,
                command.context.correlation_reference,
            )
        except EXPECTED_BOUNDARY_ERRORS as exc:
            raise translate_expected_error(
                exc, command.context.correlation_reference
            ) from exc

    @staticmethod
    def _run_response(
        run: EvalRun,
        outcome: PublicWriteOutcome,
        correlation_reference: str,
    ) -> RunMutationResponse:
        return RunMutationResponse(
            run.run_id.value,
            run.status.value,
            run.revision.value,
            run.manifest_id.value if run.manifest_id is not None else None,
            outcome,
            correlation_reference,
        )
