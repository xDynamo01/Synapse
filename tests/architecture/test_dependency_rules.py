from pathlib import Path

from .support import (
    COMPATIBILITY_ADAPTERS,
    SOURCE_ROOT,
    format_violations,
    import_edges,
    imports_for,
)

NEUTRAL_CORE_TARGETS = {"core", "observability"}
LEGACY_DOMAIN_COMMAND_IMPORTS: set[tuple[Path, str]] = set()
LEGACY_STORE_IMPORTS: set[tuple[Path, str]] = set()
CONCRETE_PROVIDER_PREFIXES = (
    "synapse.desktop_automation.providers.",
    "synapse.model_providers.lmstudio",
    "synapse.notifications.local_provider",
)
LEGACY_CONCRETE_PROVIDER_IMPORTS = {
    (Path("chat/runtime.py"), "synapse.model_providers.lmstudio"),
    (Path("desktop_automation/runtime.py"), "synapse.desktop_automation.providers.factory"),
    (Path("desktop_automation/runtime.py"), "synapse.desktop_automation.providers.fallback"),
    (Path("desktop_automation/runtime.py"), "synapse.desktop_automation.providers.input"),
    (Path("desktop_automation/screen.py"), "synapse.desktop_automation.providers.common"),
    (Path("health/runtime.py"), "synapse.model_providers.lmstudio"),
    (Path("model_hub/runtime.py"), "synapse.model_providers.lmstudio"),
    (Path("model_providers/__init__.py"), "synapse.model_providers.lmstudio"),
    (Path("notifications/runtime.py"), "synapse.notifications.local_provider"),
}


def test_core_is_neutral_except_documented_compatibility_adapters() -> None:
    violations = [
        edge
        for edge in import_edges()
        if edge.source_context == "core"
        and edge.source_file not in COMPATIBILITY_ADAPTERS
        and edge.target_context not in NEUTRAL_CORE_TARGETS
    ]
    assert not violations, format_violations("core must remain domain-neutral", violations)


def test_domains_do_not_depend_on_delivery_or_bootstrap_layers() -> None:
    violations = []
    for edge in import_edges():
        if edge.source_context in {"api", "commands", "bootstrap", "core"}:
            continue
        if edge.source_file == Path("main.py"):
            continue
        if edge.target_context not in {"api", "commands", "bootstrap"}:
            continue
        if (edge.source_file, edge.target_module) in LEGACY_DOMAIN_COMMAND_IMPORTS:
            continue
        violations.append(edge)
    assert not violations, format_violations(
        "domains cannot import api, commands, or bootstrap", violations
    )


def test_api_and_commands_do_not_add_direct_store_dependencies() -> None:
    violations = []
    for edge in import_edges():
        if edge.source_context not in {"api", "commands"}:
            continue
        if not edge.target_module.endswith((".store", ".storage", ".queue")):
            continue
        if (edge.source_file, edge.target_module) not in LEGACY_STORE_IMPORTS:
            violations.append(edge)
    assert not violations, format_violations(
        "delivery/application layers depend on facades, not stores", violations
    )


def test_consumers_do_not_add_concrete_provider_dependencies() -> None:
    violations = []
    for edge in import_edges():
        if edge.source_context == "bootstrap" or "registry" in edge.source_file.stem:
            continue
        if not edge.target_module.startswith(CONCRETE_PROVIDER_PREFIXES):
            continue
        if edge.source_context == edge.target_context:
            continue
        if (edge.source_file, edge.target_module) not in LEGACY_CONCRETE_PROVIDER_IMPORTS:
            violations.append(edge)
    assert not violations, format_violations(
        "concrete providers are wired only by bootstrap or registries", violations
    )


def test_feature_builders_do_not_import_delivery_layers() -> None:
    violations = []
    for path in (SOURCE_ROOT / "bootstrap" / "features").rglob("*.py"):
        for module in imports_for(path):
            if module.startswith(("synapse.api", "synapse.commands")):
                violations.append(f"origin={path} destination={module}")
    assert not violations, "Feature builders imported delivery layers:\n" + "\n".join(
        violations
    )
