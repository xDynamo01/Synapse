"""Independent observation/verification flow with factual journal transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from synapse.deployment import (
    CorrelationReference,
    DeploymentAppendDisposition,
    DeploymentAttemptId,
    DeploymentEventId,
    DeploymentFingerprint,
    DeploymentJournalAppendRequest,
    DeploymentJournalStore,
    DeploymentLifecycleState,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentPersistenceError,
    DeploymentTransitionEventV1,
    LocalObservationRequestV1,
    LocalObservationV1,
    LocalVerificationOutcome,
    LocalVerificationPolicyV1,
    LocalVerificationRequestV1,
    LocalVerificationResultV1,
    OccurrenceReference,
    ReleaseId,
    TransitionFailureClass,
)


class LocalObservationPort(Protocol):
    def observe(self, request: LocalObservationRequestV1) -> LocalObservationV1: ...

    def current_fingerprint(self) -> DeploymentFingerprint | None: ...


class LocalVerifierPort(Protocol):
    def verify(self, request: LocalVerificationRequestV1) -> LocalVerificationResultV1: ...


@dataclass(frozen=True, slots=True)
class LocalIndependentVerificationFlow:
    observer: LocalObservationPort
    verifier: LocalVerifierPort
    journal: DeploymentJournalStore

    def run(
        self,
        observation_request: LocalObservationRequestV1,
        policy: LocalVerificationPolicyV1,
        occurrence: OccurrenceReference,
        verified_at: datetime,
    ) -> tuple[LocalObservationV1, LocalVerificationResultV1]:
        observation = self.observer.observe(observation_request)
        self._append(
            observation_request,
            DeploymentLifecycleState.APPLIED,
            DeploymentLifecycleState.VERIFYING,
            occurrence,
            observation=observation,
        )
        result = self.verifier.verify(LocalVerificationRequestV1(
            observation_request.release_reference,
            observation_request.attempt_reference,
            observation_request.target_reference,
            observation_request.environment_reference,
            observation_request.desired_revision,
            observation_request.desired_revision_fingerprint,
            observation_request.slot_reference,
            observation,
            policy,
            self.observer.current_fingerprint(),
            verified_at,
        ))
        state, failure = {
            LocalVerificationOutcome.VERIFIED: (DeploymentLifecycleState.VERIFIED, None),
            LocalVerificationOutcome.FAILED: (
                DeploymentLifecycleState.VERIFICATION_FAILED,
                TransitionFailureClass.VERIFICATION_MISMATCH,
            ),
            LocalVerificationOutcome.UNAVAILABLE: (
                DeploymentLifecycleState.VERIFICATION_UNAVAILABLE,
                TransitionFailureClass.EVIDENCE_UNAVAILABLE,
            ),
            LocalVerificationOutcome.INDETERMINATE: (
                DeploymentLifecycleState.VERIFICATION_UNAVAILABLE,
                TransitionFailureClass.EVIDENCE_UNAVAILABLE,
            ),
        }[result.outcome]
        self._append(
            observation_request,
            DeploymentLifecycleState.VERIFYING,
            state,
            occurrence,
            observation=observation,
            verification=result,
            failure=failure,
        )
        return observation, result

    def _append(
        self,
        request: LocalObservationRequestV1,
        prior: DeploymentLifecycleState,
        resulting: DeploymentLifecycleState,
        occurrence: OccurrenceReference,
        *,
        observation: LocalObservationV1,
        verification: LocalVerificationResultV1 | None = None,
        failure: TransitionFailureClass | None = None,
    ) -> None:
        machine = DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, request.attempt_reference)
        sequence = self.journal.latest_sequence(machine) + 1
        event = DeploymentTransitionEventV1(
            DeploymentEventId(f"deployment-event:verify-{sequence}-{observation.semantic_fingerprint.value[7:31]}"),
            ReleaseId(request.release_reference),
            DeploymentAttemptId(request.attempt_reference),
            prior,
            resulting,
            CorrelationReference(
                f"correlation:verification-{request.attempt_reference.split(':', 1)[1]}"
            ),
            None,
            occurrence,
            observation_reference=observation.observation_reference,
            verification_reference=(verification.verification_reference if verification else None),
            failure_class=failure,
        )
        appended = self.journal.append(DeploymentJournalAppendRequest(machine, sequence, event))
        if appended.disposition not in {
            DeploymentAppendDisposition.APPENDED,
            DeploymentAppendDisposition.IDEMPOTENT,
        }:
            raise DeploymentPersistenceError("verification journal append failed")
