from __future__ import annotations

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId
from synapse.skills.phase8_matching import matches_declaration
from synapse.skills.phase8_models import (
    SkillCompatibilityStatus,
    SkillDependencyAnalysis,
    SkillDependencyAnalysisStatus,
    SkillDependencyCandidateFact,
    SkillDependencyCardinality,
    SkillDependencyConstraintStatus,
    SkillDependencyCycleFact,
    SkillDependencyCycleStatus,
    SkillDependencyGraphEdge,
    SkillDependencyGraphSnapshot,
    SkillDependencyId,
    SkillDependencyLifecycleStatus,
    SkillDependencyRequirementFact,
    SkillDependencyRequirementStatus,
)
from synapse.skills.phase9_errors import (
    InconsistentSkillDependencyAnalysis,
    InconsistentSkillResolutionGraph,
    InvalidSkillDependencyResolutionRequest,
)
from synapse.skills.phase9_groups import resolve_dependency_group
from synapse.skills.phase9_models import (
    ResolveSkillDependenciesRequest,
    SkillDependencyRequirementResolution,
    SkillDependencyRequirementResolutionStatus,
    SkillDependencyResolutionConflict,
    SkillDependencyResolutionConflictKind,
    SkillDependencyResolutionDiagnostic,
    SkillDependencyResolutionDiagnosticCode,
    SkillDependencyResolutionDiagnosticSeverity,
    SkillDependencyResolutionPlan,
    SkillDependencyResolutionStatus,
    SkillResolvedDependency,
)
from synapse.skills.phase9_policy import (
    SkillDependencyCompletenessPolicy,
    SkillDependencyResolutionPolicy,
)
from synapse.skills.phase9_selection import requirement_selection_view


class SkillDependencyResolutionService:
    """Resolve supplied facts deterministically without runtime side effects."""

    def resolve(
        self, request: ResolveSkillDependenciesRequest
    ) -> SkillDependencyResolutionPlan:
        if request.subject != request.analysis.subject:
            raise InvalidSkillDependencyResolutionRequest()
        requirements, candidates = _validated_analysis(request)
        graph = _validated_graph(request.graph)
        groups = _group_requirements(requirements)
        if _input_exceeds_limits(
            request.policy, requirements, candidates, groups, graph
        ):
            return _limit_plan(request, requirements)
        if (
            request.policy.completeness
            is SkillDependencyCompletenessPolicy.REQUIRE_COMPLETE_ANALYSIS
            and not request.analysis.complete
        ):
            return _incomplete_plan(request, requirements)

        outcomes: list[SkillDependencyRequirementResolution] = []
        resolved: list[SkillResolvedDependency] = []
        conflicts: list[SkillDependencyResolutionConflict] = []
        diagnostics: list[SkillDependencyResolutionDiagnostic] = []
        search_states = 0
        for target in sorted(groups, key=str):
            views = tuple(
                requirement_selection_view(
                    fact,
                    candidates.get(fact.dependency_id, ()),
                    request.policy,
                )
                for fact in groups[target]
            )
            search_states += sum(len(view.decisions) for view in views)
            if search_states > request.policy.limits.max_search_states:
                return _limit_plan(request, requirements)
            group = resolve_dependency_group(target, views, request.policy)
            outcomes.extend(group.requirements)
            resolved.extend(group.resolved)
            conflicts.extend(group.conflicts)
            diagnostics.extend(group.diagnostics)

        graph_cycles = _applicable_graph_cycles(
            graph, request.subject, tuple(resolved)
        )
        for cycle in graph_cycles:
            if cycle.status is SkillDependencyCycleStatus.BLOCKING:
                conflicts.append(
                    SkillDependencyResolutionConflict(
                        SkillDependencyResolutionConflictKind.GRAPH_CYCLE,
                        cycle.dependency_ids,
                        None,
                        True,
                    )
                )
                diagnostics.append(
                    SkillDependencyResolutionDiagnostic(
                        SkillDependencyResolutionDiagnosticCode.GRAPH_CYCLE,
                        SkillDependencyResolutionDiagnosticSeverity.BLOCKING,
                    )
                )
        if graph is not None and not graph.complete:
            conflicts.append(
                SkillDependencyResolutionConflict(
                    SkillDependencyResolutionConflictKind.INCOMPLETE_FACTS,
                    (),
                    None,
                    True,
                )
            )

        ordered_outcomes = tuple(
            sorted(outcomes, key=lambda item: str(item.dependency_id))
        )
        ordered_resolved = tuple(
            sorted(
                resolved,
                key=lambda item: (
                    str(item.target_skill_id),
                    item.selected.to_canonical_text(),
                    tuple(str(value) for value in item.requirement_ids),
                ),
            )
        )
        ordered_conflicts = tuple(
            sorted(
                set(conflicts),
                key=lambda item: (
                    item.kind.value,
                    str(item.target_skill_id) if item.target_skill_id else "",
                    tuple(str(value) for value in item.requirement_ids),
                ),
            )
        )
        ordered_diagnostics = tuple(
            sorted(
                set(diagnostics),
                key=lambda item: (
                    item.code.value,
                    item.severity.value,
                    str(item.dependency_id) if item.dependency_id else "",
                    str(item.target_skill_id) if item.target_skill_id else "",
                ),
            )
        )
        if len(ordered_diagnostics) > request.policy.limits.max_diagnostics:
            return _limit_plan(request, requirements)
        return _plan(
            request,
            requirements,
            ordered_outcomes,
            ordered_resolved,
            ordered_conflicts,
            ordered_diagnostics,
            graph_cycles,
            graph,
        )


