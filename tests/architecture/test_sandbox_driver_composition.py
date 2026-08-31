from __future__ import annotations

from tests.architecture.support import SOURCE_ROOT, imports_for

COMPOSITION_ROOT = SOURCE_ROOT / "sandbox_driver_composition"
BOOTSTRAP_ROOT = SOURCE_ROOT / "bootstrap"


def test_local_driver_composition_has_only_intended_synapse_dependencies() -> None:
    imports = {
        module
        for path in COMPOSITION_ROOT.rglob("*.py")
        for module in imports_for(path)
        if module.startswith("synapse.")
    }
    assert imports
    assert all(
        module.startswith(("synapse.sandbox", "synapse.sandbox_drivers")) for module in imports
    )


def test_global_bootstrap_never_imports_local_driver_composition() -> None:
    assert not [
        path.relative_to(SOURCE_ROOT)
        for path in BOOTSTRAP_ROOT.rglob("*.py")
        if any(
            module.startswith("synapse.sandbox_driver_composition") for module in imports_for(path)
        )
    ]
