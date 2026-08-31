from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from functools import total_ordering

from .errors import (
    InvalidChecksum,
    InvalidFingerprint,
    InvalidIdentity,
    InvalidRevision,
    InvalidTimestamp,
    InvalidVersion,
)

_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,126}[A-Za-z0-9])?$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _validate_identity(value: str, kind: str) -> None:
    if not isinstance(value, str) or not _IDENTITY_PATTERN.fullmatch(value):
        raise InvalidIdentity(f"{kind} must be a non-empty canonical identity")


@dataclass(frozen=True, order=True)
class EvalSuiteId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "suite_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class EvalCaseId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "case_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class DatasetBindingId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "binding_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class EvalRunId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "run_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class EvalRunManifestId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "manifest_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class EvalResultId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "result_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class ScoringDecisionId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "scoring_decision_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class EvalRunFinalizationId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "run_finalization_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class MaterializedOutputId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "materialized_output_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class EvaluatorId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "evaluator_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class BaselineId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "baseline_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class ComparisonId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "comparison_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class RegressionRuleId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "rule_id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class RegressionReportId:
    value: str

    def __post_init__(self) -> None:
        _validate_identity(self.value, "report_id")

    def __str__(self) -> str:
        return self.value


@total_ordering
@dataclass(frozen=True)
class EvalVersion:
    value: str

    def __post_init__(self) -> None:
        match = _SEMVER_PATTERN.fullmatch(self.value) if isinstance(self.value, str) else None
        if match is None:
            raise InvalidVersion("eval version must be canonical SemVer")
        prerelease = match.group(4)
        if prerelease is not None and any(
            part.isdigit() and len(part) > 1 and part.startswith("0")
            for part in prerelease.split(".")
        ):
            raise InvalidVersion("numeric SemVer prerelease identifiers cannot have leading zeroes")

    def __str__(self) -> str:
        return self.value

    def _precedence(self) -> tuple[int, int, int, tuple[tuple[int, int | str], ...] | None]:
        match = _SEMVER_PATTERN.fullmatch(self.value)
        assert match is not None
        prerelease = match.group(4)
        prerelease_key = None
        if prerelease is not None:
            prerelease_key = tuple(
                (0, int(part)) if part.isdigit() else (1, part)
                for part in prerelease.split(".")
            )
        return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease_key

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, EvalVersion):
            return NotImplemented
        left = self._precedence()
        right = other._precedence()
        if left[:3] != right[:3]:
            return left[:3] < right[:3]
        if left[3] is None:
            return False
        if right[3] is None:
            return True
        return left[3] < right[3]


@dataclass(frozen=True, order=True)
class Revision:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise InvalidRevision("revision must be a positive integer")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, order=True)
class ContentChecksum:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SHA256_PATTERN.fullmatch(self.value):
            raise InvalidChecksum("checksum must be a lowercase SHA-256 digest")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class Fingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SHA256_PATTERN.fullmatch(self.value):
            raise InvalidFingerprint("fingerprint must be a lowercase SHA-256 digest")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class UtcTimestamp:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise InvalidTimestamp("timestamp must be a non-empty ISO-8601 UTC value")
        try:
            parsed = datetime.fromisoformat(self.value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidTimestamp("timestamp must be valid ISO-8601") from exc
        offset = parsed.utcoffset()
        if parsed.tzinfo is None or offset is None:
            raise InvalidTimestamp("timestamp must include a UTC offset")
        if offset.total_seconds() != 0:
            raise InvalidTimestamp("timestamp must be normalized to UTC")

    def __str__(self) -> str:
        return self.value

    @property
    def instant(self) -> datetime:
        return datetime.fromisoformat(self.value.replace("Z", "+00:00"))