def _validated_analysis(
    request: ResolveSkillDependenciesRequest,
) -> tuple[
    tuple[SkillDependencyRequirementFact, ...],
    dict[SkillDependencyId, tuple[SkillDependencyCandidateFact, ...]],
]:
    analysis = request.analysis
    requirement_by_id: dict[
        SkillDependencyId, SkillDependencyRequirementFact
    ] = {}
    for fact in analysis.requirements:
        if (
            fact.owner != request.subject
            or fact.dependency_id in requirement_by_id
            or (
                fact.cardinality is SkillDependencyCardinality.OPTIONAL
            )
            != fact.declaration.optional
            or len(set(fact.matching_candidates))
            != len(fact.matching_candidates)
            or len(set(fact.eligible_candidates))
            != len(fact.eligible_candidates)
            or fact.dependency_id
            != SkillDependencyId.from_declaration(
                request.subject, fact.declaration
            )
        ):
            raise InconsistentSkillDependencyAnalysis()
        requirement_by_id[fact.dependency_id] = fact
    by_requirement: dict[
        SkillDependencyId, list[SkillDependencyCandidateFact]
    ] = {dependency_id: [] for dependency_id in requirement_by_id}
    pairs: set[tuple[SkillDependencyId, PublishedSkillVersionId]] = set()
    for candidate in analysis.candidates:
        pair = (candidate.dependency_id, candidate.candidate)
        requirement = requirement_by_id.get(candidate.dependency_id)
        if (
            requirement is None
            or pair in pairs
            or candidate.candidate.skill_id != requirement.declaration.skill_id
            or (
                candidate.constraint_status
                is SkillDependencyConstraintStatus.MATCH
            )
            != (
                candidate.candidate in requirement.matching_candidates
                and matches_declaration(
                    requirement.declaration, candidate.candidate.version
                )
            )
            or (
                candidate.constraint_status
                is SkillDependencyConstraintStatus.MATCH
                and candidate.lifecycle_status is None
            )
        ):
            raise InconsistentSkillDependencyAnalysis()
        pairs.add(pair)
        by_requirement[candidate.dependency_id].append(candidate)
    for dependency_id, requirement in requirement_by_id.items():
        matching = {
            candidate.candidate
            for candidate in by_requirement[dependency_id]
            if candidate.constraint_status is SkillDependencyConstraintStatus.MATCH
        }
        if matching != set(requirement.matching_candidates):
            raise InconsistentSkillDependencyAnalysis()
        eligible = {
            candidate.candidate
            for candidate in by_requirement[dependency_id]
            if (
                candidate.constraint_status
                is SkillDependencyConstraintStatus.MATCH
                and candidate.lifecycle_status
                is SkillDependencyLifecycleStatus.ELIGIBLE
                and candidate.compatibility_status
                in {
                    SkillCompatibilityStatus.DECLARED_COMPATIBLE,
                    SkillCompatibilityStatus.OBSERVED_COMPATIBLE,
                }
            )
        }
        if eligible != set(requirement.eligible_candidates):
            raise InconsistentSkillDependencyAnalysis()
        if (
            requirement.status is SkillDependencyRequirementStatus.SATISFIED
            and not eligible
        ) or (
            requirement.status is SkillDependencyRequirementStatus.INCOMPLETE
            and analysis.complete
        ):
            raise InconsistentSkillDependencyAnalysis()
    _validate_analysis_summary(analysis)
    _validate_shared_candidate_facts(by_requirement)
    requirements = tuple(
        sorted(requirement_by_id.values(), key=lambda item: str(item.dependency_id))
    )
    candidates = {
        dependency_id: tuple(
            sorted(
                values,
                key=lambda item: item.candidate.to_canonical_text(),
            )
        )
        for dependency_id, values in by_requirement.items()
    }
    return requirements, candidates


