"""Consumer-owned local rollback orchestration and independent verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from synapse.deployment import (
    CapabilityReference,
    CorrelationReference,
    DeploymentAppendDisposition,
    DeploymentEventId,
    DeploymentFencingAuthority,
    DeploymentFencingValidationState,
    DeploymentIdempotencyContradiction,
    DeploymentJournalAppendRequest,
    DeploymentJournalStore,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentPersistenceError,
    LocalDeploymentVerifier,
    LocalObservationRequestV1,
    LocalObservationV1,
    LocalRollbackApplyRequestV1,
    LocalRollbackFailure,
    LocalRollbackOutcome,
    LocalRollbackPreparationOutcome,
    LocalRollbackPreparationPort,
    LocalRollbackPreparationRequestV1,
    LocalRollbackPreparationResultV1,
    LocalRollbackReceiptV1,
    LocalRollbackResultV1,
    LocalRollbackStatePort,
    LocalVerificationOutcome,
    LocalVerificationPolicyV1,
    LocalVerificationRequestV1,
    LocalVerificationResultV1,
    ObservationReference,
    RollbackLifecycleState,
    RollbackReceiptReference,
    RollbackTransitionEventV1,
    SandboxLocalApplyCommandV1,
    SandboxLocalApplyOutcome,
    SandboxLocalApplyResultV1,
    TransitionFailureClass,
    rollback_authorization_is_current,
)


class SandboxRollbackStartPort(Protocol):
    def start(self, command: SandboxLocalApplyCommandV1) -> SandboxLocalApplyResultV1: ...


class CurrentRollbackAuthorizationPort(Protocol):
    def validate(
        self, request: LocalRollbackPreparationRequestV1 | LocalRollbackApplyRequestV1
    ) -> bool: ...


class RollbackObserverPort(Protocol):
    def observe(self, request: LocalObservationRequestV1) -> LocalObservationV1: ...
    def current_fingerprint(self): ...


@dataclass(frozen=True, slots=True)
class LocalRollbackOrchestrator:
    fencing: DeploymentFencingAuthority
    authorization: CurrentRollbackAuthorizationPort
    preparation: LocalRollbackPreparationPort
    sandbox: SandboxRollbackStartPort
    active_state: LocalRollbackStatePort
    journal: DeploymentJournalStore

    def prepare(self, request: LocalRollbackPreparationRequestV1) -> LocalRollbackPreparationResultV1:
        self._append(request, RollbackLifecycleState.REQUESTED, RollbackLifecycleState.AUTHORIZATION_PENDING)
        if not rollback_authorization_is_current(request) or not self.authorization.validate(request):
            self._append(
                request, RollbackLifecycleState.AUTHORIZATION_PENDING,
                RollbackLifecycleState.DENIED,
                failure=TransitionFailureClass.POLICY_DENIED,
            )
            return LocalRollbackPreparationResultV1(
                LocalRollbackPreparationOutcome.FAILED, None, None, None,
                LocalRollbackFailure.AUTHORIZATION_INVALID,
            )
        self._append(
            request, RollbackLifecycleState.AUTHORIZATION_PENDING,
            RollbackLifecycleState.AUTHORIZED, authorization=True,
        )
        self._append(request, RollbackLifecycleState.AUTHORIZED, RollbackLifecycleState.PREPARING)
        result = self.preparation.prepare(request)
        if result.outcome not in {
            LocalRollbackPreparationOutcome.PREPARED,
            LocalRollbackPreparationOutcome.ALREADY_PREPARED,
        }:
            state = (
                RollbackLifecycleState.PREPARATION_OUTCOME_UNKNOWN
                if result.outcome is LocalRollbackPreparationOutcome.OUTCOME_UNKNOWN
                else RollbackLifecycleState.PREPARATION_FAILED
            )
            self._append(
                request, RollbackLifecycleState.PREPARING, state,
                failure=TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN
                if result.outcome is LocalRollbackPreparationOutcome.OUTCOME_UNKNOWN
                else TransitionFailureClass.PRECONDITION_FAILED,
            )
            return result
        self._append(request, RollbackLifecycleState.PREPARING, RollbackLifecycleState.ROLLING_BACK)
        return result

    def apply(self, request: LocalRollbackApplyRequestV1) -> LocalRollbackResultV1:
        historical = self.active_state.receipt(request.semantic_fingerprint)
        if historical is not None:
            if historical.active_state_mutation_reference is None:
                return self._result(LocalRollbackOutcome.OUTCOME_UNKNOWN, historical, LocalRollbackFailure.RECONCILIATION_REQUIRED, True)
            return self._result(LocalRollbackOutcome.ROLLED_BACK, historical, None, False)
        if self.active_state.incomplete(request.semantic_fingerprint):
            return self._result(LocalRollbackOutcome.OUTCOME_UNKNOWN, None, LocalRollbackFailure.RECONCILIATION_REQUIRED, True)
        if request.preparation_result.outcome not in {
            LocalRollbackPreparationOutcome.PREPARED,
            LocalRollbackPreparationOutcome.ALREADY_PREPARED,
        }:
            return self._terminal(request, LocalRollbackOutcome.FAILED, LocalRollbackFailure.PREPARATION_FAILED, False)
        guarded = self._guard_apply(request)
        if guarded is not None:
            return self._terminal(request, LocalRollbackOutcome.FAILED, guarded, False)
        try:
            acceptance = self.fencing.accept_operation(
                request.idempotency, request.fencing_token,
                owner=request.authorization.requester,
                authority_identity=request.fencing_authority,
            )
        except DeploymentIdempotencyContradiction:
            return self._terminal(request, LocalRollbackOutcome.FAILED, LocalRollbackFailure.IDEMPOTENCY_CONTRADICTION, False)
        if acceptance.fencing.state is not DeploymentFencingValidationState.VALID:
            return self._terminal(request, LocalRollbackOutcome.FAILED, LocalRollbackFailure.FENCING_INVALID, False)
        try:
            mutation = self.active_state.stage(request)
        except (OSError, ValueError):
            return self._terminal(request, LocalRollbackOutcome.FAILED, LocalRollbackFailure.ACTIVE_STATE_FAILED, False)
        guarded = self._guard_apply(request)
        if guarded is not None:
            return self._terminal(request, LocalRollbackOutcome.OUTCOME_UNKNOWN, guarded, True)
        sandbox = self.sandbox.start(self._sandbox_command(request))
        if sandbox.outcome is SandboxLocalApplyOutcome.FAILED:
            failure = (
                LocalRollbackFailure.SANDBOX_AUTHORITY_INVALID
                if "sandbox-authority-invalid" in sandbox.diagnostic_codes
                else LocalRollbackFailure.SANDBOX_START_FAILED
            )
            return self._terminal(request, LocalRollbackOutcome.FAILED, failure, False)
        if sandbox.outcome is SandboxLocalApplyOutcome.UNKNOWN:
            return self._terminal(request, LocalRollbackOutcome.OUTCOME_UNKNOWN, LocalRollbackFailure.RECONCILIATION_REQUIRED, True)
        if sandbox.outcome is SandboxLocalApplyOutcome.PARTIAL:
            return self._terminal(request, LocalRollbackOutcome.PARTIALLY_ROLLED_BACK, LocalRollbackFailure.SANDBOX_START_FAILED, True)
        guarded = self._guard_apply(request)
        if guarded is not None:
            return self._terminal(request, LocalRollbackOutcome.PARTIALLY_ROLLED_BACK, guarded, True)
        try:
            active_ref = self.active_state.promote(mutation)
        except (OSError, ValueError):
            return self._terminal(request, LocalRollbackOutcome.PARTIALLY_ROLLED_BACK, LocalRollbackFailure.ACTIVE_STATE_FAILED, True)
        receipt = self._receipt(request, sandbox, active_ref)
        try:
            self.active_state.record(receipt)
            self._append(
                request.preparation_request, RollbackLifecycleState.ROLLING_BACK,
                RollbackLifecycleState.ROLLED_BACK, receipt=receipt.receipt_reference,
            )
        except (DeploymentPersistenceError, OSError, ValueError):
            return self._result(LocalRollbackOutcome.OUTCOME_UNKNOWN, receipt, LocalRollbackFailure.RECONCILIATION_REQUIRED, True)
        return self._result(LocalRollbackOutcome.ROLLED_BACK, receipt, None, False)

    def observe_and_verify(
        self,
        request: LocalRollbackApplyRequestV1,
        receipt: LocalRollbackReceiptV1,
        observer: RollbackObserverPort,
        verifier: LocalDeploymentVerifier,
        policy: LocalVerificationPolicyV1,
        observed_at: datetime,
    ) -> tuple[LocalObservationV1, LocalVerificationResultV1]:
        observation_request = LocalObservationRequestV1(
            receipt.release_reference, receipt.rollback_attempt_reference,
            receipt.target_reference, receipt.environment_reference,
            receipt.intended_revision, request.preparation_request.revision_fingerprint,
            receipt.sandbox_execution_reference.value if receipt.sandbox_execution_reference else None,
            None, policy.policy_reference,
        )
        observation = observer.observe(observation_request)
        self._append(
            request.preparation_request, RollbackLifecycleState.ROLLED_BACK,
            RollbackLifecycleState.VERIFYING,
            observation=observation.observation_reference,
        )
        verification = verifier.verify(LocalVerificationRequestV1(
            receipt.release_reference, receipt.rollback_attempt_reference,
            receipt.target_reference, receipt.environment_reference,
            receipt.intended_revision, request.preparation_request.revision_fingerprint,
            None, observation, policy, observer.current_fingerprint(), observed_at,
        ))
        state = (
            RollbackLifecycleState.VERIFIED
            if verification.outcome is LocalVerificationOutcome.VERIFIED
            else RollbackLifecycleState.ROLLBACK_UNVERIFIED
        )
        self._append(
            request.preparation_request, RollbackLifecycleState.VERIFYING, state,
            observation=observation.observation_reference,
            verification=verification.verification_reference,
            failure=None if state is RollbackLifecycleState.VERIFIED else (
                TransitionFailureClass.VERIFICATION_MISMATCH
                if verification.outcome is LocalVerificationOutcome.FAILED
                else TransitionFailureClass.EVIDENCE_UNAVAILABLE
            ),
        )
        return observation, verification

    def _guard_apply(self, request: LocalRollbackApplyRequestV1) -> LocalRollbackFailure | None:
        if not rollback_authorization_is_current(request) or not self.authorization.validate(request):
            return LocalRollbackFailure.AUTHORIZATION_INVALID
        validation = self.fencing.validate(
            request.fencing_token, scope=request.idempotency.scope,
            owner=request.authorization.requester,
            authority_identity=request.fencing_authority,
            operation=request.idempotency.operation,
            semantic_binding_fingerprint=request.semantic_fingerprint,
        )
        return None if validation.state is DeploymentFencingValidationState.VALID else LocalRollbackFailure.FENCING_INVALID

    @staticmethod
    def _sandbox_command(request: LocalRollbackApplyRequestV1) -> SandboxLocalApplyCommandV1:
        prepared = request.preparation_result.prepared_revision_reference
        token = request.fencing_token
        if prepared is None or token is None:
            raise ValueError("rollback preparation or fencing unavailable")
        return SandboxLocalApplyCommandV1(
            prepared, prepared, request.preparation_request.command_entrypoint,
            request.sandbox_authorization_reference, request.sandbox_fencing_reference,
            request.authorization.reference, token.token_fingerprint, request.occurrence,
        )

    @staticmethod
    def _receipt(
        request: LocalRollbackApplyRequestV1,
        sandbox: SandboxLocalApplyResultV1,
        active_reference: CapabilityReference,
    ) -> LocalRollbackReceiptV1:
        prep = request.preparation_request
        rollback = prep.rollback
        prepared = request.preparation_result.prepared_revision_reference
        if prepared is None:
            raise ValueError("prepared rollback revision unavailable")
        return LocalRollbackReceiptV1(
            RollbackReceiptReference(f"rollback-receipt:local-{request.semantic_fingerprint.value[7:39]}"),
            rollback.rollback_attempt_id.value, rollback.release_id.value,
            rollback.target_id.value, prep.environment_reference,
            rollback.source_revision, rollback.intended_revision, rollback.intended_revision,
            prepared, sandbox.execution_reference, active_reference, request.occurrence,
            ("verification-not-performed", "replaced-revision-retained"),
            request.semantic_fingerprint,
        )

    def _terminal(
        self, request: LocalRollbackApplyRequestV1, outcome: LocalRollbackOutcome,
        failure: LocalRollbackFailure, reconciliation: bool,
    ) -> LocalRollbackResultV1:
        state = {
            LocalRollbackOutcome.FAILED: RollbackLifecycleState.ROLLBACK_FAILED,
            LocalRollbackOutcome.PARTIALLY_ROLLED_BACK: RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN,
            LocalRollbackOutcome.OUTCOME_UNKNOWN: RollbackLifecycleState.ROLLBACK_OUTCOME_UNKNOWN,
        }[outcome]
        try:
            self._append(
                request.preparation_request, RollbackLifecycleState.ROLLING_BACK, state,
                failure=TransitionFailureClass.PARTIAL_EXTERNAL_EFFECT
                if outcome is LocalRollbackOutcome.PARTIALLY_ROLLED_BACK
                else TransitionFailureClass.EXTERNAL_OUTCOME_UNKNOWN
                if outcome is LocalRollbackOutcome.OUTCOME_UNKNOWN
                else TransitionFailureClass.EXTERNAL_FAILURE,
            )
        except DeploymentPersistenceError:
            reconciliation = True
            outcome = LocalRollbackOutcome.OUTCOME_UNKNOWN
        return self._result(outcome, None, failure, reconciliation)

    @staticmethod
    def _result(outcome, receipt, failure, reconciliation) -> LocalRollbackResultV1:
        return LocalRollbackResultV1(outcome, receipt, failure, reconciliation)

    def _append(
        self,
        request: LocalRollbackPreparationRequestV1,
        prior: RollbackLifecycleState,
        resulting: RollbackLifecycleState,
        *,
        authorization: bool = False,
        receipt: RollbackReceiptReference | None = None,
        observation: ObservationReference | None = None,
        verification=None,
        failure: TransitionFailureClass | None = None,
    ) -> None:
        rollback = request.rollback
        machine = DeploymentMachineKey(DeploymentMachineKind.ROLLBACK, rollback.rollback_attempt_id.value)
        sequence = self.journal.latest_sequence(machine) + 1
        event = RollbackTransitionEventV1(
            DeploymentEventId(f"deployment-event:rollback-{sequence}-{request.semantic_fingerprint.value[7:31]}"),
            rollback.rollback_attempt_id, rollback.release_id, rollback.target_id,
            rollback.source_revision, rollback.intended_revision, request.artifact,
            prior, resulting,
            CorrelationReference(f"correlation:rollback-{rollback.rollback_attempt_id.value.split(':', 1)[1]}"),
            None, request.occurrence,
            rollback.authorization_reference if authorization else None,
            receipt, observation, verification, failure,
        )
        appended = self.journal.append(DeploymentJournalAppendRequest(machine, sequence, event))
        if appended.disposition not in {DeploymentAppendDisposition.APPENDED, DeploymentAppendDisposition.IDEMPOTENT}:
            raise DeploymentPersistenceError("rollback journal append failed")
