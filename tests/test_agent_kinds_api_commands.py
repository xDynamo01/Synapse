from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acceptance.agent_kinds_support import provision, runtime_at
from synapse.api.routes import router
from synapse.ephemeral_agents.models import EphemeralAgentSpec


def client_for(runtime) -> TestClient:
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_primary_api_and_commands_use_canonical_runtime(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central")
    client = client_for(runtime)

    response = client.put("/api/primary-agent", json={"agent_id": "central"})
    assert response.status_code == 200
    assert response.json()["agent_id"] == "central"
    bootstrap = client.get("/api/primary-interaction/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["primary_agent"]["kind"] == "primary"
    assert runtime.commands.execute(runtime.context(), "/primary-agent-show").status == "ok"
    assert (
        runtime.commands.execute(runtime.context(), "/primary-interaction-bootstrap").data[
            "voice_status"
        ]
        == "not_started"
    )


def test_canonical_agent_creation_api_has_no_legacy_defaults(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    invalid = client.post(
        "/api/agents", json={"display_name": "Missing explicit ID", "role": "worker"}
    )
    assert invalid.status_code == 422
    created = client.post(
        "/api/agents",
        json={
            "agent_id": "explicit",
            "display_name": "Explicit",
            "role": "worker",
            "agent_kind": "persistent",
        },
    )
    assert created.status_code == 200
    assert created.json()["agent"]["kind"] == "persistent"


def test_ephemeral_api_and_commands_are_diagnostic_not_spawn_surfaces(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central")
    instance = runtime.ephemeral_agents.create_instance(
        EphemeralAgentSpec(
            mission_id="mission-api",
            parent_agent_id="central",
            role="diagnostic",
            objective="Expose bounded status",
            autonomy_ceiling="manual",
            risk_ceiling="low",
            created_by="mission",
            correlation_id="api-trace",
        ),
        authority="mission",
    )
    client = client_for(runtime)
    response = client.get(f"/api/ephemeral-agents/{instance.ephemeral_agent_id}")
    assert response.status_code == 200
    assert response.json()["state"] == "ready"
    listed = runtime.commands.execute(
        runtime.context(), "/ephemeral-agent-list mission-api"
    )
    assert listed.status == "ok"
    assert listed.data["agents"] == [asdict(instance)]
    assert runtime.commands.registry.resolve("/ephemeral-agent-spawn") is None
