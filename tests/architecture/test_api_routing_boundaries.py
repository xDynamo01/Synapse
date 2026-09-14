from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from synapse.api.router_registry import DOMAIN_ROUTERS, router

from .support import SOURCE_ROOT, imports_for

ROUTERS_ROOT = SOURCE_ROOT / "api" / "routers"
HTTP_METHODS = {"GET", "PUT", "POST", "DELETE", "PATCH", "OPTIONS", "HEAD"}
CONCRETE_PROVIDER_PREFIXES = (
    "synapse.desktop_automation.providers.",
    "synapse.model_providers.lmstudio",
    "synapse.notifications.local_provider",
)
ALLOWED_TRANSPORT_HELPERS = {
    "_action",
    "_agent_profile",
    "_correlation_id",
    "_scope",
    "_selector",
    "_verification",
    "_criteria",
    "_review",
    "_egress_request",
    "_trust_profile",
}
RUNTIME_FREE_HANDLERS = {"security_redaction_test"}


def router_files() -> list[Path]:
    return sorted(path for path in ROUTERS_ROOT.glob("*.py") if path.name != "__init__.py")


def decorated_handlers(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list
    ]


def test_routes_module_is_a_handler_free_compatibility_adapter() -> None:
    path = SOURCE_ROOT / "api" / "routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assert not [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def test_domain_routers_do_not_depend_on_storage_providers_or_bootstrap() -> None:
    violations: list[str] = []
    for path in router_files():
        for module in imports_for(path):
            if module.endswith((".store", ".storage", ".queue")):
                violations.append(f"{path.name}: direct storage import {module}")
            if module.startswith(CONCRETE_PROVIDER_PREFIXES):
                violations.append(f"{path.name}: concrete provider import {module}")
            if module.startswith("synapse.bootstrap"):
                violations.append(f"{path.name}: bootstrap import {module}")
    assert not violations, "\n".join(violations)


def test_domain_routers_do_not_instantiate_runtimes_or_access_data_dir() -> None:
    violations: list[str] = []
    for path in router_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.endswith("Runtime"):
                    violations.append(f"{path.name}:{node.lineno} instantiates {node.func.id}")
            if isinstance(node, ast.Attribute) and node.attr == "data_dir":
                violations.append(f"{path.name}:{node.lineno} accesses DataDir")
    assert not violations, "\n".join(violations)


def test_router_helpers_are_transport_mappers_only() -> None:
    violations: list[str] = []
    for path in router_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        helpers = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.decorator_list
            and node.name.startswith("_")
        }
        for helper in helpers - ALLOWED_TRANSPORT_HELPERS:
            violations.append(f"{path.name}: non-transport helper {helper}")
    assert not violations, "\n".join(violations)


def test_every_handler_resolves_the_canonical_runtime_facade() -> None:
    violations: list[str] = []
    for path in router_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for handler in decorated_handlers(tree):
            calls = {
                node.func.id
                for node in ast.walk(handler)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            if handler.name not in RUNTIME_FREE_HANDLERS and "runtime_from" not in calls:
                violations.append(f"{path.name}:{handler.lineno} {handler.name}")
    assert not violations, "Handlers bypass canonical runtime:\n" + "\n".join(violations)


def test_registry_contains_every_domain_router_once() -> None:
    discovered = []
    for path in router_files():
        module = __import__(f"synapse.api.routers.{path.stem}", fromlist=["router"])
        discovered.append(module.router)
    # Primary-only MoM and Project Knowledge add canonical routers, separate from Swarm.
    assert len(DOMAIN_ROUTERS) == len(discovered) == 23
    assert {id(item) for item in DOMAIN_ROUTERS} == {id(item) for item in discovered}
    assert len(router.routes) == sum(len(item.routes) for item in DOMAIN_ROUTERS)


def test_openapi_operations_and_method_paths_are_unique() -> None:
    pairs = [
        (method, route.path)
        for route in router.routes
        for method in route.methods
        if method in HTTP_METHODS
    ]
    duplicates = [pair for pair, count in Counter(pairs).items() if count > 1]
    operation_ids = [route.unique_id for route in router.routes]
    duplicate_ids = [
        operation_id for operation_id, count in Counter(operation_ids).items() if count > 1
    ]
    assert not duplicates
    assert not duplicate_ids
