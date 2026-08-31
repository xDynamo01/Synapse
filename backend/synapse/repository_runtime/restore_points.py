"""Pure restore-point requirements, manifests and factual verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .authorization import RepositoryAuthorizationAssessment
from .errors import InvalidRepositoryRestorePointModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPathClassification, RepositoryPlatformProfile
from .mutations import RepositoryMutationPlan
from .snapshot import RepositorySnapshot
from .states import (
    RepositoryAuthorizationOutcome,
    RepositoryGitTracking,
    RepositoryMaterialRole,
    RepositoryMutationOperationKind,
    RepositoryObservationCompleteness,
    RepositoryRestorePointCoverageKind,
    RepositoryRestorePointDimension,
    RepositoryRestorePointMaterialHandling,
    RepositoryRestorePointVerificationState,
    RepositorySensitivity,
    RepositoryTopology,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


class RepositoryRestorePointDiagnosticCode(StrEnum):
    BASE_SNAPSHOT_MISMATCH = "base_snapshot_mismatch"
    MUTATION_PLAN_MISMATCH = "mutation_plan_mismatch"
    AUTHORIZATION_ASSESSMENT_MISMATCH = "authorization_assessment_mismatch"
    AUTHORIZATION_CORRESPONDENCE_REQUIRED = "authorization_correspondence_required"
    REPOSITORY_MISMATCH = "repository_mismatch"
    CHECKOUT_MISMATCH = "checkout_mismatch"
    WORKTREE_MISMATCH = "worktree_mismatch"
    PLATFORM_MISMATCH = "platform_mismatch"
    REQUIRED_ENTRY_MISSING = "required_entry_missing"
    ENTRY_OUTSIDE_MUTATION_SCOPE = "entry_outside_mutation_scope"
    ENTRY_FINGERPRINT_MISMATCH = "entry_fingerprint_mismatch"
    LOGICAL_REFERENCE_DUPLICATE = "logical_reference_duplicate"
    ALGORITHM_UNSUPPORTED = "algorithm_unsupported"
    SENSITIVE_CONTENT_BLOCKED = "sensitive_content_blocked"
    TOPOLOGY_BOUNDARY_TRAVERSAL = "topology_boundary_traversal"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    MANIFEST_INCOMPLETE = "manifest_incomplete"
    VERIFICATION_MISSING = "verification_missing"
    VERIFICATION_MISMATCH = "verification_mismatch"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"
    VERIFICATION_CORRUPT = "verification_corrupt"
    ENTRY_OVERSIZED = "entry_oversized"
    MANIFEST_OVERSIZED = "manifest_oversized"
    ENTRY_LIMIT_EXCEEDED = "entry_limit_exceeded"


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointPolicy:
    policy_id: str
    policy_version: str
    required_operations: tuple[RepositoryMutationOperationKind, ...]
    required_dimensions: tuple[RepositoryRestorePointDimension, ...]
    cover_untracked_collisions: bool
    generated_handling: RepositoryRestorePointMaterialHandling
    artifact_handling: RepositoryRestorePointMaterialHandling
    runtime_state_handling: RepositoryRestorePointMaterialHandling
    secret_risk_handling: RepositoryRestorePointMaterialHandling
    maximum_entry_size: int
    maximum_total_size: int
    maximum_entries: int
    verification_required: bool
    accepted_integrity_algorithms: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(
            self.policy_version
        ):
            raise InvalidRepositoryRestorePointModel("restore-point policy identity is invalid")
        if min(self.maximum_entry_size, self.maximum_total_size, self.maximum_entries) < 0:
            raise InvalidRepositoryRestorePointModel("restore-point limits cannot be negative")
        if any(
            not _REFERENCE.fullmatch(algorithm) or not _REFERENCE.fullmatch(version)
            for algorithm, version in self.accepted_integrity_algorithms
        ):
            raise InvalidRepositoryRestorePointModel("integrity algorithm is invalid")
        object.__setattr__(
            self, "required_operations", tuple(sorted(set(self.required_operations)))
        )
        object.__setattr__(
            self, "required_dimensions", tuple(sorted(set(self.required_dimensions)))
        )
        object.__setattr__(
            self,
            "accepted_integrity_algorithms",
            tuple(sorted(set(self.accepted_integrity_algorithms))),
        )


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryRestorePointModel("occurrence metadata is invalid")
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return (
            self.repository_id,
            self.checkout_id,
            self.worktree_id,
            self.platform_profile,
            self.base_snapshot_fingerprint,
            self.mutation_plan_fingerprint,
            self.authorization_assessment_fingerprint,
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointCoverageRequirement:
    path_fingerprint: RepositoryFingerprint
    expected_content_fingerprint: RepositoryFingerprint | None
    expected_metadata_fingerprint: RepositoryFingerprint | None
    expected_size: int | None
    coverage_kind: RepositoryRestorePointCoverageKind
    completeness: RepositoryObservationCompleteness
    classification: RepositoryPathClassification | None


def _coverage_key(item: RepositoryRestorePointCoverageRequirement) -> tuple[str, str]:
    return item.path_fingerprint.value, item.coverage_kind.value


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointRequirement:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    coverage: tuple[RepositoryRestorePointCoverageRequirement, ...]
    completeness: RepositoryObservationCompleteness

    def __post_init__(self) -> None:
        object.__setattr__(self, "coverage", tuple(sorted(set(self.coverage), key=_coverage_key)))

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointEntry:
    path_fingerprint: RepositoryFingerprint
    expected_content_fingerprint: RepositoryFingerprint | None
    expected_metadata_fingerprint: RepositoryFingerprint | None
    logical_storage_reference: str
    size: int | None
    coverage_kind: RepositoryRestorePointCoverageKind
    completeness: RepositoryObservationCompleteness
    integrity_algorithm: str
    integrity_version: str
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.logical_storage_reference):
            raise InvalidRepositoryRestorePointModel("logical storage reference is invalid")
        if not _REFERENCE.fullmatch(self.integrity_algorithm) or not _REFERENCE.fullmatch(
            self.integrity_version
        ):
            raise InvalidRepositoryRestorePointModel("integrity identity is invalid")
        if self.size is not None and self.size < 0:
            raise InvalidRepositoryRestorePointModel("restore-point size cannot be negative")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryRestorePointModel("occurrence metadata is invalid")
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return tuple(
            getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "occurrence_metadata"
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


def _entry_key(item: RepositoryRestorePointEntry) -> tuple[str, str, str]:
    return (
        item.path_fingerprint.value,
        item.coverage_kind.value,
        item.logical_storage_reference,
    )


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointManifest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    mutation_plan_fingerprint: RepositoryFingerprint
    authorization_assessment_fingerprint: RepositoryFingerprint
    requirement_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    entries: tuple[RepositoryRestorePointEntry, ...]
    completeness: RepositoryObservationCompleteness
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        by_fingerprint = {item.fingerprint: item for item in self.entries}
        object.__setattr__(
            self,
            "entries",
            tuple(sorted(by_fingerprint.values(), key=_entry_key)),
        )
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return (
            self.repository_id,
            self.checkout_id,
            self.worktree_id,
            self.platform_profile,
            self.base_snapshot_fingerprint,
            self.mutation_plan_fingerprint,
            self.authorization_assessment_fingerprint,
            self.requirement_fingerprint,
            self.policy_id,
            self.policy_version,
            tuple(item.fingerprint for item in self.entries),
            self.completeness,
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointVerificationFact:
    entry_fingerprint: RepositoryFingerprint
    observed_content_fingerprint: RepositoryFingerprint | None
    observed_metadata_fingerprint: RepositoryFingerprint | None
    state: RepositoryRestorePointVerificationState


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointDiagnostic:
    code: RepositoryRestorePointDiagnosticCode
    path_fingerprint: RepositoryFingerprint | None = None
    entry_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositoryRestorePointDiagnostic) -> tuple[str, str, str]:
    return (
        item.code.value,
        item.path_fingerprint.value if item.path_fingerprint else "",
        item.entry_fingerprint.value if item.entry_fingerprint else "",
    )


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointVerification:
    manifest_fingerprint: RepositoryFingerprint
    state: RepositoryRestorePointVerificationState
    completeness: RepositoryObservationCompleteness
    verified_entries: tuple[RepositoryFingerprint, ...]
    recoverable: bool
    diagnostics: tuple[RepositoryRestorePointDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "verified_entries",
            tuple(sorted(set(self.verified_entries), key=lambda item: item.value)),
        )
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )
        if self.recoverable and (
            self.state is not RepositoryRestorePointVerificationState.VERIFIED
            or self.completeness is not RepositoryObservationCompleteness.COMPLETE
            or self.diagnostics
        ):
            raise InvalidRepositoryRestorePointModel(
                "recoverable requires complete verified correspondence"
            )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryRestorePointResult:
    request_fingerprint: RepositoryFingerprint
    requirement: RepositoryRestorePointRequirement | None
    manifest: RepositoryRestorePointManifest | None
    verification: RepositoryRestorePointVerification | None
    diagnostics: tuple[RepositoryRestorePointDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (
                self.request_fingerprint,
                self.requirement,
                self.manifest,
                self.verification,
                self.diagnostics,
            )
        )


class RepositoryRestorePointService:
    """Plan and verify logical restore points without creating or reading backups."""

    _blocking = {
        RepositoryRestorePointDiagnosticCode.BASE_SNAPSHOT_MISMATCH,
        RepositoryRestorePointDiagnosticCode.MUTATION_PLAN_MISMATCH,
        RepositoryRestorePointDiagnosticCode.AUTHORIZATION_ASSESSMENT_MISMATCH,
        RepositoryRestorePointDiagnosticCode.AUTHORIZATION_CORRESPONDENCE_REQUIRED,
        RepositoryRestorePointDiagnosticCode.REPOSITORY_MISMATCH,
        RepositoryRestorePointDiagnosticCode.CHECKOUT_MISMATCH,
        RepositoryRestorePointDiagnosticCode.WORKTREE_MISMATCH,
        RepositoryRestorePointDiagnosticCode.PLATFORM_MISMATCH,
        RepositoryRestorePointDiagnosticCode.SENSITIVE_CONTENT_BLOCKED,
        RepositoryRestorePointDiagnosticCode.TOPOLOGY_BOUNDARY_TRAVERSAL,
    }

    def plan(
        self,
        request: RepositoryRestorePointRequest,
        policy: RepositoryRestorePointPolicy,
        base: RepositorySnapshot,
        mutation_plan: RepositoryMutationPlan,
        authorization: RepositoryAuthorizationAssessment,
    ) -> RepositoryRestorePointResult:
        diagnostics: set[RepositoryRestorePointDiagnostic] = set()
        self._correspondence(request, base, mutation_plan, authorization, diagnostics)
        coverage = self._coverage(policy, base, mutation_plan, diagnostics)
        if any(item.code in self._blocking for item in diagnostics):
            return RepositoryRestorePointResult(
                request.fingerprint, None, None, None, tuple(diagnostics)
            )
        complete = not diagnostics and all(
            item.completeness is RepositoryObservationCompleteness.COMPLETE
            for item in coverage
        )
        requirement = RepositoryRestorePointRequirement(
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
            base.fingerprint,
            mutation_plan.fingerprint,
            authorization.fingerprint,
            policy.policy_id,
            policy.policy_version,
            tuple(coverage),
            RepositoryObservationCompleteness.COMPLETE
            if complete
            else RepositoryObservationCompleteness.PARTIAL,
        )
        return RepositoryRestorePointResult(
            request.fingerprint, requirement, None, None, tuple(diagnostics)
        )

    def evaluate(
        self,
        request: RepositoryRestorePointRequest,
        policy: RepositoryRestorePointPolicy,
        base: RepositorySnapshot,
        mutation_plan: RepositoryMutationPlan,
        authorization: RepositoryAuthorizationAssessment,
        manifest: RepositoryRestorePointManifest,
        verification_facts: tuple[RepositoryRestorePointVerificationFact, ...],
    ) -> RepositoryRestorePointResult:
        planned = self.plan(request, policy, base, mutation_plan, authorization)
        diagnostics = set(planned.diagnostics)
        requirement = planned.requirement
        if requirement is None:
            return planned
        self._manifest_correspondence(requirement, manifest, diagnostics)
        self._manifest_entries(policy, requirement, manifest, diagnostics)
        verification = self._verification(
            policy, manifest, verification_facts, diagnostics
        )
        return RepositoryRestorePointResult(
            request.fingerprint,
            requirement,
            manifest,
            verification,
            tuple(diagnostics),
        )

    @staticmethod
    def _correspondence(request, base, mutation_plan, authorization, diagnostics) -> None:
        def add(code):
            diagnostics.add(RepositoryRestorePointDiagnostic(code))

        if request.base_snapshot_fingerprint != base.fingerprint or mutation_plan.base_snapshot_fingerprint != base.fingerprint:
            add(RepositoryRestorePointDiagnosticCode.BASE_SNAPSHOT_MISMATCH)
        if request.mutation_plan_fingerprint != mutation_plan.fingerprint:
            add(RepositoryRestorePointDiagnosticCode.MUTATION_PLAN_MISMATCH)
        if request.authorization_assessment_fingerprint != authorization.fingerprint:
            add(RepositoryRestorePointDiagnosticCode.AUTHORIZATION_ASSESSMENT_MISMATCH)
        if authorization.mutation_plan_fingerprint != mutation_plan.fingerprint:
            add(RepositoryRestorePointDiagnosticCode.AUTHORIZATION_ASSESSMENT_MISMATCH)
        if authorization.outcome is not RepositoryAuthorizationOutcome.SATISFIED:
            add(RepositoryRestorePointDiagnosticCode.AUTHORIZATION_CORRESPONDENCE_REQUIRED)
        for code, values in (
            (RepositoryRestorePointDiagnosticCode.REPOSITORY_MISMATCH, (request.repository_id, base.repository_id, mutation_plan.repository_id, authorization.repository_id)),
            (RepositoryRestorePointDiagnosticCode.CHECKOUT_MISMATCH, (request.checkout_id, base.checkout_id, mutation_plan.checkout_id, authorization.checkout_id)),
            (RepositoryRestorePointDiagnosticCode.WORKTREE_MISMATCH, (request.worktree_id, base.worktree_id, mutation_plan.worktree_id, authorization.worktree_id)),
            (RepositoryRestorePointDiagnosticCode.PLATFORM_MISMATCH, (request.platform_profile, base.platform_profile, mutation_plan.platform_profile)),
        ):
            if len(set(values)) != 1:
                add(code)

    def _coverage(self, policy, base, mutation_plan, diagnostics):
        by_path = {item.path.value: item for item in base.entries}
        result: list[RepositoryRestorePointCoverageRequirement] = []
        for operation in mutation_plan.operations:
            if operation.kind not in policy.required_operations:
                continue
            before = by_path.get(operation.source_path.value if operation.source_path else operation.path.value)
            kind = {
                RepositoryMutationOperationKind.CREATE: RepositoryRestorePointCoverageKind.CREATED_ABSENCE,
                RepositoryMutationOperationKind.REPLACE: RepositoryRestorePointCoverageKind.REPLACED_CONTENT,
                RepositoryMutationOperationKind.APPEND: RepositoryRestorePointCoverageKind.REPLACED_CONTENT,
                RepositoryMutationOperationKind.DELETE: RepositoryRestorePointCoverageKind.DELETED_CONTENT,
                RepositoryMutationOperationKind.MOVE: RepositoryRestorePointCoverageKind.MOVE_SOURCE,
                RepositoryMutationOperationKind.COPY: RepositoryRestorePointCoverageKind.CREATED_ABSENCE,
                RepositoryMutationOperationKind.METADATA_UPDATE: RepositoryRestorePointCoverageKind.METADATA,
                RepositoryMutationOperationKind.CLASSIFICATION_UPDATE: RepositoryRestorePointCoverageKind.METADATA,
            }[operation.kind]
            classification = before.classification if before else None
            handling = self._handling(policy, classification)
            if handling is RepositoryRestorePointMaterialHandling.BLOCK:
                code = (
                    RepositoryRestorePointDiagnosticCode.SENSITIVE_CONTENT_BLOCKED
                    if classification and classification.sensitivity is RepositorySensitivity.SECRET_RISK
                    else RepositoryRestorePointDiagnosticCode.COVERAGE_INCOMPLETE
                )
                diagnostics.add(RepositoryRestorePointDiagnostic(code, RepositoryFingerprint.from_content(operation.path)))
                continue
            if handling is RepositoryRestorePointMaterialHandling.EXCLUDE:
                continue
            if before and before.topology in {RepositoryTopology.SUBMODULE, RepositoryTopology.NESTED_REPOSITORY, RepositoryTopology.SPARSE_EXCLUDED}:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.TOPOLOGY_BOUNDARY_TRAVERSAL, before.path_fingerprint))
                continue
            path_fingerprint = RepositoryFingerprint.from_content(operation.source_path or operation.path)
            result.append(self._required_entry(path_fingerprint, kind, before, classification))
            if operation.kind is RepositoryMutationOperationKind.MOVE:
                result.append(self._required_entry(RepositoryFingerprint.from_content(operation.path), RepositoryRestorePointCoverageKind.MOVE_DESTINATION, None, None))
            if policy.cover_untracked_collisions:
                collision = by_path.get(operation.path.value)
                if collision and collision.classification.tracking is RepositoryGitTracking.UNTRACKED:
                    result.append(self._required_entry(collision.path_fingerprint, RepositoryRestorePointCoverageKind.UNTRACKED_COLLISION, collision, collision.classification))
            if RepositoryRestorePointDimension.TOPOLOGY in policy.required_dimensions:
                result.append(self._required_entry(path_fingerprint, RepositoryRestorePointCoverageKind.TOPOLOGY_BOUNDARY, before, classification))
        global_items = (
            (RepositoryRestorePointDimension.HEAD, RepositoryRestorePointCoverageKind.HEAD_STATE, base.head_fingerprint),
            (RepositoryRestorePointDimension.BRANCH, RepositoryRestorePointCoverageKind.BRANCH_STATE, RepositoryFingerprint.from_content((base.head.kind, base.branch_reference))),
            (RepositoryRestorePointDimension.INDEX, RepositoryRestorePointCoverageKind.INDEX_STATE, base.index_fingerprint),
        )
        for dimension, kind, fingerprint in global_items:
            if dimension in policy.required_dimensions:
                result.append(RepositoryRestorePointCoverageRequirement(fingerprint, None, None, None, kind, RepositoryObservationCompleteness.COMPLETE, None))
        return result

    @staticmethod
    def _handling(policy, classification):
        if classification is None:
            return RepositoryRestorePointMaterialHandling.INCLUDE
        if classification.sensitivity is RepositorySensitivity.SECRET_RISK:
            return policy.secret_risk_handling
        return {
            RepositoryMaterialRole.GENERATED: policy.generated_handling,
            RepositoryMaterialRole.ARTIFACT: policy.artifact_handling,
            RepositoryMaterialRole.RUNTIME_STATE: policy.runtime_state_handling,
        }.get(classification.material_role, RepositoryRestorePointMaterialHandling.INCLUDE)

    @staticmethod
    def _required_entry(path_fingerprint, kind, before, classification):
        return RepositoryRestorePointCoverageRequirement(
            path_fingerprint,
            before.content_fingerprint if before else None,
            before.metadata_fingerprint if before else None,
            before.content_length if before else 0,
            kind,
            before.completeness if before else RepositoryObservationCompleteness.COMPLETE,
            classification,
        )

    @staticmethod
    def _manifest_correspondence(requirement, manifest, diagnostics) -> None:
        checks = (
            (manifest.repository_id == requirement.repository_id, RepositoryRestorePointDiagnosticCode.REPOSITORY_MISMATCH),
            (manifest.checkout_id == requirement.checkout_id, RepositoryRestorePointDiagnosticCode.CHECKOUT_MISMATCH),
            (manifest.worktree_id == requirement.worktree_id, RepositoryRestorePointDiagnosticCode.WORKTREE_MISMATCH),
            (manifest.platform_profile == requirement.platform_profile, RepositoryRestorePointDiagnosticCode.PLATFORM_MISMATCH),
            (manifest.base_snapshot_fingerprint == requirement.base_snapshot_fingerprint, RepositoryRestorePointDiagnosticCode.BASE_SNAPSHOT_MISMATCH),
            (manifest.mutation_plan_fingerprint == requirement.mutation_plan_fingerprint, RepositoryRestorePointDiagnosticCode.MUTATION_PLAN_MISMATCH),
            (manifest.authorization_assessment_fingerprint == requirement.authorization_assessment_fingerprint, RepositoryRestorePointDiagnosticCode.AUTHORIZATION_ASSESSMENT_MISMATCH),
            (manifest.requirement_fingerprint == requirement.fingerprint, RepositoryRestorePointDiagnosticCode.COVERAGE_INCOMPLETE),
        )
        for matched, code in checks:
            if not matched:
                diagnostics.add(RepositoryRestorePointDiagnostic(code))

    @staticmethod
    def _manifest_entries(policy, requirement, manifest, diagnostics) -> None:
        entries = {(item.path_fingerprint, item.coverage_kind): item for item in manifest.entries}
        required = {(item.path_fingerprint, item.coverage_kind): item for item in requirement.coverage}
        if len({item.logical_storage_reference for item in manifest.entries}) != len(manifest.entries):
            diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.LOGICAL_REFERENCE_DUPLICATE))
        if len(manifest.entries) > policy.maximum_entries:
            diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.ENTRY_LIMIT_EXCEEDED))
        total = sum(item.size or 0 for item in manifest.entries)
        if total > policy.maximum_total_size:
            diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.MANIFEST_OVERSIZED))
        for key, needed in required.items():
            entry = entries.get(key)
            if entry is None:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.REQUIRED_ENTRY_MISSING, needed.path_fingerprint))
                continue
            if entry.expected_content_fingerprint != needed.expected_content_fingerprint or entry.expected_metadata_fingerprint != needed.expected_metadata_fingerprint:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.ENTRY_FINGERPRINT_MISMATCH, entry.path_fingerprint, entry.fingerprint))
            if (entry.integrity_algorithm, entry.integrity_version) not in policy.accepted_integrity_algorithms:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.ALGORITHM_UNSUPPORTED, entry.path_fingerprint, entry.fingerprint))
            if entry.size is not None and entry.size > policy.maximum_entry_size:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.ENTRY_OVERSIZED, entry.path_fingerprint, entry.fingerprint))
            if entry.completeness is not RepositoryObservationCompleteness.COMPLETE:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.MANIFEST_INCOMPLETE, entry.path_fingerprint, entry.fingerprint))
        for key, entry in entries.items():
            if key not in required:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.ENTRY_OUTSIDE_MUTATION_SCOPE, entry.path_fingerprint, entry.fingerprint))
        if manifest.completeness is not RepositoryObservationCompleteness.COMPLETE:
            diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.MANIFEST_INCOMPLETE))

    @staticmethod
    def _verification(policy, manifest, facts, diagnostics):
        by_entry = {item.entry_fingerprint: item for item in facts}
        verified: list[RepositoryFingerprint] = []
        state = RepositoryRestorePointVerificationState.VERIFIED
        for entry in manifest.entries:
            fact = by_entry.get(entry.fingerprint)
            if fact is None:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.VERIFICATION_MISSING, entry.path_fingerprint, entry.fingerprint))
                state = RepositoryRestorePointVerificationState.INCOMPLETE
                continue
            if fact.state is not RepositoryRestorePointVerificationState.VERIFIED:
                code = {
                    RepositoryRestorePointVerificationState.CORRUPT: RepositoryRestorePointDiagnosticCode.VERIFICATION_CORRUPT,
                    RepositoryRestorePointVerificationState.UNAVAILABLE: RepositoryRestorePointDiagnosticCode.VERIFICATION_UNAVAILABLE,
                }.get(fact.state, RepositoryRestorePointDiagnosticCode.VERIFICATION_MISMATCH)
                diagnostics.add(RepositoryRestorePointDiagnostic(code, entry.path_fingerprint, entry.fingerprint))
                state = fact.state
                continue
            if fact.observed_content_fingerprint != entry.expected_content_fingerprint or fact.observed_metadata_fingerprint != entry.expected_metadata_fingerprint:
                diagnostics.add(RepositoryRestorePointDiagnostic(RepositoryRestorePointDiagnosticCode.VERIFICATION_MISMATCH, entry.path_fingerprint, entry.fingerprint))
                state = RepositoryRestorePointVerificationState.MISMATCH
                continue
            verified.append(entry.fingerprint)
        if any(item.code is RepositoryRestorePointDiagnosticCode.SENSITIVE_CONTENT_BLOCKED for item in diagnostics):
            state = RepositoryRestorePointVerificationState.SENSITIVE_CONTENT_BLOCKED
        elif any(item.code in {RepositoryRestorePointDiagnosticCode.ENTRY_OVERSIZED, RepositoryRestorePointDiagnosticCode.MANIFEST_OVERSIZED, RepositoryRestorePointDiagnosticCode.ENTRY_LIMIT_EXCEEDED} for item in diagnostics):
            state = RepositoryRestorePointVerificationState.OVERSIZED
        elif any(item.code is RepositoryRestorePointDiagnosticCode.ALGORITHM_UNSUPPORTED for item in diagnostics):
            state = RepositoryRestorePointVerificationState.UNSUPPORTED
        elif any(
            item.code
            in {
                RepositoryRestorePointDiagnosticCode.ENTRY_FINGERPRINT_MISMATCH,
                RepositoryRestorePointDiagnosticCode.LOGICAL_REFERENCE_DUPLICATE,
                RepositoryRestorePointDiagnosticCode.ENTRY_OUTSIDE_MUTATION_SCOPE,
                RepositoryRestorePointDiagnosticCode.BASE_SNAPSHOT_MISMATCH,
                RepositoryRestorePointDiagnosticCode.MUTATION_PLAN_MISMATCH,
                RepositoryRestorePointDiagnosticCode.AUTHORIZATION_ASSESSMENT_MISMATCH,
            }
            for item in diagnostics
        ):
            state = RepositoryRestorePointVerificationState.MISMATCH
        elif any(
            item.code
            in {
                RepositoryRestorePointDiagnosticCode.REQUIRED_ENTRY_MISSING,
                RepositoryRestorePointDiagnosticCode.COVERAGE_INCOMPLETE,
                RepositoryRestorePointDiagnosticCode.MANIFEST_INCOMPLETE,
                RepositoryRestorePointDiagnosticCode.VERIFICATION_MISSING,
            }
            for item in diagnostics
        ):
            state = RepositoryRestorePointVerificationState.INCOMPLETE
        if policy.verification_required and not facts:
            state = RepositoryRestorePointVerificationState.UNAVAILABLE
        recoverable = state is RepositoryRestorePointVerificationState.VERIFIED and not diagnostics and len(verified) == len(manifest.entries)
        return RepositoryRestorePointVerification(
            manifest.fingerprint,
            state,
            RepositoryObservationCompleteness.COMPLETE if recoverable else RepositoryObservationCompleteness.PARTIAL,
            tuple(verified),
            recoverable,
            tuple(diagnostics),
        )
