"""Pure mutation planning over factual repository change sets."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from .changes import RepositoryChangeEntry, RepositoryChangeSet
from .errors import InvalidRepositoryMutationPlanModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPath, RepositoryPlatformProfile
from .snapshot import RepositorySnapshot
from .states import (
    RepositoryChangeType,
    RepositoryCollisionBehavior,
    RepositoryMutationOperationKind,
    RepositoryMutationPreconditionKind,
    RepositoryMutationScope,
    RepositoryObservationCompleteness,
    RepositoryPresenceExpectation,
    RepositoryRecoveryRequirement,
    RepositoryTopology,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class RepositoryMutationDiagnosticCode(StrEnum):
    BASE_SNAPSHOT_MISMATCH = "base_snapshot_mismatch"
    TARGET_SNAPSHOT_MISMATCH = "target_snapshot_mismatch"
    CHANGE_SET_MISMATCH = "change_set_mismatch"
    REPOSITORY_MISMATCH = "repository_mismatch"
    CHECKOUT_MISMATCH = "checkout_mismatch"
    WORKTREE_MISMATCH = "worktree_mismatch"
    PLATFORM_MISMATCH = "platform_mismatch"
    CHANGE_SET_INCOMPLETE = "change_set_incomplete"
    SNAPSHOT_INCOMPLETE = "snapshot_incomplete"
    TRANSLATION_RULE_MISSING = "translation_rule_missing"
    TRANSLATION_RULE_INVALID = "translation_rule_invalid"
    DELETE_POLICY_REQUIRED = "delete_policy_required"
    EVIDENCE_REQUIRED = "evidence_required"
    PATH_EXPECTATION_STALE = "path_expectation_stale"
    OPERATION_CONTRADICTORY = "operation_contradictory"
    CREATE_DELETE_CONFLICT = "create_delete_conflict"
    MOVE_CYCLE = "move_cycle"
    SOURCE_DESTINATION_COLLISION = "source_destination_collision"
    OVERWRITE_INTENT_REQUIRED = "overwrite_intent_required"
    RECOVERY_REQUIREMENT_MISSING = "recovery_requirement_missing"
    MUTATION_SCOPE_INCOMPATIBLE = "mutation_scope_incompatible"
    REPOSITORY_BOUNDARY_TRAVERSAL = "repository_boundary_traversal"
    PATH_COLLISION = "path_collision"
    APPLICATION_REQUEST_MISMATCH = "application_request_mismatch"
    AUTHORIZATION_NOT_SATISFIED = "authorization_not_satisfied"
    RESTORE_POINT_NOT_RECOVERABLE = "restore_point_not_recoverable"
    PRECONDITION_STALE = "precondition_stale"
    PRECONDITION_MISMATCH = "precondition_mismatch"
    PRECONDITION_UNAVAILABLE = "precondition_unavailable"
    PRECONDITION_RESULT_INCOMPLETE = "precondition_result_incomplete"
    OPERATION_NOT_IN_PLAN = "operation_not_in_plan"
    APPLICATION_FAILED = "application_failed"
    APPLICATION_PARTIAL = "application_partial"
    APPLICATION_INTERRUPTED = "application_interrupted"
    OBSERVATION_MISMATCH = "observation_mismatch"
    CLEANUP_REQUIRED = "cleanup_required"
    CLEANUP_FAILED = "cleanup_failed"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"
    RESULT_ORDER_INVALID = "result_order_invalid"


@dataclass(frozen=True, slots=True)
class RepositoryMutationRule:
    change_type: RepositoryChangeType
    operation: RepositoryMutationOperationKind
    scope: RepositoryMutationScope
    collision_behavior: RepositoryCollisionBehavior
    recovery_requirement: RepositoryRecoveryRequirement


@dataclass(frozen=True, slots=True)
class RepositoryMutationPolicy:
    policy_id: str
    policy_version: str
    rules: tuple[RepositoryMutationRule, ...] = ()
    require_complete_inputs: bool = True
    require_recovery_for: tuple[RepositoryMutationOperationKind, ...] = (
        RepositoryMutationOperationKind.REPLACE,
        RepositoryMutationOperationKind.DELETE,
        RepositoryMutationOperationKind.MOVE,
    )

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(
            self.policy_version
        ):
            raise InvalidRepositoryMutationPlanModel("mutation policy identity is invalid")
        ordered = tuple(sorted(set(self.rules), key=lambda item: item.change_type.value))
        if len({item.change_type for item in ordered}) != len(ordered):
            raise InvalidRepositoryMutationPlanModel("mutation rules must be unique by change type")
        object.__setattr__(self, "rules", ordered)
        object.__setattr__(
            self, "require_recovery_for", tuple(sorted(set(self.require_recovery_for)))
        )


@dataclass(frozen=True, slots=True)
class RepositoryMutationPlanRequest:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    change_set_fingerprint: RepositoryFingerprint
    overwrite_intents: tuple[RepositoryFingerprint, ...] = ()
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryMutationPlanModel("occurrence metadata is invalid")
        object.__setattr__(self, "overwrite_intents", tuple(sorted(set(self.overwrite_intents))))
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
            self.target_snapshot_fingerprint,
            self.change_set_fingerprint,
            self.overwrite_intents,
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class RepositoryMutationPrecondition:
    kind: RepositoryMutationPreconditionKind
    expected_fingerprint: RepositoryFingerprint
    path_fingerprint: RepositoryFingerprint | None = None
    presence: RepositoryPresenceExpectation = RepositoryPresenceExpectation.NOT_APPLICABLE
    topology: RepositoryTopology | None = None


@dataclass(frozen=True, slots=True)
class RepositoryMutationOperation:
    operation_id: RepositoryFingerprint
    kind: RepositoryMutationOperationKind
    scope: RepositoryMutationScope
    path: RepositoryPath
    source_path: RepositoryPath | None
    expected_base_fingerprint: RepositoryFingerprint | None
    expected_target_fingerprint: RepositoryFingerprint | None
    collision_behavior: RepositoryCollisionBehavior
    overwrite_intent: bool
    depends_on: tuple[RepositoryFingerprint, ...]
    recovery_requirement: RepositoryRecoveryRequirement
    change_entry_fingerprint: RepositoryFingerprint

    def __post_init__(self) -> None:
        object.__setattr__(self, "depends_on", tuple(sorted(set(self.depends_on))))


@dataclass(frozen=True, slots=True)
class RepositoryMutationDiagnostic:
    code: RepositoryMutationDiagnosticCode
    operation_fingerprint: RepositoryFingerprint | None = None
    path_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositoryMutationDiagnostic) -> tuple[str, str, str]:
    return (
        item.code.value,
        item.operation_fingerprint.value if item.operation_fingerprint else "",
        item.path_fingerprint.value if item.path_fingerprint else "",
    )


def _operation_order(
    operations: tuple[RepositoryMutationOperation, ...],
) -> tuple[RepositoryMutationOperation, ...]:
    by_id = {item.operation_id: item for item in operations}
    remaining = set(by_id)
    result: list[RepositoryMutationOperation] = []
    while remaining:
        available = sorted(
            (
                by_id[item]
                for item in remaining
                if not (set(by_id[item].depends_on) & remaining)
            ),
            key=lambda item: (item.path.value, item.kind.value, item.operation_id.value),
        )
        if not available:
            return tuple(sorted(operations, key=lambda item: item.operation_id.value))
        result.extend(available)
        remaining.difference_update(item.operation_id for item in available)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class RepositoryMutationPlan:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    platform_profile: RepositoryPlatformProfile
    base_snapshot_fingerprint: RepositoryFingerprint
    target_snapshot_fingerprint: RepositoryFingerprint
    change_set_fingerprint: RepositoryFingerprint
    policy_id: str
    policy_version: str
    completeness: RepositoryObservationCompleteness
    preconditions: tuple[RepositoryMutationPrecondition, ...]
    operations: tuple[RepositoryMutationOperation, ...]
    diagnostics: tuple[RepositoryMutationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "preconditions",
            tuple(
                sorted(
                    set(self.preconditions),
                    key=lambda item: (
                        item.kind.value,
                        item.path_fingerprint.value if item.path_fingerprint else "",
                    ),
                )
            ),
        )
        object.__setattr__(self, "operations", _operation_order(self.operations))
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryMutationPlanResult:
    request_fingerprint: RepositoryFingerprint
    plan: RepositoryMutationPlan | None
    diagnostics: tuple[RepositoryMutationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (self.request_fingerprint, self.plan, self.diagnostics)
        )


class RepositoryMutationPlanService:
    """Describe intended operations only; never authorize or apply them."""

    _blocking = {
        RepositoryMutationDiagnosticCode.BASE_SNAPSHOT_MISMATCH,
        RepositoryMutationDiagnosticCode.TARGET_SNAPSHOT_MISMATCH,
        RepositoryMutationDiagnosticCode.CHANGE_SET_MISMATCH,
        RepositoryMutationDiagnosticCode.REPOSITORY_MISMATCH,
        RepositoryMutationDiagnosticCode.CHECKOUT_MISMATCH,
        RepositoryMutationDiagnosticCode.WORKTREE_MISMATCH,
        RepositoryMutationDiagnosticCode.PLATFORM_MISMATCH,
        RepositoryMutationDiagnosticCode.PATH_EXPECTATION_STALE,
        RepositoryMutationDiagnosticCode.OPERATION_CONTRADICTORY,
        RepositoryMutationDiagnosticCode.CREATE_DELETE_CONFLICT,
        RepositoryMutationDiagnosticCode.MOVE_CYCLE,
        RepositoryMutationDiagnosticCode.SOURCE_DESTINATION_COLLISION,
        RepositoryMutationDiagnosticCode.REPOSITORY_BOUNDARY_TRAVERSAL,
    }

    def plan(
        self,
        request: RepositoryMutationPlanRequest,
        policy: RepositoryMutationPolicy,
        base: RepositorySnapshot,
        target: RepositorySnapshot,
        change_set: RepositoryChangeSet,
    ) -> RepositoryMutationPlanResult:
        diagnostics: set[RepositoryMutationDiagnostic] = set()

        def add(
            code: RepositoryMutationDiagnosticCode,
            entry: RepositoryChangeEntry | None = None,
            path: RepositoryPath | None = None,
        ) -> None:
            diagnostics.add(
                RepositoryMutationDiagnostic(
                    code,
                    entry.fingerprint if entry else None,
                    RepositoryFingerprint.from_content(path) if path else None,
                )
            )

        self._compatibility(request, policy, base, target, change_set, add)
        rules = {item.change_type: item for item in policy.rules}
        base_entries = {item.path.value: item for item in base.entries}
        target_entries = {item.path.value: item for item in target.entries}
        operations: list[RepositoryMutationOperation] = []
        for entry in change_set.entries:
            if self._stale_entry(entry, base_entries, target_entries):
                add(
                    RepositoryMutationDiagnosticCode.PATH_EXPECTATION_STALE,
                    entry,
                    entry.after_path or entry.before_path,
                )
                continue
            rule = rules.get(entry.change_type)
            if rule is None:
                add(
                    RepositoryMutationDiagnosticCode.DELETE_POLICY_REQUIRED
                    if entry.change_type is RepositoryChangeType.DELETED
                    else RepositoryMutationDiagnosticCode.TRANSLATION_RULE_MISSING,
                    entry,
                    entry.after_path or entry.before_path,
                )
                continue
            if not self._valid_rule(entry, rule):
                add(RepositoryMutationDiagnosticCode.TRANSLATION_RULE_INVALID, entry)
                continue
            if entry.change_type in {
                RepositoryChangeType.RENAMED,
                RepositoryChangeType.COPIED,
            } and not entry.evidence_reference:
                add(RepositoryMutationDiagnosticCode.EVIDENCE_REQUIRED, entry)
                continue
            destination = entry.after_path or entry.before_path
            if destination is None:
                add(RepositoryMutationDiagnosticCode.OPERATION_CONTRADICTORY, entry)
                continue
            if self._boundary_path(entry, base_entries, target_entries):
                add(
                    RepositoryMutationDiagnosticCode.REPOSITORY_BOUNDARY_TRAVERSAL,
                    entry,
                    destination,
                )
                continue
            overwrite = entry.fingerprint in request.overwrite_intents
            if (
                rule.collision_behavior is RepositoryCollisionBehavior.EXPLICIT_OVERWRITE
                and not overwrite
            ):
                add(RepositoryMutationDiagnosticCode.OVERWRITE_INTENT_REQUIRED, entry, destination)
                continue
            if (
                rule.operation in policy.require_recovery_for
                and rule.recovery_requirement is not RepositoryRecoveryRequirement.REQUIRED
            ):
                add(
                    RepositoryMutationDiagnosticCode.RECOVERY_REQUIREMENT_MISSING,
                    entry,
                    destination,
                )
                continue
            source = (
                entry.before_path
                if rule.operation
                in {RepositoryMutationOperationKind.MOVE, RepositoryMutationOperationKind.COPY}
                else None
            )
            core = (
                rule,
                destination,
                source,
                entry.base_entry_fingerprint,
                entry.target_entry_fingerprint,
                overwrite,
                entry.fingerprint,
            )
            operation_id = RepositoryFingerprint.from_content(core)
            operations.append(
                RepositoryMutationOperation(
                    operation_id,
                    rule.operation,
                    rule.scope,
                    destination,
                    source,
                    entry.base_entry_fingerprint,
                    entry.target_entry_fingerprint,
                    rule.collision_behavior,
                    overwrite,
                    (),
                    rule.recovery_requirement,
                    entry.fingerprint,
                )
            )

        operations = self._dependencies(operations, diagnostics)
        self._operation_conflicts(operations, diagnostics)
        if any(item.code in self._blocking for item in diagnostics):
            return RepositoryMutationPlanResult(request.fingerprint, None, tuple(diagnostics))
        preconditions = self._preconditions(request, base, operations)
        complete = (
            base.completeness is RepositoryObservationCompleteness.COMPLETE
            and target.completeness is RepositoryObservationCompleteness.COMPLETE
            and change_set.completeness is RepositoryObservationCompleteness.COMPLETE
            and not diagnostics
        )
        result = RepositoryMutationPlan(
            request.repository_id,
            request.checkout_id,
            request.worktree_id,
            request.platform_profile,
            base.fingerprint,
            target.fingerprint,
            change_set.fingerprint,
            policy.policy_id,
            policy.policy_version,
            RepositoryObservationCompleteness.COMPLETE
            if complete
            else RepositoryObservationCompleteness.PARTIAL,
            preconditions,
            tuple(operations),
            tuple(diagnostics),
        )
        return RepositoryMutationPlanResult(request.fingerprint, result, tuple(diagnostics))

    @staticmethod
    def _compatibility(request, policy, base, target, change_set, add) -> None:
        if (
            request.base_snapshot_fingerprint != base.fingerprint
            or change_set.base_snapshot_fingerprint != base.fingerprint
        ):
            add(RepositoryMutationDiagnosticCode.BASE_SNAPSHOT_MISMATCH)
        if (
            request.target_snapshot_fingerprint != target.fingerprint
            or change_set.target_snapshot_fingerprint != target.fingerprint
        ):
            add(RepositoryMutationDiagnosticCode.TARGET_SNAPSHOT_MISMATCH)
        if request.change_set_fingerprint != change_set.fingerprint:
            add(RepositoryMutationDiagnosticCode.CHANGE_SET_MISMATCH)
        for code, values in (
            (
                RepositoryMutationDiagnosticCode.REPOSITORY_MISMATCH,
                (request.repository_id, base.repository_id, target.repository_id, change_set.repository_id),
            ),
            (
                RepositoryMutationDiagnosticCode.CHECKOUT_MISMATCH,
                (request.checkout_id, base.checkout_id, target.checkout_id, change_set.checkout_id),
            ),
            (
                RepositoryMutationDiagnosticCode.WORKTREE_MISMATCH,
                (request.worktree_id, base.worktree_id, target.worktree_id, change_set.worktree_id),
            ),
            (
                RepositoryMutationDiagnosticCode.PLATFORM_MISMATCH,
                (request.platform_profile, base.platform_profile, target.platform_profile, change_set.platform_profile),
            ),
        ):
            if len(set(values)) != 1:
                add(code)
        if policy.require_complete_inputs and (
            base.completeness is not RepositoryObservationCompleteness.COMPLETE
            or target.completeness is not RepositoryObservationCompleteness.COMPLETE
        ):
            add(RepositoryMutationDiagnosticCode.SNAPSHOT_INCOMPLETE)
        if (
            policy.require_complete_inputs
            and change_set.completeness is not RepositoryObservationCompleteness.COMPLETE
        ):
            add(RepositoryMutationDiagnosticCode.CHANGE_SET_INCOMPLETE)

    @staticmethod
    def _valid_rule(entry: RepositoryChangeEntry, rule: RepositoryMutationRule) -> bool:
        expected = {
            RepositoryChangeType.ADDED: {RepositoryMutationOperationKind.CREATE},
            RepositoryChangeType.MODIFIED: {
                RepositoryMutationOperationKind.REPLACE,
                RepositoryMutationOperationKind.APPEND,
            },
            RepositoryChangeType.DELETED: {RepositoryMutationOperationKind.DELETE},
            RepositoryChangeType.RENAMED: {RepositoryMutationOperationKind.MOVE},
            RepositoryChangeType.COPIED: {RepositoryMutationOperationKind.COPY},
            RepositoryChangeType.TYPE_CHANGED: {RepositoryMutationOperationKind.REPLACE},
            RepositoryChangeType.CLASSIFICATION_CHANGED: {
                RepositoryMutationOperationKind.CLASSIFICATION_UPDATE
            },
            RepositoryChangeType.METADATA_CHANGED: {
                RepositoryMutationOperationKind.METADATA_UPDATE
            },
            RepositoryChangeType.CONFLICT: set(),
            RepositoryChangeType.UNKNOWN: set(),
        }[entry.change_type]
        scope = {
            RepositoryMutationOperationKind.CREATE: RepositoryMutationScope.RESOURCE,
            RepositoryMutationOperationKind.REPLACE: RepositoryMutationScope.CONTENT,
            RepositoryMutationOperationKind.APPEND: RepositoryMutationScope.CONTENT,
            RepositoryMutationOperationKind.DELETE: RepositoryMutationScope.RESOURCE,
            RepositoryMutationOperationKind.MOVE: RepositoryMutationScope.RESOURCE,
            RepositoryMutationOperationKind.COPY: RepositoryMutationScope.RESOURCE,
            RepositoryMutationOperationKind.METADATA_UPDATE: RepositoryMutationScope.METADATA,
            RepositoryMutationOperationKind.CLASSIFICATION_UPDATE: RepositoryMutationScope.CLASSIFICATION,
        }[rule.operation]
        return rule.operation in expected and rule.scope is scope

    @staticmethod
    def _stale_entry(entry, base_entries, target_entries) -> bool:
        before = base_entries.get(entry.before_path.value) if entry.before_path else None
        after = target_entries.get(entry.after_path.value) if entry.after_path else None
        expected_before = RepositoryFingerprint.from_content(before) if before else None
        expected_after = RepositoryFingerprint.from_content(after) if after else None
        return (
            entry.base_entry_fingerprint != expected_before
            or entry.target_entry_fingerprint != expected_after
        )

    @staticmethod
    def _boundary_path(entry, base_entries, target_entries) -> bool:
        boundaries = {
            item.path.value
            for item in (*base_entries.values(), *target_entries.values())
            if item.topology
            in {
                RepositoryTopology.SUBMODULE,
                RepositoryTopology.NESTED_REPOSITORY,
                RepositoryTopology.SPARSE_EXCLUDED,
            }
        }
        paths = [item.value for item in (entry.before_path, entry.after_path) if item]
        return any(
            path == boundary or path.startswith(f"{boundary}/")
            for path in paths
            for boundary in boundaries
        )

    @staticmethod
    def _dependencies(
        operations: list[RepositoryMutationOperation],
        diagnostics: set[RepositoryMutationDiagnostic],
    ) -> list[RepositoryMutationOperation]:
        moves: dict[str, RepositoryMutationOperation] = {
            item.source_path.value: item
            for item in operations
            if item.kind is RepositoryMutationOperationKind.MOVE and item.source_path
        }
        result: list[RepositoryMutationOperation] = []
        for item in operations:
            dependency = (
                moves.get(item.path.value)
                if item.kind is RepositoryMutationOperationKind.MOVE
                else None
            )
            if dependency is item:
                diagnostics.add(
                    RepositoryMutationDiagnostic(
                        RepositoryMutationDiagnosticCode.SOURCE_DESTINATION_COLLISION,
                        item.operation_id,
                    )
                )
            dependencies = (
                (dependency.operation_id,)
                if dependency is not None and dependency is not item
                else ()
            )
            result.append(
                replace(
                    item,
                    depends_on=dependencies,
                )
            )
        graph = {item.operation_id: set(item.depends_on) for item in result}
        pending = set(graph)
        while pending:
            ready = {item for item in pending if not (graph[item] & pending)}
            if not ready:
                diagnostics.add(
                    RepositoryMutationDiagnostic(RepositoryMutationDiagnosticCode.MOVE_CYCLE)
                )
                break
            pending -= ready
        return result

    @staticmethod
    def _operation_conflicts(operations, diagnostics) -> None:
        by_path: dict[str, list[RepositoryMutationOperation]] = {}
        for item in operations:
            by_path.setdefault(item.path.value, []).append(item)
        for items in by_path.values():
            if len(items) <= 1:
                continue
            kinds = {item.kind for item in items}
            code = (
                RepositoryMutationDiagnosticCode.CREATE_DELETE_CONFLICT
                if RepositoryMutationOperationKind.CREATE in kinds
                and RepositoryMutationOperationKind.DELETE in kinds
                else RepositoryMutationDiagnosticCode.OPERATION_CONTRADICTORY
            )
            diagnostics.add(
                RepositoryMutationDiagnostic(
                    code,
                    path_fingerprint=RepositoryFingerprint.from_content(items[0].path),
                )
            )

    @staticmethod
    def _preconditions(request, base, operations):
        global_items = (
            (RepositoryMutationPreconditionKind.REPOSITORY_IDENTITY, request.repository_id),
            (RepositoryMutationPreconditionKind.CHECKOUT_IDENTITY, request.checkout_id),
            (RepositoryMutationPreconditionKind.WORKTREE_IDENTITY, request.worktree_id),
            (RepositoryMutationPreconditionKind.HEAD_STATE, base.head_fingerprint),
            (
                RepositoryMutationPreconditionKind.BRANCH_STATE,
                (base.head.kind, base.branch_reference),
            ),
            (RepositoryMutationPreconditionKind.INDEX_STATE, base.index_fingerprint),
            (RepositoryMutationPreconditionKind.WORKSPACE_STATE, base.workspace_fingerprint),
            (RepositoryMutationPreconditionKind.COMPLETENESS, base.completeness),
            (
                RepositoryMutationPreconditionKind.COLLISION_STATE,
                tuple(item.path for item in base.entries),
            ),
        )
        result = [
            RepositoryMutationPrecondition(kind, RepositoryFingerprint.from_content(value))
            for kind, value in global_items
        ]
        for item in operations:
            result.append(
                RepositoryMutationPrecondition(
                    RepositoryMutationPreconditionKind.PATH_STATE,
                    item.expected_base_fingerprint
                    or RepositoryFingerprint.from_content((item.path, "absent")),
                    RepositoryFingerprint.from_content(item.path),
                    RepositoryPresenceExpectation.ABSENT
                    if item.kind is RepositoryMutationOperationKind.CREATE
                    else RepositoryPresenceExpectation.PRESENT,
                )
            )
            result.append(
                RepositoryMutationPrecondition(
                    RepositoryMutationPreconditionKind.TOPOLOGY_BOUNDARY,
                    RepositoryFingerprint.from_content((item.path, RepositoryTopology.REGULAR)),
                    RepositoryFingerprint.from_content(item.path),
                    topology=RepositoryTopology.REGULAR,
                )
            )
        return tuple(result)
