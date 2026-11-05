from .support import SOURCE_ROOT, imports_for


def test_memory_extension_does_not_depend_on_models_or_delivery():
    imports = {name for path in (SOURCE_ROOT / "memory").glob("*.py") for name in imports_for(path)}
    assert {name.split(".")[1] for name in imports if name.startswith("synapse.")} <= {"memory", "core", "storage"}


def test_prompt_budget_has_no_persistence_or_memory_implementation_dependency():
    imports = imports_for(SOURCE_ROOT / "models" / "budget.py")
    assert all(not name.startswith(("synapse.memory", "synapse.storage", "synapse.bootstrap")) for name in imports)


def test_consolidation_uses_protocol_without_store_import_cycle():
    imports = imports_for(SOURCE_ROOT / "memory" / "consolidation.py")
    assert "synapse.memory.store" not in imports
