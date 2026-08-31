from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acceptance.project_governance_support import runtime
from synapse.api.routes import router
from synapse.commands.context import CommandContext, CommandInvocation
from synapse.commands.handlers.project_governance import ProjectGovernanceCommandHandler
from synapse.commands.services import CommandServices
from synapse.core.permissions import PermissionContext


def test_project_api_and_commands_are_controlled_adapters(tmp_path) -> None:
    governance = runtime(tmp_path)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(project_governance=governance)
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    payload = {
        "project_id": "synapse",
        "name": "Synapse",
        "description": "Governed",
        "root_reference": "synapse",
        "owner": "owner",
        "default_policy_id": "default",
    }
    assert client.post("/api/projects", json=payload).status_code == 403
    created = client.post("/api/projects", json=payload, headers={"x-actor-type": "admin"})
    assert created.status_code == 200
    assert client.get("/api/projects/synapse/context").status_code == 200

    handler = ProjectGovernanceCommandHandler(CommandServices(project_governance=governance))
    context = CommandContext(PermissionContext(actor_id="owner", actor_type="admin"))
    invocation = CommandInvocation(
        "/project-list",
        "/project-list",
        "/project-list",
        None,
        "",
        (),
        {},
        None,
        "owner",
        {},
    )
    result = handler.execute(context, invocation)
    assert result.status == "ok"
    assert result.data["projects"][0]["project_id"] == "synapse"
