from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "backend" / "synapse"
COMPATIBILITY_ADAPTERS = {
    Path("core/__init__.py"),
    Path("core/app.py"),
    Path("core/model_router.py"),
}


@dataclass(frozen=True, order=True)
class ImportEdge:
    source_file: Path
    source_context: str
    target_module: str
    target_context: str


def production_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def import_edges(*, exclude_compatibility: bool = False) -> set[ImportEdge]:
    edges: set[ImportEdge] = set()
    for path in production_files():
        relative = path.relative_to(SOURCE_ROOT)
        if exclude_compatibility and relative in COMPATIBILITY_ADAPTERS:
            continue
        source_context = relative.parts[0]
        for module in imports_for(path):
            if not module.startswith("synapse."):
                continue
            target_context = module.split(".", 2)[1]
            if target_context != source_context:
                edges.add(ImportEdge(relative, source_context, module, target_context))
    return edges


def context_graph() -> set[tuple[str, str]]:
    return {
        (edge.source_context, edge.target_context)
        for edge in import_edges(exclude_compatibility=True)
        if edge.source_context != "bootstrap" and edge.target_context != "bootstrap"
    }


def cyclic_components(
    graph: set[tuple[str, str]],
) -> list[tuple[frozenset[str], int]]:
    nodes = {node for edge in graph for node in edge}
    adjacency = {node: set() for node in nodes}
    for source, target in graph:
        adjacency[source].add(target)

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    lows: dict[str, int] = {}
    components: list[frozenset[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lows[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency[node]:
            if target not in indexes:
                visit(target)
                lows[node] = min(lows[node], lows[target])
            elif target in on_stack:
                lows[node] = min(lows[node], indexes[target])
        if lows[node] != indexes[node]:
            return
        members: set[str] = set()
        while True:
            target = stack.pop()
            on_stack.remove(target)
            members.add(target)
            if target == node:
                break
        if len(members) > 1:
            components.append(frozenset(members))

    for node in sorted(nodes):
        if node not in indexes:
            visit(node)
    return [
        (members, sum(source in members and target in members for source, target in graph))
        for members in components
    ]


def format_violations(rule: str, violations: list[ImportEdge]) -> str:
    details = "\n".join(
        f"- origin={edge.source_file.as_posix()} destination={edge.target_module} rule={rule}"
        for edge in sorted(violations)
    )
    return f"Architecture rule violated: {rule}\n{details}"
