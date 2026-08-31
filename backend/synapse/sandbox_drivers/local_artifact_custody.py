"""Controlled local custody for governed Sandbox artifact references."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionRequest,
    SandboxArtifactInspectionResult,
    SandboxMaterializationStepOutcome,
)


class LocalArtifactCustodyPort(Protocol):
    def inspect(
        self, request: SandboxArtifactInspectionRequest
    ) -> SandboxArtifactInspectionResult: ...

    def verified_source(
        self,
        reference: OpaqueReference,
        expected: SandboxArtifactFingerprint,
    ) -> Path | None: ...


@dataclass(frozen=True, slots=True)
class LocalArtifactRegistration:
    reference: OpaqueReference
    custody_root: str
    logical_path: str
    provenance_reference: OpaqueReference


@dataclass(frozen=True, slots=True)
class LocalArtifactCustodyConfig:
    roots: tuple[tuple[str, Path], ...]
    registrations: tuple[LocalArtifactRegistration, ...]


@dataclass(frozen=True, slots=True)
class LocalArtifactCustodyHealth:
    adapter_implemented: bool
    roots_configured: bool
    local_file_supported: bool
    local_directory_supported: bool
    tree_fingerprint_supported: bool
    reparse_rejection_supported: bool
    copy_materialization_supported: bool
    verification_supported: bool
    process_execution_available: bool = False


class LocalArtifactCustody:
    def __init__(self, config: LocalArtifactCustodyConfig) -> None:
        self._roots = {
            name: root.resolve(strict=False) for name, root in config.roots
        }
        self._registrations = {
            registration.reference: registration
            for registration in config.registrations
        }

    def health(self) -> LocalArtifactCustodyHealth:
        return LocalArtifactCustodyHealth(
            True, bool(self._roots), True, True, True, True, True, True
        )

    def inspect(
        self, request: SandboxArtifactInspectionRequest
    ) -> SandboxArtifactInspectionResult:
        try:
            source = self._resolve(request.source_ref)
        except ValueError as error:
            return SandboxArtifactInspectionResult(
                SandboxMaterializationStepOutcome.FAILED,
                None,
                False,
                (str(error),),
            )
        if source is None or not source.exists():
            return SandboxArtifactInspectionResult(
                SandboxMaterializationStepOutcome.UNAVAILABLE,
                None,
                False,
                ("artifact_unavailable",),
            )
        try:
            observed = fingerprint_local_artifact(source)
        except ValueError as error:
            return SandboxArtifactInspectionResult(
                SandboxMaterializationStepOutcome.FAILED,
                None,
                False,
                (str(error),),
            )
        except OSError:
            return SandboxArtifactInspectionResult(
                SandboxMaterializationStepOutcome.UNAVAILABLE,
                None,
                False,
                ("artifact_unavailable",),
            )
        if observed != request.expected_fingerprint:
            return SandboxArtifactInspectionResult(
                SandboxMaterializationStepOutcome.FAILED,
                observed,
                True,
                ("artifact_stale",),
            )
        return SandboxArtifactInspectionResult(
            SandboxMaterializationStepOutcome.SUCCEEDED, observed, False, ()
        )

    def verified_source(
        self,
        reference: OpaqueReference,
        expected: SandboxArtifactFingerprint,
    ) -> Path | None:
        result = self.inspect(SandboxArtifactInspectionRequest(reference, expected))
        if result.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED:
            return None
        return self._resolve(reference)

    def _resolve(self, reference: OpaqueReference) -> Path | None:
        registration = self._registrations.get(reference)
        if registration is None:
            return None
        root = self._roots.get(registration.custody_root)
        if root is None:
            raise ValueError("artifact_custody_root_unavailable")
        logical = PurePosixPath(registration.logical_path)
        if (
            logical.is_absolute()
            or not logical.parts
            or any(part in {"", ".", ".."} for part in logical.parts)
            or any("\\" in part or ":" in part or any(ord(c) < 32 for c in part) for part in logical.parts)
        ):
            raise ValueError("artifact_outside_custody")
        target = root.joinpath(*logical.parts)
        resolved = target.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ValueError("artifact_outside_custody")
        current = target
        while current != root.parent:
            if current.exists() and _is_reparse(current):
                raise ValueError("unsafe_reparse")
            if current == root:
                break
            current = current.parent
        return target


def fingerprint_local_artifact(path: Path) -> SandboxArtifactFingerprint:
    if _is_reparse(path):
        raise ValueError("unsafe_reparse")
    if path.is_file():
        if os.stat(path, follow_symlinks=False).st_nlink > 1:
            raise ValueError("hardlink_unsupported")
        content = path.read_bytes()
        return SandboxArtifactFingerprint.from_content(
            ("file", len(content), hashlib.sha256(content).hexdigest())
        )
    if not path.is_dir():
        raise ValueError("unsupported_artifact_type")
    entries: list[tuple[str, str, int | None, str | None]] = []
    for item in sorted(
        path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()
    ):
        if _is_reparse(item):
            raise ValueError("unsafe_reparse")
        relative = item.relative_to(path).as_posix()
        if item.is_dir():
            entries.append((relative, "directory", None, None))
            continue
        if not item.is_file():
            raise ValueError("unsupported_artifact_type")
        if os.stat(item, follow_symlinks=False).st_nlink > 1:
            raise ValueError("hardlink_unsupported")
        content = item.read_bytes()
        entries.append(
            (relative, "file", len(content), hashlib.sha256(content).hexdigest())
        )
    return SandboxArtifactFingerprint.from_content(("tree", tuple(entries)))


def _is_reparse(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
