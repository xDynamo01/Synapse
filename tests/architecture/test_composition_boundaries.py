import ast
from pathlib import Path

from synapse.bootstrap.container import RuntimeContainer as CanonicalContainer
from synapse.core.app import RuntimeContainer as CompatibilityContainer

from .support import SOURCE_ROOT, production_files


def test_runtime_container_has_one_canonical_definition() -> None:
    definitions: list[Path] = []
    for path in production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.ClassDef) and node.name == "RuntimeContainer" for node in tree.body
        ):
            definitions.append(path.relative_to(SOURCE_ROOT))
    assert definitions == [Path("bootstrap/container.py")]
    assert CompatibilityContainer is CanonicalContainer


def test_complete_container_composition_occurs_only_in_bootstrap() -> None:
    construction_points = []
    for path in production_files():
        relative = path.relative_to(SOURCE_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "RuntimeContainer":
                    construction_points.append(relative)
    assert construction_points == [Path("bootstrap/application.py")], (
        "RuntimeContainer must have exactly one production construction point: "
        + ", ".join(path.as_posix() for path in construction_points)
    )


def test_application_coordinates_bounded_feature_builders() -> None:
    features = SOURCE_ROOT / "bootstrap" / "features"
    builders = []
    for path in features.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        builders.extend(
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name.endswith("FeatureBuilder")
        )
    assert len(builders) == 12
    application = SOURCE_ROOT / "bootstrap" / "application.py"
    # Intelligence Trust Boundary adds one explicitly wired feature and its
    # delivery binding; application remains a composition-only module.
    assert len(application.read_text(encoding="utf-8").splitlines()) < 480


def test_core_app_is_a_thin_compatibility_adapter() -> None:
    path = SOURCE_ROOT / "core" / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assert not [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))]
    assert len(path.read_text(encoding="utf-8").splitlines()) <= 12
