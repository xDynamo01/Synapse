import ast

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for

ROOT = SOURCE_ROOT / "operational_projection"
PRESENTATION_TERMS = {"particle", "glow", "color", "position", "animation", "webgl", "gpu"}


def test_operational_projection_imports_only_stdlib_and_itself() -> None:
    violations = [
        (path.name, module)
        for path in ROOT.glob("*.py")
        for module in imports_for(path)
        if module.startswith("synapse.") and not module.startswith("synapse.operational_projection")
    ]
    assert not violations


def test_operational_projection_has_no_visual_vocabulary_or_io() -> None:
    source = "\n".join(path.read_text(encoding="utf-8").casefold() for path in ROOT.glob("*.py"))
    assert not PRESENTATION_TERMS.intersection(source.split())
    forbidden = {"open", "exec", "eval", "run", "Popen"}
    calls = []
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls.extend(
            getattr(node.func, "id", getattr(node.func, "attr", ""))
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        )
    assert forbidden.isdisjoint(calls)


def test_operational_projection_is_outside_cycles() -> None:
    assert all(
        "operational_projection" not in members for members, _ in cyclic_components(context_graph())
    )
