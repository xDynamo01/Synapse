from __future__ import annotations

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase8_errors import (
    InconsistentSkillDependencyGraph,
    InvalidSkillDependencyGraphInput,
)
from synapse.skills.phase8_matching import matches_declaration
from synapse.skills.phase8_models import (
    AnalyzeSkillDependencyGraphRequest,
    SkillDependencyCycleFact,
    SkillDependencyCycleStatus,
    SkillDependencyGraphEdge,
    SkillDependencyGraphInput,
    SkillDependencyGraphSnapshot,
    SkillDependencyId,
)

_MAX_CYCLES = 1000


class SkillDependencyGraphAnalysisService:
    """Analyze an explicit, non-authoritative graph boundary without resolution."""

    def analyze(
        self, request: AnalyzeSkillDependencyGraphRequest
    ) -> SkillDependencyGraphSnapshot:
        return _graph_snapshot(request.graph)


def _graph_snapshot(
    graph: SkillDependencyGraphInput,
) -> SkillDependencyGraphSnapshot:
    identities = tuple(record.identity for record in graph.nodes)
    if len(set(identities)) != len(identities) or len(set(graph.edges)) != len(
        graph.edges
    ):
        raise InvalidSkillDependencyGraphInput()
    records = {record.identity: record for record in graph.nodes}
    nodes = tuple(sorted(identities, key=lambda item: item.to_canonical_text()))
    edges = tuple(
        sorted(
            graph.edges,
            key=lambda edge: (
                edge.owner.to_canonical_text(),
                edge.dependency.to_canonical_text(),
                str(edge.dependency_id),
            ),
        )
    )
    pairs: set[tuple[PublishedSkillVersionId, PublishedSkillVersionId]] = set()
    for edge in edges:
        pair = (edge.owner, edge.dependency)
        owner_record = records.get(edge.owner)
        if (
            owner_record is None
            or edge.dependency not in records
            or pair in pairs
            or edge.declaration not in owner_record.manifest.dependencies
            or edge.declaration.skill_id != edge.dependency.skill_id
            or edge.dependency_id
            != SkillDependencyId.from_declaration(edge.owner, edge.declaration)
            or not matches_declaration(
                edge.declaration, edge.dependency.version
            )
        ):
            raise InvalidSkillDependencyGraphInput()
        pairs.add(pair)
    return SkillDependencyGraphSnapshot(
        nodes=nodes,
        edges=edges,
        cycles=_cycles(nodes, edges),
        complete=graph.complete,
    )


def _cycles(
    nodes: tuple[PublishedSkillVersionId, ...],
    edges: tuple[SkillDependencyGraphEdge, ...],
) -> tuple[SkillDependencyCycleFact, ...]:
    adjacency: dict[
        PublishedSkillVersionId, tuple[PublishedSkillVersionId, ...]
    ] = {}
    edge_by_pair = {(edge.owner, edge.dependency): edge for edge in edges}
    for node in nodes:
        adjacency[node] = tuple(
            sorted(
                (
                    edge.dependency
                    for edge in edges
                    if edge.owner == node
                ),
                key=lambda item: item.to_canonical_text(),
            )
        )
    found: dict[
        tuple[str, ...], tuple[PublishedSkillVersionId, ...]
    ] = {}

    def visit(
        start: PublishedSkillVersionId,
        current: PublishedSkillVersionId,
        trail: tuple[PublishedSkillVersionId, ...],
    ) -> None:
        for target in adjacency[current]:
            if target == start:
                canonical = _canonical_cycle(trail)
                found[
                    tuple(item.to_canonical_text() for item in canonical)
                ] = canonical
                if len(found) > _MAX_CYCLES:
                    raise InconsistentSkillDependencyGraph()
            elif target not in trail:
                visit(start, target, (*trail, target))

    for node in nodes:
        visit(node, node, (node,))

    cycles: list[SkillDependencyCycleFact] = []
    for cycle_nodes in found.values():
        pairs = tuple(
            zip(
                cycle_nodes,
                (*cycle_nodes[1:], cycle_nodes[0]),
                strict=True,
            )
        )
        cycle_edges = tuple(edge_by_pair[pair] for pair in pairs)
        required_only = all(
            not edge.declaration.optional for edge in cycle_edges
        )
        cycles.append(
            SkillDependencyCycleFact(
                nodes=cycle_nodes,
                dependency_ids=tuple(
                    edge.dependency_id for edge in cycle_edges
                ),
                status=(
                    SkillDependencyCycleStatus.BLOCKING
                    if required_only
                    else SkillDependencyCycleStatus.ADVISORY
                ),
            )
        )
    return tuple(
        sorted(
            cycles,
            key=lambda cycle: tuple(
                node.to_canonical_text() for node in cycle.nodes
            ),
        )
    )


def _canonical_cycle(
    nodes: tuple[PublishedSkillVersionId, ...],
) -> tuple[PublishedSkillVersionId, ...]:
    rotations = tuple(nodes[index:] + nodes[:index] for index in range(len(nodes)))
    return min(
        rotations,
        key=lambda items: tuple(item.to_canonical_text() for item in items),
    )
