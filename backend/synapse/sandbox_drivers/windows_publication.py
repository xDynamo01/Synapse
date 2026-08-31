"""Governed inspection and atomic local custody of declared workspace outputs."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol

from synapse.sandbox import OpaqueReference, SandboxArtifactFingerprint, SandboxWorkspaceId

from .local_artifact_custody import fingerprint_local_artifact
from .windows_authority import WindowsAuthorityContextV1, WindowsExecutionAuthorityGuard


class WindowsArtifactPublicationState(StrEnum):
    CANDIDATE = "candidate"
    INSPECTED = "inspected"
    VERIFIED = "verified"
    CUSTODY_ACCEPTED = "custody_accepted"
    PUBLICATION_REQUESTED = "publication_requested"
    PUBLISHED = "published"
    PUBLICATION_FAILED = "publication_failed"
    PUBLICATION_UNVERIFIED = "publication_unverified"


class WindowsCleanupState(StrEnum):
    REQUESTED = "requested"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True, slots=True)
class WindowsDeclaredOutputV1:
    logical_path: str
    expected_fingerprint: SandboxArtifactFingerprint
    binding_reference: OpaqueReference
    provenance_reference: OpaqueReference


@dataclass(frozen=True, slots=True)
class WindowsArtifactCandidateV1:
    execution_reference: OpaqueReference
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    logical_path: str
    binding_reference: OpaqueReference
    observed_type: str
    size_bytes: int
    fingerprint: SandboxArtifactFingerprint
    occurrence_reference: OpaqueReference
    provenance_reference: OpaqueReference
    state: WindowsArtifactPublicationState
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsArtifactPublicationRequestV1:
    candidate: WindowsArtifactCandidateV1
    expected_fingerprint: SandboxArtifactFingerprint
    idempotency_reference: OpaqueReference
    publication_capability: OpaqueReference
    authority_context: WindowsAuthorityContextV1 | None


@dataclass(frozen=True, slots=True)
class WindowsArtifactPublicationFactV1:
    candidate: WindowsArtifactCandidateV1
    state: WindowsArtifactPublicationState
    custody_reference: OpaqueReference | None
    publication_reference: OpaqueReference | None
    publication_verified: bool
    source_preserved: bool
    reconciliation_required: bool
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsPublicationHealth:
    output_inspection_available: bool
    candidate_verification_available: bool
    local_custody_available: bool
    external_publication_available: bool
    publication_fencing_enforced: bool
    cleanup_capability: bool
    cleanup_reconciliation_capability: bool


@dataclass(frozen=True, slots=True)
class WindowsCleanupFactV1:
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    state: WindowsCleanupState
    completed_steps: tuple[str, ...]
    failed_steps: tuple[str, ...]
    reconciliation_required: bool


class WindowsPublicationGrantValidationPort(Protocol):
    def validate(self, grant: object) -> bool: ...


class WindowsOutputPublicationAdapter:
    def __init__(
        self,
        workspace_root: Path,
        custody_root: Path,
        authority: WindowsExecutionAuthorityGuard,
        declared_outputs: tuple[tuple[SandboxWorkspaceId, WindowsDeclaredOutputV1], ...],
    ) -> None:
        self._workspace_root = workspace_root.resolve(strict=False)
        self._custody_root = custody_root.resolve(strict=False)
        self._authority = authority
        for _, declared in declared_outputs:
            self._logical(declared.logical_path)
        self._declared = {
            (workspace_id, declared.logical_path): declared
            for workspace_id, declared in declared_outputs
        }

    def health(self) -> WindowsPublicationHealth:
        return WindowsPublicationHealth(True, True, True, False, True, True, True)

    def inspect(
        self,
        *,
        execution_reference: OpaqueReference,
        attempt_reference: OpaqueReference,
        workspace_id: SandboxWorkspaceId,
        declared: WindowsDeclaredOutputV1,
        occurrence_reference: OpaqueReference,
    ) -> tuple[WindowsArtifactCandidateV1 | None, tuple[str, ...]]:
        if self._declared.get((workspace_id, declared.logical_path)) != declared:
            return None, ("output_undeclared",)
        try:
            source = self._source(workspace_id, declared.logical_path)
            fingerprint = fingerprint_local_artifact(source)
            size, observed_type = self._measure(source)
        except ValueError as error:
            return None, (str(error),)
        except OSError:
            return None, ("output_unavailable",)
        if fingerprint != declared.expected_fingerprint:
            return None, ("output_fingerprint_stale",)
        return (
            WindowsArtifactCandidateV1(
                execution_reference,
                attempt_reference,
                workspace_id,
                declared.logical_path,
                declared.binding_reference,
                observed_type,
                size,
                fingerprint,
                occurrence_reference,
                declared.provenance_reference,
                WindowsArtifactPublicationState.VERIFIED,
                ("published-artifact-is-not-trusted-artifact",),
            ),
            (),
        )

    def publish(
        self, request: WindowsArtifactPublicationRequestV1
    ) -> WindowsArtifactPublicationFactV1:
        candidate, context = request.candidate, request.authority_context
        mismatch = self._correspondence(request)
        if mismatch is not None:
            return self._failed(candidate, mismatch)
        try:
            source = self._source(candidate.workspace_id, candidate.logical_path)
            if fingerprint_local_artifact(source) != request.expected_fingerprint:
                return self._failed(candidate, "output_fingerprint_stale")
        except (OSError, ValueError):
            return self._failed(candidate, "output_verification_failed")
        check = self._authority.authorize(context, candidate.workspace_id, "artifact_publication")
        if not check.allowed:
            return self._failed(candidate, check.decision.value)
        self._custody_root.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(request.idempotency_reference.value.encode("ascii")).hexdigest()
        destination = self._custody_root / f"{key}{Path(candidate.logical_path).suffix}"
        if destination.exists():
            try:
                if fingerprint_local_artifact(destination) == candidate.fingerprint:
                    return self._published(candidate, destination, request.idempotency_reference)
            except (OSError, ValueError):
                pass
            return self._failed(candidate, "publication_idempotency_conflict")
        temporary = self._custody_root / f".{key}.{uuid.uuid4().hex}.publishing"
        try:
            shutil.copy2(source, temporary, follow_symlinks=False)
            if fingerprint_local_artifact(temporary) != candidate.fingerprint:
                temporary.unlink(missing_ok=True)
                return self._unverified(candidate, "publication_copy_verification_failed")
            check = self._authority.authorize(
                context, candidate.workspace_id, "artifact_publication"
            )
            if not check.allowed:
                temporary.unlink(missing_ok=True)
                return self._failed(candidate, check.decision.value)
            os.replace(temporary, destination)
            if fingerprint_local_artifact(destination) != candidate.fingerprint:
                return self._unverified(candidate, "publication_verification_failed")
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                return self._unverified(candidate, "publication_partial_cleanup_unproven")
            return self._failed(candidate, "publication_failed")
        return self._published(candidate, destination, request.idempotency_reference)

    @staticmethod
    def replay(fact: WindowsArtifactPublicationFactV1) -> WindowsArtifactPublicationFactV1:
        if fact.state is WindowsArtifactPublicationState.PUBLISHED and fact.publication_verified:
            return fact
        return replace(
            fact,
            state=WindowsArtifactPublicationState.PUBLICATION_UNVERIFIED,
            reconciliation_required=True,
            diagnostic_codes=tuple(
                sorted(set((*fact.diagnostic_codes, "publication_reconciliation_required")))
            ),
        )

    def _source(self, workspace_id: SandboxWorkspaceId, logical_path: str) -> Path:
        logical = self._logical(logical_path)

        root = self._workspace_root / workspace_id.value.replace(":", "-") / "output"
        target = root.joinpath(*logical.parts)
        if not target.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
            raise ValueError("output_outside_root")
        current = target
        while current != root.parent:
            if current.exists() and self._is_reparse(current):
                raise ValueError("unsafe_reparse")
            if current == root:
                break
            current = current.parent
        return target

    @staticmethod
    def _logical(logical_path: str) -> PurePosixPath:
        logical = PurePosixPath(logical_path)
        if (
            logical.is_absolute()
            or not logical.parts
            or any(part in {"", ".", ".."} for part in logical.parts)
            or any(
                "\\" in part or ":" in part or any(ord(c) < 32 for c in part)
                for part in logical.parts
            )
        ):
            raise ValueError("output_path_invalid")
        return logical

    @staticmethod
    def _measure(path: Path) -> tuple[int, str]:
        if path.is_file():
            if os.stat(path, follow_symlinks=False).st_nlink > 1:
                raise ValueError("hardlink_unsupported")
            return path.stat().st_size, "file"
        if path.is_dir():
            return sum(
                item.stat().st_size for item in path.rglob("*") if item.is_file()
            ), "directory"
        raise ValueError("output_type_unsupported")

    @staticmethod
    def _is_reparse(path: Path) -> bool:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)

    @staticmethod
    def _correspondence(request: WindowsArtifactPublicationRequestV1) -> str | None:
        candidate, context = request.candidate, request.authority_context
        if candidate.state is not WindowsArtifactPublicationState.VERIFIED:
            return "output_not_verified"
        if candidate.fingerprint != request.expected_fingerprint:
            return "publication_binding_mismatch"
        if context is None or context.grant is None:
            return "publication_authorization_invalid"
        if candidate.attempt_reference != context.attempt_reference:
            return "publication_attempt_mismatch"
        if candidate.workspace_id != context.workspace_id:
            return "publication_workspace_mismatch"
        if request.publication_capability not in context.grant.capabilities:
            return "publication_capability_missing"
        return None

    @staticmethod
    def _published(
        candidate: WindowsArtifactCandidateV1, destination: Path, identity: OpaqueReference
    ) -> WindowsArtifactPublicationFactV1:
        return WindowsArtifactPublicationFactV1(
            candidate,
            WindowsArtifactPublicationState.PUBLISHED,
            OpaqueReference(f"local-custody:{identity.value}"),
            OpaqueReference(f"local-publication:{identity.value}"),
            True,
            True,
            False,
            (),
        )

    @staticmethod
    def _failed(
        candidate: WindowsArtifactCandidateV1, code: str
    ) -> WindowsArtifactPublicationFactV1:
        return WindowsArtifactPublicationFactV1(
            candidate,
            WindowsArtifactPublicationState.PUBLICATION_FAILED,
            None,
            None,
            False,
            True,
            False,
            (code,),
        )

    @staticmethod
    def _unverified(
        candidate: WindowsArtifactCandidateV1, code: str
    ) -> WindowsArtifactPublicationFactV1:
        return WindowsArtifactPublicationFactV1(
            candidate,
            WindowsArtifactPublicationState.PUBLICATION_UNVERIFIED,
            None,
            None,
            False,
            True,
            True,
            (code,),
        )


class WindowsCleanupCampaign:
    """Ordered factual cleanup; replay never executes these callbacks."""

    ORDER = (
        "termination_state",
        "output_finalization",
        "secret_revocation",
        "publication_completion",
        "handle_resources",
        "network_resources",
        "artifact_temporary_state",
        "workspace_cleanup",
    )

    def __init__(self, authority: WindowsExecutionAuthorityGuard) -> None:
        self._authority = authority

    def run(
        self,
        attempt_reference: OpaqueReference,
        workspace_id: SandboxWorkspaceId,
        steps: tuple[tuple[str, Callable[[], bool]], ...],
        authority_context: WindowsAuthorityContextV1 | None,
    ) -> WindowsCleanupFactV1:
        callbacks = dict(steps)
        completed: list[str] = []
        failed: list[str] = []
        for name in self.ORDER:
            callback = callbacks.get(name)
            if callback is None:
                continue
            if name == "workspace_cleanup":
                check = self._authority.authorize(
                    authority_context, workspace_id, "destructive_cleanup"
                )
                if not check.allowed:
                    failed.append(name)
                    continue
            try:
                proven = callback()
            except OSError:
                proven = False
            (completed if proven else failed).append(name)
        state = (
            WindowsCleanupState.COMPLETED
            if not failed
            else (WindowsCleanupState.PARTIAL if completed else WindowsCleanupState.FAILED)
        )
        return WindowsCleanupFactV1(
            attempt_reference, workspace_id, state, tuple(completed), tuple(failed), bool(failed)
        )

    @staticmethod
    def replay(fact: WindowsCleanupFactV1) -> WindowsCleanupFactV1:
        if fact.state is WindowsCleanupState.COMPLETED:
            return fact
        return replace(
            fact, state=WindowsCleanupState.RECONCILIATION_REQUIRED, reconciliation_required=True
        )
