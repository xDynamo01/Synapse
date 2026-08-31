"""Windows/NTFS workspace materialization without process authority."""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionRequest,
    SandboxArtifactInspectionResult,
    SandboxFilesystemResource,
    SandboxMaterializationAction,
    SandboxMaterializationStepOutcome,
    SandboxMaterializationStepRequest,
    SandboxMaterializationStepResult,
    SandboxMaterializedFingerprintRequest,
    SandboxMaterializedFingerprintResult,
    SandboxWorkspaceCleanupRequest,
    SandboxWorkspaceId,
    SandboxWorkspacePreparationRequest,
    SandboxWorkspaceVerificationRequest,
    SandboxWorkspaceVerificationResult,
)

from .local_artifact_custody import (
    LocalArtifactCustodyPort,
    fingerprint_local_artifact,
)
from .windows_authority import (
    WindowsAuthorityContextV1,
    WindowsExecutionAuthorityGuard,
)


class SandboxFencingDecision(StrEnum):
    VALID = "valid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class SandboxFencingValidationPort(Protocol):
    def validate(self, workspace_id: SandboxWorkspaceId, operation: str) -> SandboxFencingDecision: ...


class _AuthorityRejected(RuntimeError):
    def __init__(self, decision: str) -> None:
        self.decision = decision


@dataclass(frozen=True, slots=True)
class WindowsWorkspaceConfig:
    physical_root: Path
    artifacts: tuple[tuple[OpaqueReference, Path], ...] = ()
    custody: LocalArtifactCustodyPort | None = None


@dataclass(frozen=True, slots=True)
class WindowsWorkspaceHealth:
    driver_implemented: bool
    ntfs_root_configured: bool
    root_available: bool
    path_containment_supported: bool
    reparse_detection_supported: bool
    hardlink_rejection_supported: bool
    readonly_enforcement: str
    fencing_validation_available: bool
    materialization_available: bool
    cleanup_available: bool
    grant_validation_available: bool = True
    mutation_guard_available: bool = True
    sandbox_end_to_end_fencing_enforced: bool = True
    repository_end_to_end_fencing_enforced: bool = False


