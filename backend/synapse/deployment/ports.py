"""Provider-neutral operational contracts and consumer-owned Deployment ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .errors import InvalidDeploymentAttemptBinding, InvalidRollbackProgression
from .identities import (
    ApplyReceiptReference,
    ArtifactFingerprintReference,
    AuthorizationReference,
    CapabilityReference,
    CausationReference,
    CorrelationReference,
    CustodyReference,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    EvidenceReference,
    FencingReference,
    ObservationReference,
    PolicyReference,
    PreparationReference,
    RequesterReference,
    RollbackReceiptReference,
    VerificationReference,
)
from .models import (
    DeploymentArtifactRefV1,
    DeploymentAttemptV1,
    DeploymentEnvironmentV1,
    DeploymentReleaseV1,
    DeploymentRollbackAttemptV1,
    DeploymentTargetV1,
    DesiredRevisionV1,
    ObservedRevisionV1,
)


class ArtifactAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ArtifactFingerprintCorrespondence(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class ProvenanceAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DeploymentOperation(StrEnum):
    PREPARE = "prepare"
    APPLY = "apply"
    OBSERVE = "observe"
    VERIFY = "verify"
    ROLLBACK_PREPARE = "rollback-prepare"
    ROLLBACK_APPLY = "rollback-apply"
    ROLLBACK_OBSERVE = "rollback-observe"
    ROLLBACK_VERIFY = "rollback-verify"


class DeploymentAuthorizationOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval-required"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    EXPIRED = "expired"


class DeploymentPreparationOutcome(StrEnum):
    PREPARED = "prepared"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class DeploymentApplyOutcome(StrEnum):
    APPLIED = "applied"
    PARTIALLY_APPLIED = "partially-applied"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"


class DeploymentObservationOutcome(StrEnum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DeploymentVerificationOutcome(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class RollbackPreparationOutcome(StrEnum):
    PREPARED = "prepared"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class RollbackApplyOutcome(StrEnum):
    ROLLED_BACK = "rolled-back"
    PARTIALLY_ROLLED_BACK = "partially-rolled-back"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome-unknown"


class RollbackObservationOutcome(StrEnum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class RollbackVerificationOutcome(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


def _normalize_limitations(
    limitations: tuple[CapabilityReference, ...],
) -> tuple[CapabilityReference, ...]:
    if not isinstance(limitations, tuple) or not all(
        isinstance(item, CapabilityReference) for item in limitations
    ):
        raise InvalidDeploymentAttemptBinding(
            "operational limitations must be immutable opaque references"
        )
    normalized = tuple(sorted(set(limitations)))
    if len(normalized) > 32:
        raise InvalidDeploymentAttemptBinding("operational limitations are unbounded")
    return normalized


def _normalize_evidence(
    evidence: tuple[EvidenceReference, ...],
) -> tuple[EvidenceReference, ...]:
    if not isinstance(evidence, tuple) or not all(
        isinstance(item, EvidenceReference) for item in evidence
    ):
        raise InvalidDeploymentAttemptBinding(
            "authorization evidence must use immutable opaque evidence references"
        )
    normalized = tuple(sorted(set(evidence)))
    if len(normalized) > 32:
        raise InvalidDeploymentAttemptBinding("authorization evidence is unbounded")
    return normalized


def _validate_release_attempt(
    release: DeploymentReleaseV1,
    attempt: DeploymentAttemptV1,
    target: DeploymentTargetV1,
    artifact: DeploymentArtifactRefV1,
    revision: DesiredRevisionV1,
) -> None:
    if (
        attempt.release_id != release.release_id
        or attempt.target_id != target.target_id
        or release.target_id != target.target_id
        or attempt.artifact != artifact
        or release.artifact != artifact
        or attempt.desired_revision != revision
        or release.desired_revision != revision
        or revision.artifact_fingerprint != artifact.fingerprint
    ):
        raise InvalidDeploymentAttemptBinding(
            "release, attempt, target, artifact and revision do not correspond"
        )


def _validate_environment_target(
    environment: DeploymentEnvironmentV1, target: DeploymentTargetV1
) -> None:
    if target.environment_id != environment.environment_id:
        raise InvalidDeploymentAttemptBinding("target and environment do not correspond")


@dataclass(frozen=True, slots=True)
class DeploymentArtifactFactsRequestV1:
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    artifact: DeploymentArtifactRefV1
    requester: RequesterReference
    correlation: CorrelationReference

    def __post_init__(self) -> None:
        if (
            self.attempt.release_id != self.release.release_id
            or self.release.artifact != self.artifact
            or self.attempt.artifact != self.artifact
        ):
            raise InvalidDeploymentAttemptBinding("artifact facts request binding mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentArtifactFactsResultV1:
    availability: ArtifactAvailability
    fingerprint_correspondence: ArtifactFingerprintCorrespondence
    provenance_availability: ProvenanceAvailability
    observed_fingerprint: ArtifactFingerprintReference | None = None
    custody_reference: CustodyReference | None = None
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.observed_fingerprint is not None
            and not isinstance(self.observed_fingerprint, ArtifactFingerprintReference)
        ) or (
            self.custody_reference is not None
            and not isinstance(self.custody_reference, CustodyReference)
        ):
            raise InvalidDeploymentAttemptBinding("artifact facts contain a wrong reference type")
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentAuthorizationRequestV1:
    operation: DeploymentOperation
    requester: RequesterReference
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    environment: DeploymentEnvironmentV1
    target: DeploymentTargetV1
    artifact: DeploymentArtifactRefV1
    desired_revision: DesiredRevisionV1
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: CausationReference | None

    def __post_init__(self) -> None:
        _validate_release_attempt(
            self.release, self.attempt, self.target, self.artifact, self.desired_revision
        )
        _validate_environment_target(self.environment, self.target)


@dataclass(frozen=True, slots=True)
class DeploymentAuthorizationResultV1:
    outcome: DeploymentAuthorizationOutcome
    authorization_reference: AuthorizationReference | None = None
    evidence_references: tuple[EvidenceReference, ...] = ()
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.authorization_reference is not None and not isinstance(
            self.authorization_reference, AuthorizationReference
        ):
            raise InvalidDeploymentAttemptBinding("authorization reference has wrong type")
        if self.outcome is DeploymentAuthorizationOutcome.ALLOWED and not isinstance(
            self.authorization_reference, AuthorizationReference
        ):
            raise InvalidDeploymentAttemptBinding(
                "allowed authorization requires a typed authorization reference"
            )
        object.__setattr__(
            self, "evidence_references", _normalize_evidence(self.evidence_references)
        )
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentPreparationRequestV1:
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    target: DeploymentTargetV1
    artifact: DeploymentArtifactRefV1
    desired_revision: DesiredRevisionV1
    policy_reference: PolicyReference
    configuration_fingerprint: DeploymentFingerprint

    def __post_init__(self) -> None:
        _validate_release_attempt(
            self.release, self.attempt, self.target, self.artifact, self.desired_revision
        )
        if self.configuration_fingerprint != self.attempt.configuration_fingerprint:
            raise InvalidDeploymentAttemptBinding("preparation configuration mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentPreparationResultV1:
    outcome: DeploymentPreparationOutcome
    preparation_reference: PreparationReference | None = None
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.preparation_reference is not None and not isinstance(
            self.preparation_reference, PreparationReference
        ):
            raise InvalidDeploymentAttemptBinding("preparation reference has wrong type")
        if self.outcome is DeploymentPreparationOutcome.PREPARED and not isinstance(
            self.preparation_reference, PreparationReference
        ):
            raise InvalidDeploymentAttemptBinding(
                "prepared result requires a preparation reference"
            )
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentApplyRequestV1:
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    target: DeploymentTargetV1
    artifact: DeploymentArtifactRefV1
    desired_revision: DesiredRevisionV1
    preparation_reference: PreparationReference
    authorization_reference: AuthorizationReference
    idempotency_key: DeploymentIdempotencyKey
    semantic_fingerprint: DeploymentFingerprint
    fencing_reference: FencingReference | None = None

    def __post_init__(self) -> None:
        _validate_release_attempt(
            self.release, self.attempt, self.target, self.artifact, self.desired_revision
        )
        if (
            not isinstance(self.preparation_reference, PreparationReference)
            or not isinstance(self.authorization_reference, AuthorizationReference)
            or not isinstance(self.idempotency_key, DeploymentIdempotencyKey)
            or not isinstance(self.semantic_fingerprint, DeploymentFingerprint)
            or (
                self.fencing_reference is not None
                and not isinstance(self.fencing_reference, FencingReference)
            )
        ):
            raise InvalidDeploymentAttemptBinding("apply request reference type mismatch")
        if self.semantic_fingerprint != self.attempt.semantic_fingerprint:
            raise InvalidDeploymentAttemptBinding("apply semantic fingerprint mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentApplyResultV1:
    outcome: DeploymentApplyOutcome
    apply_receipt_reference: ApplyReceiptReference | None = None
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.apply_receipt_reference is not None and not isinstance(
            self.apply_receipt_reference, ApplyReceiptReference
        ):
            raise InvalidDeploymentAttemptBinding("apply receipt has wrong type")
        if self.outcome is DeploymentApplyOutcome.APPLIED and not isinstance(
            self.apply_receipt_reference, ApplyReceiptReference
        ):
            raise InvalidDeploymentAttemptBinding("applied result requires an apply receipt")
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentObservationRequestV1:
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    target: DeploymentTargetV1
    desired_revision: DesiredRevisionV1

    def __post_init__(self) -> None:
        _validate_release_attempt(
            self.release,
            self.attempt,
            self.target,
            self.attempt.artifact,
            self.desired_revision,
        )


@dataclass(frozen=True, slots=True)
class DeploymentObservationResultV1:
    outcome: DeploymentObservationOutcome
    observation_reference: ObservationReference | None = None
    observed_revision: ObservedRevisionV1 | None = None
    runtime_facts: tuple[CapabilityReference, ...] = ()
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.observation_reference is not None and not isinstance(
            self.observation_reference, ObservationReference
        ):
            raise InvalidDeploymentAttemptBinding("observation reference has wrong type")
        if self.outcome is DeploymentObservationOutcome.OBSERVED and (
            self.observation_reference is None
            or self.observed_revision is None
            or self.observed_revision.observation != self.observation_reference
        ):
            raise InvalidDeploymentAttemptBinding(
                "observed result requires corresponding observation and revision facts"
            )
        object.__setattr__(self, "runtime_facts", _normalize_limitations(self.runtime_facts))
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentVerificationRequestV1:
    release: DeploymentReleaseV1
    attempt: DeploymentAttemptV1
    target: DeploymentTargetV1
    desired_revision: DesiredRevisionV1
    observation: DeploymentObservationResultV1
    verification_policy_reference: PolicyReference

    def __post_init__(self) -> None:
        _validate_release_attempt(
            self.release,
            self.attempt,
            self.target,
            self.attempt.artifact,
            self.desired_revision,
        )
        if (
            self.observation.outcome is not DeploymentObservationOutcome.OBSERVED
            or self.observation.observation_reference is None
        ):
            raise InvalidDeploymentAttemptBinding(
                "verification requires an available factual observation"
            )


@dataclass(frozen=True, slots=True)
class DeploymentVerificationResultV1:
    outcome: DeploymentVerificationOutcome
    verification_reference: VerificationReference | None = None
    reason_references: tuple[CapabilityReference, ...] = ()
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.verification_reference is not None and not isinstance(
            self.verification_reference, VerificationReference
        ):
            raise InvalidDeploymentAttemptBinding("verification reference has wrong type")
        if self.outcome is DeploymentVerificationOutcome.VERIFIED and not isinstance(
            self.verification_reference, VerificationReference
        ):
            raise InvalidDeploymentAttemptBinding(
                "verified result requires a typed verification reference"
            )
        object.__setattr__(
            self, "reason_references", _normalize_limitations(self.reason_references)
        )
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


def _validate_rollback_binding(
    rollback: DeploymentRollbackAttemptV1,
    target: DeploymentTargetV1,
    artifact: DeploymentArtifactRefV1,
) -> None:
    if (
        rollback.target_id != target.target_id
        or rollback.source_revision == rollback.intended_revision
        or artifact.fingerprint.value == ""
    ):
        raise InvalidRollbackProgression("rollback request binding mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentRollbackPreparationRequestV1:
    rollback: DeploymentRollbackAttemptV1
    target: DeploymentTargetV1
    rollback_artifact: DeploymentArtifactRefV1
    authorization_reference: AuthorizationReference
    policy_reference: PolicyReference

    def __post_init__(self) -> None:
        _validate_rollback_binding(self.rollback, self.target, self.rollback_artifact)
        if self.authorization_reference != self.rollback.authorization_reference:
            raise InvalidRollbackProgression("rollback authorization binding mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentRollbackPreparationResultV1:
    outcome: RollbackPreparationOutcome
    preparation_reference: PreparationReference | None = None
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.preparation_reference is not None and not isinstance(
            self.preparation_reference, PreparationReference
        ):
            raise InvalidRollbackProgression("rollback preparation reference has wrong type")
        if self.outcome is RollbackPreparationOutcome.PREPARED and not isinstance(
            self.preparation_reference, PreparationReference
        ):
            raise InvalidRollbackProgression("prepared rollback requires a preparation reference")
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentRollbackApplyRequestV1:
    rollback: DeploymentRollbackAttemptV1
    target: DeploymentTargetV1
    rollback_artifact: DeploymentArtifactRefV1
    preparation_reference: PreparationReference
    authorization_reference: AuthorizationReference
    idempotency_key: DeploymentIdempotencyKey
    semantic_fingerprint: DeploymentFingerprint
    fencing_reference: FencingReference | None = None

    def __post_init__(self) -> None:
        _validate_rollback_binding(self.rollback, self.target, self.rollback_artifact)
        if (
            not isinstance(self.preparation_reference, PreparationReference)
            or not isinstance(self.authorization_reference, AuthorizationReference)
            or not isinstance(self.idempotency_key, DeploymentIdempotencyKey)
            or not isinstance(self.semantic_fingerprint, DeploymentFingerprint)
            or (
                self.fencing_reference is not None
                and not isinstance(self.fencing_reference, FencingReference)
            )
        ):
            raise InvalidRollbackProgression("rollback apply reference type mismatch")
        if self.authorization_reference != self.rollback.authorization_reference:
            raise InvalidRollbackProgression("rollback authorization binding mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentRollbackApplyResultV1:
    outcome: RollbackApplyOutcome
    rollback_receipt_reference: RollbackReceiptReference | None = None
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.rollback_receipt_reference is not None and not isinstance(
            self.rollback_receipt_reference, RollbackReceiptReference
        ):
            raise InvalidRollbackProgression("rollback receipt has wrong type")
        if self.outcome is RollbackApplyOutcome.ROLLED_BACK and not isinstance(
            self.rollback_receipt_reference, RollbackReceiptReference
        ):
            raise InvalidRollbackProgression("rolled back result requires a rollback receipt")
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentRollbackObservationRequestV1:
    rollback: DeploymentRollbackAttemptV1
    target: DeploymentTargetV1

    def __post_init__(self) -> None:
        if self.rollback.target_id != self.target.target_id:
            raise InvalidRollbackProgression("rollback observation target mismatch")


@dataclass(frozen=True, slots=True)
class DeploymentRollbackObservationResultV1:
    outcome: RollbackObservationOutcome
    observation_reference: ObservationReference | None = None
    observed_revision: ObservedRevisionV1 | None = None
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.observation_reference is not None and not isinstance(
            self.observation_reference, ObservationReference
        ):
            raise InvalidRollbackProgression("rollback observation reference has wrong type")
        if self.outcome is RollbackObservationOutcome.OBSERVED and (
            self.observation_reference is None
            or self.observed_revision is None
            or self.observed_revision.observation != self.observation_reference
        ):
            raise InvalidRollbackProgression(
                "rollback observation requires corresponding revision facts"
            )
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@dataclass(frozen=True, slots=True)
class DeploymentRollbackVerificationRequestV1:
    rollback: DeploymentRollbackAttemptV1
    target: DeploymentTargetV1
    observation: DeploymentRollbackObservationResultV1
    verification_policy_reference: PolicyReference

    def __post_init__(self) -> None:
        if (
            self.rollback.target_id != self.target.target_id
            or self.observation.outcome is not RollbackObservationOutcome.OBSERVED
            or self.observation.observed_revision is None
            or self.observation.observed_revision.revision_id != self.rollback.intended_revision
        ):
            raise InvalidRollbackProgression(
                "rollback verification observation does not match intended revision"
            )


@dataclass(frozen=True, slots=True)
class DeploymentRollbackVerificationResultV1:
    outcome: RollbackVerificationOutcome
    verification_reference: VerificationReference | None = None
    reason_references: tuple[CapabilityReference, ...] = ()
    limitations: tuple[CapabilityReference, ...] = ()

    def __post_init__(self) -> None:
        if self.verification_reference is not None and not isinstance(
            self.verification_reference, VerificationReference
        ):
            raise InvalidRollbackProgression("rollback verification reference has wrong type")
        if self.outcome is RollbackVerificationOutcome.VERIFIED and not isinstance(
            self.verification_reference, VerificationReference
        ):
            raise InvalidRollbackProgression("verified rollback requires a verification reference")
        object.__setattr__(
            self, "reason_references", _normalize_limitations(self.reason_references)
        )
        object.__setattr__(self, "limitations", _normalize_limitations(self.limitations))


@runtime_checkable
class DeploymentArtifactFactsPort(Protocol):
    def artifact_facts(
        self, request: DeploymentArtifactFactsRequestV1
    ) -> DeploymentArtifactFactsResultV1: ...


@runtime_checkable
class DeploymentAuthorizationPort(Protocol):
    def authorize(
        self, request: DeploymentAuthorizationRequestV1
    ) -> DeploymentAuthorizationResultV1: ...


@runtime_checkable
class DeploymentPreparationPort(Protocol):
    def prepare(self, request: DeploymentPreparationRequestV1) -> DeploymentPreparationResultV1: ...


@runtime_checkable
class DeploymentApplyPort(Protocol):
    def apply(self, request: DeploymentApplyRequestV1) -> DeploymentApplyResultV1: ...


@runtime_checkable
class DeploymentObservationPort(Protocol):
    def observe(self, request: DeploymentObservationRequestV1) -> DeploymentObservationResultV1: ...


@runtime_checkable
class DeploymentVerificationPort(Protocol):
    def verify(
        self, request: DeploymentVerificationRequestV1
    ) -> DeploymentVerificationResultV1: ...


@runtime_checkable
class DeploymentRollbackPreparationPort(Protocol):
    def prepare_rollback(
        self, request: DeploymentRollbackPreparationRequestV1
    ) -> DeploymentRollbackPreparationResultV1: ...


@runtime_checkable
class DeploymentRollbackApplyPort(Protocol):
    def apply_rollback(
        self, request: DeploymentRollbackApplyRequestV1
    ) -> DeploymentRollbackApplyResultV1: ...


@runtime_checkable
class DeploymentRollbackObservationPort(Protocol):
    def observe_rollback(
        self, request: DeploymentRollbackObservationRequestV1
    ) -> DeploymentRollbackObservationResultV1: ...


@runtime_checkable
class DeploymentRollbackVerificationPort(Protocol):
    def verify_rollback(
        self, request: DeploymentRollbackVerificationRequestV1
    ) -> DeploymentRollbackVerificationResultV1: ...
