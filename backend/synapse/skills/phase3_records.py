from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.skills.phase2_models import (
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillPublicationScope,
    SkillSemanticReference,
)
from synapse.skills.phase3_errors import InvalidSkillStoreRecord
from synapse.skills.phase3_values import (
    SkillStoreRecordFingerprint,
    SkillStoreRecordId,
    validate_store_timestamp,
)


class SkillLifecycleKind(StrEnum):
    DEACTIVATED = "deactivated"
    DEPRECATED = "deprecated"
    REENABLED = "reenabled"
    SUPERSEDED = "superseded"
    ROLLBACK_REFERENCED = "rollback_referenced"


class SkillLifecycleReason(StrEnum):
    POLICY = "policy"
    SECURITY = "security"
    QUALITY = "quality"
    REPLACED = "replaced"
    OPERATOR = "operator"


class SkillInstallationTerminationReason(StrEnum):
    DETACHED = "detached"
    UNINSTALLED = "uninstalled"
    REPLACED = "replaced"
    CORRUPTED = "corrupted"


class SkillAssignmentTerminationReason(StrEnum):
    REVOKED = "revoked"
    REPLACED = "replaced"
    EXPIRED = "expired"


class SkillLeaseTerminationReason(StrEnum):
    EXPIRED = "expired"
    TERMINATED = "terminated"
    SUPERSEDED = "superseded"


def _validate_header(
    record_id: SkillStoreRecordId,
    occurred_at: datetime,
    actor_ref: SkillSemanticReference,
) -> None:
    if (
        not isinstance(record_id, SkillStoreRecordId)
        or not isinstance(actor_ref, SkillSemanticReference)
    ):
        raise InvalidSkillStoreRecord("skill store record header is invalid")
    validate_store_timestamp(occurred_at)


def _validate_namespace(record_id: SkillStoreRecordId, namespace: str) -> None:
    if not record_id.value.startswith(f"{namespace}:"):
        raise InvalidSkillStoreRecord("skill store record namespace is invalid")


@dataclass(frozen=True)
class PublishedSkillVersionRecord:
    identity: PublishedSkillVersionId
    manifest: PublishedSkillManifest
    recorded_at: datetime
    actor_ref: SkillSemanticReference
    publication_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        validate_store_timestamp(self.recorded_at)
        if (
            not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.publication_ref, SkillSemanticReference)
        ):
            raise InvalidSkillStoreRecord("published skill version record is invalid")
        if not isinstance(self.identity, PublishedSkillVersionId) or not isinstance(
            self.manifest, PublishedSkillManifest
        ):
            raise InvalidSkillStoreRecord("published skill version record is invalid")
        try:
            self.identity.assert_manifest(self.manifest)
        except ValueError as exc:
            raise InvalidSkillStoreRecord(
                "published skill version record is invalid"
            ) from exc

@dataclass(frozen=True)
class SkillLifecycleRecord:
    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    kind: SkillLifecycleKind
    reason: SkillLifecycleReason
    occurred_at: datetime
    actor_ref: SkillSemanticReference
    related_version: PublishedSkillVersionId | None = None
    decision_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.occurred_at, self.actor_ref)
        _validate_namespace(self.record_id, "lifecycle")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.kind, SkillLifecycleKind)
            or not isinstance(self.reason, SkillLifecycleReason)
            or (
                self.related_version is not None
                and not isinstance(self.related_version, PublishedSkillVersionId)
            )
            or (
                self.decision_ref is not None
                and not isinstance(self.decision_ref, SkillSemanticReference)
            )
        ):
            raise InvalidSkillStoreRecord("skill lifecycle record is invalid")
        needs_related = self.kind in {
            SkillLifecycleKind.SUPERSEDED,
            SkillLifecycleKind.ROLLBACK_REFERENCED,
        }
        if needs_related != (self.related_version is not None):
            raise InvalidSkillStoreRecord("skill lifecycle relation is invalid")
        if (
            self.kind is SkillLifecycleKind.ROLLBACK_REFERENCED
            and self.decision_ref is None
        ):
            raise InvalidSkillStoreRecord("skill lifecycle decision is invalid")
        if (
            self.kind
            not in {
                SkillLifecycleKind.SUPERSEDED,
                SkillLifecycleKind.ROLLBACK_REFERENCED,
            }
            and self.decision_ref is not None
        ):
            raise InvalidSkillStoreRecord("skill lifecycle decision is invalid")


