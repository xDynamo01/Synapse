"""Stable semantic identities for repositories and their materializations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from .canonical import content_fingerprint
from .errors import InvalidRepositoryIdentity

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,254}$")
_IDENTITY = re.compile(r"^(repository|checkout|worktree):[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


def _validate_key(value: str) -> None:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise InvalidRepositoryIdentity("identity key must be bounded printable ASCII")


@dataclass(frozen=True, slots=True)
class RepositoryFingerprint:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _FINGERPRINT.fullmatch(self.value):
            raise InvalidRepositoryIdentity("fingerprint must use sha256 lowercase hex")

    @classmethod
    def from_content(cls, content: object) -> RepositoryFingerprint:
        return cls(content_fingerprint(content))

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class _SemanticIdentity:
    value: str
    prefix: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not _IDENTITY.fullmatch(self.value)
            or not self.value.startswith(f"{self.prefix}:")
        ):
            raise InvalidRepositoryIdentity("semantic identity has an invalid form")

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RepositoryIdentity(_SemanticIdentity):
    prefix = "repository"

    @classmethod
    def from_stable_key(cls, stable_key: str) -> RepositoryIdentity:
        """Create identity from an admitted stable key, never branch, remote or host path."""

        _validate_key(stable_key)
        digest = content_fingerprint(("repository-identity-v1", stable_key)).removeprefix("sha256:")
        return cls(f"repository:{digest}")


@dataclass(frozen=True, slots=True)
class RepositoryCheckoutIdentity(_SemanticIdentity):
    prefix = "checkout"

    @classmethod
    def derive(
        cls, repository_id: RepositoryIdentity, materialization_key: str
    ) -> RepositoryCheckoutIdentity:
        _validate_key(materialization_key)
        digest = content_fingerprint(
            ("repository-checkout-identity-v1", repository_id, materialization_key)
        ).removeprefix("sha256:")
        return cls(f"checkout:{digest}")


@dataclass(frozen=True, slots=True)
class RepositoryWorktreeIdentity(_SemanticIdentity):
    prefix = "worktree"

    @classmethod
    def derive(
        cls, checkout_id: RepositoryCheckoutIdentity, worktree_key: str
    ) -> RepositoryWorktreeIdentity:
        _validate_key(worktree_key)
        digest = content_fingerprint(
            ("repository-worktree-identity-v1", checkout_id, worktree_key)
        ).removeprefix("sha256:")
        return cls(f"worktree:{digest}")
