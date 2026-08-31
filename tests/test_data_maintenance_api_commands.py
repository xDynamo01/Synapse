from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def settings_for(data_dir: Path) -> Settings:
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )


def test_maintenance_api_is_admin_only_bounded_and_path_free(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "data")
    app = create_app(settings)
    headers = {"X-Actor-Id": "local_owner", "X-Actor-Type": "admin"}
    with TestClient(app) as client:
        assert client.get("/api/maintenance/status").status_code == 403
        contributors = client.get(
            "/api/maintenance/contributors", headers=headers
        )
        assert contributors.status_code == 200
        assert len(contributors.json()) == 4
        inspected = client.post(
            "/api/maintenance/inspect",
            headers=headers,
            json={"scope": {"kind": "all"}},
        )
        assert inspected.status_code == 200
        assert str(tmp_path.resolve()) not in json.dumps(inspected.json())
        traversal = client.post(
            "/api/maintenance/inspect",
            headers=headers,
            json={"scope": {"kind": "contributor", "value": "../outside"}},
        )
        assert traversal.status_code == 422
        unknown_category = client.post(
            "/api/maintenance/inspect",
            headers=headers,
            json={"scope": {"kind": "category", "value": "not_registered"}},
        )
        assert unknown_category.status_code == 422
        arbitrary = client.post(
            "/api/maintenance/plan",
            headers=headers,
            json={"path": "C:/outside", "scope": {"kind": "all"}},
        )
        assert arbitrary.status_code == 422
        assert client.post("/api/foundation/cleanup-temp").status_code == 404
        assert client.post("/api/retention/cleanup-all").status_code == 404
        assert (
            client.post("/api/retention/domains/notifications/cleanup").status_code
            == 404
        )


def test_read_only_foundation_compatibility_uses_maintenance_runtime(
    tmp_path: Path,
) -> None:
    app = create_app(settings_for(tmp_path / "data"))
    with TestClient(app) as client:
        data_dir = client.get("/api/foundation/validate-data-dir")
        config = client.get("/api/foundation/validate-config")
        assert data_dir.status_code == 200
        assert data_dir.json()["state"] == "ready"
        assert config.status_code == 200 and config.json()["valid"]


def test_maintenance_commands_share_runtime_and_old_destructive_aliases_are_absent(
    tmp_path: Path,
) -> None:
    runtime = create_runtime(settings_for(tmp_path / "data"))
    status = runtime.commands.execute(runtime.context(), "/maintenance-status")
    contributors = runtime.commands.execute(
        runtime.context(), "/maintenance-contributors"
    )
    inspected = runtime.commands.execute(
        runtime.context(), "/maintenance-inspect contributor=foundation"
    )
    assert status.status == contributors.status == inspected.status == "ok"
    assert contributors.data["contributors"] == [
        {
                "contributor_id": item.contributor_id,
                "capabilities": item.capabilities,
                "categories": item.categories,
                "required": item.required,
            "domain": item.domain,
        }
        for item in runtime.maintenance.list_contributors()
    ]
    for removed in ("/cleanup-temp", "/retention-cleanup", "/retention-cleanup-all"):
        assert runtime.commands.execute(runtime.context(), removed).status == "error"
