from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from synapse.skills.phase2_models import PublishedSkillManifest, SkillContentKind
from synapse.skills.phase2_values import SkillContentFingerprint
from synapse.skills.phase4_errors import (
    InvalidSkillPackageRoot,
    InvalidSkillSnapshotCorrespondence,
    SkillAssetChecksumMismatch,
    SkillAssetMissing,
    SkillContentChangedDuringVerification,
    SkillContentFingerprintMismatch,
    SkillPackagePathEscape,
    SkillVerificationResourceLimitExceeded,
    UndeclaredSkillAsset,
    UnsafeSkillPackageLink,
    UnsupportedSkillPackageFileType,
)
from synapse.skills.phase4_models import (
    SkillAssetChecksum,
    SkillVerificationMetadata,
    SkillVerificationPolicy,
    VerifiedSkillAsset,
    VerifiedSkillContentSnapshot,
    content_fingerprint,
)
from synapse.skills.phase4_parser import parse_published_skill_manifest

_MANIFEST = "manifest.yaml"
_INSTRUCTIONS = "SKILL.md"
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class _FileFact:
    relative_path: str
    path: Path
    stat_result: os.stat_result


class SkillPackageVerifier:
    """Read-only verifier for an explicitly supplied local candidate directory."""

    def __init__(self, policy: SkillVerificationPolicy | None = None) -> None:
        self._policy = policy or SkillVerificationPolicy()

    @property
    def policy(self) -> SkillVerificationPolicy:
        return self._policy

    def verify(
        self,
        package_root: Path,
        *,
        expected_content_fingerprint: SkillContentFingerprint | None = None,
        verification: SkillVerificationMetadata | None = None,
    ) -> VerifiedSkillContentSnapshot:
        root = self._resolve_root(package_root)
        files = self._inventory(root)
        by_path = {item.relative_path: item for item in files}
        manifest_fact = by_path.get(_MANIFEST)
        if manifest_fact is None:
            raise SkillAssetMissing()
        raw = self._read_bytes(manifest_fact, self._policy.max_manifest_bytes)
        manifest = parse_published_skill_manifest(raw, policy=self._policy)
        declared = {item.logical_path.value: item for item in manifest.content}
        self._validate_declarations(manifest)
        if _INSTRUCTIONS not in declared or (
            declared[_INSTRUCTIONS].kind is not SkillContentKind.INSTRUCTIONS
        ):
            raise InvalidSkillSnapshotCorrespondence()
        actual_paths = set(by_path) - {_MANIFEST}
        missing = set(declared) - actual_paths
        extra = actual_paths - set(declared)
        if missing:
            raise SkillAssetMissing()
        if extra:
            raise UndeclaredSkillAsset()
        assets: list[VerifiedSkillAsset] = []
        for logical_path in sorted(declared):
            declaration = declared[logical_path]
            checksum, size = self._hash_file(by_path[logical_path])
            if size != declaration.size_bytes or checksum.value != declaration.fingerprint.value:
                raise SkillAssetChecksumMismatch()
            assets.append(
                VerifiedSkillAsset(
                    logical_path=declaration.logical_path,
                    kind=declaration.kind,
                    media_type=declaration.media_type,
                    size_bytes=size,
                    checksum=checksum,
                    role=declaration.role,
                )
            )
        immutable_assets = tuple(assets)
        fingerprint = content_fingerprint(immutable_assets)
        if (
            expected_content_fingerprint is not None
            and fingerprint != expected_content_fingerprint
        ):
            raise SkillContentFingerprintMismatch()
        final_files = self._inventory(root)
        self._assert_inventory_unchanged(files, final_files)
        final_by_path = {item.relative_path: item for item in final_files}
        final_manifest = final_by_path.get(_MANIFEST)
        if (
            final_manifest is None
            or self._read_bytes(final_manifest, self._policy.max_manifest_bytes) != raw
        ):
            raise SkillContentChangedDuringVerification()
        return VerifiedSkillContentSnapshot(
            manifest=manifest,
            manifest_fingerprint=manifest.fingerprint(),
            content_fingerprint=fingerprint,
            assets=immutable_assets,
            policy_version=self._policy.version,
            verification=verification or SkillVerificationMetadata.now(),
        )

    def _resolve_root(self, supplied: Path) -> Path:
        if not isinstance(supplied, Path) or supplied.is_symlink():
            raise InvalidSkillPackageRoot()
        try:
            root = supplied.resolve(strict=True)
            info = root.stat(follow_symlinks=False)
        except OSError:
            raise InvalidSkillPackageRoot() from None
        if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
            raise InvalidSkillPackageRoot()
        return root

    def _inventory(self, root: Path) -> tuple[_FileFact, ...]:
        facts: list[_FileFact] = []
        total = 0
        folded: set[str] = set()

        def walk(directory: Path, parts: tuple[str, ...]) -> None:
            nonlocal total
            try:
                entries = sorted(os.scandir(directory), key=lambda item: item.name)
            except OSError:
                raise InvalidSkillPackageRoot() from None
            for entry in entries:
                relative_parts = (*parts, entry.name)
                relative = "/".join(relative_parts)
                _validate_portable_path(relative, len(relative_parts), self._policy)
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    raise UnsupportedSkillPackageFileType() from None
                if entry.is_symlink() or _is_reparse(info):
                    raise UnsafeSkillPackageLink()
                if stat.S_ISDIR(info.st_mode):
                    walk(Path(entry.path), relative_parts)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise UnsupportedSkillPackageFileType()
                if getattr(info, "st_nlink", 1) > 1:
                    raise UnsafeSkillPackageLink()
                _add_unique_portable_path(relative, folded)
                if info.st_size > self._policy.max_file_bytes:
                    raise SkillVerificationResourceLimitExceeded()
                total += info.st_size
                if total > self._policy.max_total_bytes:
                    raise SkillVerificationResourceLimitExceeded()
                facts.append(_FileFact(relative, Path(entry.path), info))
                if len(facts) > self._policy.max_files:
                    raise SkillVerificationResourceLimitExceeded()

        walk(root, ())
        return tuple(sorted(facts, key=lambda item: item.relative_path))

    def _validate_declarations(self, manifest: PublishedSkillManifest) -> None:
        folded: set[str] = set()
        for declaration in manifest.content:
            _validate_portable_path(
                declaration.logical_path.value,
                len(declaration.logical_path.value.split("/")),
                self._policy,
            )
            try:
                _add_unique_portable_path(declaration.logical_path.value, folded)
            except SkillPackagePathEscape:
                raise InvalidSkillSnapshotCorrespondence() from None

    def _assert_inventory_unchanged(
        self,
        initial: tuple[_FileFact, ...],
        final: tuple[_FileFact, ...],
    ) -> None:
        def identity(fact: _FileFact) -> tuple[str, int, int, int, int]:
            return (
                fact.relative_path,
                fact.stat_result.st_size,
                fact.stat_result.st_mtime_ns,
                fact.stat_result.st_dev,
                fact.stat_result.st_ino,
            )

        if tuple(map(identity, initial)) != tuple(map(identity, final)):
            raise SkillContentChangedDuringVerification()

    def _read_bytes(self, fact: _FileFact, maximum: int) -> bytes:
        data, _checksum, _size = self._read(fact, maximum, retain=True)
        return data

    def _hash_file(self, fact: _FileFact) -> tuple[SkillAssetChecksum, int]:
        _data, checksum, size = self._read(
            fact, self._policy.max_file_bytes, retain=False
        )
        return checksum, size

    def _read(
        self, fact: _FileFact, maximum: int, *, retain: bool
    ) -> tuple[bytes, SkillAssetChecksum, int]:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(fact.path, flags)
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or _is_reparse(before):
                    raise UnsupportedSkillPackageFileType()
                digest = hashlib.sha256()
                chunks: list[bytes] = []
                size = 0
                while chunk := stream.read(self._policy.read_chunk_bytes):
                    size += len(chunk)
                    if size > maximum:
                        raise SkillVerificationResourceLimitExceeded()
                    digest.update(chunk)
                    if retain:
                        chunks.append(chunk)
                after = os.fstat(stream.fileno())
        except SkillVerificationResourceLimitExceeded:
            raise
        except OSError:
            raise UnsupportedSkillPackageFileType() from None
        if (
            fact.stat_result.st_size != before.st_size
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or (
                before.st_ino
                and after.st_ino
                and (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            )
        ):
            raise SkillContentChangedDuringVerification()
        return b"".join(chunks), SkillAssetChecksum(digest.hexdigest()), size


def _is_reparse(value: os.stat_result) -> bool:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(value, "st_file_attributes", 0)
    return bool(marker and attributes & marker)


def _validate_portable_path(
    relative: str,
    depth: int,
    policy: SkillVerificationPolicy,
) -> None:
    if depth > policy.max_depth or len(relative) > policy.max_path_chars:
        raise SkillVerificationResourceLimitExceeded()
    if (
        not relative
        or "\\" in relative
        or "\x00" in relative
        or relative.startswith(("/", "\\"))
        or len(relative) >= 2
        and relative[1] == ":"
    ):
        raise SkillPackagePathEscape()
    for part in relative.split("/"):
        stem = part.split(".", 1)[0].upper()
        if (
            part in {"", ".", ".."}
            or part.endswith((".", " "))
            or ":" in part
            or any(ord(character) < 32 or ord(character) > 126 for character in part)
            or stem in _WINDOWS_RESERVED
        ):
            raise SkillPackagePathEscape()


def _add_unique_portable_path(relative: str, folded: set[str]) -> None:
    key = relative.casefold()
    if key in folded:
        raise SkillPackagePathEscape()
    folded.add(key)
