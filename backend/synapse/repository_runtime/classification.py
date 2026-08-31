"""Pure deterministic path and resource classification for Repository Runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .canonical import CANONICAL_FORMAT
from .errors import InvalidRepositoryPathClassificationPolicy, InvalidRepositoryPathFacts
from .identities import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryWorktreeIdentity,
)
from .models import RepositoryPath, RepositoryPathClassification, RepositoryPlatformProfile
from .states import (
    RepositoryContentKind,
    RepositoryGitTracking,
    RepositoryLinkPolicy,
    RepositoryMaterialRole,
    RepositoryObservationCompleteness,
    RepositoryResourceKind,
    RepositorySensitivity,
    RepositorySizeClass,
    RepositoryTopology,
)

_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


def _validate_reference(value: str | None, label: str) -> None:
    if value is not None and not _REFERENCE.fullmatch(value):
        raise InvalidRepositoryPathFacts(f"{label} reference is invalid")


class RepositoryPathDiagnosticCode(StrEnum):
    PATH_BINDING_MISMATCH = "path_binding_mismatch"
    PATH_COLLISION = "path_collision"
    TRACKING_CONFLICT = "tracking_conflict"
    MATERIAL_ROLE_CONFLICT = "material_role_conflict"
    SENSITIVITY_CONFLICT = "sensitivity_conflict"
    TOPOLOGY_CONFLICT = "topology_conflict"
    RESOURCE_KIND_CONFLICT = "resource_kind_conflict"
    SPARSE_EXCLUDED_CONTENT = "sparse_excluded_content"
    TOPOLOGY_CONTENT_TRAVERSAL = "topology_content_traversal"
    LINK_POLICY_REQUIRED = "link_policy_required"
    LINK_REJECTED = "link_rejected"
    UNKNOWN_MATERIAL_RULE = "unknown_material_rule"
    UNKNOWN_SENSITIVITY_RULE = "unknown_sensitivity_rule"
    FACTS_INCOMPLETE = "facts_incomplete"


@dataclass(frozen=True, slots=True, order=True)
class RepositoryMaterialRule:
    reference: str
    role: RepositoryMaterialRole

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.reference) or self.role is RepositoryMaterialRole.UNKNOWN:
            raise InvalidRepositoryPathClassificationPolicy("material rule is invalid")


@dataclass(frozen=True, slots=True, order=True)
class RepositorySensitivityRule:
    reference: str
    sensitivity: RepositorySensitivity

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.reference) or self.sensitivity is RepositorySensitivity.UNKNOWN:
            raise InvalidRepositoryPathClassificationPolicy("sensitivity rule is invalid")


@dataclass(frozen=True, slots=True)
class RepositoryPathClassificationPolicy:
    policy_id: str
    policy_version: str
    material_rules: tuple[RepositoryMaterialRule, ...] = ()
    sensitivity_rules: tuple[RepositorySensitivityRule, ...] = ()
    link_policy: RepositoryLinkPolicy | None = None
    canonical_format: str = CANONICAL_FORMAT

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(self.policy_id) or not _REFERENCE.fullmatch(self.policy_version):
            raise InvalidRepositoryPathClassificationPolicy("policy identity is invalid")
        if self.canonical_format != CANONICAL_FORMAT:
            raise InvalidRepositoryPathClassificationPolicy("canonical format is unsupported")
        materials = tuple(sorted(self.material_rules))
        sensitivities = tuple(sorted(self.sensitivity_rules))
        if len({rule.reference for rule in materials}) != len(materials):
            raise InvalidRepositoryPathClassificationPolicy("material rule references must be unique")
        if len({rule.reference for rule in sensitivities}) != len(sensitivities):
            raise InvalidRepositoryPathClassificationPolicy("sensitivity rule references must be unique")
        object.__setattr__(self, "material_rules", materials)
        object.__setattr__(self, "sensitivity_rules", sensitivities)


@dataclass(frozen=True, slots=True)
class RepositoryPathFacts:
    path: RepositoryPath
    tracking: RepositoryGitTracking
    topology: RepositoryTopology
    resource_kind: RepositoryResourceKind
    executable: bool | None
    content_kind: RepositoryContentKind
    size_class: RepositorySizeClass
    content_observed: bool
    descendants_observed: bool
    completeness: RepositoryObservationCompleteness
    material_rule_references: tuple[str, ...] = ()
    generated_rule_reference: str | None = None
    sensitivity_rule_reference: str | None = None
    ownership_scope_reference: str | None = None
    occurrence_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for reference in self.material_rule_references:
            _validate_reference(reference, "material rule")
        _validate_reference(self.generated_rule_reference, "generated rule")
        _validate_reference(self.sensitivity_rule_reference, "sensitivity rule")
        _validate_reference(self.ownership_scope_reference, "ownership scope")
        if any(
            not _REFERENCE.fullmatch(key) or not _REFERENCE.fullmatch(value)
            for key, value in self.occurrence_metadata
        ):
            raise InvalidRepositoryPathFacts("occurrence metadata is invalid")
        object.__setattr__(self, "material_rule_references", tuple(sorted(set(self.material_rule_references))))
        object.__setattr__(self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata))))

    def semantic_content(self) -> object:
        return (
            self.path,
            self.tracking,
            self.topology,
            self.resource_kind,
            self.executable,
            self.content_kind,
            self.size_class,
            self.content_observed,
            self.descendants_observed,
            self.completeness,
            self.material_rule_references,
            self.generated_rule_reference,
            self.sensitivity_rule_reference,
            self.ownership_scope_reference,
        )


@dataclass(frozen=True, slots=True, order=True)
class RepositoryPathDiagnostic:
    path_fingerprint: RepositoryFingerprint
    code: RepositoryPathDiagnosticCode


@dataclass(frozen=True, slots=True)
class RepositoryPathCatalogEntry:
    path: RepositoryPath
    resource_kind: RepositoryResourceKind
    executable: bool | None
    content_kind: RepositoryContentKind
    size_class: RepositorySizeClass
    ownership_scope_reference: str | None
    completeness: RepositoryObservationCompleteness
    classification: RepositoryPathClassification
    diagnostics: tuple[RepositoryPathDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(sorted(set(self.diagnostics))))


@dataclass(frozen=True, slots=True)
class RepositoryPathCatalog:
    repository_id: RepositoryIdentity
    checkout_id: RepositoryCheckoutIdentity
    worktree_id: RepositoryWorktreeIdentity | None
    observation_fingerprint: RepositoryFingerprint
    platform_profile: RepositoryPlatformProfile
    policy_id: str
    policy_version: str
    completeness: RepositoryObservationCompleteness
    entries: tuple[RepositoryPathCatalogEntry, ...]
    diagnostics: tuple[RepositoryPathDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda item: item.path.value)))
        object.__setattr__(self, "diagnostics", tuple(sorted(set(self.diagnostics))))

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return RepositoryFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class RepositoryPathClassificationResult:
    catalog: RepositoryPathCatalog

    @property
    def fingerprint(self) -> RepositoryFingerprint:
        return self.catalog.fingerprint

    @property
    def diagnostics(self) -> tuple[RepositoryPathDiagnostic, ...]:
        return self.catalog.diagnostics


class RepositoryPathClassificationService:
    """Classify supplied facts only; grants no observation or mutation authority."""

    def classify(
        self,
        *,
        repository_id: RepositoryIdentity,
        checkout_id: RepositoryCheckoutIdentity,
        worktree_id: RepositoryWorktreeIdentity | None,
        observation_fingerprint: RepositoryFingerprint,
        platform_profile: RepositoryPlatformProfile,
        policy: RepositoryPathClassificationPolicy,
        facts: tuple[RepositoryPathFacts, ...],
    ) -> RepositoryPathClassificationResult:
        material_rules = {rule.reference: rule.role for rule in policy.material_rules}
        sensitivity_rules = {
            rule.reference: rule.sensitivity for rule in policy.sensitivity_rules
        }
        grouped: dict[str, list[RepositoryPathFacts]] = {}
        for fact in facts:
            grouped.setdefault(fact.path.value, []).append(fact)

        entries: list[RepositoryPathCatalogEntry] = []
        diagnostics: set[RepositoryPathDiagnostic] = set()
        for path_value in sorted(grouped):
            candidates = grouped[path_value]
            primary = min(candidates, key=lambda item: repr(item.semantic_content()))
            path_fingerprint = RepositoryFingerprint.from_content(primary.path)
            path_diagnostics: set[RepositoryPathDiagnostic] = set()

            def diagnose(code: RepositoryPathDiagnosticCode) -> None:
                path_diagnostics.add(RepositoryPathDiagnostic(path_fingerprint, code))

            if len(candidates) > 1:
                diagnose(RepositoryPathDiagnosticCode.PATH_COLLISION)
            if any(
                fact.path.checkout_id != checkout_id
                or fact.path.worktree_id != worktree_id
                or fact.path.profile != platform_profile
                for fact in candidates
            ):
                diagnose(RepositoryPathDiagnosticCode.PATH_BINDING_MISMATCH)

            tracking_values = {fact.tracking for fact in candidates}
            topology_values = {fact.topology for fact in candidates}
            resource_values = {fact.resource_kind for fact in candidates}
            if len(tracking_values) != 1:
                diagnose(RepositoryPathDiagnosticCode.TRACKING_CONFLICT)
            if len(topology_values) != 1:
                diagnose(RepositoryPathDiagnosticCode.TOPOLOGY_CONFLICT)
            if len(resource_values) != 1:
                diagnose(RepositoryPathDiagnosticCode.RESOURCE_KIND_CONFLICT)

            tracking = next(iter(tracking_values)) if len(tracking_values) == 1 else RepositoryGitTracking.UNKNOWN
            topology = next(iter(topology_values)) if len(topology_values) == 1 else RepositoryTopology.UNKNOWN
            resource_kind = (
                next(iter(resource_values))
                if len(resource_values) == 1
                else RepositoryResourceKind.UNKNOWN
            )
            if topology is RepositoryTopology.SPARSE_EXCLUDED and any(
                fact.content_observed for fact in candidates
            ):
                diagnose(RepositoryPathDiagnosticCode.SPARSE_EXCLUDED_CONTENT)
            if topology in {
                RepositoryTopology.SUBMODULE,
                RepositoryTopology.NESTED_REPOSITORY,
            } and any(fact.descendants_observed for fact in candidates):
                diagnose(RepositoryPathDiagnosticCode.TOPOLOGY_CONTENT_TRAVERSAL)
            if resource_kind is RepositoryResourceKind.LINK:
                if policy.link_policy is None:
                    diagnose(RepositoryPathDiagnosticCode.LINK_POLICY_REQUIRED)
                elif policy.link_policy is RepositoryLinkPolicy.REJECT:
                    diagnose(RepositoryPathDiagnosticCode.LINK_REJECTED)

            material_references = {
                reference
                for fact in candidates
                for reference in fact.material_rule_references
            }
            material_values: set[RepositoryMaterialRole] = set()
            for reference in material_references:
                role = material_rules.get(reference)
                if role is None:
                    diagnose(RepositoryPathDiagnosticCode.UNKNOWN_MATERIAL_RULE)
                else:
                    material_values.add(role)
            for fact in candidates:
                generated_reference = fact.generated_rule_reference
                if generated_reference is None:
                    continue
                role = material_rules.get(generated_reference)
                if role is None:
                    diagnose(RepositoryPathDiagnosticCode.UNKNOWN_MATERIAL_RULE)
                elif role is not RepositoryMaterialRole.GENERATED:
                    diagnose(RepositoryPathDiagnosticCode.MATERIAL_ROLE_CONFLICT)
                else:
                    material_values.add(role)
            if len(material_values) > 1:
                diagnose(RepositoryPathDiagnosticCode.MATERIAL_ROLE_CONFLICT)
            material_role = (
                next(iter(material_values))
                if len(material_values) == 1
                else RepositoryMaterialRole.UNKNOWN
            )

            sensitivity_values: set[RepositorySensitivity] = set()
            for fact in candidates:
                sensitivity_reference = fact.sensitivity_rule_reference
                if sensitivity_reference is None:
                    continue
                sensitivity = sensitivity_rules.get(sensitivity_reference)
                if sensitivity is None:
                    diagnose(RepositoryPathDiagnosticCode.UNKNOWN_SENSITIVITY_RULE)
                else:
                    sensitivity_values.add(sensitivity)
            if len(sensitivity_values) > 1:
                diagnose(RepositoryPathDiagnosticCode.SENSITIVITY_CONFLICT)
            sensitivity = (
                next(iter(sensitivity_values))
                if len(sensitivity_values) == 1
                else RepositorySensitivity.UNKNOWN
            )

            fact_completeness = {fact.completeness for fact in candidates}
            if fact_completeness != {RepositoryObservationCompleteness.COMPLETE}:
                diagnose(RepositoryPathDiagnosticCode.FACTS_INCOMPLETE)
            complete = not path_diagnostics and fact_completeness == {
                RepositoryObservationCompleteness.COMPLETE
            }
            entry_completeness = (
                RepositoryObservationCompleteness.COMPLETE
                if complete
                else RepositoryObservationCompleteness.PARTIAL
            )
            classification = RepositoryPathClassification(
                tracking,
                material_role,
                sensitivity,
                topology,
            )
            ordered_path_diagnostics = tuple(sorted(path_diagnostics))
            entries.append(
                RepositoryPathCatalogEntry(
                    primary.path,
                    resource_kind,
                    primary.executable,
                    primary.content_kind,
                    primary.size_class,
                    primary.ownership_scope_reference,
                    entry_completeness,
                    classification,
                    ordered_path_diagnostics,
                )
            )
            diagnostics.update(path_diagnostics)

        catalog_completeness = (
            RepositoryObservationCompleteness.COMPLETE
            if all(
                entry.completeness is RepositoryObservationCompleteness.COMPLETE
                for entry in entries
            )
            else RepositoryObservationCompleteness.PARTIAL
        )
        return RepositoryPathClassificationResult(
            RepositoryPathCatalog(
                repository_id,
                checkout_id,
                worktree_id,
                observation_fingerprint,
                platform_profile,
                policy.policy_id,
                policy.policy_version,
                catalog_completeness,
                tuple(entries),
                tuple(diagnostics),
            )
        )
