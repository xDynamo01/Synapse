from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillSemanticReference,
)
from synapse.skills.phase3_records import (
    SkillActivationRecord,
    SkillInstallationRecord,
    SkillInstallationTerminationReason,
    SkillInstallationTerminationRecord,
    SkillLifecycleReason,
    SkillLifecycleRecord,
)
from synapse.skills.phase3_values import SkillStoreRecordId, validate_store_timestamp
from synapse.skills.phase4_models import VerifiedSkillContentSnapshot
from synapse.skills.phase6_models import SkillLifecycleOutcome, SkillLifecycleProjection
from synapse.skills.phase7_errors import InvalidSkillInstallationRequest


class SkillInstallationOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True)
class InstalledSkillContentRef:
    """Registered address metadata; it does not prove physical content custody."""

    content_ref: SkillSemanticReference
    content_fingerprint: SkillContentFingerprint
    storage_profile_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        if (
            not isinstance(self.content_ref, SkillSemanticReference)
            or not isinstance(self.content_fingerprint, SkillContentFingerprint)
            or not isinstance(self.storage_profile_ref, SkillSemanticReference)
            or not self.content_ref.value.startswith("content:")
            or not self.storage_profile_ref.value.startswith("storage-profile:")
        ):
            raise InvalidSkillInstallationRequest()


@dataclass(frozen=True, kw_only=True)
class InstallVerifiedSkillVersionRequest:
    identity: PublishedSkillVersionId
    snapshot: VerifiedSkillContentSnapshot
    local_content: InstalledSkillContentRef
    actor_ref: SkillSemanticReference
    registration_ref: SkillSemanticReference
    idempotency_ref: SkillSemanticReference
    installed_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.snapshot, VerifiedSkillContentSnapshot)
            or not isinstance(self.local_content, InstalledSkillContentRef)
            or not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.registration_ref, SkillSemanticReference)
            or not self.registration_ref.value.startswith("registration:")
            or not isinstance(self.idempotency_ref, SkillSemanticReference)
        ):
            raise InvalidSkillInstallationRequest()
        _validate_time(self.installed_at)


@dataclass(frozen=True, kw_only=True)
class TerminateSkillInstallationRequest:
    identity: PublishedSkillVersionId
    installation_id: SkillStoreRecordId
    reason: SkillInstallationTerminationReason
    actor_ref: SkillSemanticReference
    event_ref: SkillSemanticReference
    idempotency_ref: SkillSemanticReference
    occurred_at: datetime
    replacement_installation_id: SkillStoreRecordId | None = None
    integrity_observation_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.installation_id, SkillStoreRecordId)
            or not self.installation_id.value.startswith("installation:")
            or not isinstance(self.reason, SkillInstallationTerminationReason)
            or not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.event_ref, SkillSemanticReference)
            or not isinstance(self.idempotency_ref, SkillSemanticReference)
            or (
                self.replacement_installation_id is not None
                and not isinstance(self.replacement_installation_id, SkillStoreRecordId)
            )
            or (
                self.integrity_observation_ref is not None
                and (
                    not isinstance(
                        self.integrity_observation_ref, SkillSemanticReference
                    )
                    or not self.integrity_observation_ref.value.startswith(
                        "integrity-observation:"
                    )
                )
            )
        ):
            raise InvalidSkillInstallationRequest()
        replaced = self.reason is SkillInstallationTerminationReason.REPLACED
        if replaced != (self.replacement_installation_id is not None):
            raise InvalidSkillInstallationRequest()
        corrupted = self.reason is SkillInstallationTerminationReason.CORRUPTED
        if corrupted != (self.integrity_observation_ref is not None):
            raise InvalidSkillInstallationRequest()
        _validate_time(self.occurred_at)


@dataclass(frozen=True, kw_only=True)
class ActivateInstalledSkillVersionRequest:
    identity: PublishedSkillVersionId
    installation_id: SkillStoreRecordId
    actor_ref: SkillSemanticReference
    reason: SkillLifecycleReason
    idempotency_ref: SkillSemanticReference
    occurred_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.installation_id, SkillStoreRecordId)
            or not self.installation_id.value.startswith("installation:")
            or not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.reason, SkillLifecycleReason)
            or not isinstance(self.idempotency_ref, SkillSemanticReference)
        ):
            raise InvalidSkillInstallationRequest()
        _validate_time(self.occurred_at)


@dataclass(frozen=True, kw_only=True)
class DeactivateInstalledSkillVersionRequest:
    identity: PublishedSkillVersionId
    actor_ref: SkillSemanticReference
    reason: SkillLifecycleReason
    deactivation_ref: SkillSemanticReference
    idempotency_ref: SkillSemanticReference
    occurred_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.reason, SkillLifecycleReason)
            or not isinstance(self.deactivation_ref, SkillSemanticReference)
            or not isinstance(self.idempotency_ref, SkillSemanticReference)
        ):
            raise InvalidSkillInstallationRequest()
        _validate_time(self.occurred_at)


InstallationFact = SkillInstallationRecord | SkillInstallationTerminationRecord


@dataclass(frozen=True)
class SkillInstallationProjection:
    """Projection of registration facts, with no physical-availability assertion."""

    identity: PublishedSkillVersionId
    installations: tuple[SkillInstallationRecord, ...]
    current_registrations: tuple[SkillInstallationRecord, ...]
    terminations: tuple[SkillInstallationTerminationRecord, ...]
    terminated_installation_ids: tuple[SkillStoreRecordId, ...]
    corrupted_installation_ids: tuple[SkillStoreRecordId, ...]
    has_current_registration: bool
    last_fact: InstallationFact | None
    complete: bool


@dataclass(frozen=True)
class SkillOperationalProjection:
    """Combined lifecycle/registration facts; this is not execution state."""

    identity: PublishedSkillVersionId
    installation: SkillInstallationProjection
    lifecycle: SkillLifecycleProjection
    has_current_registration: bool
    activation_eligible: bool
    operationally_active: bool


@dataclass(frozen=True)
class SkillInstallationResult:
    identity: PublishedSkillVersionId
    record: SkillInstallationRecord
    outcome: SkillInstallationOutcome
    projection: SkillInstallationProjection


@dataclass(frozen=True)
class SkillInstallationTerminationResult:
    identity: PublishedSkillVersionId
    record: SkillInstallationTerminationRecord
    outcome: SkillInstallationOutcome
    projection: SkillInstallationProjection


OperationalRecord = SkillActivationRecord | SkillLifecycleRecord


@dataclass(frozen=True)
class SkillActivationResult:
    identity: PublishedSkillVersionId
    record: OperationalRecord
    outcome: SkillLifecycleOutcome
    projection: SkillOperationalProjection


def _validate_time(value: datetime) -> None:
    try:
        validate_store_timestamp(value)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise InvalidSkillInstallationRequest() from exc