def _validate_analysis_summary(analysis: SkillDependencyAnalysis) -> None:
    has_unsatisfied_required = any(
        requirement.cardinality is SkillDependencyCardinality.REQUIRED
        and requirement.status is SkillDependencyRequirementStatus.UNSATISFIED
        for requirement in analysis.requirements
    )
    has_conflicting_facts = any(
        candidate.compatibility_status
        is SkillCompatibilityStatus.CONFLICTING_INFORMATION
        for candidate in analysis.candidates
    )
    if has_conflicting_facts:
        expected_status = SkillDependencyAnalysisStatus.CONFLICTING_FACTS
    elif analysis.incomplete_reasons:
        expected_status = SkillDependencyAnalysisStatus.INCOMPLETE
    elif has_unsatisfied_required:
        expected_status = SkillDependencyAnalysisStatus.UNSATISFIABLE
    else:
        expected_status = SkillDependencyAnalysisStatus.SATISFIABLE
    if (
        analysis.has_unsatisfied_required != has_unsatisfied_required
        or analysis.has_conflicting_facts != has_conflicting_facts
        or analysis.status is not expected_status
    ):
        raise InconsistentSkillDependencyAnalysis()


def _validate_shared_candidate_facts(
    candidates: dict[
        SkillDependencyId, list[SkillDependencyCandidateFact]
    ],
) -> None:
    dimensions: dict[
        PublishedSkillVersionId,
        tuple[
            SkillDependencyLifecycleStatus,
            SkillCompatibilityStatus,
            tuple[object, ...],
            tuple[object, ...],
        ],
    ] = {}
    for candidate in (
        candidate
        for values in candidates.values()
        for candidate in values
        if candidate.constraint_status is SkillDependencyConstraintStatus.MATCH
    ):
        lifecycle = candidate.lifecycle_status
        if lifecycle is None:
            raise InconsistentSkillDependencyAnalysis()
        current = (
            lifecycle,
            candidate.compatibility_status,
            candidate.compatibility_requirement_ids,
            candidate.observation_refs,
        )
        previous = dimensions.setdefault(candidate.candidate, current)
        if previous != current:
            raise InconsistentSkillDependencyAnalysis()


def _validated_graph(
    graph: SkillDependencyGraphSnapshot | None,
) -> SkillDependencyGraphSnapshot | None:
    if graph is None:
        return None
    if (
        len(set(graph.nodes)) != len(graph.nodes)
        or len(set(graph.edges)) != len(graph.edges)
        or len(set(graph.cycles)) != len(graph.cycles)
    ):
        raise InconsistentSkillResolutionGraph()
    nodes = set(graph.nodes)
    edge_by_pair: dict[
        tuple[PublishedSkillVersionId, PublishedSkillVersionId],
        SkillDependencyGraphEdge,
    ] = {}
    for edge in graph.edges:
        pair = (edge.owner, edge.dependency)
        if (
            edge.owner not in nodes
            or edge.dependency not in nodes
            or pair in edge_by_pair
            or edge.dependency_id
            != SkillDependencyId.from_declaration(
                edge.owner, edge.declaration
            )
            or not matches_declaration(
                edge.declaration, edge.dependency.version
            )
        ):
            raise InconsistentSkillResolutionGraph()
        edge_by_pair[pair] = edge
    for cycle in graph.cycles:
        pairs = tuple(
            zip(
                cycle.nodes,
                (*cycle.nodes[1:], cycle.nodes[0]),
                strict=True,
            )
        )
        cycle_edges = tuple(edge_by_pair.get(pair) for pair in pairs)
        if (
            len(set(cycle.nodes)) != len(cycle.nodes)
            or not set(cycle.nodes).issubset(nodes)
            or any(edge is None for edge in cycle_edges)
        ):
            raise InconsistentSkillResolutionGraph()
        typed_edges = tuple(edge for edge in cycle_edges if edge is not None)
        if (
            tuple(edge.dependency_id for edge in typed_edges)
            != cycle.dependency_ids
            or (
                all(not edge.declaration.optional for edge in typed_edges)
                != (cycle.status is SkillDependencyCycleStatus.BLOCKING)
            )
        ):
            raise InconsistentSkillResolutionGraph()
    return graph


