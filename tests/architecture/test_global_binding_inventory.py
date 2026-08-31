from __future__ import annotations

import ast
from pathlib import Path

from synapse.bootstrap import (
    GlobalBindingActivationAuthority,
    GlobalBindingActivationState,
    GlobalBindingAvailability,
    GlobalBindingId,
    GlobalBindingMode,
    GlobalBindingRequirement,
    build_application,
    canonical_global_binding_inventory,
)

from .support import SOURCE_ROOT


def test_inventory_is_complete_unique_and_immutable() -> None:
    inventory = canonical_global_binding_inventory()

    assert isinstance(inventory, tuple)
    assert tuple(item.binding_id for item in inventory) == tuple(GlobalBindingId)
    assert len({item.binding_id for item in inventory}) == len(inventory) == 9
    active = {
        item.binding_id
        for item in inventory
        if item.activation_authority is GlobalBindingActivationAuthority.AUTHORIZED
        and item.activation_state is GlobalBindingActivationState.ACTIVE
    }
    assert active == {
        GlobalBindingId.PRIVATE_EVALS,
        GlobalBindingId.CODING_SESSIONS,
        GlobalBindingId.SKILLS_RUNTIME_PHASE_2,
        GlobalBindingId.SANDBOX_EXECUTION_BOUNDARY,
        GlobalBindingId.REPOSITORY_RUNTIME,
        GlobalBindingId.VOICE_AUDIO_PERCEPTION,
        GlobalBindingId.DEPLOYMENT_RUNTIME,
    }
    assert all(
        item.activation_authority is GlobalBindingActivationAuthority.NOT_AUTHORIZED
        and item.activation_state is GlobalBindingActivationState.INERT
        for item in inventory
        if item.binding_id not in active
    )


def test_inventory_preserves_required_optional_and_local_composition_facts() -> None:
    inventory = {item.binding_id: item for item in canonical_global_binding_inventory()}

    assert inventory[GlobalBindingId.DEPLOYMENT_RUNTIME].requirement is (
        GlobalBindingRequirement.REQUIRED
    )
    assert inventory[GlobalBindingId.DEPLOYMENT_RUNTIME].availability is (
        GlobalBindingAvailability.AVAILABLE
    )
    assert inventory[GlobalBindingId.DEPLOYMENT_RUNTIME].mode is GlobalBindingMode.GLOBAL
    assert (
        inventory[GlobalBindingId.DEPLOYMENT_RUNTIME].composition_reference
        == "deployment_composition"
    )
    assert not inventory[GlobalBindingId.DEPLOYMENT_RUNTIME].blocks_backend_readiness
    assert inventory[GlobalBindingId.PRIVATE_EVALS].mode is GlobalBindingMode.GLOBAL
    assert not inventory[GlobalBindingId.PRIVATE_EVALS].blocks_backend_readiness
    assert inventory[GlobalBindingId.CODING_SESSIONS].mode is GlobalBindingMode.GLOBAL
    assert not inventory[GlobalBindingId.CODING_SESSIONS].blocks_backend_readiness
    assert inventory[GlobalBindingId.SKILLS_RUNTIME_PHASE_2].mode is GlobalBindingMode.GLOBAL
    assert not inventory[GlobalBindingId.SKILLS_RUNTIME_PHASE_2].blocks_backend_readiness
    assert inventory[GlobalBindingId.SANDBOX_EXECUTION_BOUNDARY].mode is GlobalBindingMode.GLOBAL
    assert not inventory[GlobalBindingId.SANDBOX_EXECUTION_BOUNDARY].blocks_backend_readiness
    assert inventory[GlobalBindingId.REPOSITORY_RUNTIME].mode is GlobalBindingMode.GLOBAL
    assert not inventory[GlobalBindingId.REPOSITORY_RUNTIME].blocks_backend_readiness

    for binding_id in (
        GlobalBindingId.CONCRETE_SANDBOX_DRIVER,
        GlobalBindingId.SEARCH_RUNTIME,
    ):
        declaration = inventory[binding_id]
        assert declaration.requirement is GlobalBindingRequirement.INTENTIONALLY_OPTIONAL
        assert declaration.availability is GlobalBindingAvailability.CAPABILITY_LIMITED
        assert not declaration.blocks_backend_readiness

    voice = inventory[GlobalBindingId.VOICE_AUDIO_PERCEPTION]
    assert voice.mode is GlobalBindingMode.LEGACY_GLOBAL_ONLY
    assert voice.activation_state is GlobalBindingActivationState.ACTIVE
    assert not voice.blocks_backend_readiness

    assert all(
        declaration.blocks_backend_readiness
        for declaration in inventory.values()
        if declaration.requirement is GlobalBindingRequirement.REQUIRED
            and declaration.binding_id
            not in {
                GlobalBindingId.PRIVATE_EVALS,
                GlobalBindingId.CODING_SESSIONS,
                GlobalBindingId.SKILLS_RUNTIME_PHASE_2,
                GlobalBindingId.SANDBOX_EXECUTION_BOUNDARY,
                GlobalBindingId.REPOSITORY_RUNTIME,
                GlobalBindingId.DEPLOYMENT_RUNTIME,
            }
    )


def test_inventory_does_not_import_or_activate_local_composition_roots() -> None:
    path = SOURCE_ROOT / "bootstrap" / "bindings.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imported_modules <= {"__future__", "dataclasses", "enum"}

    source_overrides = {
        GlobalBindingId.VOICE_AUDIO_PERCEPTION: Path("voice_composition"),
    }
    for declaration in canonical_global_binding_inventory():
        if declaration.composition_reference is None:
            continue
        relative = source_overrides.get(
            declaration.binding_id,
            Path(*declaration.composition_reference.split(".")),
        )
        assert (SOURCE_ROOT / relative).is_dir() or (SOURCE_ROOT / relative).with_suffix(
            ".py"
        ).is_file()


def test_application_exposes_same_inventory_as_inert_metadata(tmp_path: Path) -> None:
    from synapse.core.config import Settings

    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="global_binding_test",
    )
    application = build_application(settings)
    try:
        assert application.metadata["global_binding_inventory"] == (
            canonical_global_binding_inventory()
        )
        assert application.startup_report is None
    finally:
        application.close()
