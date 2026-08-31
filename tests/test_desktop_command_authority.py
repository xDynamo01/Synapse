from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from synapse.core.config import Settings
from synapse.main import create_app


def settings_for(data_dir: Path) -> Settings:
    return Settings(
        project_root=Path(__file__).parents[1], data_dir=data_dir,
        host="127.0.0.1", port=8717, default_actor_id="local_owner",
    )


def register_project(client: TestClient, project_id: str) -> None:
    response = client.post(
        "/api/projects",
        headers={"X-Actor-Type": "admin", "X-Actor-Id": "local_owner"},
        json={
            "project_id": project_id, "name": project_id, "description": "test",
            "root_reference": project_id, "owner": "local_owner", "default_policy_id": "default",
        },
    )
    assert response.status_code == 200


def session(client: TestClient, project_id: str, launch_token: str) -> dict[str, object]:
    response = client.post(
        "/api/desktop/sessions",
        headers={"Authorization": f"Bearer {launch_token}"},
        json={"project_id": project_id},
    )
    assert response.status_code == 200
    return response.json()


def envelope(session_data: dict[str, object], project_id: str, command_id: str | None = None) -> dict[str, object]:
    return {
        "command_id": command_id or str(uuid4()), "command_type": "task.create",
        "project_id": project_id, "session_id": session_data["session_id"],
        "issued_at": datetime.now(UTC).isoformat(),
        "payload": {"title": "RC command proof", "description": "real task work", "agent_id": "orchestrator"},
    }


def test_authenticated_authorized_project_scoped_command_is_idempotent_and_projected(tmp_path, monkeypatch) -> None:
    launch_token = "release-launch-token-with-sufficient-entropy"
    monkeypatch.setenv("SYNAPSE_LAUNCH_TOKEN", launch_token)
    app = create_app(settings_for(tmp_path / "data"))
    with TestClient(app) as client:
        register_project(client, "alpha")
        session_data = session(client, "alpha", launch_token)
        command = envelope(session_data, "alpha")
        headers = {"Authorization": f"Bearer {session_data['session_token']}"}

        first = client.post("/api/desktop/commands", headers=headers, json=command)
        assert first.status_code == 200
        assert first.json()["status"] == "completed"
        assert first.json()["task"]["metadata"]["project_id"] == "alpha"
        assert first.json()["task"]["metadata"]["assigned_agent"] == "orchestrator"
        retry = client.post("/api/desktop/commands", headers=headers, json=command)
        assert retry.status_code == 200
        assert retry.json()["replayed"] is True
        assert retry.json()["task"]["id"] == first.json()["task"]["id"]
        conflicting = {**command, "payload": {**command["payload"], "title": "conflict"}}
        assert client.post("/api/desktop/commands", headers=headers, json=conflicting).status_code == 409
        assert len(app.state.runtime.tasks.list_tasks()) == 1

        activity = client.get("/api/projects/alpha/activity")
        assert activity.status_code == 200
        assert activity.json()["revision"] >= 1
        assert first.json()["correlation_id"] == command["command_id"]


def test_security_rejections_are_effect_free(tmp_path, monkeypatch) -> None:
    launch_token = "release-launch-token-with-sufficient-entropy"
    monkeypatch.setenv("SYNAPSE_LAUNCH_TOKEN", launch_token)
    app = create_app(settings_for(tmp_path / "data"))
    with TestClient(app) as client:
        register_project(client, "alpha")
        register_project(client, "beta")
        assert client.post("/api/desktop/sessions", headers={"Authorization": "Bearer wrong"}, json={"project_id": "alpha"}).status_code == 401
        session_data = session(client, "alpha", launch_token)
        headers = {"Authorization": f"Bearer {session_data['session_token']}"}

        authority = app.state.desktop_command_authority
        current = authority._sessions[str(session_data["session_token"])]
        authority._sessions[current.token] = replace(current, capabilities=())
        assert client.post("/api/desktop/commands", headers=headers, json=envelope(session_data, "alpha")).status_code == 403
        authority._sessions[current.token] = current

        wrong_project = envelope(session_data, "beta")
        assert client.post("/api/desktop/commands", headers=headers, json=wrong_project).status_code == 403
        stale = envelope(session_data, "alpha")
        stale["issued_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert client.post("/api/desktop/commands", headers=headers, json=stale).status_code == 401
        malformed = envelope(session_data, "alpha")
        malformed["payload"] = {"title": "x", "agent_id": "../escape"}
        assert client.post("/api/desktop/commands", headers=headers, json=malformed).status_code == 422
        unknown = envelope(session_data, "alpha")
        unknown["command_type"] = "shell.execute"
        assert client.post("/api/desktop/commands", headers=headers, json=unknown).status_code == 422
        assert client.post("/api/desktop/commands", json=envelope(session_data, "alpha")).status_code == 401
        assert app.state.runtime.tasks.list_tasks() == []

    restarted = create_app(settings_for(tmp_path / "data"))
    with TestClient(restarted) as client:
        assert client.post("/api/desktop/commands", headers=headers, json=envelope(session_data, "alpha")).status_code == 401
