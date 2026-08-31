from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillSemanticReference
from synapse.skills.phase3_records import (
    SkillActivationRecord,
    SkillLifecycleReason,
    SkillLifecycleRecord,
    SkillRevocationRecord,
)
from synapse.skills.phase3_values import SkillStoreRecordId, validate_store_timestamp
from synapse.skills.phase6_errors import (
    InvalidSkillLifecycleRequest,
    MissingLifecycleDecisionReference,
)


class SkillActivationState(StrEnum):
    NEVER_ACTIVATED = "never_activated"
    ACTIVE = "active"
    INACTIVE = "inactive"


class SkillSelectionState(StrEnum):
    ELIGIBLE = "eligible"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class SkillLifecycleOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"


class SkillActivationParentVerificationPort(Protocol):
    """Verifies correspondence without exposing installation storage or payload."""

    def is_valid_parent(
        self,
        identity: PublishedSkillVersionId,
        installation_id: SkillStoreRecordId,
    ) -> bool: ...


@dataclass(frozen=True)
class SkillLifecycleProjection:
    identity: PublishedSkillVersionId
    activation_state: SkillActivationState
    selection_state: SkillSelectionState
    deprecated: bool
    revoked: bool
    superseded: bool
    resolvable: bool
    activatable: bool
    active: bool
    active_selection_eligible: bool
    active_installation_id: SkillStoreRecordId | None
    superseded_by: PublishedSkillVersionId | None
    rollback_target: PublishedSkillVersionId | None
    rollback_decision_ref: SkillSemanticReference | None
    last_record_id: SkillStoreRecordId | None


LifecycleEventRecord = (
    SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord
)


@dataclass(frozen=True)
class SkillLifecycleResult:
    identity: PublishedSkillVersionId
    record: LifecycleEventRecord
    outcome: SkillLifecycleOutcome
    projection: SkillLifecycleProjection


@dataclass(frozen=True, kw_only=True)
class _BaseRequest:
    identity: PublishedSkillVersionId
    actor_ref: SkillSemanticReference
    reason: SkillLifecycleReason
    occurred_at: datetime
    event_ref: SkillSemanticReference

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, PublishedSkillVersionId)
            or not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.reason, SkillLifecycleReason)
            or not isinstance(self.event_ref, SkillSemanticReference)
        ):
            raise InvalidSkillLifecycleRequest()
        try:
            validate_store_timestamp(self.occurred_at)
        except (TypeError, ValueError, RuntimeError) as exc:
            raise InvalidSkillLifecycleRequest() from exc


@dataclass(frozen=True, kw_only=True)
class DeactivateSkillVersionRequest(_BaseRequest):
    pass


@dataclass(frozen=True, kw_only=True)
class DeprecateSkillVersionRequest(_BaseRequest):
    pass


@dataclass(frozen=True, kw_only=True)
class ReenableSkillVersionRequest(_BaseRequest):
    pass


@dataclass(frozen=True, kw_only=True)
class SupersedeSkillVersionRequest(_BaseRequest):
    replacement: PublishedSkillVersionId
    decision_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.replacement, PublishedSkillVersionId) or (
            self.decision_ref is not None
            and not isinstance(self.decision_ref, SkillSemanticReference)
        ):
            raise InvalidSkillLifecycleRequest()


@dataclass(frozen=True, kw_only=True)
class RollbackSkillVersionRequest(_BaseRequest):
    target: PublishedSkillVersionId
    decision_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.target, PublishedSkillVersionId):
            raise InvalidSkillLifecycleRequest()
        if not isinstance(self.decision_ref, SkillSemanticReference):
            raise MissingLifecycleDecisionReference()


@dataclass(frozen=True, kw_only=True)
class RevokeSkillVersionRequest(_BaseRequest):
    decision_ref: SkillSemanticReference | None = None
    evidence_ref: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.decision_ref, SkillSemanticReference):
            raise MissingLifecycleDecisionReference()
        if self.evidence_ref is not None and not isinstance(
            self.evidence_ref, SkillSemanticReference
        ):
            raise InvalidSkillLifecycleRequest()
