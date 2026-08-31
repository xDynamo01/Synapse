from __future__ import annotations

from collections.abc import Iterable

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillDependencyDeclaration,
    SkillSemanticReference,
)
from synapse.skills.phase2_serialization import canonical_sort_key
from synapse.skills.phase3_errors import SkillStoreNotFound, SkillStoreUnavailable
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase6_errors import (
    CorruptedSkillLifecycleHistory,
    IncompleteSkillLifecycleHistory,
    InvalidSkillActivationParent,
    SkillLifecycleConflict,
    SkillLifecycleStoreUnavailable,
    SkillVersionNotPublished,
)
from synapse.skills.phase6_models import (
    SkillLifecycleProjection,
    SkillSelectionState,
)
from synapse.skills.phase8_compatibility import (
    compatibility_requirements,
    compatibility_status,
)
from synapse.skills.phase8_contracts import (
    SkillDependencyCatalogPage,
    SkillDependencyCatalogProvider,
    SkillLifecycleProjectionProvider,
)
from synapse.skills.phase8_errors import (
    InconsistentSkillDependencyCatalog,
    InvalidSkillCompatibilityObservation,
    InvalidSkillDependencyDeclaration,
    SkillDependencyCatalogUnavailable,
    SkillDependencySubjectNotPublished,
)
from synapse.skills.phase8_matching import (
    constraint_has_solution,
    matches_declaration,
)
from synapse.skills.phase8_models import (
    AnalyzeSkillDependenciesRequest,
    SkillCompatibilityObservation,
    SkillCompatibilityRequirementFact,
    SkillCompatibilityRequirementId,
    SkillCompatibilityStatus,
    SkillDependencyAnalysis,
    SkillDependencyAnalysisStatus,
    SkillDependencyCandidateFact,
    SkillDependencyCardinality,
    SkillDependencyConstraintStatus,
    SkillDependencyDiagnostic,
    SkillDependencyDiagnosticCode,
    SkillDependencyDiagnosticSeverity,
    SkillDependencyId,
    SkillDependencyIncompleteReason,
    SkillDependencyLifecycleStatus,
    SkillDependencyRequirementFact,
    SkillDependencyRequirementStatus,
)