def _group_requirements(
    requirements: tuple[SkillDependencyRequirementFact, ...],
) -> dict[SkillId, tuple[SkillDependencyRequirementFact, ...]]:
    groups: dict[SkillId, list[SkillDependencyRequirementFact]] = {}
    for requirement in requirements:
        groups.setdefault(requirement.declaration.skill_id, []).append(requirement)
    return {
        target: tuple(sorted(values, key=lambda item: str(item.dependency_id)))
        for target, values in groups.items()
    }


def _input_exceeds_limits(
    policy: SkillDependencyResolutionPolicy,
    requirements: tuple[SkillDependencyRequirementFact, ...],
    candidates: dict[
        SkillDependencyId, tuple[SkillDependencyCandidateFact, ...]
    ],
    groups: dict[SkillId, tuple[SkillDependencyRequirementFact, ...]],
    graph: SkillDependencyGraphSnapshot | None,
) -> bool:
    return (
        len(requirements) > policy.limits.max_requirements
        or len(groups) > policy.limits.max_groups
        or any(
            len(candidates.get(requirement.dependency_id, ()))
            > policy.limits.max_candidates_per_requirement
            for requirement in requirements
        )
        or (
            graph is not None
            and (
                len(graph.nodes) > policy.limits.max_graph_nodes
                or len(graph.edges) > policy.limits.max_graph_edges
            )
        )
    )


def _applicable_graph_cycles(
    graph: SkillDependencyGraphSnapshot | None,
    subject: PublishedSkillVersionId,
    resolved: tuple[SkillResolvedDependency, ...],
) -> tuple[SkillDependencyCycleFact, ...]:
    if graph is None:
        return ()
    selected = {subject, *(item.selected for item in resolved)}
    return tuple(
        sorted(
            (
                cycle
                for cycle in graph.cycles
                if set(cycle.nodes).issubset(selected)
            ),
            key=lambda cycle: tuple(
                node.to_canonical_text() for node in cycle.nodes
            ),
        )
    )


def _plan(
    request: ResolveSkillDependenciesRequest,
    requirements: tuple[SkillDependencyRequirementFact, ...],
    outcomes: tuple[SkillDependencyRequirementResolution, ...],
    resolved: tuple[SkillResolvedDependency, ...],
    conflicts: tuple[SkillDependencyResolutionConflict, ...],
    diagnostics: tuple[SkillDependencyResolutionDiagnostic, ...],
    graph_cycles: tuple[SkillDependencyCycleFact, ...],
    graph: SkillDependencyGraphSnapshot | None,
) -> SkillDependencyResolutionPlan:
    required_ids = {
        fact.dependency_id
        for fact in requirements
        if fact.cardinality is SkillDependencyCardinality.REQUIRED
    }
    resolved_ids = {
        outcome.dependency_id
        for outcome in outcomes
        if outcome.status is SkillDependencyRequirementResolutionStatus.RESOLVED
    }
    required_resolved = required_ids.issubset(resolved_ids)
    has_optional_omissions = any(
        outcome.status
        in {
            SkillDependencyRequirementResolutionStatus.OMITTED_NO_CANDIDATE,
            SkillDependencyRequirementResolutionStatus.OMITTED_CONFLICT,
            SkillDependencyRequirementResolutionStatus.OMITTED_POLICY,
            SkillDependencyRequirementResolutionStatus.UNRESOLVED_INCOMPLETE,
        }
        and outcome.dependency_id not in required_ids
        for outcome in outcomes
    )
    incomplete = (
        not request.analysis.complete
        or (graph is not None and not graph.complete)
        or any(
            outcome.status
            is SkillDependencyRequirementResolutionStatus.UNRESOLVED_INCOMPLETE
            for outcome in outcomes
        )
    )
    return SkillDependencyResolutionPlan(
        subject=request.subject,
        resolution_profile_ref=request.resolution_profile_ref,
        policy=request.policy,
        requirements=outcomes,
        resolved=resolved,
        conflicts=conflicts,
        diagnostics=diagnostics,
        graph_cycles=graph_cycles,
        status=_resolution_status(
            conflicts,
            required_resolved,
            has_optional_omissions,
            incomplete,
        ),
        complete=not incomplete,
        required_resolved=required_resolved,
        has_optional_omissions=has_optional_omissions,
        has_degraded_selections=any(item.degraded for item in resolved),
    )