@dataclass(frozen=True)
class SkillActivationRecord:
    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    installation_id: SkillStoreRecordId
    activated_at: datetime
    actor_ref: SkillSemanticReference
    reason: SkillLifecycleReason

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.activated_at, self.actor_ref)
        _validate_namespace(self.record_id, "activation")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.installation_id, SkillStoreRecordId)
            or not isinstance(self.reason, SkillLifecycleReason)
        ):
            raise InvalidSkillStoreRecord("skill activation record is invalid")
        _validate_namespace(self.installation_id, "installation")


@dataclass(frozen=True)
class SkillRevocationRecord:
    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    revoked_at: datetime
    actor_ref: SkillSemanticReference
    reason: SkillLifecycleReason
    revocation_ref: SkillSemanticReference
    evidence_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.revoked_at, self.actor_ref)
        _validate_namespace(self.record_id, "revocation")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.reason, SkillLifecycleReason)
            or not isinstance(self.revocation_ref, SkillSemanticReference)
            or (
                self.evidence_ref is not None
                and not isinstance(self.evidence_ref, SkillSemanticReference)
            )
        ):
            raise InvalidSkillStoreRecord("skill revocation record is invalid")


@dataclass(frozen=True)
class SkillInstallationRecord:
    """Immutable registration fact; it does not attest that bytes exist."""

    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    content_fingerprint: SkillContentFingerprint
    content_ref: SkillSemanticReference
    storage_profile_ref: SkillSemanticReference
    installed_at: datetime
    actor_ref: SkillSemanticReference
    registration_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.installed_at, self.actor_ref)
        _validate_namespace(self.record_id, "installation")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.content_fingerprint, SkillContentFingerprint)
            or not isinstance(self.content_ref, SkillSemanticReference)
            or not isinstance(self.storage_profile_ref, SkillSemanticReference)
            or not isinstance(self.registration_ref, SkillSemanticReference)
            or not self.content_ref.value.startswith("content:")
            or not self.storage_profile_ref.value.startswith("storage-profile:")
            or not self.registration_ref.value.startswith("registration:")
            or self.content_fingerprint != self.identity.content_fingerprint
        ):
            raise InvalidSkillStoreRecord("skill installation record is invalid")


@dataclass(frozen=True)
class SkillInstallationTerminationRecord:
    """Terminal registration fact, not a physical deletion or damage report."""

    record_id: SkillStoreRecordId
    installation_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    terminated_at: datetime
    actor_ref: SkillSemanticReference
    reason: SkillInstallationTerminationReason
    replacement_installation_id: SkillStoreRecordId | None = None
    integrity_observation_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.terminated_at, self.actor_ref)
        _validate_namespace(self.record_id, "installation-end")
        if (
            not isinstance(self.installation_id, SkillStoreRecordId)
            or not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.reason, SkillInstallationTerminationReason)
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
            raise InvalidSkillStoreRecord(
                "skill installation termination record is invalid"
            )
        _validate_namespace(self.installation_id, "installation")
        if self.replacement_installation_id is not None:
            _validate_namespace(self.replacement_installation_id, "installation")
        replaced = self.reason is SkillInstallationTerminationReason.REPLACED
        if replaced != (self.replacement_installation_id is not None):
            raise InvalidSkillStoreRecord(
                "skill installation replacement is invalid"
            )
        corrupted = self.reason is SkillInstallationTerminationReason.CORRUPTED
        if corrupted != (self.integrity_observation_ref is not None):
            raise InvalidSkillStoreRecord(
                "skill installation integrity observation is invalid"
            )


@dataclass(frozen=True)
class SkillAssignmentRecord:
    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    subject_ref: SkillSemanticReference
    scope: SkillPublicationScope
    assigned_at: datetime
    actor_ref: SkillSemanticReference
    reason_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.assigned_at, self.actor_ref)
        _validate_namespace(self.record_id, "assignment")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.subject_ref, SkillSemanticReference)
            or not isinstance(self.scope, SkillPublicationScope)
            or not isinstance(self.reason_ref, SkillSemanticReference)
        ):
            raise InvalidSkillStoreRecord("skill assignment record is invalid")


