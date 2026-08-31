"""Pure correspondence assessment for external repository authorization facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .errors import InvalidRepositoryAuthorizationModel
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPath
from .mutations import RepositoryMutationOperation, RepositoryMutationPlan
from .states import (
    RepositoryAuthorizationFactEffect,
    RepositoryAuthorizationFreshness,
    RepositoryAuthorizationOutcome,
    RepositoryAuthorizationPathScope,
    RepositoryCollisionBehavior,
    RepositoryCorrespondence,
    RepositoryMutationOperationKind,
    RepositoryMutationScope,
    RepositoryObservationCompleteness,
    RepositoryRecoveryRequirement,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class RepositoryAuthorizationDiagnosticCode(StrEnum):
    PLAN_FINGERPRINT_MISMATCH = "plan_fingerprint_mismatch"
    REPOSITORY_MISMATCH = "repository_mismatch"
    CHECKOUT_MISMATCH = "checkout_mismatch"
    WORKTREE_MISMATCH = "worktree_mismatch"
    ACTOR_MISMATCH = "actor_mismatch"
    PURPOSE_MISMATCH = "purpose_mismatch"
    OPERATION_NOT_COVERED = "operation_not_covered"
    MUTATION_SCOPE_NOT_COVERED = "mutation_scope_not_covered"
    PATH_NOT_COVERED = "path_not_covered"
    COLLISION_NOT_COVERED = "collision_not_covered"
    OVERWRITE_CORRESPONDENCE_REQUIRED = "overwrite_correspondence_required"
    DELETE_CORRESPONDENCE_REQUIRED = "delete_correspondence_required"
    RECOVERY_NOT_COVERED = "recovery_not_covered"
    FACT_STALE = "fact_stale"
    FACT_EXPIRED = "fact_expired"
    FACT_NOT_YET_VALID = "fact_not_yet_valid"
    FACT_INCOMPLETE = "fact_incomplete"
    FACTS_UNAVAILABLE = "facts_unavailable"
    FACTS_CONFLICT = "facts_conflict"
    AUTHORIZATION_PARTIAL = "authorization_partial"
    SOURCE_UNKNOWN = "source_unknown"
    SOURCE_VERSION_UNKNOWN = "source_version_unknown"
    BROADER_FACT_REQUIRES_RULE = "broader_fact_requires_rule"


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationFact:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    mutation_plan_fingerprint: RepositoryFingerprint
    actor: str
    purpose: str
    operation_kinds: tuple[RepositoryMutationOperationKind, ...]
    mutation_scopes: tuple[RepositoryMutationScope, ...]
    collision_behaviors: tuple[RepositoryCollisionBehavior, ...]
    recovery_requirements: tuple[RepositoryRecoveryRequirement, ...]
    paths: tuple[RepositoryPath, ...]
    path_fingerprints: tuple[RepositoryFingerprint, ...]
    path_scope: RepositoryAuthorizationPathScope
    allows_delete: bool
    allows_overwrite: bool
    authorization_source: str
    authorization_reference: str
    policy_id: str
    policy_version: str
    issued_at: int
    valid_from: int
    valid_until: int
    completeness: RepositoryObservationCompleteness
    effect: RepositoryAuthorizationFactEffect = RepositoryAuthorizationFactEffect.ASSERTED
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.actor,
            self.purpose,
            self.authorization_source,
            self.authorization_reference,
            self.policy_id,
            self.policy_version,
        ):
            if not _REFERENCE.fullmatch(value):
                raise InvalidRepositoryAuthorizationModel("authorization reference is invalid")
        if min(self.issued_at, self.valid_from, self.valid_until) < 0:
            raise InvalidRepositoryAuthorizationModel("authorization time cannot be negative")
        if self.valid_from > self.valid_until or self.issued_at > self.valid_until:
            raise InvalidRepositoryAuthorizationModel("authorization validity window is invalid")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryAuthorizationModel("occurrence metadata is invalid")
        for name in (
            "operation_kinds",
            "mutation_scopes",
            "collision_behaviors",
            "recovery_requirements",
        ):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))
        object.__setattr__(
            self, "paths", tuple(sorted(set(self.paths), key=lambda item: item.value))
        )
        object.__setattr__(
            self,
            "path_fingerprints",
            tuple(sorted(set(self.path_fingerprints), key=lambda item: item.value)),
        )
        if self.path_scope is RepositoryAuthorizationPathScope.WILDCARD and (
            self.paths or self.path_fingerprints
        ):
            raise InvalidRepositoryAuthorizationModel("wildcard scope cannot hide path filters")
        if self.path_scope is not RepositoryAuthorizationPathScope.WILDCARD and not (
            self.paths or self.path_fingerprints
        ):
            raise InvalidRepositoryAuthorizationModel("path scope requires explicit path facts")
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

    @property
    def source_fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (self.authorization_source, self.authorization_reference, self.policy_id)
        )


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationFactsSnapshot:
    facts: tuple[RepositoryAuthorizationFact, ...]
    completeness: RepositoryObservationCompleteness
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryAuthorizationModel("occurrence metadata is invalid")
        by_fingerprint = {item.fingerprint: item for item in self.facts}
        object.__setattr__(
            self,
            "facts",
            tuple(by_fingerprint[key] for key in sorted(by_fingerprint, key=lambda item: item.value)),
        )
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (tuple(item.fingerprint for item in self.facts), self.completeness)
        )


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationRequirement:
    mutation_plan_fingerprint: RepositoryFingerprint
    actor: str
    purpose: str
    operations: tuple[RepositoryMutationOperation, ...]
    assessment_time: int
    maximum_fact_age: int
    accepted_sources: tuple[tuple[str, str, str], ...]
    allow_broader_facts: bool = False
    allow_combined_subset_facts: bool = False
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.actor) or not _REFERENCE.fullmatch(self.purpose):
            raise InvalidRepositoryAuthorizationModel("authorization requirement is invalid")
        if self.assessment_time < 0 or self.maximum_fact_age < 0:
            raise InvalidRepositoryAuthorizationModel("authorization assessment time is invalid")
        if any(
            not _REFERENCE.fullmatch(value)
            for source_tuple in self.accepted_sources
            for value in source_tuple
        ):
            raise InvalidRepositoryAuthorizationModel("accepted authorization source is invalid")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryAuthorizationModel("occurrence metadata is invalid")
        object.__setattr__(
            self, "operations", tuple(sorted(set(self.operations), key=lambda item: item.operation_id.value))
        )
        object.__setattr__(self, "accepted_sources", tuple(sorted(set(self.accepted_sources))))
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    @classmethod
    def from_plan(
        cls,
        plan: RepositoryMutationPlan,
        *,
        actor: str,
        purpose: str,
        assessment_time: int,
        maximum_fact_age: int,
        accepted_sources: tuple[tuple[str, str, str], ...],
        allow_broader_facts: bool = False,
        allow_combined_subset_facts: bool = False,
        occurrence_metadata: tuple[tuple[str, str], ...] = (),
    ) -> RepositoryAuthorizationRequirement:
        return cls(
            plan.fingerprint,
            actor,
            purpose,
            plan.operations,
            assessment_time,
            maximum_fact_age,
            accepted_sources,
            allow_broader_facts,
            allow_combined_subset_facts,
            occurrence_metadata,
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


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationOperationAssessment:
    operation_fingerprint: RepositoryFingerprint
    correspondence: RepositoryCorrespondence
    fact_fingerprints: tuple[RepositoryFingerprint, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fact_fingerprints",
            tuple(sorted(set(self.fact_fingerprints), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationDiagnostic:
    code: RepositoryAuthorizationDiagnosticCode
    operation_fingerprint: RepositoryFingerprint | None = None
    fact_fingerprint: RepositoryFingerprint | None = None
    source_fingerprint: RepositoryFingerprint | None = None


def _diagnostic_key(item: RepositoryAuthorizationDiagnostic) -> tuple[str, str, str, str]:
    return (
        item.code.value,
        item.operation_fingerprint.value if item.operation_fingerprint else "",
        item.fact_fingerprint.value if item.fact_fingerprint else "",
        item.source_fingerprint.value if item.source_fingerprint else "",
    )


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationAssessment:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    mutation_plan_fingerprint: RepositoryFingerprint
    requirement_fingerprint: RepositoryFingerprint
    facts_snapshot_fingerprint: RepositoryFingerprint
    outcome: RepositoryAuthorizationOutcome
    completeness: RepositoryObservationCompleteness
    freshness: RepositoryAuthorizationFreshness
    operations: tuple[RepositoryAuthorizationOperationAssessment, ...]
    diagnostics: tuple[RepositoryAuthorizationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operations",
            tuple(sorted(self.operations, key=lambda item: item.operation_fingerprint.value)),
        )
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryAuthorizationAssessmentResult:
    requirement_fingerprint: RepositoryFingerprint
    assessment: RepositoryAuthorizationAssessment
    diagnostics: tuple[RepositoryAuthorizationDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "diagnostics", tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        )

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(
            (self.requirement_fingerprint, self.assessment, self.diagnostics)
        )


class RepositoryAuthorizationAssessmentService:
    """Assess fact correspondence only; never decide or grant authorization."""

    def assess(
        self,
        requirement: RepositoryAuthorizationRequirement,
        plan: RepositoryMutationPlan,
        snapshot: RepositoryAuthorizationFactsSnapshot,
    ) -> RepositoryAuthorizationAssessmentResult:
        diagnostics: set[RepositoryAuthorizationDiagnostic] = set()

        def add(
            code: RepositoryAuthorizationDiagnosticCode,
            operation: RepositoryMutationOperation | None = None,
            fact: RepositoryAuthorizationFact | None = None,
        ) -> None:
            diagnostics.add(
                RepositoryAuthorizationDiagnostic(
                    code,
                    operation.operation_id if operation else None,
                    fact.fingerprint if fact else None,
                    fact.source_fingerprint if fact else None,
                )
            )

        if requirement.mutation_plan_fingerprint != plan.fingerprint:
            add(RepositoryAuthorizationDiagnosticCode.PLAN_FINGERPRINT_MISMATCH)
        if snapshot.completeness is RepositoryObservationCompleteness.UNAVAILABLE:
            add(RepositoryAuthorizationDiagnosticCode.FACTS_UNAVAILABLE)
        elif snapshot.completeness is not RepositoryObservationCompleteness.COMPLETE:
            add(RepositoryAuthorizationDiagnosticCode.FACT_INCOMPLETE)
        conflicts = self._conflicts(snapshot.facts)
        for fact in conflicts:
            add(RepositoryAuthorizationDiagnosticCode.FACTS_CONFLICT, fact=fact)

        valid_facts: list[RepositoryAuthorizationFact] = []
        freshnesses: list[RepositoryAuthorizationFreshness] = []
        for fact in snapshot.facts:
            freshness = self._freshness(requirement, fact)
            freshnesses.append(freshness)
            if not self._fact_corresponds(requirement, plan, fact, freshness, add):
                continue
            if fact in conflicts or fact.effect is RepositoryAuthorizationFactEffect.REVOKED:
                continue
            valid_facts.append(fact)

        if not requirement.allow_combined_subset_facts:
            valid_facts = [
                fact
                for fact in valid_facts
                if all(
                    self._covers_operation(requirement, operation, fact, add)
                    for operation in requirement.operations
                )
            ]

        operation_assessments: list[RepositoryAuthorizationOperationAssessment] = []
        for operation in requirement.operations:
            matches = tuple(
                fact.fingerprint
                for fact in valid_facts
                if self._covers_operation(requirement, operation, fact, add)
            )
            correspondence = (
                RepositoryCorrespondence.MATCH
                if matches
                else RepositoryCorrespondence.MISMATCH
            )
            if not matches:
                add(RepositoryAuthorizationDiagnosticCode.OPERATION_NOT_COVERED, operation)
            operation_assessments.append(
                RepositoryAuthorizationOperationAssessment(
                    operation.operation_id, correspondence, matches
                )
            )

        matched = sum(
            item.correspondence is RepositoryCorrespondence.MATCH
            for item in operation_assessments
        )
        outcome = self._outcome(
            len(operation_assessments), matched, snapshot.completeness, freshnesses, bool(conflicts)
        )
        if outcome is RepositoryAuthorizationOutcome.PARTIAL:
            add(RepositoryAuthorizationDiagnosticCode.AUTHORIZATION_PARTIAL)
        freshness = self._aggregate_freshness(snapshot.completeness, freshnesses)
        completeness = (
            RepositoryObservationCompleteness.COMPLETE
            if outcome is RepositoryAuthorizationOutcome.SATISFIED
            else RepositoryObservationCompleteness.PARTIAL
        )
        assessment = RepositoryAuthorizationAssessment(
            plan.repository_id,
            plan.checkout_id,
            plan.worktree_id,
            plan.fingerprint,
            requirement.fingerprint,
            snapshot.fingerprint,
            outcome,
            completeness,
            freshness,
            tuple(operation_assessments),
            tuple(diagnostics),
        )
        return RepositoryAuthorizationAssessmentResult(
            requirement.fingerprint, assessment, tuple(diagnostics)
        )

    @staticmethod
    def _freshness(requirement, fact):
        if fact.completeness is RepositoryObservationCompleteness.UNAVAILABLE:
            return RepositoryAuthorizationFreshness.UNAVAILABLE
        if fact.completeness is not RepositoryObservationCompleteness.COMPLETE:
            return RepositoryAuthorizationFreshness.UNKNOWN
        if requirement.assessment_time > fact.valid_until:
            return RepositoryAuthorizationFreshness.EXPIRED
        if requirement.assessment_time < fact.valid_from:
            return RepositoryAuthorizationFreshness.STALE
        if requirement.assessment_time - fact.issued_at > requirement.maximum_fact_age:
            return RepositoryAuthorizationFreshness.STALE
        return RepositoryAuthorizationFreshness.FRESH

    @staticmethod
    def _conflicts(facts):
        grouped: dict[tuple[object, ...], set[RepositoryAuthorizationFactEffect]] = {}
        for fact in facts:
            key = (
                fact.authorization_source,
                fact.authorization_reference,
                fact.policy_id,
                fact.policy_version,
                fact.mutation_plan_fingerprint,
                fact.actor,
                fact.purpose,
            )
            grouped.setdefault(key, set()).add(fact.effect)
        conflicting = {key for key, effects in grouped.items() if len(effects) > 1}
        return {
            fact
            for fact in facts
            if (
                fact.authorization_source,
                fact.authorization_reference,
                fact.policy_id,
                fact.policy_version,
                fact.mutation_plan_fingerprint,
                fact.actor,
                fact.purpose,
            )
            in conflicting
        }

    @staticmethod
    def _fact_corresponds(requirement, plan, fact, freshness, add):
        valid = True
        checks = (
            (fact.mutation_plan_fingerprint == plan.fingerprint, RepositoryAuthorizationDiagnosticCode.PLAN_FINGERPRINT_MISMATCH),
            (fact.repository_id == plan.repository_id, RepositoryAuthorizationDiagnosticCode.REPOSITORY_MISMATCH),
            (fact.checkout_id == plan.checkout_id, RepositoryAuthorizationDiagnosticCode.CHECKOUT_MISMATCH),
            (fact.worktree_id == plan.worktree_id, RepositoryAuthorizationDiagnosticCode.WORKTREE_MISMATCH),
            (fact.actor == requirement.actor, RepositoryAuthorizationDiagnosticCode.ACTOR_MISMATCH),
            (fact.purpose == requirement.purpose, RepositoryAuthorizationDiagnosticCode.PURPOSE_MISMATCH),
        )
        for matches, code in checks:
            if not matches:
                add(code, fact=fact)
                valid = False
        accepted_policies = {
            (policy_id, version)
            for source, policy_id, version in requirement.accepted_sources
            if source == fact.authorization_source
        }
        if not accepted_policies:
            add(RepositoryAuthorizationDiagnosticCode.SOURCE_UNKNOWN, fact=fact)
            valid = False
        elif (fact.policy_id, fact.policy_version) not in accepted_policies:
            add(RepositoryAuthorizationDiagnosticCode.SOURCE_VERSION_UNKNOWN, fact=fact)
            valid = False
        freshness_code = {
            RepositoryAuthorizationFreshness.STALE: RepositoryAuthorizationDiagnosticCode.FACT_STALE,
            RepositoryAuthorizationFreshness.EXPIRED: RepositoryAuthorizationDiagnosticCode.FACT_EXPIRED,
            RepositoryAuthorizationFreshness.UNKNOWN: RepositoryAuthorizationDiagnosticCode.FACT_INCOMPLETE,
            RepositoryAuthorizationFreshness.UNAVAILABLE: RepositoryAuthorizationDiagnosticCode.FACTS_UNAVAILABLE,
        }.get(freshness)
        if freshness_code:
            add(freshness_code, fact=fact)
            valid = False
        if requirement.assessment_time < fact.valid_from:
            add(RepositoryAuthorizationDiagnosticCode.FACT_NOT_YET_VALID, fact=fact)
            valid = False
        if requirement.operations and not any(
            RepositoryAuthorizationAssessmentService._path_matches(operation, fact)
            for operation in requirement.operations
        ):
            add(
                RepositoryAuthorizationDiagnosticCode.PATH_NOT_COVERED,
                requirement.operations[0],
                fact,
            )
            valid = False
        if not requirement.allow_broader_facts and RepositoryAuthorizationAssessmentService._broader(requirement, fact):
            add(RepositoryAuthorizationDiagnosticCode.BROADER_FACT_REQUIRES_RULE, fact=fact)
            valid = False
        return valid

    @staticmethod
    def _broader(requirement, fact):
        kinds = {item.kind for item in requirement.operations}
        scopes = {item.scope for item in requirement.operations}
        collisions = {item.collision_behavior for item in requirement.operations}
        paths = {item.path for item in requirement.operations}
        path_fingerprints = {RepositoryFingerprint.from_content(item) for item in paths}
        return (
            not set(fact.operation_kinds) <= kinds
            or not set(fact.mutation_scopes) <= scopes
            or not set(fact.collision_behaviors) <= collisions
            or fact.path_scope is not RepositoryAuthorizationPathScope.EXACT
            or not set(fact.paths) <= paths
            or not set(fact.path_fingerprints) <= path_fingerprints
        )

    @staticmethod
    def _covers_operation(requirement, operation, fact, add):
        if operation.kind not in fact.operation_kinds:
            add(RepositoryAuthorizationDiagnosticCode.OPERATION_NOT_COVERED, operation, fact)
            return False
        if operation.scope not in fact.mutation_scopes:
            add(RepositoryAuthorizationDiagnosticCode.MUTATION_SCOPE_NOT_COVERED, operation, fact)
            return False
        if operation.collision_behavior not in fact.collision_behaviors:
            add(RepositoryAuthorizationDiagnosticCode.COLLISION_NOT_COVERED, operation, fact)
            return False
        if operation.recovery_requirement not in fact.recovery_requirements:
            add(RepositoryAuthorizationDiagnosticCode.RECOVERY_NOT_COVERED, operation, fact)
            return False
        if operation.kind is RepositoryMutationOperationKind.DELETE and not fact.allows_delete:
            add(RepositoryAuthorizationDiagnosticCode.DELETE_CORRESPONDENCE_REQUIRED, operation, fact)
            return False
        if operation.overwrite_intent and not fact.allows_overwrite:
            add(RepositoryAuthorizationDiagnosticCode.OVERWRITE_CORRESPONDENCE_REQUIRED, operation, fact)
            return False
        if not RepositoryAuthorizationAssessmentService._path_matches(operation, fact):
            add(RepositoryAuthorizationDiagnosticCode.PATH_NOT_COVERED, operation, fact)
            return False
        return True

    @staticmethod
    def _path_matches(operation, fact):
        if fact.path_scope is RepositoryAuthorizationPathScope.WILDCARD:
            return True
        fingerprint = RepositoryFingerprint.from_content(operation.path)
        if fingerprint in fact.path_fingerprints:
            return True
        for authorized in fact.paths:
            if operation.path == authorized:
                return True
            if fact.path_scope is RepositoryAuthorizationPathScope.PREFIX:
                relative = operation.path.value.removeprefix(f"{authorized.value}/")
                if relative != operation.path.value and "/" not in relative:
                    return True
            if fact.path_scope is RepositoryAuthorizationPathScope.RECURSIVE and operation.path.value.startswith(f"{authorized.value}/"):
                return True
        return False

    @staticmethod
    def _aggregate_freshness(completeness, freshnesses):
        if completeness is RepositoryObservationCompleteness.UNAVAILABLE:
            return RepositoryAuthorizationFreshness.UNAVAILABLE
        for value in (
            RepositoryAuthorizationFreshness.EXPIRED,
            RepositoryAuthorizationFreshness.STALE,
            RepositoryAuthorizationFreshness.UNKNOWN,
            RepositoryAuthorizationFreshness.UNAVAILABLE,
        ):
            if value in freshnesses:
                return value
        return RepositoryAuthorizationFreshness.FRESH

    @staticmethod
    def _outcome(total, matched, completeness, freshnesses, conflict):
        if conflict:
            return RepositoryAuthorizationOutcome.CONFLICT
        if completeness is RepositoryObservationCompleteness.UNAVAILABLE:
            return RepositoryAuthorizationOutcome.UNAVAILABLE
        if RepositoryAuthorizationFreshness.EXPIRED in freshnesses:
            return RepositoryAuthorizationOutcome.EXPIRED
        if RepositoryAuthorizationFreshness.STALE in freshnesses:
            return RepositoryAuthorizationOutcome.STALE
        if completeness is not RepositoryObservationCompleteness.COMPLETE or RepositoryAuthorizationFreshness.UNKNOWN in freshnesses:
            return RepositoryAuthorizationOutcome.INCOMPLETE
        if total > 0 and matched == total:
            return RepositoryAuthorizationOutcome.SATISFIED
        if matched:
            return RepositoryAuthorizationOutcome.PARTIAL
        return RepositoryAuthorizationOutcome.MISMATCH