class SkillDependencyAnalysisService:
    """Derive dependency facts without choosing, writing or progressing state."""

    def __init__(
        self,
        catalog: SkillDependencyCatalogProvider,
        lifecycle: SkillLifecycleProjectionProvider,
    ) -> None:
        self._catalog = catalog
        self._lifecycle = lifecycle

    def analyze(
        self, request: AnalyzeSkillDependenciesRequest
    ) -> SkillDependencyAnalysis:
        subject = self._subject(request.subject)
        declarations = _validated_declarations(subject)
        observations = _validated_observations(request)
        requirements: list[SkillDependencyRequirementFact] = []
        candidate_facts: list[SkillDependencyCandidateFact] = []
        compatibility_facts: dict[
            SkillCompatibilityRequirementId, SkillCompatibilityRequirementFact
        ] = {}
        diagnostics: set[SkillDependencyDiagnostic] = set()
        incomplete: set[SkillDependencyIncompleteReason] = set()
        used_observations: set[SkillSemanticReference] = set()

        for declaration in declarations:
            dependency_id = SkillDependencyId.from_declaration(
                subject.identity, declaration
            )
            try:
                page = self._catalog.list_dependency_candidates(
                    declaration.skill_id, request.candidate_limit
                )
            except SkillStoreUnavailable:
                incomplete.add(SkillDependencyIncompleteReason.CATALOG_UNAVAILABLE)
                diagnostics.add(
                    _diagnostic(
                        subject.identity,
                        dependency_id,
                        SkillDependencyDiagnosticCode.CATALOG_UNAVAILABLE,
                        SkillDependencyDiagnosticSeverity.INCOMPLETE,
                    )
                )
                requirements.append(
                    _requirement_fact(
                        subject.identity,
                        declaration,
                        dependency_id,
                        (),
                        (),
                        SkillDependencyRequirementStatus.INCOMPLETE,
                    )
                )
                continue
            records = _validated_catalog_page(
                declaration, page, request.candidate_limit.limit
            )
            dependency_incomplete = not page.complete
            if dependency_incomplete:
                incomplete.add(SkillDependencyIncompleteReason.CATALOG_TRUNCATED)
                diagnostics.add(
                    _diagnostic(
                        subject.identity,
                        dependency_id,
                        SkillDependencyDiagnosticCode.CATALOG_TRUNCATED,
                        SkillDependencyDiagnosticSeverity.INCOMPLETE,
                    )
                )

            matching: list[PublishedSkillVersionId] = []
            eligible: list[PublishedSkillVersionId] = []
            compatibility_mismatch = False
            lifecycle_ineligible = False
            compatibility_conflict = False
            for candidate_record in records:
                candidate = candidate_record.identity
                if not matches_declaration(declaration, candidate.version):
                    candidate_facts.append(
                        SkillDependencyCandidateFact(
                            dependency_id=dependency_id,
                            candidate=candidate,
                            constraint_status=SkillDependencyConstraintStatus.MISMATCH,
                            lifecycle_status=None,
                            compatibility_status=SkillCompatibilityStatus.UNKNOWN,
                            compatibility_requirement_ids=(),
                            observation_refs=(),
                        )
                    )
                    continue

                matching.append(candidate)
                lifecycle_status = self._lifecycle_status(candidate)
                if lifecycle_status in {
                    SkillDependencyLifecycleStatus.UNAVAILABLE,
                    SkillDependencyLifecycleStatus.INCOMPLETE,
                    SkillDependencyLifecycleStatus.INCONSISTENT,
                }:
                    dependency_incomplete = True
                    reason, code = _lifecycle_incomplete_reason(lifecycle_status)
                    incomplete.add(reason)
                    diagnostics.add(
                        _diagnostic(
                            subject.identity,
                            dependency_id,
                            code,
                            SkillDependencyDiagnosticSeverity.INCOMPLETE,
                        )
                    )
                    candidate_facts.append(
                        SkillDependencyCandidateFact(
                            dependency_id=dependency_id,
                            candidate=candidate,
                            constraint_status=SkillDependencyConstraintStatus.MATCH,
                            lifecycle_status=lifecycle_status,
                            compatibility_status=SkillCompatibilityStatus.UNKNOWN,
                            compatibility_requirement_ids=(),
                            observation_refs=(),
                        )
                    )
                    continue

                candidate_requirements = compatibility_requirements(
                    subject, candidate_record
                )
                for fact in candidate_requirements:
                    compatibility_facts[fact.requirement_id] = fact
                (
                    candidate_compatibility,
                    observation_refs,
                    missing_observation,
                ) = compatibility_status(
                    subject,
                    candidate_record,
                    candidate_requirements,
                    observations,
                    request.analysis_profile_ref,
                    used_observations,
                )
                if missing_observation:
                    dependency_incomplete = True
                    incomplete.update(
                        {
                            SkillDependencyIncompleteReason.COMPATIBILITY_UNKNOWN,
                            SkillDependencyIncompleteReason.OBSERVATION_MISSING,
                        }
                    )
                    diagnostics.add(
                        _diagnostic(
                            subject.identity,
                            dependency_id,
                            SkillDependencyDiagnosticCode.COMPATIBILITY_UNKNOWN,
                            SkillDependencyDiagnosticSeverity.INCOMPLETE,
                        )
                    )
                if candidate_compatibility in {
                    SkillCompatibilityStatus.DECLARED_INCOMPATIBLE,
                    SkillCompatibilityStatus.OBSERVED_INCOMPATIBLE,
                }:
                    compatibility_mismatch = True
                if (
                    candidate_compatibility
                    is SkillCompatibilityStatus.CONFLICTING_INFORMATION
                ):
                    compatibility_conflict = True
                    diagnostics.add(
                        _diagnostic(
                            subject.identity,
                            dependency_id,
                            SkillDependencyDiagnosticCode.CONFLICTING_COMPATIBILITY,
                            SkillDependencyDiagnosticSeverity.BLOCKING,
                        )
                    )
                if lifecycle_status is not SkillDependencyLifecycleStatus.ELIGIBLE:
                    lifecycle_ineligible = True
                if (
                    lifecycle_status is SkillDependencyLifecycleStatus.ELIGIBLE
                    and candidate_compatibility
                    in {
                        SkillCompatibilityStatus.DECLARED_COMPATIBLE,
                        SkillCompatibilityStatus.OBSERVED_COMPATIBLE,
                    }
                ):
                    eligible.append(candidate)
                candidate_facts.append(
                    SkillDependencyCandidateFact(
                        dependency_id=dependency_id,
                        candidate=candidate,
                        constraint_status=SkillDependencyConstraintStatus.MATCH,
                        lifecycle_status=lifecycle_status,
                        compatibility_status=candidate_compatibility,
                        compatibility_requirement_ids=tuple(
                            sorted(
                                (
                                    fact.requirement_id
                                    for fact in candidate_requirements
                                ),
                                key=str,
                            )
                        ),
                        observation_refs=observation_refs,
                    )
                )

            requirement_status = _requirement_status(
                eligible, dependency_incomplete, compatibility_conflict
            )
            requirements.append(
                _requirement_fact(
                    subject.identity,
                    declaration,
                    dependency_id,
                    matching,
                    eligible,
                    requirement_status,
                )
            )
            _add_requirement_diagnostic(
                diagnostics,
                subject.identity,
                declaration,
                dependency_id,
                records,
                matching,
                eligible,
                dependency_incomplete,
                lifecycle_ineligible,
                compatibility_mismatch,
            )

        if any(
            observation.observation_ref not in used_observations
            for observation in observations
        ):
            raise InvalidSkillCompatibilityObservation()

        ordered_requirements = tuple(
            sorted(requirements, key=lambda fact: str(fact.dependency_id))
        )
        ordered_candidates = tuple(
            sorted(
                candidate_facts,
                key=lambda fact: (
                    str(fact.dependency_id),
                    _version_order_text(fact.candidate),
                ),
            )
        )
        ordered_compatibility = tuple(
            compatibility_facts[key]
            for key in sorted(compatibility_facts, key=str)
        )
        ordered_diagnostics = tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    item.code.value,
                    item.severity.value,
                    (
                        str(item.dependency_id)
                        if item.dependency_id is not None
                        else ""
                    ),
                ),
            )
        )
        incomplete_reasons = tuple(
            sorted(incomplete, key=lambda item: item.value)
        )
        has_unsatisfied_required = any(
            requirement.cardinality is SkillDependencyCardinality.REQUIRED
            and requirement.status is SkillDependencyRequirementStatus.UNSATISFIED
            for requirement in ordered_requirements
        )
        has_conflicting_facts = any(
            candidate.compatibility_status
            is SkillCompatibilityStatus.CONFLICTING_INFORMATION
            for candidate in ordered_candidates
        )
        return SkillDependencyAnalysis(
            subject=subject.identity,
            requirements=ordered_requirements,
            candidates=ordered_candidates,
            compatibility_requirements=ordered_compatibility,
            observation_refs=tuple(
                sorted(used_observations, key=lambda item: str(item))
            ),
            diagnostics=ordered_diagnostics,
            incomplete_reasons=incomplete_reasons,
            status=_analysis_status(
                has_unsatisfied_required,
                has_conflicting_facts,
                incomplete_reasons,
            ),
            complete=not incomplete_reasons,
            has_unsatisfied_required=has_unsatisfied_required,
            has_conflicting_facts=has_conflicting_facts,
            analysis_profile_ref=request.analysis_profile_ref,
        )

    def _subject(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        try:
            record = self._catalog.get_version(identity)
        except SkillStoreNotFound as exc:
            raise SkillDependencySubjectNotPublished() from exc
        except SkillStoreUnavailable as exc:
            raise SkillDependencyCatalogUnavailable() from exc
        if (
            not isinstance(record, PublishedSkillVersionRecord)
            or record.identity != identity
        ):
            raise InconsistentSkillDependencyCatalog()
        return record

    def _lifecycle_status(
        self, identity: PublishedSkillVersionId
    ) -> SkillDependencyLifecycleStatus:
        try:
            projection = self._lifecycle.projection(identity)
        except IncompleteSkillLifecycleHistory:
            return SkillDependencyLifecycleStatus.INCOMPLETE
        except SkillLifecycleStoreUnavailable:
            return SkillDependencyLifecycleStatus.UNAVAILABLE
        except (
            CorruptedSkillLifecycleHistory,
            InvalidSkillActivationParent,
            SkillLifecycleConflict,
            SkillVersionNotPublished,
        ):
            return SkillDependencyLifecycleStatus.INCONSISTENT
        if (
            not isinstance(projection, SkillLifecycleProjection)
            or projection.identity != identity
        ):
            return SkillDependencyLifecycleStatus.INCONSISTENT
        if projection.revoked:
            return SkillDependencyLifecycleStatus.REVOKED
        if (
            projection.superseded
            or projection.selection_state is SkillSelectionState.SUPERSEDED
        ):
            return SkillDependencyLifecycleStatus.SUPERSEDED
        if projection.deprecated:
            return SkillDependencyLifecycleStatus.DEPRECATED
        if (
            projection.selection_state is SkillSelectionState.ELIGIBLE
            and projection.resolvable
        ):
            return SkillDependencyLifecycleStatus.ELIGIBLE
        return SkillDependencyLifecycleStatus.INCONSISTENT


def _validated_declarations(
    subject: PublishedSkillVersionRecord,
) -> tuple[SkillDependencyDeclaration, ...]:
    declarations = subject.manifest.dependencies
    if not isinstance(declarations, tuple) or any(
        not isinstance(item, SkillDependencyDeclaration) for item in declarations
    ):
        raise InvalidSkillDependencyDeclaration()
    for declaration in declarations:
        if declaration.skill_id == subject.identity.skill_id:
            raise InvalidSkillDependencyDeclaration()
        if (
            declaration.constraint is not None
            and not constraint_has_solution(declaration.constraint)
        ):
            raise InvalidSkillDependencyDeclaration()
    return tuple(sorted(declarations, key=canonical_sort_key))


def _validated_observations(
    request: AnalyzeSkillDependenciesRequest,
) -> tuple[SkillCompatibilityObservation, ...]:
    refs: set[SkillSemanticReference] = set()
    ordered = sorted(
        request.observations,
        key=lambda item: (
            str(item.observation_ref),
            item.observed_at.isoformat(),
        ),
    )
    for observation in ordered:
        if (
            observation.subject != request.subject
            or observation.analysis_profile_ref != request.analysis_profile_ref
            or observation.observation_ref in refs
        ):
            raise InvalidSkillCompatibilityObservation()
        refs.add(observation.observation_ref)
    return tuple(ordered)


def _validated_catalog_page(
    declaration: SkillDependencyDeclaration,
    page: SkillDependencyCatalogPage,
    limit: int,
) -> tuple[PublishedSkillVersionRecord, ...]:
    if not isinstance(page, SkillDependencyCatalogPage) or len(page.records) > limit:
        raise InconsistentSkillDependencyCatalog()
    identities: set[PublishedSkillVersionId] = set()
    for record in page.records:
        if (
            record.identity.skill_id != declaration.skill_id
            or record.identity in identities
        ):
            raise InconsistentSkillDependencyCatalog()
        identities.add(record.identity)
    return tuple(sorted(page.records, key=lambda item: _version_order_text(item.identity)))


def _requirement_status(
    eligible: list[PublishedSkillVersionId],
    incomplete: bool,
    conflicting: bool,
) -> SkillDependencyRequirementStatus:
    if conflicting:
        return SkillDependencyRequirementStatus.UNSATISFIED
    if incomplete:
        return SkillDependencyRequirementStatus.INCOMPLETE
    if eligible:
        return SkillDependencyRequirementStatus.SATISFIED
    return SkillDependencyRequirementStatus.UNSATISFIED


def _requirement_fact(
    owner: PublishedSkillVersionId,
    declaration: SkillDependencyDeclaration,
    dependency_id: SkillDependencyId,
    matching: Iterable[PublishedSkillVersionId],
    eligible: Iterable[PublishedSkillVersionId],
    status: SkillDependencyRequirementStatus,
) -> SkillDependencyRequirementFact:
    return SkillDependencyRequirementFact(
        dependency_id=dependency_id,
        owner=owner,
        declaration=declaration,
        cardinality=(
            SkillDependencyCardinality.OPTIONAL
            if declaration.optional
            else SkillDependencyCardinality.REQUIRED
        ),
        matching_candidates=tuple(sorted(matching, key=_version_order_text)),
        eligible_candidates=tuple(sorted(eligible, key=_version_order_text)),
        status=status,
    )


def _add_requirement_diagnostic(
    diagnostics: set[SkillDependencyDiagnostic],
    subject: PublishedSkillVersionId,
    declaration: SkillDependencyDeclaration,
    dependency_id: SkillDependencyId,
    records: tuple[PublishedSkillVersionRecord, ...],
    matching: list[PublishedSkillVersionId],
    eligible: list[PublishedSkillVersionId],
    incomplete: bool,
    lifecycle_ineligible: bool,
    compatibility_mismatch: bool,
) -> None:
    if incomplete:
        return
    if not records:
        code = (
            SkillDependencyDiagnosticCode.OPTIONAL_DEPENDENCY_UNAVAILABLE
            if declaration.optional
            else SkillDependencyDiagnosticCode.NO_PUBLISHED_VERSION
        )
    elif not matching:
        code = (
            SkillDependencyDiagnosticCode.OPTIONAL_DEPENDENCY_UNMATCHED
            if declaration.optional
            else SkillDependencyDiagnosticCode.NO_CONSTRAINT_MATCH
        )
    elif not eligible and compatibility_mismatch:
        code = (
            SkillDependencyDiagnosticCode.OPTIONAL_DEPENDENCY_INCOMPATIBLE
            if declaration.optional
            else SkillDependencyDiagnosticCode.COMPATIBILITY_MISMATCH
        )
    elif not eligible and lifecycle_ineligible:
        code = (
            SkillDependencyDiagnosticCode.OPTIONAL_DEPENDENCY_INCOMPATIBLE
            if declaration.optional
            else SkillDependencyDiagnosticCode.NO_LIFECYCLE_ELIGIBLE
        )
    else:
        return
    diagnostics.add(
        _diagnostic(
            subject,
            dependency_id,
            code,
            (
                SkillDependencyDiagnosticSeverity.WARNING
                if declaration.optional
                else SkillDependencyDiagnosticSeverity.BLOCKING
            ),
        )
    )


def _diagnostic(
    subject: PublishedSkillVersionId,
    dependency_id: SkillDependencyId,
    code: SkillDependencyDiagnosticCode,
    severity: SkillDependencyDiagnosticSeverity,
) -> SkillDependencyDiagnostic:
    return SkillDependencyDiagnostic(subject, code, severity, dependency_id)


def _lifecycle_incomplete_reason(
    status: SkillDependencyLifecycleStatus,
) -> tuple[SkillDependencyIncompleteReason, SkillDependencyDiagnosticCode]:
    if status is SkillDependencyLifecycleStatus.UNAVAILABLE:
        return (
            SkillDependencyIncompleteReason.LIFECYCLE_UNAVAILABLE,
            SkillDependencyDiagnosticCode.LIFECYCLE_UNAVAILABLE,
        )
    if status is SkillDependencyLifecycleStatus.INCOMPLETE:
        return (
            SkillDependencyIncompleteReason.LIFECYCLE_INCOMPLETE,
            SkillDependencyDiagnosticCode.LIFECYCLE_INCOMPLETE,
        )
    return (
        SkillDependencyIncompleteReason.LIFECYCLE_INCONSISTENT,
        SkillDependencyDiagnosticCode.LIFECYCLE_INCONSISTENT,
    )


def _analysis_status(
    has_unsatisfied_required: bool,
    has_conflicting_facts: bool,
    incomplete: tuple[SkillDependencyIncompleteReason, ...],
) -> SkillDependencyAnalysisStatus:
    if has_conflicting_facts:
        return SkillDependencyAnalysisStatus.CONFLICTING_FACTS
    if incomplete:
        return SkillDependencyAnalysisStatus.INCOMPLETE
    if has_unsatisfied_required:
        return SkillDependencyAnalysisStatus.UNSATISFIABLE
    return SkillDependencyAnalysisStatus.SATISFIABLE


def _version_order_text(
    identity: PublishedSkillVersionId,
) -> tuple[object, str, str]:
    return (
        identity.version.precedence_key(),
        str(identity.version),
        identity.to_canonical_text(),
    )
