from __future__ import annotations

import ast
import tempfile
from pathlib import Path

from fastapi import FastAPI

from synapse.api.routes import router
from synapse.core.app import create_runtime
from synapse.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOVED_API_PATHS = {
    "/api/ui-contracts",
    "/api/ui-contracts/mission-control",
    "/api/ui-contracts/agents",
    "/api/ui-contracts/health",
    "/api/ui-contracts/readiness",
    "/api/ui-contracts/notifications",
    "/api/ui-contracts/conversations/{conversation_id}",
    "/api/ui-contracts/missions/{mission_id}",
    "/api/app-shell",
    "/api/app-shell/modules",
    "/api/app-shell/panels",
    "/api/app-shell/navigation",
}
REMOVED_COMMANDS = {
    "/ui-contracts",
    "/ui-contract",
    "/app-shell",
    "/app-shell-modules",
    "/app-shell-panels",
    "/app-shell-navigation",
}


def test_visual_contract_routes_are_absent() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    assert REMOVED_API_PATHS.isdisjoint(app.openapi()["paths"])


def test_visual_contract_commands_and_runtimes_are_absent() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = create_runtime(
            Settings(
                project_root=PROJECT_ROOT,
                data_dir=Path(directory) / "data",
                host="127.0.0.1",
                port=8717,
                default_actor_id="local_owner",
            )
        )
        help_result = runtime.commands.execute(runtime.context(), "/help")

    assert not hasattr(runtime, "ui_contracts")
    assert not hasattr(runtime, "app_shell")
    assert REMOVED_COMMANDS.isdisjoint(help_result.data["commands"])


def test_neutral_contracts_do_not_import_runtimes() -> None:
    contracts_root = PROJECT_ROOT / "backend" / "synapse" / "contracts"
    for path in contracts_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        assert not any(module.endswith(".runtime") for module in imports), path


def test_abandoned_frontend_roots_are_absent() -> None:
    assert not (PROJECT_ROOT / "frontend").exists()
    assert not (PROJECT_ROOT / "desktop").exists()
