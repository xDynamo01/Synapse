from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

from synapse.intelligence_boundary.models import DataClassification, InformationOwnership

from .states import BaselineStatus, RunStatus, SuiteStatus
from .store_errors import EvalInvalidCursor, EvalInvalidStoreQuery
from .values import (
    BaselineId,
    ContentChecksum,
    EvalRunId,
    EvalSuiteId,
    EvalVersion,
    Revision,
    UtcTimestamp,
)

_OPAQUE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~:-]{1,512}$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,126}[A-Za-z0-9])?$")
T = TypeVar("T")


def _require_type(value: object, expected: type, field_name: str) -> None:
    if not isinstance(value, expected):
        raise EvalInvalidStoreQuery(f"{field_name} has an invalid type")


@dataclass(frozen=True)
class StoreCursor:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _OPAQUE_TOKEN_PATTERN.fullmatch(self.value):
            raise EvalInvalidCursor("store cursor must be a non-empty opaque token")

    def __str__(self) -> str:
        return "<opaque-cursor>"


@dataclass(frozen=True)
class IdempotencyKey:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _IDEMPOTENCY_PATTERN.fullmatch(self.value):
            raise EvalInvalidStoreQuery("idempotency key must be a non-empty canonical token")

    def __str__(self) -> str:
        return "<idempotency-key>"


class StoreOrder(StrEnum):
    ID_ASC = "id_asc"
    ID_DESC = "id_desc"
    CREATED_AT_ASC = "created_at_asc"
    CREATED_AT_DESC = "created_at_desc"


@dataclass(frozen=True)
class PageRequest:
    cursor: StoreCursor | None = None
    limit: int = 100
    order: StoreOrder = StoreOrder.ID_ASC

    def __post_init__(self) -> None:
        if self.cursor is not None:
            _require_type(self.cursor, StoreCursor, "cursor")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 500:
            raise EvalInvalidStoreQuery("page limit must be between 1 and 500")
        _require_type(self.order, StoreOrder, "page order")


@dataclass(frozen=True)
class StorePage(Generic[T]):
    items: tuple[T, ...]
    next_cursor: StoreCursor | None = None
    total: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise EvalInvalidStoreQuery("page items must be an immutable tuple")
        if self.next_cursor is not None:
            _require_type(self.next_cursor, StoreCursor, "next cursor")
        if self.total is not None and (
            isinstance(self.total, bool) or not isinstance(self.total, int) or self.total < 0
        ):
            raise EvalInvalidStoreQuery("page total cannot be negative")
        if self.total is not None and self.total < len(self.items):
            raise EvalInvalidStoreQuery("page total cannot be smaller than the returned items")


class WriteDisposition(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True)
class StoreWriteOutcome:
    record_reference: str
    previous_revision: Revision | None
    stored_revision: Revision
    disposition: WriteDisposition
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        if not isinstance(self.record_reference, str) or not self.record_reference.strip():
            raise EvalInvalidStoreQuery("write outcome requires a record reference")
        if self.previous_revision is not None:
            _require_type(self.previous_revision, Revision, "previous revision")
        _require_type(self.stored_revision, Revision, "stored revision")
        _require_type(self.disposition, WriteDisposition, "write disposition")
        _require_type(self.checksum, ContentChecksum, "write checksum")
        if self.disposition is WriteDisposition.CREATED and self.previous_revision is not None:
            raise EvalInvalidStoreQuery("created outcome cannot have a previous revision")
        if self.disposition is WriteDisposition.CREATED and self.stored_revision != Revision(1):
            raise EvalInvalidStoreQuery("created outcome must start at revision one")
        if self.disposition is WriteDisposition.UPDATED:
            if self.previous_revision is None:
                raise EvalInvalidStoreQuery("updated outcome requires a previous revision")
            if self.stored_revision.value <= self.previous_revision.value:
                raise EvalInvalidStoreQuery("updated outcome must advance the revision")


