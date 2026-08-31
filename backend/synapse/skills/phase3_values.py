from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from synapse.skills.phase3_errors import InvalidSkillStoreRecord

_RECORD_ID = re.compile(r"^[a-z][a-z0-9-]{1,31}:[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, order=True)
class SkillStoreRecordId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _RECORD_ID.fullmatch(self.value):
            raise InvalidSkillStoreRecord("skill store record identity is invalid")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillStoreRecordFingerprint:
    ALGORITHM: ClassVar[str] = "sha256"
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SHA256.fullmatch(self.value):
            raise InvalidSkillStoreRecord("skill store fingerprint is invalid")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SkillStoreQueryLimit:
    limit: int = 100

    def __post_init__(self) -> None:
        if (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or not 1 <= self.limit <= 200
        ):
            raise InvalidSkillStoreRecord("skill store query limit is invalid")


def validate_store_timestamp(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise InvalidSkillStoreRecord("skill store timestamp must be UTC aware")
