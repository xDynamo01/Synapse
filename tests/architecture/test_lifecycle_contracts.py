from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse.bootstrap import build_application
from synapse.bootstrap.lifecycle import (
    LifecycleManager,
    LifecycleResource,
    LifecycleStartupError,
)
from synapse.core.config import Settings
from synapse.daemon.runner import DaemonRunner
from synapse.main import create_app


def settings_for(data_dir: Path) -> Settings:
    return Settings(
        project_root=Path(__file__).parents[2],
        data_dir=data_dir,
        host="127.0.0.1",
        port=8717,
        default_actor_id="architecture_test",
    )


def test_start_and_close_order_idempotency_and_structured_reports() -> None:
    actions: list[str] = []
    lifecycle = LifecycleManager()
    for name in ("foundation", "provider", "stream"):
        lifecycle.register(
            LifecycleResource(
                name,
                start=lambda current=name: actions.append(f"start:{current}"),
                close=lambda current=name: actions.append(f"close:{current}"),
            )
        )

    first_start = lifecycle.start()
    assert lifecycle.start() is first_start
    assert actions == ["start:foundation", "start:provider", "start:stream"]
    first_close = lifecycle.close()
    assert lifecycle.close() is first_close
    assert actions[-3:] == ["close:stream", "close:provider", "close:foundation"]
    assert first_start.status == "ready"
    assert first_close.status == "completed"


def test_required_start_failure_rolls_back_and_preserves_error() -> None:
    actions: list[str] = []
    lifecycle = LifecycleManager()
    lifecycle.register(
        LifecycleResource(
            "started",
            start=lambda: actions.append("start"),
            close=lambda: actions.append("rollback"),
        )
    )

    def fail() -> None:
        raise RuntimeError("required dependency unavailable")

    lifecycle.register(LifecycleResource("required", start=fail))
    with pytest.raises(LifecycleStartupError) as raised:
        lifecycle.start()
    assert actions == ["start", "rollback"]
    assert raised.value.report.status == "failed"
    assert any(
        result.error == "required dependency unavailable" for result in raised.value.report.results
    )


def test_optional_start_failure_degrades_without_aborting() -> None:
    lifecycle = LifecycleManager()
    lifecycle.register(
        LifecycleResource(
            "optional-camera",
            start=lambda: (_ for _ in ()).throw(RuntimeError("not configured")),
            required=False,
        )
    )
    lifecycle.register(LifecycleResource("required-foundation", start=lambda: None))
    report = lifecycle.start()
    assert report.status == "degraded"
    assert [result.status for result in report.results] == ["failed", "ok"]


def test_close_failure_does_not_prevent_remaining_cleanup() -> None:
    actions: list[str] = []
    lifecycle = LifecycleManager()
    lifecycle.register(LifecycleResource("first", close=lambda: actions.append("close:first")))

    def fail_close() -> None:
        actions.append("close:failing")
        raise RuntimeError("cleanup failed")

    lifecycle.register(LifecycleResource("failing", close=fail_close))
    lifecycle.register(LifecycleResource("last", close=lambda: actions.append("close:last")))
    lifecycle.start()
    report = lifecycle.close()
    assert actions == ["close:last", "close:failing", "close:first"]
    assert report.status == "degraded"


def test_application_construction_does_not_start_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    starts: list[object] = []
    monkeypatch.setattr(DaemonRunner, "start_loop", lambda self, *args: starts.append(self))
    application = build_application(settings_for(tmp_path / "data"))
    assert starts == []
    assert application.startup_report is None
    assert application.metadata["auto_started_resources"] == (
        "agent-loop",
        "deployment-runtime",
        "private-evals-runtime",
            "coding-sessions-runtime",
            "skills-phase2-runtime",
            "sandbox-runtime",
            "repository-runtime",
    )
    resource = application.lifecycle.resources[0]
    assert resource.feature == "world-state-and-agent-loop"
    assert resource.reason
    assert resource.start is not None
    assert resource.close is not None
    assert resource.metadata["failure_behavior"]
    assert application.container.model_hub.model_router is application.container.models
    assert application.container.audio.providers is application.container.providers
    assert application.container.deployment.health().lifecycle == "constructed"
    assert not (tmp_path / "data" / "deployment-runtime.sqlite3").exists()
    assert application.container.private_evals.state == "constructed"
    assert not (tmp_path / "data" / "private-evals-runtime.sqlite3").exists()
    assert application.container.coding_sessions.state == "constructed"
    assert not (tmp_path / "data" / "coding-sessions-runtime.sqlite3").exists()
    assert application.container.skills_phase2.state == "constructed"
    assert not (tmp_path / "data" / "skills-phase2-runtime.sqlite3").exists()
    assert application.container.repository_runtime.state == "constructed"
    assert not (tmp_path / "data" / "repository-runtime.sqlite3").exists()
    application.close()


def test_fastapi_lifespan_builds_starts_and_closes_application(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path / "data"))
    assert getattr(app.state, "runtime", None) is None
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert app.state.startup_report.status == "ready"
        assert app.state.runtime.agent_loop.status().state == "idle"
        assert app.state.runtime.scheduler.lock.is_locked() is False
        assert app.state.runtime.deployment.health().lifecycle == "started"
        assert (tmp_path / "data" / "deployment-runtime.sqlite3").is_file()
        assert app.state.runtime.private_evals.state == "started"
        assert (tmp_path / "data" / "private-evals-runtime.sqlite3").is_file()
        assert app.state.runtime.coding_sessions.state == "started"
        assert (tmp_path / "data" / "coding-sessions-runtime.sqlite3").is_file()
        assert app.state.runtime.skills_phase2.state == "started"
        assert (tmp_path / "data" / "skills-phase2-runtime.sqlite3").is_file()
        assert app.state.runtime.repository_runtime.state == "started"
        assert (tmp_path / "data" / "repository-runtime.sqlite3").is_file()
        deployment_health = app.state.runtime.health.module_health("synapse.deployment")
        assert len(deployment_health) == 1
        assert deployment_health[0].ready is True
    assert app.state.shutdown_report.status == "completed"
    assert app.state.runtime.agent_loop.status().state == "stopped"
    assert app.state.runtime.scheduler.lock.is_locked() is False
    assert not app.state.runtime.agent_loop.lock_path.exists()


def test_importing_main_does_not_bootstrap_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "must-not-exist"
    environment = os.environ.copy()
    environment["SYNAPSE_DATA_DIR"] = str(data_dir)
    completed = subprocess.run(
        [sys.executable, "-c", "import synapse.main"],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert not data_dir.exists()


def test_openapi_surface_remains_at_frozen_baseline() -> None:
    schema = create_app().openapi()
    operations = [
        operation
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method.lower() in {"get", "put", "post", "delete", "patch", "options", "head"}
    ]
    operation_ids = [operation["operationId"] for operation in operations]
    # Intentional frontend V2 deltas: typed `/api/frontend/*` operations,
    # Slice 4 cancellation, Slice 5 transcription, Slice 6 voice turns and
    # Slice 13 governed attachment staging and Slice 15.7 voice-pack discovery,
    # without generic IPC, visual state or a second conversation engine.
    assert len(schema["paths"]) == 493
    assert len(operations) == 546
    assert len(schema["components"]["schemas"]) == 132
    assert len(operation_ids) == len(set(operation_ids))
