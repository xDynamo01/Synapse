"""Windows-aware hybrid Git CLI and filesystem adapter for Repository Runtime."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from .application import (
    RepositoryMutationAttempt,
    RepositoryMutationCleanupResult,
    RepositoryMutationInterruptionResult,
    RepositoryMutationObservationResult,
    RepositoryMutationPreconditionReport,
    RepositoryMutationPreconditionResult,
    RepositoryMutationStep,
    RepositoryMutationStepRequest,
    RepositoryMutationStepResult,
)
from .errors import RepositoryAdapterBoundaryViolation, RepositoryAdapterUnavailable
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import (
    RepositoryCheckout,
    RepositoryHeadState,
    RepositoryIndexState,
    RepositoryPath,
    RepositoryPathClassification,
    RepositoryPlatformProfile,
    RepositoryWorktree,
)
from .mutations import RepositoryMutationOperation, RepositoryMutationPlan
from .observation import (
    RepositoryDimensionCompleteness,
    RepositoryObservationFacts,
    RepositoryObservationRequest,
    RepositoryObservationSource,
    RepositoryObservedEntry,
)
from .recovery import (
    RepositoryRecoveryAttempt,
    RepositoryRecoveryInterruption,
    RepositoryRecoveryObservation,
    RepositoryRecoveryPlan,
    RepositoryRecoveryPreconditionReport,
    RepositoryRecoveryPreconditionState,
    RepositoryRecoveryStep,
    RepositoryRecoveryStepResult,
    RepositoryRecoveryStepState,
    RepositoryRecoveryVerification,
)
from .restore_points import (
    RepositoryRestorePointManifest,
    RepositoryRestorePointVerificationFact,
)
from .snapshot import RepositoryPathFingerprintFact, RepositorySnapshot
from .states import (
    RepositoryEntryStatus,
    RepositoryGitTracking,
    RepositoryHeadKind,
    RepositoryIndexPresence,
    RepositoryMaterialRole,
    RepositoryMutationApplicationOutcome,
    RepositoryMutationCleanupRequirement,
    RepositoryMutationOperationKind,
    RepositoryMutationPreconditionOutcome,
    RepositoryMutationSideEffect,
    RepositoryObservationCompleteness,
    RepositoryObservationDimension,
    RepositoryPresence,
    RepositoryRestorePointVerificationState,
    RepositorySensitivity,
    RepositoryTopology,
    RepositoryWorkspaceStatus,
)


class RepositoryAdapterCapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class RepositoryAdapterFeature(StrEnum):
    WINDOWS = "windows"
    WORKTREES = "worktrees"
    COMMON_GIT_DIR = "common_git_dir"
    DETACHED_HEAD = "detached_head"
    UNBORN_HEAD = "unborn_head"
    SUBMODULES = "submodules"
    NESTED_REPOSITORIES = "nested_repositories"
    SPARSE_CHECKOUT = "sparse_checkout"
    LFS = "lfs"
    HOOKS = "hooks"
    FILTERS = "filters"
    ENCODINGS = "encodings"
    CASE_SENSITIVITY = "case_sensitivity"
    REPARSE_POINTS = "reparse_points"
    MUTATION = "mutation"
    RECOVERY = "recovery"
    STAGING = "staging"
    COMMIT = "commit"
    PUSH = "push"


@dataclass(frozen=True, slots=True, order=True)
class RepositoryAdapterCapability:
    feature: RepositoryAdapterFeature
    state: RepositoryAdapterCapabilityState
    diagnostic_code: str


@dataclass(frozen=True, slots=True)
class RepositoryAdapterCapabilityReport:
    adapter_id: str
    adapter_version: str
    git_version: str | None
    capabilities: tuple[RepositoryAdapterCapability, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", tuple(sorted(self.capabilities)))

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryMutationMaterial:
    operation_id: RepositoryFingerprint
    target_entry_fingerprint: RepositoryFingerprint | None
    content: bytes

    @property
    def content_fingerprint(self) -> RepositoryFingerprint:
        return _bytes_fingerprint(self.content)


@dataclass(frozen=True, slots=True)
class RepositoryRecoveryMaterial:
    recovery_step_fingerprint: RepositoryFingerprint
    path: RepositoryPath
    content: bytes | None


@dataclass(frozen=True, slots=True)
class RepositoryLocalAdapterConfig:
    repository_root: str
    restore_root: str
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    mutation_plan: RepositoryMutationPlan | None = None
    mutation_materials: tuple[RepositoryMutationMaterial, ...] = ()
    recovery_plan: RepositoryRecoveryPlan | None = None
    recovery_materials: tuple[RepositoryRecoveryMaterial, ...] = ()
    restore_manifest: RepositoryRestorePointManifest | None = None


def _bytes_fingerprint(value: bytes) -> RepositoryFingerprint:
    return RepositoryFingerprint("sha256:" + hashlib.sha256(value).hexdigest())


class RepositoryLocalAdapter:
    """Concrete adapter with closed Git argv and allowlisted filesystem effects."""

    _git_commands = {"rev-parse", "symbolic-ref", "status", "ls-files", "config"}

    def __init__(self, config: RepositoryLocalAdapterConfig) -> None:
        self._config = config
        self._root = Path(config.repository_root).resolve(strict=True)
        self._restore_root = Path(config.restore_root).resolve(strict=False)
        self._assert_root()
        self._operations = (
            {item.operation_id: item for item in config.mutation_plan.operations}
            if config.mutation_plan
            else {}
        )
        self._mutation_materials = {item.operation_id: item for item in config.mutation_materials}
        self._recovery_steps = (
            {item.fingerprint: item for item in config.recovery_plan.steps}
            if config.recovery_plan
            else {}
        )
        self._recovery_materials = {
            item.recovery_step_fingerprint: item for item in config.recovery_materials
        }
        self._path_map = self._build_path_map()
        self._restore_verified: set[RepositoryFingerprint] = set()
        self._interrupted = False
        self._baseline_token = self._live_token()

    def capability_report(self) -> RepositoryAdapterCapabilityReport:
        git_version = self._git("--version", allow_global=True).stdout.strip()
        hooks = self._hooks_present()
        filters = bool(self._git("config", "--get-regexp", r"^filter\.", check=False).stdout)
        lfs = bool(self._git("config", "--get-regexp", r"^filter\.lfs\.", check=False).stdout)
        sparse = (
            self._git("config", "--bool", "core.sparseCheckout", check=False).stdout.strip()
            == "true"
        )
        values = {
            RepositoryAdapterFeature.WINDOWS: RepositoryAdapterCapabilityState.SUPPORTED
            if os.name == "nt"
            else RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.WORKTREES: RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.COMMON_GIT_DIR: RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.DETACHED_HEAD: RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.UNBORN_HEAD: RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.SUBMODULES: RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.NESTED_REPOSITORIES: RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.SPARSE_CHECKOUT: RepositoryAdapterCapabilityState.DEGRADED
            if sparse
            else RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.LFS: RepositoryAdapterCapabilityState.DEGRADED
            if lfs
            else RepositoryAdapterCapabilityState.UNAVAILABLE,
            RepositoryAdapterFeature.HOOKS: RepositoryAdapterCapabilityState.DEGRADED
            if hooks
            else RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.FILTERS: RepositoryAdapterCapabilityState.DEGRADED
            if filters
            else RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.ENCODINGS: RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.CASE_SENSITIVITY: RepositoryAdapterCapabilityState.SUPPORTED,
            RepositoryAdapterFeature.REPARSE_POINTS: RepositoryAdapterCapabilityState.SUPPORTED
            if os.name == "nt"
            else RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.MUTATION: RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.RECOVERY: RepositoryAdapterCapabilityState.DEGRADED,
            RepositoryAdapterFeature.STAGING: RepositoryAdapterCapabilityState.UNSUPPORTED,
            RepositoryAdapterFeature.COMMIT: RepositoryAdapterCapabilityState.UNSUPPORTED,
            RepositoryAdapterFeature.PUSH: RepositoryAdapterCapabilityState.UNSUPPORTED,
        }
        capabilities = tuple(
            RepositoryAdapterCapability(feature, state, f"adapter:{feature.value}:{state.value}")
            for feature, state in values.items()
        )
        return RepositoryAdapterCapabilityReport(
            "repository-local-hybrid", "v1", git_version, capabilities
        )

    def facts_for(self, request: RepositoryObservationRequest) -> RepositoryObservationFacts:
        if (
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
        ) != (
            self._config.repository_id,
            self._config.checkout_id,
            self._config.worktree_id,
            self._config.platform_profile,
        ):
            raise RepositoryAdapterBoundaryViolation("observation binding mismatch")
        head, branch, object_reference = self._head()
        statuses, staged, conflicted = self._status()
        tracked, submodules, sparse_paths = self._tracked_paths()
        entries: list[RepositoryObservedEntry] = []
        for value in sorted(set(statuses) | tracked):
            path = RepositoryPath(
                value, request.platform_profile, request.checkout_id, request.worktree_id
            )
            tracking, status = statuses.get(
                value, (RepositoryGitTracking.TRACKED, RepositoryEntryStatus.UNCHANGED)
            )
            topology = (
                RepositoryTopology.SUBMODULE
                if value in submodules
                else RepositoryTopology.SPARSE_EXCLUDED
                if value in sparse_paths
                else RepositoryTopology.NESTED_REPOSITORY
                if self._nested_repository(value)
                else RepositoryTopology.REGULAR
            )
            entries.append(
                RepositoryObservedEntry(
                    path,
                    RepositoryPathClassification(
                        tracking,
                        RepositoryMaterialRole.UNKNOWN,
                        RepositorySensitivity.UNKNOWN,
                        topology,
                    ),
                    status,
                    self._safe_path(path, allow_missing=True).is_file(),
                    False,
                )
            )
        workspace = (
            RepositoryWorkspaceStatus.CONFLICTED
            if conflicted
            else RepositoryWorkspaceStatus.DIRTY
            if statuses
            else RepositoryWorkspaceStatus.CLEAN
        )
        completeness = tuple(
            RepositoryDimensionCompleteness(item, RepositoryObservationCompleteness.COMPLETE)
            for item in RepositoryObservationDimension
        )
        return RepositoryObservationFacts(
            RepositoryObservationSource(
                "repository-local-hybrid", "v1", datetime.now(timezone.utc)
            ),
            RepositoryPresence.PRESENT,
            request.repository_id,
            RepositoryCheckout(request.checkout_id, request.repository_id),
            RepositoryWorktree(request.worktree_id, request.checkout_id, request.repository_id)
            if request.worktree_id
            else None,
            request.platform_profile,
            head,
            branch,
            object_reference,
            RepositoryIndexState(RepositoryIndexPresence.PRESENT),
            workspace,
            tuple(entries),
            tuple(
                RepositoryPath(
                    value, request.platform_profile, request.checkout_id, request.worktree_id
                )
                for value in sorted(staged)
            ),
            completeness,
        )

    def fingerprint_facts_for(
        self, paths: tuple[RepositoryPath, ...]
    ) -> tuple[RepositoryPathFingerprintFact, ...]:
        result = []
        for logical in sorted(set(paths), key=lambda item: item.value):
            path = self._safe_path(logical, allow_missing=True)
            content = _bytes_fingerprint(path.read_bytes()) if path.is_file() else None
            metadata = self._metadata_fingerprint(path) if path.exists() else None
            result.append(
                RepositoryPathFingerprintFact(
                    RepositoryFingerprint.from_content(logical),
                    content,
                    metadata,
                    path.stat().st_size if path.is_file() else None,
                    "sha256",
                    "v1",
                    RepositoryObservationCompleteness.COMPLETE,
                )
            )
        return tuple(result)

    def revalidate_preconditions(
        self, attempt: RepositoryMutationAttempt, preconditions: tuple
    ) -> RepositoryMutationPreconditionReport:
        plan = self._config.mutation_plan
        matches = (
            plan is not None
            and attempt.mutation_plan_fingerprint == plan.fingerprint
            and tuple(item.operation_id for item in plan.operations) == attempt.operation_ids
            and self._live_token() == self._baseline_token
        )
        outcome = (
            RepositoryMutationPreconditionOutcome.SATISFIED
            if matches
            else RepositoryMutationPreconditionOutcome.STALE
        )
        return RepositoryMutationPreconditionReport(
            attempt.attempt_id,
            attempt.mutation_plan_fingerprint,
            tuple(
                RepositoryMutationPreconditionResult(
                    RepositoryFingerprint.from_content(item),
                    outcome,
                    item.expected_fingerprint if matches else self._live_token(),
                )
                for item in preconditions
            ),
        )

    def apply_operation(self, step: RepositoryMutationStepRequest) -> RepositoryMutationStepResult:
        operation = self._operations.get(step.operation.operation_id)
        if (
            operation != step.operation
            or self._config.mutation_plan is None
            or step.mutation_plan_fingerprint != self._config.mutation_plan.fingerprint
            or self._interrupted
        ):
            return self._mutation_failure(step, RepositoryMutationSideEffect.NONE)
        if self._live_token() != self._baseline_token:
            return self._mutation_failure(step, RepositoryMutationSideEffect.NONE)
        if (
            operation.recovery_requirement.value == "required"
            and operation.operation_id not in self._restore_verified
        ):
            return self._mutation_failure(step, RepositoryMutationSideEffect.NONE)
        try:
            self._apply(operation)
        except (OSError, RepositoryAdapterBoundaryViolation):
            return self._mutation_failure(step, RepositoryMutationSideEffect.PARTIAL)
        observed = self._operation_observation(operation)
        self._baseline_token = self._live_token()
        return RepositoryMutationStepResult(
            step.attempt_id,
            operation.operation_id,
            RepositoryMutationApplicationOutcome.APPLIED,
            RepositoryMutationSideEffect.DECLARED,
            RepositoryMutationCleanupRequirement.NOT_REQUIRED,
            (observed,),
        )

    def observe_result(
        self, step: RepositoryMutationStepRequest, result: RepositoryMutationStepResult
    ) -> RepositoryMutationObservationResult:
        operation = self._operations.get(step.operation.operation_id)
        observed = (self._operation_observation(operation),) if operation else ()
        return RepositoryMutationObservationResult(
            step.attempt_id,
            step.operation.operation_id,
            observed,
            result.outcome is RepositoryMutationApplicationOutcome.APPLIED
            and observed == result.observed_fingerprints,
        )

    def interrupt_sequence(
        self, attempt: RepositoryMutationAttempt, operation_id: RepositoryFingerprint
    ) -> RepositoryMutationInterruptionResult:
        self._interrupted = operation_id in self._operations
        return RepositoryMutationInterruptionResult(
            attempt.attempt_id, operation_id, self._interrupted
        )

    def request_cleanup(
        self,
        attempt: RepositoryMutationAttempt,
        completed_steps: tuple[RepositoryMutationStep, ...],
    ) -> RepositoryMutationCleanupResult:
        return RepositoryMutationCleanupResult(
            attempt.attempt_id, RepositoryMutationApplicationOutcome.CLEANUP_REQUIRED
        )

    def materialize_restore_point(
        self, manifest: RepositoryRestorePointManifest
    ) -> tuple[RepositoryRestorePointVerificationFact, ...]:
        if (
            self._config.restore_manifest is None
            or manifest.fingerprint != self._config.restore_manifest.fingerprint
        ):
            raise RepositoryAdapterBoundaryViolation("restore manifest binding mismatch")
        self._restore_root.mkdir(parents=True, exist_ok=True)
        facts = []
        for entry in manifest.entries:
            logical = self._path_map.get(entry.path_fingerprint)
            if logical is None:
                state = RepositoryRestorePointVerificationState.UNAVAILABLE
                observed_content = None
                observed_metadata = None
            else:
                source = self._safe_path(logical, allow_missing=True)
                target = self._restore_root / entry.fingerprint.value.removeprefix("sha256:")
                if source.is_file():
                    target.write_bytes(source.read_bytes())
                    observed_content = _bytes_fingerprint(target.read_bytes())
                else:
                    target.write_bytes(b"")
                    observed_content = None
                observed_metadata = self._metadata_fingerprint(source) if source.exists() else None
                state = (
                    RepositoryRestorePointVerificationState.VERIFIED
                    if observed_content == entry.expected_content_fingerprint
                    and observed_metadata == entry.expected_metadata_fingerprint
                    else RepositoryRestorePointVerificationState.MISMATCH
                )
                if state is RepositoryRestorePointVerificationState.VERIFIED:
                    self._restore_verified.update(
                        item.operation_id
                        for item in self._operations.values()
                        if RepositoryFingerprint.from_content(item.source_path or item.path)
                        == entry.path_fingerprint
                    )
            facts.append(
                RepositoryRestorePointVerificationFact(
                    entry.fingerprint, observed_content, observed_metadata, state
                )
            )
        return tuple(facts)

    def revalidate_recovery_preconditions(
        self, attempt: RepositoryRecoveryAttempt, plan: RepositoryRecoveryPlan
    ) -> RepositoryRecoveryPreconditionReport:
        matches = (
            self._config.recovery_plan is not None
            and plan.fingerprint == self._config.recovery_plan.fingerprint
            and attempt.plan_fingerprint == plan.fingerprint
            and self._live_token() == self._baseline_token
        )
        return RepositoryRecoveryPreconditionReport(
            attempt.attempt_id,
            plan.fingerprint,
            RepositoryRecoveryPreconditionState.SATISFIED
            if matches
            else RepositoryRecoveryPreconditionState.EXTERNAL_INTERFERENCE,
            (self._live_token(),),
        )

    def apply_recovery_step(
        self, attempt: RepositoryRecoveryAttempt, step: RepositoryRecoveryStep
    ) -> RepositoryRecoveryStepResult:
        if self._recovery_steps.get(step.fingerprint) != step:
            return RepositoryRecoveryStepResult(
                attempt.attempt_id,
                step.fingerprint,
                RepositoryRecoveryStepState.FAILED,
                RepositoryMutationSideEffect.NONE,
            )
        material = self._recovery_materials.get(step.fingerprint)
        if material is None or step.coverage_entry_fingerprint is None:
            return RepositoryRecoveryStepResult(
                attempt.attempt_id,
                step.fingerprint,
                RepositoryRecoveryStepState.FAILED,
                RepositoryMutationSideEffect.NONE,
            )
        path = self._safe_path(material.path, allow_missing=True)
        try:
            if step.action.value == "restore-absence":
                if path.exists() and path.is_file():
                    path.unlink()
            elif material.content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(material.content)
            else:
                return RepositoryRecoveryStepResult(
                    attempt.attempt_id,
                    step.fingerprint,
                    RepositoryRecoveryStepState.FAILED,
                    RepositoryMutationSideEffect.NONE,
                )
        except OSError:
            return RepositoryRecoveryStepResult(
                attempt.attempt_id,
                step.fingerprint,
                RepositoryRecoveryStepState.PARTIAL,
                RepositoryMutationSideEffect.PARTIAL,
            )
        self._baseline_token = self._live_token()
        return RepositoryRecoveryStepResult(
            attempt.attempt_id,
            step.fingerprint,
            RepositoryRecoveryStepState.APPLIED,
            RepositoryMutationSideEffect.DECLARED,
            (self._path_token(path),),
        )

    def observe_recovery_step(
        self,
        attempt: RepositoryRecoveryAttempt,
        step: RepositoryRecoveryStep,
        result: RepositoryRecoveryStepResult,
    ) -> RepositoryRecoveryObservation:
        material = self._recovery_materials.get(step.fingerprint)
        observed = (
            (self._path_token(self._safe_path(material.path, allow_missing=True)),)
            if material
            else ()
        )
        return RepositoryRecoveryObservation(
            attempt.attempt_id,
            step.fingerprint,
            result.state is RepositoryRecoveryStepState.APPLIED,
            False,
            observed,
        )

    def interrupt_recovery(
        self, attempt: RepositoryRecoveryAttempt, step_fingerprint: RepositoryFingerprint
    ) -> RepositoryRecoveryInterruption:
        self._interrupted = step_fingerprint in self._recovery_steps
        return RepositoryRecoveryInterruption(attempt.attempt_id, self._interrupted)

    def verify_recovered_state(
        self, attempt: RepositoryRecoveryAttempt, base: RepositorySnapshot
    ) -> RepositoryRecoveryVerification:
        restored = self._live_token() == self._baseline_token and all(
            self._recovery_material_matches(item) for item in self._recovery_materials.values()
        )
        return RepositoryRecoveryVerification(
            attempt.attempt_id,
            base.fingerprint,
            base.fingerprint if restored else self._live_token(),
            RepositoryObservationCompleteness.COMPLETE,
            restored,
            False,
        )

    def _apply(self, operation: RepositoryMutationOperation) -> None:
        target = self._safe_path(operation.path, allow_missing=True)
        source = (
            self._safe_path(operation.source_path, allow_missing=False)
            if operation.source_path
            else None
        )
        material = self._mutation_materials.get(operation.operation_id)
        if operation.kind in {
            RepositoryMutationOperationKind.CREATE,
            RepositoryMutationOperationKind.REPLACE,
            RepositoryMutationOperationKind.APPEND,
        }:
            if (
                material is None
                or material.target_entry_fingerprint != operation.expected_target_fingerprint
            ):
                raise RepositoryAdapterBoundaryViolation("mutation material binding mismatch")
            if operation.kind is RepositoryMutationOperationKind.CREATE and target.exists():
                raise RepositoryAdapterBoundaryViolation("create collision")
            if operation.kind is RepositoryMutationOperationKind.REPLACE and not target.is_file():
                raise RepositoryAdapterBoundaryViolation("replace target missing")
            target.parent.mkdir(parents=True, exist_ok=True)
            if operation.kind is RepositoryMutationOperationKind.APPEND:
                with target.open("ab") as stream:
                    stream.write(material.content)
            else:
                target.write_bytes(material.content)
        elif operation.kind is RepositoryMutationOperationKind.DELETE:
            if not target.is_file():
                raise RepositoryAdapterBoundaryViolation("delete target missing")
            target.unlink()
        elif operation.kind in {
            RepositoryMutationOperationKind.MOVE,
            RepositoryMutationOperationKind.COPY,
        }:
            if source is None or not source.is_file() or target.exists():
                raise RepositoryAdapterBoundaryViolation("source/destination invalid")
            target.parent.mkdir(parents=True, exist_ok=True)
            if operation.kind is RepositoryMutationOperationKind.MOVE:
                source.replace(target)
            else:
                shutil.copyfile(source, target)
        else:
            raise RepositoryAdapterBoundaryViolation("operation unsupported by adapter")

    def _safe_path(self, logical: RepositoryPath | None, *, allow_missing: bool) -> Path:
        if (
            logical is None
            or logical.checkout_id != self._config.checkout_id
            or logical.worktree_id != self._config.worktree_id
        ):
            raise RepositoryAdapterBoundaryViolation("path binding mismatch")
        candidate = self._root.joinpath(*logical.value.split("/"))
        current = self._root
        for component in logical.value.split("/"):
            current = current / component
            if current.exists() and self._is_reparse(current):
                raise RepositoryAdapterBoundaryViolation("reparse boundary")
            if current != candidate and (current / ".git").exists():
                raise RepositoryAdapterBoundaryViolation("nested repository boundary")
        resolved = candidate.resolve(strict=False)
        if self._root != resolved and self._root not in resolved.parents:
            raise RepositoryAdapterBoundaryViolation("repository root escape")
        if not allow_missing and not resolved.exists():
            raise RepositoryAdapterBoundaryViolation("path missing")
        return resolved

    @staticmethod
    def _is_reparse(path: Path) -> bool:
        info = path.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        return path.is_symlink() or bool(
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )

    def _assert_root(self) -> None:
        result = self._git("rev-parse", "--show-toplevel")
        if Path(result.stdout.strip()).resolve() != self._root:
            raise RepositoryAdapterBoundaryViolation("canonical repository root mismatch")
        common_dir = Path(
            self._git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        )
        git_dir = Path(self._git("rev-parse", "--path-format=absolute", "--git-dir").stdout.strip())
        if not common_dir.is_dir() or not git_dir.is_dir():
            raise RepositoryAdapterBoundaryViolation("Git directory binding unavailable")

    def _git(
        self, *args: str, check: bool = True, allow_global: bool = False
    ) -> subprocess.CompletedProcess[str]:
        if (
            not args
            or (not allow_global and args[0] not in self._git_commands)
            or any("\x00" in item for item in args)
        ):
            raise RepositoryAdapterBoundaryViolation("Git argv is not allowlisted")
        command = ["git", *args] if allow_global else ["git", "-C", str(self._root), *args]
        result = subprocess.run(
            command,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
        )
        if check and result.returncode != 0:
            raise RepositoryAdapterUnavailable("Git factual command failed")
        return result

    def _head(self) -> tuple[RepositoryHeadState, str | None, str | None]:
        commit = self._git("rev-parse", "--verify", "HEAD", check=False).stdout.strip() or None
        branch = (
            self._git("symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
            or None
        )
        if commit and branch:
            return (
                RepositoryHeadState(RepositoryHeadKind.NAMED_BRANCH, branch, commit),
                branch,
                commit,
            )
        if commit:
            return RepositoryHeadState(RepositoryHeadKind.DETACHED, None, commit), None, commit
        if branch:
            return RepositoryHeadState(RepositoryHeadKind.UNBORN_BRANCH, branch, None), branch, None
        return RepositoryHeadState(RepositoryHeadKind.ABSENT), None, None

    def _status(
        self,
    ) -> tuple[dict[str, tuple[RepositoryGitTracking, RepositoryEntryStatus]], set[str], bool]:
        raw = self._git(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching"
        ).stdout
        parts = raw.split("\0")
        result = {}
        staged = set()
        conflicted = False
        index = 0
        while index < len(parts) and parts[index]:
            item = parts[index]
            code = item[:2]
            value = item[3:].replace("\\", "/")
            if code[0] in "RC":
                index += 1
            tracking = (
                RepositoryGitTracking.UNTRACKED
                if code == "??"
                else RepositoryGitTracking.IGNORED
                if code == "!!"
                else RepositoryGitTracking.TRACKED
            )
            status = (
                RepositoryEntryStatus.CONFLICTED
                if code in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
                else RepositoryEntryStatus.ADDED
                if "A" in code or code == "??"
                else RepositoryEntryStatus.DELETED
                if "D" in code
                else RepositoryEntryStatus.MODIFIED
            )
            result[value] = (tracking, status)
            conflicted = conflicted or status is RepositoryEntryStatus.CONFLICTED
            if code[0] not in {" ", "?", "!"}:
                staged.add(value)
            index += 1
        return result, staged, conflicted

    def _tracked_paths(self) -> tuple[set[str], set[str], set[str]]:
        raw = self._git("ls-files", "--stage", "-z").stdout
        tracked = set()
        submodules = set()
        for item in raw.split("\0"):
            if not item or "\t" not in item:
                continue
            metadata, value = item.split("\t", 1)
            value = value.replace("\\", "/")
            tracked.add(value)
            if metadata.startswith("160000 "):
                submodules.add(value)
        sparse_paths = {
            item[2:].replace("\\", "/")
            for item in self._git("ls-files", "-t", "-z").stdout.split("\0")
            if item.startswith("S ")
        }
        return tracked, submodules, sparse_paths

    def _live_token(self) -> RepositoryFingerprint:
        head = self._git("rev-parse", "--verify", "HEAD", check=False).stdout.strip()
        status = self._git(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=no"
        ).stdout
        index = self._git("ls-files", "--stage", "-z").stdout
        paths = tuple(
            (item.path.value, self._operation_observation(item))
            for item in self._operations.values()
        )
        return RepositoryFingerprint.from_content(
            (
                str(self._root),
                self._config.repository_id,
                self._config.checkout_id,
                self._config.worktree_id,
                head,
                index,
                status,
                paths,
            )
        )

    def _operation_observation(
        self, operation: RepositoryMutationOperation | None
    ) -> RepositoryFingerprint:
        if operation is None:
            return RepositoryFingerprint.from_content("operation-absent")
        return self._path_token(self._safe_path(operation.path, allow_missing=True))

    @staticmethod
    def _path_token(path: Path) -> RepositoryFingerprint:
        if not path.exists():
            return RepositoryFingerprint.from_content(("absent",))
        if path.is_file():
            return RepositoryFingerprint.from_content(
                ("file", _bytes_fingerprint(path.read_bytes()), path.stat().st_size)
            )
        return RepositoryFingerprint.from_content(("other", path.stat().st_mode))

    @staticmethod
    def _metadata_fingerprint(path: Path) -> RepositoryFingerprint:
        info = path.lstat()
        return RepositoryFingerprint.from_content(
            (
                stat.S_IFMT(info.st_mode),
                info.st_mode & 0o777,
                getattr(info, "st_file_attributes", 0),
            )
        )

    def _build_path_map(self) -> dict[RepositoryFingerprint, RepositoryPath]:
        result = {}
        for operation in self._operations.values():
            result[RepositoryFingerprint.from_content(operation.path)] = operation.path
            if operation.source_path:
                result[RepositoryFingerprint.from_content(operation.source_path)] = (
                    operation.source_path
                )
        for material in self._config.recovery_materials:
            result[RepositoryFingerprint.from_content(material.path)] = material.path
        return result

    def _recovery_material_matches(self, material: RepositoryRecoveryMaterial) -> bool:
        path = self._safe_path(material.path, allow_missing=True)
        if material.content is None:
            return not path.exists()
        return path.is_file() and path.read_bytes() == material.content

    def _hooks_present(self) -> bool:
        configured = self._git("config", "--path", "--get", "core.hooksPath", check=False)
        if configured.stdout.strip():
            hooks = Path(configured.stdout.strip())
            if not hooks.is_absolute():
                hooks = self._root / hooks
        else:
            git_dir = Path(self._git("rev-parse", "--git-dir").stdout.strip())
            if not git_dir.is_absolute():
                git_dir = self._root / git_dir
            hooks = git_dir.resolve() / "hooks"
        return hooks.exists() and any(
            item.is_file() and not item.name.endswith(".sample") for item in hooks.iterdir()
        )

    def _nested_repository(self, value: str) -> bool:
        current = self._root
        for component in value.split("/")[:-1]:
            current = current / component
            if (current / ".git").exists():
                return True
        return False

    @staticmethod
    def _mutation_failure(
        step: RepositoryMutationStepRequest, effect: RepositoryMutationSideEffect
    ) -> RepositoryMutationStepResult:
        return RepositoryMutationStepResult(
            step.attempt_id,
            step.operation.operation_id,
            RepositoryMutationApplicationOutcome.FAILED,
            effect,
            RepositoryMutationCleanupRequirement.REQUIRED
            if effect is RepositoryMutationSideEffect.PARTIAL
            else RepositoryMutationCleanupRequirement.NOT_REQUIRED,
        )