@dataclass(frozen=True)
class ConflictMetadata:
    record_reference: str
    expected_revision: Revision | None
    actual_revision: Revision | None
    idempotency_key: IdempotencyKey | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.record_reference, str) or not self.record_reference.strip():
            raise EvalInvalidStoreQuery("conflict metadata requires a record reference")
        if self.expected_revision is not None:
            _require_type(self.expected_revision, Revision, "expected revision")
        if self.actual_revision is not None:
            _require_type(self.actual_revision, Revision, "actual revision")
        if self.idempotency_key is not None:
            _require_type(self.idempotency_key, IdempotencyKey, "idempotency key")
        if self.expected_revision == self.actual_revision and self.idempotency_key is None:
            raise EvalInvalidStoreQuery("conflict metadata must describe a real conflict")


@dataclass(frozen=True)
class CreationInterval:
    created_from: UtcTimestamp | None = None
    created_until: UtcTimestamp | None = None

    def __post_init__(self) -> None:
        if self.created_from is not None:
            _require_type(self.created_from, UtcTimestamp, "created_from")
        if self.created_until is not None:
            _require_type(self.created_until, UtcTimestamp, "created_until")
        if (
            self.created_from is not None
            and self.created_until is not None
            and self.created_from.instant > self.created_until.instant
        ):
            raise EvalInvalidStoreQuery("creation interval is inverted")


@dataclass(frozen=True)
class SuiteListFilter:
    status: SuiteStatus | None = None
    owner: InformationOwnership | None = None
    classification: DataClassification | None = None

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.status, SuiteStatus, "suite status"),
            (self.owner, InformationOwnership, "suite owner"),
            (self.classification, DataClassification, "suite classification"),
        ):
            if value is not None:
                _require_type(value, expected, name)


@dataclass(frozen=True)
class DatasetBindingListFilter:
    asset_id: str | None = None
    owner: InformationOwnership | None = None
    classification: DataClassification | None = None

    def __post_init__(self) -> None:
        if self.asset_id is not None and (
            not isinstance(self.asset_id, str) or not self.asset_id.strip()
        ):
            raise EvalInvalidStoreQuery("asset_id filter must be non-empty")
        if self.owner is not None:
            _require_type(self.owner, InformationOwnership, "dataset owner")
        if self.classification is not None:
            _require_type(self.classification, DataClassification, "dataset classification")


@dataclass(frozen=True)
class RunListFilter:
    suite_id: EvalSuiteId | None = None
    status: RunStatus | None = None
    creation: CreationInterval | None = None

    def __post_init__(self) -> None:
        if self.suite_id is not None:
            _require_type(self.suite_id, EvalSuiteId, "suite_id")
        if self.status is not None:
            _require_type(self.status, RunStatus, "run status")
        if self.creation is not None:
            _require_type(self.creation, CreationInterval, "creation interval")


@dataclass(frozen=True)
class BaselineListFilter:
    suite_id: EvalSuiteId | None = None
    suite_version: EvalVersion | None = None
    status: BaselineStatus | None = None

    def __post_init__(self) -> None:
        if self.suite_id is not None:
            _require_type(self.suite_id, EvalSuiteId, "suite_id")
        if self.suite_version is not None:
            _require_type(self.suite_version, EvalVersion, "suite version")
        if self.status is not None:
            _require_type(self.status, BaselineStatus, "baseline status")
        if self.suite_version is not None and self.suite_id is None:
            raise EvalInvalidStoreQuery("suite version filter requires suite_id")


@dataclass(frozen=True)
class ComparisonListFilter:
    suite_id: EvalSuiteId | None = None
    suite_version: EvalVersion | None = None
    current_run_id: EvalRunId | None = None
    baseline_id: BaselineId | None = None

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.suite_id, EvalSuiteId, "suite_id"),
            (self.suite_version, EvalVersion, "suite version"),
            (self.current_run_id, EvalRunId, "current run_id"),
            (self.baseline_id, BaselineId, "baseline_id"),
        ):
            if value is not None:
                _require_type(value, expected, name)
        if self.suite_version is not None and self.suite_id is None:
            raise EvalInvalidStoreQuery("suite version filter requires suite_id")
