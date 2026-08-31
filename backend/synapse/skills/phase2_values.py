from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from synapse.skills.phase2_errors import (
    InvalidSkillCompatibilityDeclaration,
    InvalidSkillContentReference,
    InvalidSkillDependencyDeclaration,
    InvalidSkillFingerprint,
    InvalidSkillId,
    InvalidSkillReference,
    InvalidSkillVersion,
    InvalidSkillVersionConstraint,
    UnsupportedSkillManifestFormat,
)

_SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_CARET_CONSTRAINT = re.compile(
    r"^\^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
_COMPARATOR = re.compile(
    r"^(>=|>)(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*),"
    r"(<=|<)(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEMANTIC_REF = re.compile(r"^[a-z][a-z0-9-]{1,31}:[a-z0-9][a-z0-9._-]{0,127}$")
_REQUIREMENT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
_SCHEMA_VERSION = re.compile(r"^[a-z][a-z0-9._-]{1,63}:[1-9][0-9]*$")
_MAX_LOGICAL_PATH = 512
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True, order=True)
class SkillId:
    """Canonical ASCII identity: lowercase kebab-case, 3-64 characters."""

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not _SKILL_ID.fullmatch(self.value)
            or "--" in self.value
            or self.value in _WINDOWS_RESERVED_NAMES
        ):
            raise InvalidSkillId("skill ID must be canonical lowercase kebab-case")

    @classmethod
    def parse(cls, value: str) -> SkillId:
        return cls(value)

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True)
class SkillVersion:
    """Concrete SemVer identity with structural equality and SemVer precedence."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        numeric = (self.major, self.minor, self.patch)
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in numeric):
            raise InvalidSkillVersion("skill version must be explicit SemVer")
        _validate_semver_identifiers(self.prerelease, prerelease=True)
        _validate_semver_identifiers(self.build, prerelease=False)

    @classmethod
    def parse(cls, value: str) -> SkillVersion:
        if not isinstance(value, str):
            raise InvalidSkillVersion("skill version must be explicit SemVer")
        match = _SEMVER.fullmatch(value)
        if match is None:
            raise InvalidSkillVersion("skill version must be explicit SemVer")
        prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
        build = tuple(match.group(5).split(".")) if match.group(5) else ()
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease, build)

    def __str__(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += "-" + ".".join(self.prerelease)
        if self.build:
            value += "+" + ".".join(self.build)
        return value

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SkillVersion):
            return NotImplemented
        return self.precedence_key() < other.precedence_key()

    def precedence_key(
        self,
    ) -> tuple[int, int, int, tuple[tuple[int, int | str], ...]]:
        return (
            self.major,
            self.minor,
            self.patch,
            _prerelease_key(self.prerelease),
        )

    def compare_precedence(self, other: SkillVersion) -> int:
        if not isinstance(other, SkillVersion):
            raise InvalidSkillVersion("skill version comparison requires SkillVersion")
        left, right = self.precedence_key(), other.precedence_key()
        return (left > right) - (left < right)

    def has_same_precedence(self, other: SkillVersion) -> bool:
        return self.compare_precedence(other) == 0

    def to_canonical_text(self) -> str:
        return str(self)


@dataclass(frozen=True, order=True)
class SkillVersionConstraint:
    """A caret or explicitly bounded comparator range; never a moving alias."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidSkillVersionConstraint("skill version constraint is invalid")
        if _CARET_CONSTRAINT.fullmatch(self.value):
            return
        match = _COMPARATOR.fullmatch(self.value)
        if match is None:
            raise InvalidSkillVersionConstraint("skill version constraint is invalid")
        lower = (int(match.group(2)), int(match.group(3)), int(match.group(4)))
        upper = (int(match.group(6)), int(match.group(7)), int(match.group(8)))
        if lower >= upper:
            raise InvalidSkillVersionConstraint("skill version constraint is invalid")

    @classmethod
    def parse(cls, value: str) -> SkillVersionConstraint:
        return cls(value)

    @property
    def kind(self) -> str:
        return "caret" if self.value.startswith("^") else "bounded_range"

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillManifestFingerprint:
    ALGORITHM: ClassVar[str] = "sha256"
    value: str

    def __post_init__(self) -> None:
        _validate_fingerprint(self.value)

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillContentFingerprint:
    ALGORITHM: ClassVar[str] = "sha256"
    value: str

    def __post_init__(self) -> None:
        _validate_fingerprint(self.value)

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillPackageFingerprint:
    ALGORITHM: ClassVar[str] = "sha256"
    value: str

    def __post_init__(self) -> None:
        _validate_fingerprint(self.value)

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillManifestFormatVersion:
    CURRENT: ClassVar[int] = 1
    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or self.value != self.CURRENT
        ):
            raise UnsupportedSkillManifestFormat("skill manifest format version is unsupported")

    @classmethod
    def parse(cls, value: int) -> SkillManifestFormatVersion:
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)

    def to_canonical_text(self) -> str:
        return str(self.value)


@dataclass(frozen=True, order=True)
class SkillSemanticReference:
    """A non-URL, non-path namespaced reference."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SEMANTIC_REF.fullmatch(self.value):
            raise InvalidSkillReference("skill semantic reference is invalid")

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillLogicalPath:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value or len(self.value) > _MAX_LOGICAL_PATH:
            raise InvalidSkillContentReference("skill content logical path is invalid")
        if (
            self.value.startswith(("/", "\\"))
            or "\\" in self.value
            or ":" in self.value
            or "//" in self.value
        ):
            raise InvalidSkillContentReference("skill content logical path is invalid")
        parts = self.value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise InvalidSkillContentReference("skill content logical path is invalid")
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part) for part in parts):
            raise InvalidSkillContentReference("skill content logical path is invalid")

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillRequirementId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _REQUIREMENT_ID.fullmatch(self.value):
            raise InvalidSkillDependencyDeclaration("skill requirement identifier is invalid")

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillSchemaVersionRequirement:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SCHEMA_VERSION.fullmatch(self.value):
            raise InvalidSkillCompatibilityDeclaration(
                "skill schema version requirement is invalid"
            )

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


def _validate_semver_identifiers(values: tuple[str, ...], *, prerelease: bool) -> None:
    if not isinstance(values, tuple):
        raise InvalidSkillVersion("skill version must be deeply immutable")
    for value in values:
        if not isinstance(value, str) or not value or not re.fullmatch(r"[0-9A-Za-z-]+", value):
            raise InvalidSkillVersion("skill version must be explicit SemVer")
        if prerelease and value.isdigit() and len(value) > 1 and value.startswith("0"):
            raise InvalidSkillVersion("skill version must be explicit SemVer")


def _prerelease_key(values: tuple[str, ...]) -> tuple[tuple[int, int | str], ...]:
    if not values:
        return ((2, 0),)
    return tuple((0, int(value)) if value.isdigit() else (1, value) for value in values)


def _validate_fingerprint(value: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise InvalidSkillFingerprint("skill fingerprint must be a lowercase SHA-256 digest")
