"""Consumer-owned read-only ports for neutral external facts."""

from typing import Protocol

from .application import (
    RepositoryMutationAttempt,
    RepositoryMutationCleanupResult,
    RepositoryMutationInterruptionResult,
    RepositoryMutationObservationResult,
    RepositoryMutationPreconditionReport,
    RepositoryMutationStep,
    RepositoryMutationStepRequest,
    RepositoryMutationStepResult,
)
from .authorization import (
    RepositoryAuthorizationFactsSnapshot,
    RepositoryAuthorizationRequirement,
)
from .identities import RepositoryCheckoutIdentity, RepositoryFingerprint, RepositoryIdentity
from .models import RepositoryPath
from .mutations import RepositoryMutationPrecondition
from .observation import RepositoryObservationFacts, RepositoryObservationRequest
from .recovery import (
    RepositoryRecoveryAttempt,
    RepositoryRecoveryInterruption,
    RepositoryRecoveryObservation,
    RepositoryRecoveryPlan,
    RepositoryRecoveryPreconditionReport,
    RepositoryRecoveryStep,
    RepositoryRecoveryStepResult,
    RepositoryRecoveryVerification,
)
from .restore_points import (
    RepositoryRestorePointManifest,
    RepositoryRestorePointVerificationFact,
)
from .snapshot import RepositoryPathFingerprintFact, RepositorySnapshot


class RepositoryObservationView(Protocol):
    """A consumer-readable immutable observation shape, not a Git/filesystem reader."""

    @property
    def repository_id(self) -> RepositoryIdentity: ...

    @property
    def checkout_id(self) -> RepositoryCheckoutIdentity: ...

    @property
    def fingerprint(self) -> RepositoryFingerprint: ...


class RepositoryObservationFactsPort(Protocol):
    """Consumer-owned read port returning neutral facts; implementations are future adapters."""

    def facts_for(self, request: RepositoryObservationRequest) -> RepositoryObservationFacts: ...


class RepositoryPathFingerprintFactsPort(Protocol):
    def fingerprint_facts_for(
        self, paths: tuple[RepositoryPath, ...]
    ) -> tuple[RepositoryPathFingerprintFact, ...]: ...


class RepositoryRestorePointMaterializationPort(Protocol):
    def materialize_restore_point(
        self, manifest: RepositoryRestorePointManifest
    ) -> tuple[RepositoryRestorePointVerificationFact, ...]: ...


class RepositoryAuthorizationFactsPort(Protocol):
    """Read-only provider boundary; facts do not carry a Governance decision."""

    def facts_for(
        self, requirement: RepositoryAuthorizationRequirement
    ) -> RepositoryAuthorizationFactsSnapshot: ...


class RepositoryMutationPreconditionPort(Protocol):
    """Revalidate declared facts before the first application side effect."""

    def revalidate_preconditions(
        self,
        attempt: RepositoryMutationAttempt,
        preconditions: tuple[RepositoryMutationPrecondition, ...],
    ) -> RepositoryMutationPreconditionReport: ...


class RepositoryMutationOperationPort(Protocol):
    """Apply exactly one declared operation; concrete adapters are future work."""

    def apply_operation(
        self, step: RepositoryMutationStepRequest
    ) -> RepositoryMutationStepResult: ...


class RepositoryMutationObservationPort(Protocol):
    """Return immediate neutral fingerprints, never final verification."""

    def observe_result(
        self, step: RepositoryMutationStepRequest, result: RepositoryMutationStepResult
    ) -> RepositoryMutationObservationResult: ...


class RepositoryMutationInterruptionPort(Protocol):
    """Request sequence interruption after a non-recoverable step fact."""

    def interrupt_sequence(
        self,
        attempt: RepositoryMutationAttempt,
        operation_id: RepositoryFingerprint,
    ) -> RepositoryMutationInterruptionResult: ...


class RepositoryMutationCleanupPort(Protocol):
    """Request cleanup of an explicitly partial attempt; completion is factual."""

    def request_cleanup(
        self,
        attempt: RepositoryMutationAttempt,
        completed_steps: tuple[RepositoryMutationStep, ...],
    ) -> RepositoryMutationCleanupResult: ...


class RepositoryRecoveryPreconditionPort(Protocol):
    def revalidate_recovery_preconditions(
        self, attempt: RepositoryRecoveryAttempt, plan: RepositoryRecoveryPlan
    ) -> RepositoryRecoveryPreconditionReport: ...


class RepositoryRecoveryStepPort(Protocol):
    def apply_recovery_step(
        self, attempt: RepositoryRecoveryAttempt, step: RepositoryRecoveryStep
    ) -> RepositoryRecoveryStepResult: ...


class RepositoryRecoveryObservationPort(Protocol):
    def observe_recovery_step(
        self,
        attempt: RepositoryRecoveryAttempt,
        step: RepositoryRecoveryStep,
        result: RepositoryRecoveryStepResult,
    ) -> RepositoryRecoveryObservation: ...


class RepositoryRecoveryInterruptionPort(Protocol):
    def interrupt_recovery(
        self, attempt: RepositoryRecoveryAttempt, step_fingerprint: RepositoryFingerprint
    ) -> RepositoryRecoveryInterruption: ...


class RepositoryRecoveryVerificationPort(Protocol):
    def verify_recovered_state(
        self, attempt: RepositoryRecoveryAttempt, base: RepositorySnapshot
    ) -> RepositoryRecoveryVerification: ...