class WindowsWorkspaceDriver:
    _LAYOUT = ("input", "work", "output", "temp", "state")
    _RESOURCE = {
        SandboxFilesystemResource.ARTIFACT: "input",
        SandboxFilesystemResource.INPUT: "input",
        SandboxFilesystemResource.WORKSPACE: "work",
        SandboxFilesystemResource.OUTPUT: "output",
        SandboxFilesystemResource.TEMPORARY: "temp",
        SandboxFilesystemResource.STATE: "state",
    }

    def __init__(
        self,
        config: WindowsWorkspaceConfig,
        authority: WindowsExecutionAuthorityGuard,
        authority_context: Callable[[SandboxWorkspaceId], WindowsAuthorityContextV1 | None],
    ) -> None:
        self._root = config.physical_root.resolve(strict=False)
        self._artifacts = dict(config.artifacts)
        self._custody = config.custody
        self._authority = authority
        self._authority_context = authority_context
        self._sealed: dict[SandboxWorkspaceId, SandboxArtifactFingerprint] = {}

    def health(self) -> WindowsWorkspaceHealth:
        authority = self._authority.health()
        return WindowsWorkspaceHealth(
            True,
            self._root.is_absolute(),
            self._root.parent.exists(),
            True,
            True,
            True,
            "readonly-attribute",
            authority.fencing_validation_available,
            True,
            True,
            authority.grant_validation_available,
            authority.mutation_guard_available,
            authority.sandbox_end_to_end_fencing_enforced,
            authority.repository_end_to_end_fencing_enforced,
        )

    def inspect(self, request: SandboxArtifactInspectionRequest) -> SandboxArtifactInspectionResult:
        if self._custody is not None:
            return self._custody.inspect(request)
        source = self._artifacts.get(request.source_ref)
        if source is None or not source.exists():
            return SandboxArtifactInspectionResult(SandboxMaterializationStepOutcome.UNAVAILABLE, None, False, ("source_artifact_unavailable",))
        try:
            observed = self._fingerprint(source)
        except OSError:
            return SandboxArtifactInspectionResult(SandboxMaterializationStepOutcome.FAILED, None, False, ("source_artifact_unavailable",))
        if observed != request.expected_fingerprint:
            return SandboxArtifactInspectionResult(SandboxMaterializationStepOutcome.FAILED, observed, True, ("fingerprint_mismatch",))
        return SandboxArtifactInspectionResult(SandboxMaterializationStepOutcome.SUCCEEDED, observed, False, ())

    def prepare(self, request: SandboxWorkspacePreparationRequest) -> SandboxMaterializationStepResult:
        denied = self._check(request.workspace_id, "workspace_write")
        if denied:
            return denied
        target = self._workspace(request.workspace_id)
        if target.exists():
            return self._failed("workspace_reuse_denied")
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            denied = self._check(request.workspace_id, "workspace_write")
            if denied:
                return denied
            target.mkdir(exist_ok=False)
            for name in self._LAYOUT:
                denied = self._check(request.workspace_id, "workspace_write")
                if denied:
                    return denied
                (target / name).mkdir(exist_ok=False)
            return self._ok()
        except OSError:
            return self._failed("workspace_root_unavailable")

    def apply(self, request: SandboxMaterializationStepRequest) -> SandboxMaterializationStepResult:
        operation = request.operation
        destination: Path | None = None
        if operation.action in {SandboxMaterializationAction.SEAL_WORKSPACE, SandboxMaterializationAction.CLEANUP_WORKSPACE}:
            return self._failed("materialization_action_invalid")
        denied = self._check(request.workspace_id, "workspace_write")
        if denied:
            return denied
        if operation.destination_resource is None or operation.destination is None:
            return self._ok()
        try:
            destination = self._target(request.workspace_id, operation.destination_resource, operation.destination.value)
            self._assert_safe_chain(destination.parent, self._workspace(request.workspace_id))
            if operation.source_ref is None:
                self._mkdir_parents(request.workspace_id, destination)
                return self._ok()
            source = self._source(operation.source_ref, operation.expected_fingerprint)
            if source is None or not source.exists() or self._is_link(source) or self._hardlinked(source):
                return self._failed("source_artifact_unavailable" if source is None or not source.exists() else "link_policy_violation")
            observed = self._fingerprint(source)
            if observed != operation.expected_fingerprint:
                return self._failed("fingerprint_mismatch")
            if source.is_dir():
                self._copy_tree(request.workspace_id, source, destination)
            else:
                self._mkdir_parents(request.workspace_id, destination.parent)
                temporary = destination.with_name(destination.name + ".materializing")
                if temporary.exists():
                    return self._failed("materialization_partial")
                self._require(request.workspace_id, "workspace_delete_replace")
                shutil.copy2(source, temporary, follow_symlinks=False)
                if self._fingerprint(temporary) != operation.expected_fingerprint:
                    return self._failed("destination_verification_failed")
                self._require(request.workspace_id, "workspace_delete_replace")
                os.replace(temporary, destination)
            if self._fingerprint(destination) != operation.expected_fingerprint:
                return self._failed("fingerprint_mismatch")
            if operation.action is SandboxMaterializationAction.BIND_READONLY_INPUT:
                self._readonly(request.workspace_id, destination)
            return self._ok()
        except _AuthorityRejected as error:
            codes: tuple[str, ...] = (error.decision,)
            if destination is not None and destination.exists():
                codes += ("materialization_partial",)
            return SandboxMaterializationStepResult(
                SandboxMaterializationStepOutcome.FAILED, codes
            )
        except (OSError, ValueError):
            return self._failed("materialization_failed")

    def seal(self, request: SandboxMaterializationStepRequest) -> SandboxMaterializationStepResult:
        denied = self._check(request.workspace_id, "mutable_state_write")
        if denied:
            return denied
        try:
            workspace = self._workspace(request.workspace_id)
            self._assert_tree_safe(workspace)
            observed = self._fingerprint(workspace)
            self._require(request.workspace_id, "mutable_state_write")
            self._sealed[request.workspace_id] = observed
            return self._ok()
        except _AuthorityRejected as error:
            return self._failed(error.decision)
        except (OSError, ValueError):
            return self._failed("seal_failed")

    def cleanup(self, request: SandboxWorkspaceCleanupRequest) -> SandboxMaterializationStepResult:
        denied = self._check(request.workspace_id, "destructive_cleanup")
        if denied:
            return denied
        target = self._workspace(request.workspace_id)
        try:
            self._assert_safe_chain(target, self._root)
            self._remove_tree(request.workspace_id, target)
            self._require(request.workspace_id, "mutable_state_write")
            self._sealed.pop(request.workspace_id, None)
            return self._ok()
        except _AuthorityRejected as error:
            return self._failed(error.decision)
        except (OSError, ValueError):
            return self._failed("cleanup_incomplete")

    def refingerprint(self, request: SandboxMaterializedFingerprintRequest) -> SandboxMaterializedFingerprintResult:
        try:
            target = self._target(request.workspace_id, request.destination_resource, request.destination.value)
            self._assert_safe_chain(target, self._workspace(request.workspace_id))
            if not target.exists() or self._is_link(target):
                return SandboxMaterializedFingerprintResult(SandboxMaterializationStepOutcome.FAILED, None, ("materialized_path_unsafe",))
            return SandboxMaterializedFingerprintResult(SandboxMaterializationStepOutcome.SUCCEEDED, self._fingerprint(target), ())
        except (OSError, ValueError):
            return SandboxMaterializedFingerprintResult(SandboxMaterializationStepOutcome.FAILED, None, ("materialized_path_unsafe",))

    def verify(self, request: SandboxWorkspaceVerificationRequest) -> SandboxWorkspaceVerificationResult:
        try:
            observed = self._fingerprint(self._workspace(request.workspace_id))
            expected = request.expected_workspace_fingerprint
            outcome = SandboxMaterializationStepOutcome.SUCCEEDED if expected == observed else SandboxMaterializationStepOutcome.FAILED
            return SandboxWorkspaceVerificationResult(outcome, observed, () if outcome is SandboxMaterializationStepOutcome.SUCCEEDED else ("workspace_mismatch",))
        except OSError:
            return SandboxWorkspaceVerificationResult(SandboxMaterializationStepOutcome.UNAVAILABLE, None, ("workspace_unavailable",))

    def _workspace(self, identity: SandboxWorkspaceId) -> Path:
        return self._root / identity.value.replace(":", "-")

    def _source(
        self,
        reference: OpaqueReference,
        expected: SandboxArtifactFingerprint | None,
    ) -> Path | None:
        if expected is None:
            return None
        if self._custody is not None:
            return self._custody.verified_source(reference, expected)
        return self._artifacts.get(reference)

    def _target(self, identity: SandboxWorkspaceId, resource: SandboxFilesystemResource, logical: str) -> Path:
        if resource not in self._RESOURCE:
            raise ValueError("resource unsupported")
        segments = logical.split("/")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if (
            any(x in logical for x in ("\\", ":", "\0"))
            or any(ord(character) < 32 for character in logical)
            or Path(logical).is_absolute()
            or any(segment in {"", ".", ".."} or segment.endswith((" ", ".")) for segment in segments)
            or any(segment.split(".", 1)[0].upper() in reserved for segment in segments)
        ):
            raise ValueError("invalid logical path")
        target = self._workspace(identity) / self._RESOURCE[resource] / Path(logical)
        self._assert_safe_chain(target, self._workspace(identity))
        return target

    def _check(self, workspace: SandboxWorkspaceId, operation: str) -> SandboxMaterializationStepResult | None:
        check = self._authority.authorize(
            self._authority_context(workspace), workspace, operation
        )
        return None if check.allowed else self._failed(check.decision.value)

    def _require(self, workspace: SandboxWorkspaceId, operation: str) -> None:
        check = self._authority.authorize(
            self._authority_context(workspace), workspace, operation
        )
        if not check.allowed:
            raise _AuthorityRejected(check.decision.value)

    @staticmethod
    def _ok() -> SandboxMaterializationStepResult:
        return SandboxMaterializationStepResult(SandboxMaterializationStepOutcome.SUCCEEDED, ())

    @staticmethod
    def _failed(code: str) -> SandboxMaterializationStepResult:
        return SandboxMaterializationStepResult(SandboxMaterializationStepOutcome.FAILED, (code,))

    @staticmethod
    def _is_link(path: Path) -> bool:
        return path.is_symlink() or bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)

    @staticmethod
    def _hardlinked(path: Path) -> bool:
        return path.is_file() and os.stat(path, follow_symlinks=False).st_nlink > 1

    def _assert_safe_chain(self, target: Path, boundary: Path) -> None:
        resolved_boundary = boundary.resolve(strict=False)
        resolved_target = target.resolve(strict=False)
        if not resolved_target.is_relative_to(resolved_boundary):
            raise ValueError("containment violation")
        current = target
        while current != boundary.parent and current != self._root.parent:
            if current.exists() and self._is_link(current):
                raise ValueError("reparse violation")
            if current == boundary:
                break
            current = current.parent

    def _assert_tree_safe(self, root: Path) -> None:
        for current, dirs, files in os.walk(root, followlinks=False):
            for name in (*dirs, *files):
                path = Path(current) / name
                if self._is_link(path) or self._hardlinked(path):
                    raise ValueError("link policy violation")

    def _fingerprint(self, path: Path) -> SandboxArtifactFingerprint:
        return fingerprint_local_artifact(path)

    def _readonly(self, workspace: SandboxWorkspaceId, path: Path) -> None:
        targets = [path, *path.rglob("*")] if path.is_dir() else [path]
        for target in targets:
            if target.is_file():
                self._require(workspace, "workspace_write")
                target.chmod(stat.S_IREAD)

    def _mkdir_parents(self, workspace: SandboxWorkspaceId, target: Path) -> None:
        missing = []
        current = target
        while not current.exists():
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            self._require(workspace, "workspace_write")
            directory.mkdir()

    def _copy_tree(self, workspace: SandboxWorkspaceId, source: Path, destination: Path) -> None:
        self._assert_tree_safe(source)
        self._mkdir_parents(workspace, destination.parent)
        self._require(workspace, "workspace_write")
        destination.mkdir()
        for item in sorted(source.rglob("*"), key=lambda value: value.relative_to(source).as_posix()):
            target = destination / item.relative_to(source)
            self._require(workspace, "workspace_write")
            if item.is_dir():
                target.mkdir()
            else:
                shutil.copy2(item, target, follow_symlinks=False)

    def _remove_tree(self, workspace: SandboxWorkspaceId, root: Path) -> None:
        if not root.exists():
            return
        self._assert_tree_safe(root)
        paths = sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
        for path in paths:
            if path.is_file():
                self._require(workspace, "destructive_cleanup")
                path.chmod(stat.S_IWRITE)
                self._require(workspace, "destructive_cleanup")
                path.unlink()
            else:
                self._require(workspace, "destructive_cleanup")
                path.rmdir()
        self._require(workspace, "destructive_cleanup")
        root.rmdir()
