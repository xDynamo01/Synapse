from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acceptance.intelligence_boundary_support import boundary_runtime
from synapse.api.routes import router
from synapse.commands.context import CommandContext, CommandInvocation
from synapse.commands.handlers.intelligence_boundary import (
    IntelligenceBoundaryCommandHandler,
)
from synapse.commands.services import CommandServices
from synapse.core.permissions import PermissionContext


def test_intelligence_api_and_commands_have_no_bypass(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(intelligence_boundary=runtime)
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    asset = {
        "asset_id": "asset-a",
        "owner": "project-owned",
        "source_domain": "test",
        "source_reference": "test:asset-a",
        "content_type": "text/plain",
        "classification": "internal",
        "categories": ["memory.project"],
    }
    assert client.post("/api/information-assets", json=asset).status_code == 403
    created = client.post(
        "/api/information-assets", json=asset, headers={"x-actor-type": "admin"}
    )
    assert created.status_code == 200
    assert client.get("/api/information-assets/asset-a").status_code == 200
    assert client.get("/api/intelligence-boundary/status").json()["assets"] == 1

    handler = IntelligenceBoundaryCommandHandler(
        CommandServices(intelligence_boundary=runtime)
    )
    context = CommandContext(PermissionContext(actor_id="admin", actor_type="admin"))
    invocation = CommandInvocation(
        "/intelligence-boundary-status",
        "/intelligence-boundary-status",
        "/intelligence-boundary-status",
        None,
        "",
        (),
        {},
        None,
        "admin",
        {},
    )
    result = handler.execute(context, invocation)
    assert result.status == "ok"
    assert result.data["assets"] == 1