@dataclass(frozen=True)
class SkillAssignmentTerminationRecord:
    record_id: SkillStoreRecordId
    assignment_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    terminated_at: datetime
    actor_ref: SkillSemanticReference
    reason: SkillAssignmentTerminationReason
    replacement_assignment_id: SkillStoreRecordId | None = None

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.terminated_at, self.actor_ref)
        _validate_namespace(self.record_id, "assignment-end")
        if (
            not isinstance(self.assignment_id, SkillStoreRecordId)
            or not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.reason, SkillAssignmentTerminationReason)
            or (
                self.replacement_assignment_id is not None
                and not isinstance(self.replacement_assignment_id, SkillStoreRecordId)
            )
        ):
            raise InvalidSkillStoreRecord(
                "skill assignment termination record is invalid"
            )
        _validate_namespace(self.assignment_id, "assignment")
        if self.replacement_assignment_id is not None:
            _validate_namespace(self.replacement_assignment_id, "assignment")
        replacement = self.reason is SkillAssignmentTerminationReason.REPLACED
        if replacement != (self.replacement_assignment_id is not None):
            raise InvalidSkillStoreRecord("skill assignment replacement is invalid")


@dataclass(frozen=True)
class SkillLeaseRecord:
    record_id: SkillStoreRecordId
    assignment_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    agent_ref: SkillSemanticReference
    task_ref: SkillSemanticReference
    granted_at: datetime
    expires_at: datetime
    actor_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.granted_at, self.actor_ref)
        _validate_namespace(self.record_id, "lease")
        validate_store_timestamp(self.expires_at)
        if (
            not isinstance(self.assignment_id, SkillStoreRecordId)
            or not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.agent_ref, SkillSemanticReference)
            or not isinstance(self.task_ref, SkillSemanticReference)
            or self.expires_at <= self.granted_at
        ):
            raise InvalidSkillStoreRecord("skill lease record is invalid")
        _validate_namespace(self.assignment_id, "assignment")


@dataclass(frozen=True)
class SkillLeaseTerminationRecord:
    record_id: SkillStoreRecordId
    lease_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    terminated_at: datetime
    actor_ref: SkillSemanticReference
    reason: SkillLeaseTerminationReason
    replacement_lease_id: SkillStoreRecordId | None = None

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.terminated_at, self.actor_ref)
        _validate_namespace(self.record_id, "lease-end")
        if (
            not isinstance(self.lease_id, SkillStoreRecordId)
            or not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.reason, SkillLeaseTerminationReason)
            or (
                self.replacement_lease_id is not None
                and not isinstance(self.replacement_lease_id, SkillStoreRecordId)
            )
        ):
            raise InvalidSkillStoreRecord("skill lease termination record is invalid")
        _validate_namespace(self.lease_id, "lease")
        if self.replacement_lease_id is not None:
            _validate_namespace(self.replacement_lease_id, "lease")
        superseded = self.reason is SkillLeaseTerminationReason.SUPERSEDED
        if superseded != (self.replacement_lease_id is not None):
            raise InvalidSkillStoreRecord("skill lease supersession is invalid")


@dataclass(frozen=True)
class SkillGovernanceBindingRecord:
    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    governance_ref: SkillSemanticReference
    decision_fingerprint: SkillStoreRecordFingerprint
    bound_at: datetime
    actor_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.bound_at, self.actor_ref)
        _validate_namespace(self.record_id, "governance-binding")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.governance_ref, SkillSemanticReference)
            or not isinstance(self.decision_fingerprint, SkillStoreRecordFingerprint)
        ):
            raise InvalidSkillStoreRecord("skill governance binding record is invalid")


@dataclass(frozen=True)
class SkillEvaluationBindingRecord:
    record_id: SkillStoreRecordId
    identity: PublishedSkillVersionId
    evaluation_ref: SkillSemanticReference
    result_fingerprint: SkillStoreRecordFingerprint
    bound_at: datetime
    actor_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        _validate_header(self.record_id, self.bound_at, self.actor_ref)
        _validate_namespace(self.record_id, "evaluation-binding")
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.evaluation_ref, SkillSemanticReference)
            or not isinstance(self.result_fingerprint, SkillStoreRecordFingerprint)
        ):
            raise InvalidSkillStoreRecord("skill evaluation binding record is invalid")
