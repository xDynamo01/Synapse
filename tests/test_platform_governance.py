from __future__ import annotations

import tempfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import correlation_scope, new_correlation
from synapse.observability.redaction import redaction_self_test
from synapse.policies.models import PolicyRule

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runtime():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    value = create_runtime(settings)
    try:
        yield value
    finally:
        directory.cleanup()


def rule(effect: str, *, scope: str = "agent", priority: int = 100, **kwargs) -> PolicyRule:
    return PolicyRule(
        scope=scope,
        subject=kwargs.get("subject", "agent:artemis"),
        action=kwargs.get("action", "tool.execute"),
        resource=kwargs.get("resource", "tool:write_file"),
        effect=effect,
        source="test",
        priority=priority,
        conditions=kwargs.get("conditions", {}),
        expires_at=kwargs.get("expires_at"),
    )


def test_policy_deny_precedence_is_deterministic(runtime) -> None:
    allow = runtime.policies.create_rule(rule("allow", priority=1))
    deny = runtime.policies.create_rule(rule("deny", priority=999))
    first = runtime.policies.evaluate_policy("agent:artemis", "tool.execute", "tool:write_file")
    second = runtime.policies.evaluate_policy("agent:artemis", "tool.execute", "tool:write_file")
    assert first.decision == "deny"
    assert first.winning_rule["id"] == deny.id
    assert [item["id"] for item in first.matched_rules] == [
        item["id"] for item in second.matched_rules
    ]
    assert allow.id != deny.id
    command = runtime.commands.execute(
        runtime.context(),
        "/policy-evaluate agent:artemis tool.execute tool:write_file",
    )
    assert command.data["effective_policy"]["decision"] == "deny"

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse.api.routes import router

    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    assert len(client.get("/api/policies").json()) == 2
    response = client.post(
        "/api/policies/evaluate",
        json={
            "subject": "agent:artemis",
            "action": "tool.execute",
            "resource": "tool:write_file",
            "context": {},
        },
    )
    assert response.json()["decision"] == "deny"


def test_policy_expiry_constraints_approval_revision_and_history(runtime) -> None:
    runtime.policies.create_rule(rule(
        "deny", expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    ))
    constrained = runtime.policies.create_rule(rule(
        "constrain", conditions={"constraints": {"autonomy_ceiling": "act_local"}}
    ))
    approval = runtime.policies.create_rule(rule("require_approval", priority=5))
    result = runtime.policies.evaluate_policy("agent:artemis", "tool.execute", "tool:write_file")
    assert result.decision == "require_approval"
    assert result.approval_required
    assert result.constraints["autonomy_ceiling"] == "act_local"
    updated = runtime.policies.update_rule(constrained.id, {"priority": 3}, constrained.revision)
    assert updated.revision == 2
    with pytest.raises(ValidationError, match="revision"):
        runtime.policies.update_rule(constrained.id, {"priority": 4}, constrained.revision)
    assert len(runtime.policies.rule_history(constrained.id)) == 2
    assert approval.id


def test_policy_autonomy_ceiling_cannot_be_elevated(runtime) -> None:
    runtime.policies.create_rule(rule("allow", priority=1))
    runtime.policies.create_rule(
        rule(
            "constrain",
            scope="system",
            conditions={"constraints": {"autonomy_ceiling": "act_local"}},
        )
    )
    result = runtime.policies.evaluate_policy(
        "agent:artemis",
        "tool.execute",
        "tool:write_file",
        {"autonomy_level": "act_external"},
    )
    assert result.decision == "deny"
    assert "autonomy_ceiling_exceeded" in result.reasons


def test_observability_redacts_secrets_preserves_trace_and_reports_real_metrics(runtime) -> None:
    secret = "sk-super-secret-value"
    correlation = new_correlation(source="test")
    with correlation_scope(correlation):
        runtime.events.emit("model.generation.completed", "artemis", {
            "api_key": secret, "authorization": f"Bearer {secret}", "duration_ms": 12
        })
    event = runtime.events.trace(correlation.correlation_id)[0]
    assert secret not in repr(asdict(event))
    assert event.trace_id == correlation.correlation_id
    assert runtime.events.metrics()["counters"]["events_total"] >= 1
    assert redaction_self_test(secret)["safe"]
    command = runtime.commands.execute(runtime.context(), "/observability-metrics")
    assert command.data["metrics"]["event_metrics"]["counters"]["events_total"] >= 1


def test_observability_cleanup_is_dry_run_and_idempotent(runtime) -> None:
    runtime.events.emit("test.event", "test", {})
    dry_run = runtime.events.cleanup(retention_days=-1, dry_run=True)
    cleanup = runtime.events.cleanup(retention_days=-1)
    repeated = runtime.events.cleanup(retention_days=-1)
    assert dry_run["removed"] >= 1
    assert cleanup["removed"] == dry_run["removed"]
    assert repeated["removed"] == 0


def test_health_is_structured_and_optional_provider_is_not_configured(runtime) -> None:
    components = runtime.health.component_health()
    assert all(item.state in {
        "not_configured", "ready", "degraded", "unavailable", "misconfigured", "starting", "stopping"
    } for item in components)
    optional = next(item for item in components if item.component_id == "external_providers")
    assert optional.state == "not_configured"
    assert not optional.degraded
    assert runtime.health.dependency_graph()["voice"] == ["audio", "speech_adapters"]


def test_structured_writes_are_atomic_and_leave_no_temp_files(runtime) -> None:
    path = runtime.data_dir.resolve("config/atomic-test.yaml")
    dump_structured_file(path, {"revision": 1})
    dump_structured_file(path, {"revision": 2})
    assert load_structured_file(path) == {"revision": 2}
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_operational_metrics_are_derived_from_runtime_state(runtime) -> None:
    runtime.scheduler.enqueue(runtime.context(), "notification_cleanup", {})
    metrics = runtime.health.operational_metrics()
    assert metrics["gauges"]["scheduler_queue_depth"] == 1
    assert metrics["gauges"]["active_missions"] == 0
    assert metrics["event_metrics"]["counters"]["events_total"] >= 1
