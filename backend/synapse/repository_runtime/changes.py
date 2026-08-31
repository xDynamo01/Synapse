"""Pure factual change-set construction between compatible repository snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .errors import InvalidRepositoryChangeSetModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPath, RepositoryPathClassification, RepositoryPlatformProfile
from .snapshot import RepositorySnapshot, RepositorySnapshotEntry
from .states import (
    RepositoryChangeAxisState,
    RepositoryChangeType,
    RepositoryObservationCompleteness,
    RepositorySensitivity,
    RepositoryTopology,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class RepositoryChangeDiagnosticCode(StrEnum):
    BASE_FINGERPRINT_MISMATCH = "base_fingerprint_mismatch"
    TARGET_FINGERPRINT_MISMATCH = "target_fingerprint_mismatch"
    REPOSITORY_MISMATCH = "repository_mismatch"
    CHECKOUT_MISMATCH = "checkout_mismatch"
    WORKTREE_MISMATCH = "worktree_mismatch"
    PLATFORM_MISMATCH = "platform_mismatch"
    IDENTICAL_SNAPSHOTS = "identical_snapshots"
    SNAPSHOT_ORDER_INVALID = "snapshot_order_invalid"
    SNAPSHOT_INCOMPLETE = "snapshot_incomplete"
    PATH_DUPLICATE = "path_duplicate"
    PATH_COLLISION = "path_collision"
    CHANGE_FACT_DUPLICATE = "change_fact_duplicate"
    CHANGE_FACT_CONTRADICTORY = "change_fact_contradictory"
    RENAME_ENDPOINT_MISSING = "rename_endpoint_missing"
    RENAME_EVIDENCE_REQUIRED = "rename_evidence_required"
    COPY_SOURCE_INVALID = "copy_source_invalid"
    COPY_EVIDENCE_REQUIRED = "copy_evidence_required"
    REPOSITORY_BOUNDARY_TRAVERSAL = "repository_boundary_traversal"
    SENSITIVITY_REDUCTION = "sensitivity_reduction"
    FACTS_INCOMPLETE = "facts_incomplete"


@dataclass(frozen=True, slots=True)
class RepositoryChangeSetPolicy:
    policy_id: str
    policy_version: str
    allow_content_identity_rename_inference: bool = False
    allow_content_identity_copy_inference: bool = False
    require_complete_snapshots: bool = True

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(self.policy_version):
            raise InvalidRepositoryChangeSetModel("change-set policy identity is invalid")


@dataclass(frozen=True, slots=True)
class RepositoryChangeSetRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    base_order: int
    target_order: int
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.base_order < 0 or self.target_order < 0:
            raise InvalidRepositoryChangeSetModel("snapshot order cannot be negative")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryChangeSetModel("occurrence metadata is invalid")
        object.__setattr__(self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata))))

    def semantic_content(self) -> object:
        return (
            self.repository_id,
            self.checkout_id,
            self.worktree_id,
            self.platform_profile,
            self.base_snapshot_fingerprint,
            self.target_snapshot_fingerprint,
            self.base_order,
            self.target_order,
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryChangeFact:
    change_type: RepositoryChangeType
    before_path: RepositoryPath | None
    after_path: RepositoryPath | None
    base_entry_fingerprint: RepositoryFingerprint | None
    target_entry_fingerprint: RepositoryFingerprint | None
    base_content_fingerprint: RepositoryFingerprint | None
    target_content_fingerprint: RepositoryFingerprint | None
    base_content_length: int | None
    target_content_length: int | None
    classification_before: RepositoryPathClassification | None
    classification_after: RepositoryPathClassification | None
    completeness: RepositoryObservationCompleteness
    evidence_reference: str | None = None
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.base_content_length is not None and self.base_content_length < 0:
            raise InvalidRepositoryChangeSetModel("base content length cannot be negative")
        if self.target_content_length is not None and self.target_content_length < 0:
            raise InvalidRepositoryChangeSetModel("target content length cannot be negative")
        if self.evidence_reference is not None and not _REFERENCE.fullmatch(self.evidence_reference):
            raise InvalidRepositoryChangeSetModel("change evidence reference is invalid")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryChangeSetModel("occurrence metadata is invalid")
        object.__setattr__(self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata))))

    def semantic_content(self) -> object:
        return (
            self.change_type,
            self.before_path,
            self.after_path,
            self.base_entry_fingerprint,
            self.target_entry_fingerprint,
            self.base_content_fingerprint,
            self.target_content_fingerprint,
            self.base_content_length,
            self.target_content_length,
            self.classification_before,
            self.classification_after,
            self.completeness,
            self.evidence_reference,
        )


@dataclass(frozen=True, slots=True)
class RepositoryChangeAxes:
    content: RepositoryChangeAxisState
    metadata: RepositoryChangeAxisState
    tracking: RepositoryChangeAxisState
    material_role: RepositoryChangeAxisState
    sensitivity: RepositoryChangeAxisState
    topology: RepositoryChangeAxisState


@dataclass(frozen=True, slots=True)
class RepositoryChangeEntry:
    change_type: RepositoryChangeType
    before_path: RepositoryPath | None
    after_path: RepositoryPath | None
    base_entry_fingerprint: RepositoryFingerprint | None
    target_entry_fingerprint: RepositoryFingerprint | None
    base_content_fingerprint: RepositoryFingerprint | None
    target_content_fingerprint: RepositoryFingerprint | None
    base_content_length: int | None
    target_content_length: int | None
    classification_before: RepositoryPathClassification | None
    classification_after: RepositoryPathClassification | None
    axes: RepositoryChangeAxes
    completeness: RepositoryObservationCompleteness
    evidence_reference: str | None = None

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryChangeDiagnostic:
    code: RepositoryChangeDiagnosticCode
    before_path_fingerprint: RepositoryFingerprint | None = None
    after_path_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositoryChangeDiagnostic) -> tuple[str, str, str]:
    return (
        item.code.value,
        item.before_path_fingerprint.value if item.before_path_fingerprint else "",
        item.after_path_fingerprint.value if item.after_path_fingerprint else "",
    )


def _entry_key(entry: RepositoryChangeEntry) -> tuple[str, str, str]:
    return (
        entry.before_path.value if entry.before_path is not None else "",
        entry.after_path.value if entry.after_path is not None else "",
        entry.change_type.value,
    )


@dataclass(frozen=True, slots=True)
class RepositoryChangeSet:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    completeness: RepositoryObservationCompleteness
    entries: tuple[RepositoryChangeEntry, ...]
    diagnostics: tuple[RepositoryChangeDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=_entry_key)))
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryChangeSetResult:
    request_fingerprint: RepositoryFingerprint
    change_set: RepositoryChangeSet | None
    diagnostics: tuple[RepositoryChangeDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (self.request_fingerprint, self.change_set, self.diagnostics)
        )


class RepositoryChangeSetService:
    """Describe differences only; never plan, authorize or apply repository changes."""

    _blocking = {
        RepositoryChangeDiagnosticCode.BASE_FINGERPRINT_MISMATCH,
        RepositoryChangeDiagnosticCode.TARGET_FINGERPRINT_MISMATCH,
        RepositoryChangeDiagnosticCode.REPOSITORY_MISMATCH,
        RepositoryChangeDiagnosticCode.CHECKOUT_MISMATCH,
        RepositoryChangeDiagnosticCode.WORKTREE_MISMATCH,
        RepositoryChangeDiagnosticCode.PLATFORM_MISMATCH,
        RepositoryChangeDiagnosticCode.IDENTICAL_SNAPSHOTS,
        RepositoryChangeDiagnosticCode.SNAPSHOT_ORDER_INVALID,
    }

    def compare(
        self,
        request: RepositoryChangeSetRequest,
        policy: RepositoryChangeSetPolicy,
        base: RepositorySnapshot,
        target: RepositorySnapshot,
        facts: tuple[RepositoryChangeFact, ...] = (),
    ) -> RepositoryChangeSetResult:
        diagnostics: set[RepositoryChangeDiagnostic] = set()

        def add(
            code: RepositoryChangeDiagnosticCode,
            before: RepositoryPath | None = None,
            after: RepositoryPath | None = None,
        ) -> None:
            diagnostics.add(
                RepositoryChangeDiagnostic(
                    code,
                    RepositoryFingerprint.from_content(before) if before is not None else None,
                    RepositoryFingerprint.from_content(after) if after is not None else None,
                )
            )

        self._compatibility(request, policy, base, target, add)
        base_by_path = self._entry_map(base.entries, add)
        target_by_path = self._entry_map(target.entries, add)
        self._collisions(base.entries, target.entries, add)
        if any(item.code in self._blocking for item in diagnostics):
            return RepositoryChangeSetResult(request.fingerprint, None, tuple(diagnostics))

        consumed_base: set[str] = set()
        consumed_target: set[str] = set()
        entries = self._explicit_entries(
            facts,
            base_by_path,
            target_by_path,
            consumed_base,
            consumed_target,
            diagnostics,
            add,
        )
        if policy.allow_content_identity_rename_inference:
            entries.extend(
                self._infer_renames(
                    policy, base_by_path, target_by_path, consumed_base, consumed_target
                )
            )
        if policy.allow_content_identity_copy_inference:
            entries.extend(
                self._infer_copies(
                    policy, base_by_path, target_by_path, consumed_target
                )
            )
        entries.extend(
            self._ordinary_entries(base_by_path, target_by_path, consumed_base, consumed_target)
        )

        for entry in entries:
            if self._crosses_repository_boundary(entry, base_by_path, target_by_path):
                add(
                    RepositoryChangeDiagnosticCode.REPOSITORY_BOUNDARY_TRAVERSAL,
                    entry.before_path,
                    entry.after_path,
                )
            if self._reduces_sensitivity(entry):
                add(
                    RepositoryChangeDiagnosticCode.SENSITIVITY_REDUCTION,
                    entry.before_path,
                    entry.after_path,
                )
        complete = (
            base.completeness is RepositoryObservationCompleteness.COMPLETE
            and target.completeness is RepositoryObservationCompleteness.COMPLETE
            and all(
                entry.completeness is RepositoryObservationCompleteness.COMPLETE
                for entry in entries
            )
            and not diagnostics
        )
        change_set = RepositoryChangeSet(
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
            base.fingerprint,
            target.fingerprint,
            policy.policy_id,
            policy.policy_version,
            RepositoryObservationCompleteness.COMPLETE
            if complete
            else RepositoryObservationCompleteness.PARTIAL,
            tuple(entries),
            tuple(diagnostics),
        )
        return RepositoryChangeSetResult(request.fingerprint, change_set, tuple(diagnostics))

    @staticmethod
    def _compatibility(request, policy, base, target, add) -> None:
        if request.base_snapshot_fingerprint != base.fingerprint:
            add(RepositoryChangeDiagnosticCode.BASE_FINGERPRINT_MISMATCH)
        if request.target_snapshot_fingerprint != target.fingerprint:
            add(RepositoryChangeDiagnosticCode.TARGET_FINGERPRINT_MISMATCH)
        if base.repository_id != target.repository_id or base.repository_id != request.repository_id:
            add(RepositoryChangeDiagnosticCode.REPOSITORY_MISMATCH)
        if base.checkout_id != target.checkout_id or base.checkout_id != request.checkout_id:
            add(RepositoryChangeDiagnosticCode.CHECKOUT_MISMATCH)
        if base.worktree_id != target.worktree_id or base.worktree_id != request.worktree_id:
            add(RepositoryChangeDiagnosticCode.WORKTREE_MISMATCH)
        if base.platform_profile != target.platform_profile or base.platform_profile != request.platform_profile:
            add(RepositoryChangeDiagnosticCode.PLATFORM_MISMATCH)
        if base.fingerprint == target.fingerprint:
            add(RepositoryChangeDiagnosticCode.IDENTICAL_SNAPSHOTS)
        if request.base_order >= request.target_order:
            add(RepositoryChangeDiagnosticCode.SNAPSHOT_ORDER_INVALID)
        if policy.require_complete_snapshots and (
            base.completeness is not RepositoryObservationCompleteness.COMPLETE
            or target.completeness is not RepositoryObservationCompleteness.COMPLETE
        ):
            add(RepositoryChangeDiagnosticCode.SNAPSHOT_INCOMPLETE)

    @staticmethod
    def _entry_map(entries, add) -> dict[str, RepositorySnapshotEntry]:
        result: dict[str, RepositorySnapshotEntry] = {}
        for entry in entries:
            if entry.path.value in result:
                add(RepositoryChangeDiagnosticCode.PATH_DUPLICATE, entry.path, entry.path)
            result[entry.path.value] = entry
        return result

    @staticmethod
    def _collisions(base_entries, target_entries, add) -> None:
        for entries in (base_entries, target_entries):
            seen: set[str] = set()
            for entry in entries:
                canonical = entry.path.value
                if canonical in seen:
                    add(RepositoryChangeDiagnosticCode.PATH_COLLISION, entry.path, entry.path)
                seen.add(canonical)

    def _explicit_entries(
        self,
        facts,
        base_by_path,
        target_by_path,
        consumed_base,
        consumed_target,
        diagnostics,
        add,
    ) -> list[RepositoryChangeEntry]:
        result: list[RepositoryChangeEntry] = []
        seen: set[tuple[str, str, str]] = set()
        for fact in sorted(facts, key=lambda item: repr(item.semantic_content())):
            key = (
                fact.change_type.value,
                fact.before_path.value if fact.before_path else "",
                fact.after_path.value if fact.after_path else "",
            )
            if key in seen:
                add(RepositoryChangeDiagnosticCode.CHANGE_FACT_DUPLICATE, fact.before_path, fact.after_path)
                continue
            seen.add(key)
            before = base_by_path.get(fact.before_path.value) if fact.before_path else None
            after = target_by_path.get(fact.after_path.value) if fact.after_path else None
            if fact.change_type is RepositoryChangeType.RENAMED:
                if before is None or after is None:
                    add(RepositoryChangeDiagnosticCode.RENAME_ENDPOINT_MISSING, fact.before_path, fact.after_path)
                    continue
                if fact.evidence_reference is None:
                    add(RepositoryChangeDiagnosticCode.RENAME_EVIDENCE_REQUIRED, fact.before_path, fact.after_path)
                    continue
            elif fact.change_type is RepositoryChangeType.COPIED:
                if before is None:
                    add(RepositoryChangeDiagnosticCode.COPY_SOURCE_INVALID, fact.before_path, fact.after_path)
                    continue
                if after is None or fact.evidence_reference is None:
                    add(RepositoryChangeDiagnosticCode.COPY_EVIDENCE_REQUIRED, fact.before_path, fact.after_path)
                    continue
            elif fact.change_type in {
                RepositoryChangeType.CONFLICT,
                RepositoryChangeType.UNKNOWN,
            }:
                if before is None and after is None:
                    add(
                        RepositoryChangeDiagnosticCode.CHANGE_FACT_CONTRADICTORY,
                        fact.before_path,
                        fact.after_path,
                    )
                    continue
            else:
                add(RepositoryChangeDiagnosticCode.CHANGE_FACT_CONTRADICTORY, fact.before_path, fact.after_path)
                continue
            if not self._fact_matches(fact, before, after):
                add(RepositoryChangeDiagnosticCode.CHANGE_FACT_CONTRADICTORY, fact.before_path, fact.after_path)
                continue
            if before is not None:
                consumed_base.add(before.path.value)
            if after is not None:
                consumed_target.add(after.path.value)
            if fact.completeness is not RepositoryObservationCompleteness.COMPLETE:
                add(RepositoryChangeDiagnosticCode.FACTS_INCOMPLETE, fact.before_path, fact.after_path)
            result.append(self._entry(fact.change_type, before, after, fact.evidence_reference, fact.completeness))
        return result

    @staticmethod
    def _fact_matches(fact, before, after) -> bool:
        return (
            fact.base_entry_fingerprint
            == (RepositoryFingerprint.from_content(before) if before is not None else None)
            and fact.target_entry_fingerprint
            == (RepositoryFingerprint.from_content(after) if after is not None else None)
            and fact.base_content_fingerprint
            == (before.content_fingerprint if before is not None else None)
            and fact.target_content_fingerprint
            == (after.content_fingerprint if after is not None else None)
            and fact.base_content_length == (before.content_length if before is not None else None)
            and fact.target_content_length == (after.content_length if after is not None else None)
            and fact.classification_before == (before.classification if before is not None else None)
            and fact.classification_after == (after.classification if after is not None else None)
        )

    def _ordinary_entries(self, base_by_path, target_by_path, consumed_base, consumed_target):
        result: list[RepositoryChangeEntry] = []
        for value in sorted(set(base_by_path) | set(target_by_path)):
            if value in consumed_base or value in consumed_target:
                continue
            before = base_by_path.get(value)
            after = target_by_path.get(value)
            if before is None:
                result.append(self._entry(RepositoryChangeType.ADDED, None, after, None))
            elif after is None:
                result.append(self._entry(RepositoryChangeType.DELETED, before, None, None))
            elif before != after:
                result.append(self._entry(self._primary_type(before, after), before, after, None))
        return result

    def _infer_renames(self, policy, base_by_path, target_by_path, consumed_base, consumed_target):
        deleted = [entry for key, entry in base_by_path.items() if key not in target_by_path]
        added = [entry for key, entry in target_by_path.items() if key not in base_by_path]
        result: list[RepositoryChangeEntry] = []
        for before in deleted:
            matches = [
                after
                for after in added
                if after.path.value not in consumed_target
                and before.content_fingerprint is not None
                and before.content_fingerprint == after.content_fingerprint
            ]
            if len(matches) == 1:
                after = matches[0]
                consumed_base.add(before.path.value)
                consumed_target.add(after.path.value)
                result.append(
                    self._entry(
                        RepositoryChangeType.RENAMED,
                        before,
                        after,
                        f"policy:{policy.policy_id}:{policy.policy_version}",
                    )
                )
        return result

    def _infer_copies(self, policy, base_by_path, target_by_path, consumed_target):
        result: list[RepositoryChangeEntry] = []
        for value, after in target_by_path.items():
            if value in base_by_path or value in consumed_target or after.content_fingerprint is None:
                continue
            matches = [
                before
                for before in base_by_path.values()
                if before.content_fingerprint == after.content_fingerprint
            ]
            if len(matches) == 1:
                consumed_target.add(value)
                result.append(
                    self._entry(
                        RepositoryChangeType.COPIED,
                        matches[0],
                        after,
                        f"policy:{policy.policy_id}:{policy.policy_version}",
                    )
                )
        return result

    @staticmethod
    def _primary_type(before, after) -> RepositoryChangeType:
        if before.resource_kind != after.resource_kind:
            return RepositoryChangeType.TYPE_CHANGED
        if before.content_fingerprint != after.content_fingerprint:
            return RepositoryChangeType.MODIFIED
        if before.classification != after.classification:
            return RepositoryChangeType.CLASSIFICATION_CHANGED
        if (
            before.metadata_fingerprint != after.metadata_fingerprint
            or before.content_length != after.content_length
        ):
            return RepositoryChangeType.METADATA_CHANGED
        return RepositoryChangeType.UNKNOWN

    @staticmethod
    def _entry(change_type, before, after, evidence, completeness=None):
        complete = completeness or (
            RepositoryObservationCompleteness.COMPLETE
            if (before is None or before.completeness is RepositoryObservationCompleteness.COMPLETE)
            and (after is None or after.completeness is RepositoryObservationCompleteness.COMPLETE)
            else RepositoryObservationCompleteness.PARTIAL
        )
        axes = RepositoryChangeSetService._axes(before, after)
        if change_type is RepositoryChangeType.CONFLICT:
            axes = RepositoryChangeAxes(
                RepositoryChangeAxisState.CONFLICT,
                RepositoryChangeAxisState.CONFLICT,
                RepositoryChangeAxisState.CONFLICT,
                RepositoryChangeAxisState.CONFLICT,
                RepositoryChangeAxisState.CONFLICT,
                RepositoryChangeAxisState.CONFLICT,
            )
        return RepositoryChangeEntry(
            change_type,
            before.path if before else None,
            after.path if after else None,
            RepositoryFingerprint.from_content(before) if before else None,
            RepositoryFingerprint.from_content(after) if after else None,
            before.content_fingerprint if before else None,
            after.content_fingerprint if after else None,
            before.content_length if before else None,
            after.content_length if after else None,
            before.classification if before else None,
            after.classification if after else None,
            axes,
            complete,
            evidence,
        )

    @staticmethod
    def _axes(before, after) -> RepositoryChangeAxes:
        def axis(left, right) -> RepositoryChangeAxisState:
            if left is None or right is None:
                return RepositoryChangeAxisState.UNKNOWN
            return (
                RepositoryChangeAxisState.UNCHANGED
                if left == right
                else RepositoryChangeAxisState.CHANGED
            )

        return RepositoryChangeAxes(
            axis(before.content_fingerprint if before else None, after.content_fingerprint if after else None),
            axis(before.metadata_fingerprint if before else None, after.metadata_fingerprint if after else None),
            axis(before.classification.tracking if before else None, after.classification.tracking if after else None),
            axis(before.classification.material_role if before else None, after.classification.material_role if after else None),
            axis(before.classification.sensitivity if before else None, after.classification.sensitivity if after else None),
            axis(before.classification.topology if before else None, after.classification.topology if after else None),
        )

    @staticmethod
    def _crosses_repository_boundary(entry, base_by_path, target_by_path) -> bool:
        boundaries = [
            item.path.value
            for item in (*base_by_path.values(), *target_by_path.values())
            if item.classification.topology
            in {RepositoryTopology.SUBMODULE, RepositoryTopology.NESTED_REPOSITORY}
        ]
        return any(
            path is not None and any(path.value.startswith(f"{boundary}/") for boundary in boundaries)
            for path in (entry.before_path, entry.after_path)
        )

    @staticmethod
    def _reduces_sensitivity(entry) -> bool:
        before = entry.classification_before
        after = entry.classification_after
        if before is None or after is None:
            return False
        ranks = {
            RepositorySensitivity.UNKNOWN: 0,
            RepositorySensitivity.NORMAL: 1,
            RepositorySensitivity.SECRET_RISK: 2,
            RepositorySensitivity.PRIVATE: 3,
        }
        return ranks[after.sensitivity] < ranks[before.sensitivity]
