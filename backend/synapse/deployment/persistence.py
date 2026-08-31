"""Pure append-only journal contracts and deterministic Deployment replay."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias, runtime_checkable

from .errors import DeploymentReplayFailed
from .identities import DeploymentEventId, DeploymentFingerprint
from .state_machines import (
    DeploymentStateProjection,
    DeploymentTransitionEventV1,
    PromotionStateProjection,
    PromotionTransitionEventV1,
    RollbackStateProjection,
    RollbackTransitionEventV1,
    RolloutStateProjection,
    RolloutTransitionEventV1,
)

DEPLOYMENT_JOURNAL_SCHEMA_VERSION = 1
DEPLOYMENT_JOURNAL_FORMAT_V1 = "deployment-journal-json-v1"

DeploymentJournalEvent: TypeAlias = (
    DeploymentTransitionEventV1
    | RolloutTransitionEventV1
    | PromotionTransitionEventV1
    | RollbackTransitionEventV1
)
DeploymentProjection: TypeAlias = (
    DeploymentStateProjection
    | RolloutStateProjection
    | PromotionStateProjection
    | RollbackStateProjection
)


class DeploymentMachineKind(StrEnum):
    DEPLOYMENT = "deployment"
    ROLLOUT = "rollout"
    PROMOTION = "promotion"
    ROLLBACK = "rollback"


class DeploymentAppendDisposition(StrEnum):
    APPENDED = "appended"
    IDEMPOTENT = "idempotent"


@dataclass(frozen=True, slots=True, order=True)
class DeploymentMachineKey:
    kind: DeploymentMachineKind
    identity: str

    def __post_init__(self) -> None:
        prefixes = {
            DeploymentMachineKind.DEPLOYMENT: "deployment-attempt:",
            DeploymentMachineKind.ROLLOUT: "deployment-rollout:",
            DeploymentMachineKind.PROMOTION: "deployment-promotion:",
            DeploymentMachineKind.ROLLBACK: "deployment-rollback-attempt:",
        }
        if (
            not isinstance(self.identity, str)
            or not self.identity.startswith(prefixes[self.kind])
            or len(self.identity) > 256
        ):
            raise ValueError("deployment machine identity does not match machine kind")


def machine_key_for(event: DeploymentJournalEvent) -> DeploymentMachineKey:
    if isinstance(event, DeploymentTransitionEventV1):
        return DeploymentMachineKey(DeploymentMachineKind.DEPLOYMENT, event.attempt_id.value)
    if isinstance(event, RolloutTransitionEventV1):
        return DeploymentMachineKey(DeploymentMachineKind.ROLLOUT, event.rollout_id.value)
    if isinstance(event, PromotionTransitionEventV1):
        return DeploymentMachineKey(DeploymentMachineKind.PROMOTION, event.promotion_id.value)
    return DeploymentMachineKey(DeploymentMachineKind.ROLLBACK, event.rollback_attempt_id.value)


@dataclass(frozen=True, slots=True)
class DeploymentJournalAppendRequest:
    machine: DeploymentMachineKey
    sequence: int
    event: DeploymentJournalEvent

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
            or machine_key_for(self.event) != self.machine
        ):
            raise ValueError("deployment journal append binding is invalid")


@dataclass(frozen=True, slots=True)
class DeploymentJournalRecord:
    machine: DeploymentMachineKey
    sequence: int
    event_id: DeploymentEventId
    event_fingerprint: DeploymentFingerprint
    event: DeploymentJournalEvent
    canonical_payload: str
    payload_checksum: str
    schema_version: int = DEPLOYMENT_JOURNAL_SCHEMA_VERSION
    record_format: str = DEPLOYMENT_JOURNAL_FORMAT_V1


@dataclass(frozen=True, slots=True)
class DeploymentAppendResult:
    disposition: DeploymentAppendDisposition
    record: DeploymentJournalRecord


@dataclass(frozen=True, slots=True)
class DeploymentJournalIntegrity:
    store_available: bool
    schema_compatible: bool
    append_integrity: bool
    replay_available: bool
    corruption_detected: bool
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeploymentPersistenceHealth:
    store_available: bool
    schema_compatible: bool
    append_integrity: bool
    replay_available: bool
    corruption_detected: bool


def replay_deployment_history(
    machine: DeploymentMachineKey, records: tuple[DeploymentJournalRecord, ...]
) -> DeploymentProjection:
    if any(record.machine != machine for record in records):
        raise DeploymentReplayFailed("journal contains a foreign machine record")
    if tuple(record.sequence for record in records) != tuple(range(1, len(records) + 1)):
        raise DeploymentReplayFailed("journal sequence is not contiguous")
    try:
        if machine.kind is DeploymentMachineKind.DEPLOYMENT:
            events = tuple(_deployment_event(record) for record in records)
            if not events:
                raise DeploymentReplayFailed("deployment replay requires an initial event")
            first = events[0]
            return DeploymentStateProjection.replay(first.release_id, first.attempt_id, events)
        if machine.kind is DeploymentMachineKind.ROLLOUT:
            rollout_events = tuple(_rollout_event(record) for record in records)
            if not rollout_events:
                raise DeploymentReplayFailed("rollout replay requires an initial event")
            first_rollout = rollout_events[0]
            return RolloutStateProjection.replay(
                first_rollout.rollout_id, first_rollout.release_id, rollout_events
            )
        if machine.kind is DeploymentMachineKind.PROMOTION:
            promotion_events = tuple(_promotion_event(record) for record in records)
            if not promotion_events:
                raise DeploymentReplayFailed("promotion replay requires an initial event")
            first_promotion = promotion_events[0]
            return PromotionStateProjection.replay(
                first_promotion.promotion_id,
                first_promotion.rollout_id,
                promotion_events,
            )
        rollback_events = tuple(_rollback_event(record) for record in records)
        if not rollback_events:
            raise DeploymentReplayFailed("rollback replay requires an initial event")
        first_rollback = rollback_events[0]
        return RollbackStateProjection.replay(
            first_rollback.rollback_attempt_id,
            first_rollback.release_id,
            first_rollback.target_id,
            first_rollback.source_revision,
            first_rollback.intended_revision,
            rollback_events,
        )
    except DeploymentReplayFailed:
        raise
    except (TypeError, ValueError) as exc:
        raise DeploymentReplayFailed("deployment journal reducer rejected history") from exc


def _deployment_event(record: DeploymentJournalRecord) -> DeploymentTransitionEventV1:
    if not isinstance(record.event, DeploymentTransitionEventV1):
        raise DeploymentReplayFailed("event is incompatible with deployment machine")
    return record.event


def _rollout_event(record: DeploymentJournalRecord) -> RolloutTransitionEventV1:
    if not isinstance(record.event, RolloutTransitionEventV1):
        raise DeploymentReplayFailed("event is incompatible with rollout machine")
    return record.event


def _promotion_event(record: DeploymentJournalRecord) -> PromotionTransitionEventV1:
    if not isinstance(record.event, PromotionTransitionEventV1):
        raise DeploymentReplayFailed("event is incompatible with promotion machine")
    return record.event


def _rollback_event(record: DeploymentJournalRecord) -> RollbackTransitionEventV1:
    if not isinstance(record.event, RollbackTransitionEventV1):
        raise DeploymentReplayFailed("event is incompatible with rollback machine")
    return record.event


@runtime_checkable
class DeploymentJournalStore(Protocol):
    def initialize(self) -> None: ...

    def append(self, request: DeploymentJournalAppendRequest) -> DeploymentAppendResult: ...

    def history(self, machine: DeploymentMachineKey) -> tuple[DeploymentJournalRecord, ...]: ...

    def latest_sequence(self, machine: DeploymentMachineKey) -> int: ...

    def replay(self, machine: DeploymentMachineKey) -> DeploymentProjection: ...

    def integrity_check(self) -> DeploymentJournalIntegrity: ...

    def health(self) -> DeploymentPersistenceHealth: ...
