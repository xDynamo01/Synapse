"""Pure immutable Repository Runtime Slice 2 models."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .errors import InvalidRepositoryModel, InvalidRepositoryPath
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .states import (
    RepositoryCaseSensitivity,
    RepositoryGitTracking,
    RepositoryHeadKind,
    RepositoryIndexPresence,
    RepositoryMaterialRole,
    RepositoryObservationCompleteness,
    RepositoryPlatformKind,
    RepositorySensitivity,
    RepositoryTopology,
    RepositoryUnicodeNormalization,
    RepositoryWorkspaceStatus,
)

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_COMMIT = re.compile(r"^[0-9a-f]{4,128}$")


def _valid_path_component(value: str) -> bool:
    return bool(value) and all(unicodedata.category(character)[0] != "C" for character in value)


@dataclass(frozen=True, slots=True)
class RepositoryPlatformProfile:
    platform: RepositoryPlatformKind
    case_sensitivity: RepositoryCaseSensitivity
    unicode_normalization: RepositoryUnicodeNormalization
    canonical_separator: str = "/"
    profile_version: str = "repository-platform-profile-v1"

    def __post_init__(self) -> None:
        if self.canonical_separator != "/":
            raise InvalidRepositoryModel("canonical separator must be explicit forward slash")
        if self.profile_version != "repository-platform-profile-v1":
            raise InvalidRepositoryModel("unsupported platform profile version")

    def normalize_component(self, component: str) -> str:
        if self.unicode_normalization is RepositoryUnicodeNormalization.NFC:
            component = unicodedata.normalize("NFC", component)
        elif self.unicode_normalization is RepositoryUnicodeNormalization.NFD:
            component = unicodedata.normalize("NFD", component)
        if self.case_sensitivity is RepositoryCaseSensitivity.INSENSITIVE:
            component = component.casefold()
        return component


@dataclass(frozen=True, slots=True)
class RepositoryCheckout:
    identity: RepositoryCheckoutIdentity
    repository_id: RepositoryIdentity


@dataclass(frozen=True, slots=True)
class RepositoryWorktree:
    identity: RepositoryWorktreeIdentity
    checkout_id: RepositoryCheckoutIdentity
    repository_id: RepositoryIdentity


@dataclass(frozen=True, slots=True)
class RepositoryPath:
    value: str
    profile: RepositoryPlatformProfile
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None = None

    def __post_init__(self) -> None:
        raw = self.value
        if not isinstance(raw, str) or not raw or len(raw) > 512:
            raise InvalidRepositoryPath("path must be non-empty and bounded")
        if "\\" in raw or "//" in raw or raw.startswith("/") or raw.endswith("/"):
            raise InvalidRepositoryPath("path separator or root form is ambiguous")
        if re.match(r"^[A-Za-z]:", raw) or raw.startswith(("~", "//")):
            raise InvalidRepositoryPath("absolute host paths are forbidden")
        parts = raw.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise InvalidRepositoryPath("path traversal and implicit root escape are forbidden")
        normalized = "/".join(self.profile.normalize_component(part) for part in parts)
        if not all(_valid_path_component(part) for part in normalized.split("/")):
            raise InvalidRepositoryPath("path contains unsupported logical characters")
        object.__setattr__(self, "value", normalized)

    def canonical_value(self) -> object:
        return {
            "checkout_id": self.checkout_id,
            "profile": self.profile,
            "value": self.value,
            "worktree_id": self.worktree_id,
        }


@dataclass(frozen=True, slots=True)
class RepositoryPathClassification:
    tracking: RepositoryGitTracking
    material_role: RepositoryMaterialRole
    sensitivity: RepositorySensitivity
    topology: RepositoryTopology

    @property
    def allows_implicit_traversal(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class RepositoryPathObservation:
    path: RepositoryPath
    classification: RepositoryPathClassification


@dataclass(frozen=True, slots=True)
class RepositoryHeadState:
    kind: RepositoryHeadKind
    branch_name: str | None = None
    commit_id: str | None = None

    def __post_init__(self) -> None:
        if self.branch_name is not None and not _NAME.fullmatch(self.branch_name):
            raise InvalidRepositoryModel("branch name is invalid")
        if self.commit_id is not None and not _COMMIT.fullmatch(self.commit_id):
            raise InvalidRepositoryModel("commit identity is invalid")
        expected = {
            RepositoryHeadKind.NAMED_BRANCH: (True, True),
            RepositoryHeadKind.DETACHED: (False, True),
            RepositoryHeadKind.UNBORN_BRANCH: (True, False),
            RepositoryHeadKind.ABSENT: (False, False),
        }[self.kind]
        if (self.branch_name is not None, self.commit_id is not None) != expected:
            raise InvalidRepositoryModel("HEAD fields do not match the explicit state")


@dataclass(frozen=True, slots=True)
class RepositoryIndexState:
    presence: RepositoryIndexPresence


@dataclass(frozen=True, slots=True)
class RepositoryWorkspaceState:
    status: RepositoryWorkspaceStatus
    completeness: RepositoryObservationCompleteness

    def __post_init__(self) -> None:
        if (
            self.status is RepositoryWorkspaceStatus.CLEAN
            and self.completeness is not RepositoryObservationCompleteness.COMPLETE
        ):
            raise InvalidRepositoryModel("clean workspace requires complete observation")


@dataclass(frozen=True, slots=True)
class RepositoryObservation:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    head: RepositoryHeadState
    index: RepositoryIndexState
    workspace: RepositoryWorkspaceState
    completeness: RepositoryObservationCompleteness
    paths: tuple[RepositoryPathObservation, ...] = ()

    def __post_init__(self) -> None:
        if self.workspace.completeness is not self.completeness:
            raise InvalidRepositoryModel("workspace and observation completeness must correspond")
        ordered = tuple(sorted(self.paths, key=lambda item: item.path.value))
        if len({item.path.canonical_value().__repr__() for item in ordered}) != len(ordered):
            raise InvalidRepositoryModel("path observations must be unique")
        object.__setattr__(self, "paths", ordered)

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)
