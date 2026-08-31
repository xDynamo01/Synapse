"""Consumer-owned local apply orchestration over Deployment and Sandbox seams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from synapse.deployment import (
    ApplyReceiptReference,
    CapabilityReference,
    DeploymentAppendDisposition,
    DeploymentEventId,
    DeploymentFencingAuthority,
    DeploymentFencingValidationState,
    DeploymentIdempotencyContradiction,
    DeploymentJournalAppendRequest,
    DeploymentJournalStore,
    DeploymentLifecycleState,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentPersistenceError,
    DeploymentTransitionEventV1,
    LocalActiveStateMutationV1,
    LocalActiveStatePort,
    LocalApplyFailure,
    LocalApplyOutcome,
    LocalApplyReceiptV1,
    LocalApplyRequestV1,
    LocalApplyResultV1,
    SandboxLocalApplyCommandV1,
    SandboxLocalApplyOutcome,
    SandboxLocalApplyResultV1,
    TransitionFailureClass,
    preparation_corresponds,
)


class CurrentDeploymentApplyAuthorizationPort(Protocol):
    def validate(self, request: LocalApplyRequestV1) -> bool: ...


class SandboxLocalApplyPort(Protocol):
    def start(self, command: SandboxLocalApplyCommandV1) -> SandboxLocalApplyResultV1: ...


@dataclass(frozen=True, slots=True)
class LocalApplyOrchestrator:
    fencing: DeploymentFencingAuthority
    authorization: CurrentDeploymentApplyAuthorizationPort
    sandbox: SandboxLocalApplyPort
    active_state: LocalActiveStatePort
    journal: DeploymentJournalStore

    def apply(self, request: LocalApplyRequestV1) -> LocalApplyResultV1:
        historical = self.active_state.staged_receipt(request.semantic_fingerprint)
        if historical is not None:
            if historical.active_state_mutation_reference is None:
                return LocalApplyResultV1(
                    LocalApplyOutcome.OUTCOME_UNKNOWN,
                    historical,
                    LocalApplyFailure.RECONCILIATION_REQUIRED,
                    True,
                )
            return LocalApplyResultV1(LocalApplyOutcome.APPLIED, historical, None, False)
        if self.active_state.incomplete(request.semantic_fingerprint):
            return self._result(
                LocalApplyOutcome.OUTCOME_UNKNOWN,
                LocalApplyFailure.RECONCILIATION_REQUIRED,
                True,
            )
        if not preparation_corresponds(request):
            return self._result(
                LocalApplyOutcome.FAILED,
                LocalApplyFailure.PREPARED_REVISION_REQUIRED,
                False,
            )
        if not request.target_ready:
            return self._result(LocalApplyOutcome.FAILED, LocalApplyFailure.TARGET_NOT_READY, False)
        guarded = self._guard(request)
        if guarded is not None:
            return guarded
        try:
            acceptance = self.fencing.accept_operation(
                request.idempotency,
                request.deployment_fencing_token,
                owner=request.preparation_request.authorization.requester,
                authority_identity=request.deployment_fencing_authority,
            )
        except DeploymentIdempotencyContradiction:
            return self._result(
                LocalApplyOutcome.FAILED,
                LocalApplyFailure.IDEMPOTENCY_CONTRADICTION,
                False,
            )
        if acceptance.fencing.state is not DeploymentFencingValidationState.VALID:
            return self._result(
                LocalApplyOutcome.FAILED,
                LocalApplyFailure.DEPLOYMENT_FENCING_INVALID,
                False,
            )
        try:
            self._append(
                request, DeploymentLifecycleState.PREPARED, DeploymentLifecycleState.APPLYING
            )
        except DeploymentPersistenceError:
            return self._result(
                LocalApplyOutcome.FAILED,
                LocalApplyFailure.RECONCILIATION_REQUIRED,
                True,
            )
        guarded = self._guard(request)
        if guarded is not None:
            return self._terminal(request, guarded, None, None)
        try:
            mutation = self.active_state.stage(request)
        except (OSError, ValueError):
            return self._terminal(
                request,
                self._result(
                    LocalApplyOutcome.FAILED,
                    LocalApplyFailure.ACTIVE_STATE_FAILED,
                    False,
                ),
                None,
                None,
            )
        guarded = self._guard(request)
        if guarded is not None:
            return self._terminal(request, guarded, mutation, None)
        sandbox = self.sandbox.start(self._sandbox_command(request))
        if sandbox.outcome is SandboxLocalApplyOutcome.FAILED:
            failure = (
                LocalApplyFailure.SANDBOX_AUTHORITY_INVALID
                if "sandbox-authority-invalid" in sandbox.diagnostic_codes
                else LocalApplyFailure.SANDBOX_START_FAILED
            )
            return self._terminal(
                request,
                self._result(LocalApplyOutcome.FAILED, failure, False),
                mutation,
                sandbox,
            )
        if sandbox.outcome is SandboxLocalApplyOutcome.UNKNOWN:
            return self._terminal(
                request,
                self._result(
                    LocalApplyOutcome.OUTCOME_UNKNOWN,
                    LocalApplyFailure.RECONCILIATION_REQUIRED,
                    True,
                ),
                mutation,
                sandbox,
            )
        if sandbox.outcome is SandboxLocalApplyOutcome.PARTIAL:
            return self._terminal(
                request,
                self._result(
                    LocalApplyOutcome.PARTIALLY_APPLIED,
                    LocalApplyFailure.SANDBOX_START_FAILED,
                    True,
                ),
                mutation,
                sandbox,
            )
        guarded = self._guard(request)
        if guarded is not None:
            return self._terminal(
                request,
                LocalApplyResultV1(
                    LocalApplyOutcome.PARTIALLY_APPLIED,
                    None,
                    guarded.failure,
                    True,
                ),
                mutation,
                sandbox,
            )
        try:
            active_reference = self.active_state.promote(mutation)
        except (OSError, ValueError):
            return self._terminal(
                request,
                self._result(
                    LocalApplyOutcome.PARTIALLY_APPLIED,
                    LocalApplyFailure.ACTIVE_STATE_FAILED,
                    True,
                ),
                mutation,
                sandbox,
            )
        receipt = self._receipt(request, mutation, sandbox, active_reference)
        try:
            self.active_state.record_receipt(receipt)
            self._append(
                request,
                DeploymentLifecycleState.APPLYING,
                DeploymentLifecycleState.APPLIED,
                receipt.receipt_reference,
            )
        except (DeploymentPersistenceError, OSError, ValueError):
            return LocalApplyResultV1(
                LocalApplyOutcome.OUTCOME_UNKNOWN,
                receipt,
                LocalApplyFailure.RECONCILIATION_REQUIRED,
                True,
            )
        return LocalApplyResultV1(LocalApplyOutcome.APPLIED, receipt, None, False)

    def _guard(self, request: LocalApplyRequestV1) -> LocalApplyResultV1 | None:
        if (
            request.authorization_semantic_fingerprint != request.semantic_fingerprint
            or not self.authorization.validate(request)
        ):
            return self._result(
                LocalApplyOutcome.FAILED,
                LocalApplyFailure.AUTHORIZATION_INVALID,
                False,
            )
        validation = self.fencing.validate(
            request.deployment_fencing_token,
            scope=request.idempotency.scope,
            owner=request.preparation_request.authorization.requester,
            authority_identity=request.deployment_fencing_authority,
            operation=request.idempotency.operation,
            semantic_binding_fingerprint=request.semantic_fingerprint,
        )
        if validation.state is not DeploymentFencingValidationState.VALID:
            return self._result(
                LocalApplyOutcome.FAILED,
                LocalApplyFailure.DEPLOYMENT_FENCING_INVALID,
                False,
            )
        return None

    def _terminal(
        self,
        request: LocalApplyRequestV1,
        result: LocalApplyResultV1,
        mutation: LocalActiveStateMutationV1 | None,
        sandbox: SandboxLocalApplyResultV1 | None,
    ) -> LocalApplyResultV1:
        receipt = (
            self._receipt(request, mutation, sandbox, None)
            if mutation is not None and sandbox is not None and sandbox.process_started
            else None
        )
        state, failure = {
            LocalApplyOutcome.FAILED: (
                DeploymentLifecycleState.APPLY_FAILED,
                TransitionFailureClass.EXTERNAL_FAILURE,
            ),
            LocalApplyOutcome.PARTIALLY_APPLIED: (
                DeploymentLifecycleState.PARTIALLY_APPLIED,
                TransitionFailureClass.PARTIAL_EXTERNAL_EFFECT,
            ),
            LocalApplyOutcome.OUTCOME_UNKNOWN: (
                DeploymentLifecycleState.APPLY_OUTCOME_UNKNOWN,
                TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN,
            ),
        }[result.outcome]
        try:
            self._append(
                request,
                DeploymentLifecycleState.APPLYING,
                state,
                receipt.receipt_reference if receipt else None,
                failure,
            )
            if receipt is not None:
                self.active_state.record_receipt(receipt)
        except (DeploymentPersistenceError, OSError, ValueError):
            return LocalApplyResultV1(
                LocalApplyOutcome.OUTCOME_UNKNOWN,
                receipt,
                LocalApplyFailure.RECONCILIATION_REQUIRED,
                True,
            )
        return LocalApplyResultV1(
            result.outcome, receipt, result.failure, result.reconciliation_required
        )

    @staticmethod
    def _result(
        outcome: LocalApplyOutcome,
        failure: LocalApplyFailure,
        reconciliation: bool,
    ) -> LocalApplyResultV1:
        return LocalApplyResultV1(outcome, None, failure, reconciliation)

    @staticmethod
    def _sandbox_command(request: LocalApplyRequestV1) -> SandboxLocalApplyCommandV1:
        prepared = request.preparation_result
        handoff = prepared.handoff
        if prepared.prepared_revision_reference is None or handoff is None:
            raise ValueError("prepared Sandbox handoff is unavailable")
        token = request.deployment_fencing_token
        if token is None:
            raise ValueError("Deployment fencing token is unavailable")
        return SandboxLocalApplyCommandV1(
            prepared.prepared_revision_reference,
            handoff.workspace_reference,
            handoff.command_entrypoint,
            request.sandbox_authorization_reference,
            request.sandbox_fencing_reference,
            request.authorization_reference,
            token.token_fingerprint,
            request.occurrence,
        )

    @staticmethod
    def _receipt(
        request: LocalApplyRequestV1,
        mutation: LocalActiveStateMutationV1,
        sandbox: SandboxLocalApplyResultV1,
        active_reference: CapabilityReference | None,
    ) -> LocalApplyReceiptV1:
        digest = request.semantic_fingerprint.value.split(":", 1)[1]
        correspondence = request.preparation_request.correspondence
        prepared = request.preparation_result.prepared_revision_reference
        if prepared is None:
            raise ValueError("prepared revision reference is unavailable")
        return LocalApplyReceiptV1(
            ApplyReceiptReference(f"apply-receipt:local-{digest[:32]}"),
            correspondence.attempt.release_id.value,
            correspondence.attempt.attempt_id.value,
            correspondence.target.target.target_id.value,
            correspondence.environment.environment.environment_id.value,
            correspondence.desired_revision.desired_revision.revision_id,
            prepared,
            sandbox.execution_reference,
            active_reference,
            mutation.previous_active_revision,
            request.occurrence,
            ("verification-not-performed", "rollback-eligibility-unknown"),
            request.semantic_fingerprint,
        )

    def _append(
        self,
        request: LocalApplyRequestV1,
        prior: DeploymentLifecycleState,
        resulting: DeploymentLifecycleState,
        receipt: ApplyReceiptReference | None = None,
        failure: TransitionFailureClass | None = None,
    ) -> None:
        attempt = request.preparation_request.correspondence.attempt
        machine = DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, attempt.attempt_id.value)
        sequence = self.journal.latest_sequence(machine) + 1
        digest = request.semantic_fingerprint.value.split(":", 1)[1]
        event = DeploymentTransitionEventV1(
            DeploymentEventId(f"deployment-event:apply-{sequence}-{digest[:24]}"),
            attempt.release_id,
            attempt.attempt_id,
            prior,
            resulting,
            attempt.correlation,
            None,
            request.occurrence,
            request.authorization_reference,
            receipt,
            failure_class=failure,
        )
        appended = self.journal.append(DeploymentJournalAppendRequest(machine, sequence, event))
        if appended.disposition not in {
            DeploymentAppendDisposition.APPENDED,
            DeploymentAppendDisposition.IDEMPOTENT,
        }:
            raise DeploymentPersistenceError("apply journal append failed")
