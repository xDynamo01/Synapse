"""Independent factual observation and verification for a local target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from .canonical import content_fingerprint
from .identities import (
    DeploymentFingerprint,
    ObservationReference,
    PolicyReference,
    RevisionId,
    VerificationReference,
)
from .models import ObservedRevisionV1


class LocalObservationOutcome(StrEnum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"
    INCONSISTENT = "inconsistent"


class LocalVerificationOutcome(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


class LocalProcessState(StrEnum):
    RUNNING = "running"
    ABSENT = "absent"
    UNAVAILABLE = "unavailable"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class LocalProcessObservationFactV1:
    state: LocalProcessState
    process_reference: str | None = None
    containment_confirmed: bool | None = None
    limitations: tuple[str, ...] = ()


class LocalProcessObservationPort(Protocol):
    def observe(self, execution_reference: str | None) -> LocalProcessObservationFactV1: ...


@dataclass(frozen=True, slots=True)
class LocalObservationRequestV1:
    release_reference: str
    attempt_reference: str
    target_reference: str
    environment_reference: str
    desired_revision: RevisionId
    desired_revision_fingerprint: DeploymentFingerprint
    sandbox_execution_reference: str | None = None
    slot_reference: str | None = None
    evidence_policy_reference: PolicyReference | None = None


@dataclass(frozen=True, slots=True)
class LocalTargetFactsV1:
    active_revision: RevisionId | None
    revision_fingerprint: DeploymentFingerprint | None
    target_reference: str | None
    environment_reference: str | None
    slot_reference: str | None
    active_state_fingerprint: DeploymentFingerprint | None
    runtime: LocalProcessObservationFactV1


@dataclass(frozen=True, slots=True)
class LocalObservationV1:
    outcome: LocalObservationOutcome
    observation_reference: ObservationReference | None
    release_reference: str
    attempt_reference: str
    target_reference: str
    environment_reference: str
    observed_at: datetime
    facts: LocalTargetFactsV1 | None
    observed_revision: ObservedRevisionV1 | None
    limitations: tuple[str, ...]
    semantic_fingerprint: DeploymentFingerprint
    evidence_policy_reference: PolicyReference | None = None


@dataclass(frozen=True, slots=True)
class LocalVerificationPolicyV1:
    policy_reference: PolicyReference
    active_revision_required: bool = True
    revision_fingerprint_required: bool = True
    process_running_required: bool = False
    containment_required: bool = False
    max_observation_age_seconds: int = 60

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_observation_age_seconds, bool)
            or self.max_observation_age_seconds < 0
        ):
            raise ValueError("observation age policy must be non-negative")


@dataclass(frozen=True, slots=True)
class LocalVerificationRequestV1:
    release_reference: str
    attempt_reference: str
    target_reference: str
    environment_reference: str
    desired_revision: RevisionId
    desired_revision_fingerprint: DeploymentFingerprint
    slot_reference: str | None
    observation: LocalObservationV1
    policy: LocalVerificationPolicyV1
    current_target_fingerprint: DeploymentFingerprint | None
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class LocalVerificationResultV1:
    outcome: LocalVerificationOutcome
    verification_reference: VerificationReference | None
    observation_reference: ObservationReference | None
    release_reference: str
    attempt_reference: str
    target_reference: str
    environment_reference: str
    policy_reference: PolicyReference
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    semantic_fingerprint: DeploymentFingerprint


class LocalDeploymentVerifier:
    """Compare desired state with an independently captured observation."""

    def verify(self, request: LocalVerificationRequestV1) -> LocalVerificationResultV1:
        observation = request.observation
        reasons: list[str] = []
        limitations = list(observation.limitations)
        outcome = LocalVerificationOutcome.INDETERMINATE
        if (
            observation.target_reference != request.target_reference
            or observation.environment_reference != request.environment_reference
            or observation.release_reference != request.release_reference
            or observation.attempt_reference != request.attempt_reference
            or observation.evidence_policy_reference != request.policy.policy_reference
        ):
            reasons.append("observation-binding-mismatch")
        elif observation.outcome is LocalObservationOutcome.UNAVAILABLE:
            outcome = LocalVerificationOutcome.UNAVAILABLE
            reasons.append("observation-unavailable")
        elif observation.outcome in {
            LocalObservationOutcome.INDETERMINATE,
            LocalObservationOutcome.INCONSISTENT,
        }:
            reasons.append(f"observation-{observation.outcome.value}")
        elif request.verified_at.tzinfo is None or observation.observed_at.tzinfo is None:
            reasons.append("observation-time-invalid")
        elif (request.verified_at - observation.observed_at).total_seconds() < 0:
            reasons.append("observation-time-in-future")
        elif (request.verified_at - observation.observed_at).total_seconds() > request.policy.max_observation_age_seconds:
            reasons.append("observation-stale")
        elif observation.facts is None:
            reasons.append("observation-facts-missing")
        elif request.current_target_fingerprint != observation.facts.active_state_fingerprint:
            reasons.append("target-changed-after-observation")
        else:
            facts = observation.facts
            mismatches: list[str] = []
            missing: list[str] = []
            if facts.target_reference != request.target_reference:
                mismatches.append("target-mismatch")
            if facts.environment_reference != request.environment_reference:
                mismatches.append("environment-mismatch")
            if facts.slot_reference != request.slot_reference:
                mismatches.append("slot-mismatch")
            if facts.active_revision is not None and facts.active_revision != request.desired_revision:
                mismatches.append("revision-mismatch")
            elif request.policy.active_revision_required and facts.active_revision is None:
                missing.append("active-revision-unavailable")
            if (
                facts.revision_fingerprint is not None
                and facts.revision_fingerprint != request.desired_revision_fingerprint
            ):
                mismatches.append("revision-fingerprint-mismatch")
            elif request.policy.revision_fingerprint_required and facts.revision_fingerprint is None:
                missing.append("revision-fingerprint-unavailable")
            if request.policy.process_running_required:
                if facts.runtime.state is LocalProcessState.ABSENT:
                    mismatches.append("process-absent")
                elif facts.runtime.state is not LocalProcessState.RUNNING:
                    missing.append("process-state-unavailable")
            if request.policy.containment_required:
                if facts.runtime.containment_confirmed is False:
                    mismatches.append("containment-mismatch")
                elif facts.runtime.containment_confirmed is not True:
                    missing.append("containment-unavailable")
            if mismatches:
                outcome, reasons = LocalVerificationOutcome.FAILED, mismatches
            elif missing:
                outcome, reasons = LocalVerificationOutcome.UNAVAILABLE, missing
            else:
                outcome = LocalVerificationOutcome.VERIFIED
                reasons.append("required-facts-correspond")
        semantic = DeploymentFingerprint(content_fingerprint((
            request.release_reference, request.attempt_reference, request.target_reference,
            request.environment_reference, request.desired_revision,
            request.desired_revision_fingerprint, request.slot_reference,
            observation.semantic_fingerprint,
            request.policy, outcome, tuple(reasons), tuple(limitations),
        )))
        reference = VerificationReference(f"verification:local-{semantic.value[7:39]}")
        return LocalVerificationResultV1(
            outcome, reference, observation.observation_reference,
            request.release_reference, request.attempt_reference,
            request.target_reference, request.environment_reference,
            request.policy.policy_reference, tuple(reasons), tuple(limitations), semantic,
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
