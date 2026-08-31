from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillSemanticReference
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import validate_store_timestamp
from synapse.skills.phase4_models import VerifiedSkillContentSnapshot
from synapse.skills.phase5_errors import InvalidSkillPublicationRequest


@dataclass(frozen=True)
class PublishVerifiedSkillVersionRequest:
    snapshot: VerifiedSkillContentSnapshot
    actor_ref: SkillSemanticReference
    publication_ref: SkillSemanticReference
    idempotency_ref: SkillSemanticReference
    published_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.snapshot, VerifiedSkillContentSnapshot)
            or not isinstance(self.actor_ref, SkillSemanticReference)
            or not isinstance(self.publication_ref, SkillSemanticReference)
            or not isinstance(self.idempotency_ref, SkillSemanticReference)
        ):
            raise InvalidSkillPublicationRequest()
        try:
            validate_store_timestamp(self.published_at)
        except ValueError:
            raise InvalidSkillPublicationRequest() from None


class SkillPublicationOutcome(StrEnum):
    CREATED = "created"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True)
class SkillPublicationResult:
    record: PublishedSkillVersionRecord
    identity: PublishedSkillVersionId
    outcome: SkillPublicationOutcome

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, PublishedSkillVersionRecord)
            or not isinstance(self.identity, PublishedSkillVersionId)
            or self.record.identity != self.identity
            or not isinstance(self.outcome, SkillPublicationOutcome)
        ):
            raise InvalidSkillPublicationRequest()