def _resolution_status(
    conflicts: tuple[SkillDependencyResolutionConflict, ...],
    required_resolved: bool,
    optional_omissions: bool,
    incomplete: bool,
) -> SkillDependencyResolutionStatus:
    if any(
        conflict.kind
        in {
            SkillDependencyResolutionConflictKind.CONSTRAINT_INTERSECTION,
            SkillDependencyResolutionConflictKind.SINGLE_VERSION,
            SkillDependencyResolutionConflictKind.GRAPH_CYCLE,
        }
        and conflict.blocking
        for conflict in conflicts
    ):
        return SkillDependencyResolutionStatus.CONFLICTING
    if incomplete:
        return SkillDependencyResolutionStatus.INCOMPLETE
    if not required_resolved:
        return SkillDependencyResolutionStatus.UNRESOLVABLE
    if optional_omissions:
        return SkillDependencyResolutionStatus.PARTIALLY_RESOLVED
    return SkillDependencyResolutionStatus.RESOLVED


def _limit_plan(
    request: ResolveSkillDependenciesRequest,
    requirements: tuple[SkillDependencyRequirementFact, ...],
) -> SkillDependencyResolutionPlan:
    return _terminal_incomplete_plan(
        request,
        requirements,
        SkillDependencyResolutionConflictKind.SEARCH_LIMIT_EXCEEDED,
        SkillDependencyResolutionDiagnosticCode.SEARCH_LIMIT_EXCEEDED,
    )


def _incomplete_plan(
    request: ResolveSkillDependenciesRequest,
    requirements: tuple[SkillDependencyRequirementFact, ...],
) -> SkillDependencyResolutionPlan:
    return _terminal_incomplete_plan(
        request,
        requirements,
        SkillDependencyResolutionConflictKind.INCOMPLETE_FACTS,
        SkillDependencyResolutionDiagnosticCode.INCOMPLETE_REQUIREMENT,
    )


def _terminal_incomplete_plan(
    request: ResolveSkillDependenciesRequest,
    requirements: tuple[SkillDependencyRequirementFact, ...],
    conflict_kind: SkillDependencyResolutionConflictKind,
    diagnostic_code: SkillDependencyResolutionDiagnosticCode,
) -> SkillDependencyResolutionPlan:
    outcomes = tuple(
        SkillDependencyRequirementResolution(
            requirement.dependency_id,
            SkillDependencyRequirementResolutionStatus.UNRESOLVED_INCOMPLETE,
        )
        for requirement in requirements
    )
    conflict = SkillDependencyResolutionConflict(
        conflict_kind,
        tuple(
            requirement.dependency_id
            for requirement in requirements
            if requirement.cardinality is SkillDependencyCardinality.REQUIRED
        ),
        None,
        True,
    )
    diagnostics = (
        SkillDependencyResolutionDiagnostic(
            diagnostic_code,
            SkillDependencyResolutionDiagnosticSeverity.INCOMPLETE,
        ),
    )
    return SkillDependencyResolutionPlan(
        request.subject,
        request.resolution_profile_ref,
        request.policy,
        outcomes,
        (),
        (conflict,),
        diagnostics,
        (),
        SkillDependencyResolutionStatus.INCOMPLETE,
        False,
        not any(
            requirement.cardinality is SkillDependencyCardinality.REQUIRED
            for requirement in requirements
        ),
        any(
            requirement.cardinality is SkillDependencyCardinality.OPTIONAL
            for requirement in requirements
        ),
        False,
    )
