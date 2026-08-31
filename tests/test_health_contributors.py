from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep

import pytest

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth
from synapse.health.registry import HealthContributorRegistry
from synapse.health.runtime import HealthRuntime
from synapse.observability.correlation import correlation_scope, new_correlation


class Events:
    def __init__(self) -> None:
        self.items = []

    def emit(self, *args) -> None:
        self.items.append(args)

    def metrics(self) -> dict:
        return {}


@dataclass
class Contributor:
    contributor_id: str
    result: object
    delay: float = 0
    raised: Exception | None = None
    contexts: list[HealthCheckContext] | None = None

    def collect_health(self, context: HealthCheckContext):
        if self.contexts is not None:
            self.contexts.append(context)
        if self.delay:
            sleep(self.delay)
        if self.raised:
            raise self.raised
        return self.result


def healthy(component_id: str, order: int = 0) -> HealthContribution:
    return HealthContribution(
        components=(
            (
                order,
                ComponentHealth(
                    component_id,
                    f"synapse.{component_id}",
                    "ready",
                    True,
                    True,
                    True,
                    False,
                ),
            ),
        )
    )


def runtime(*contributors: Contributor, timeout: float = 0.1) -> HealthRuntime:
    registry = HealthContributorRegistry()
    registry.register_all(contributors)
    return HealthRuntime(registry, Events(), timeout_seconds=timeout)


def test_registry_rejects_duplicate_and_mismatched_ids() -> None:
    registry = HealthContributorRegistry()
    registry.register(Contributor("one", healthy("one")))
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(Contributor("one", healthy("other")))
    with pytest.raises(ValueError, match="mismatch"):
        registry.register(Contributor("actual", healthy("actual")), contributor_id="other")


def test_order_is_deterministic_and_collection_is_repeatable() -> None:
    health = runtime(
        Contributor("late", healthy("late", 20)),
        Contributor("early", healthy("early", 10)),
        Contributor("empty", HealthContribution()),
    )
    assert [item.component_id for item in health.component_health()] == ["early", "late"]
    assert [item.component_id for item in health.component_health()] == ["early", "late"]


def test_exception_is_isolated_and_redacted() -> None:
    health = runtime(
        Contributor("broken", None, raised=RuntimeError("secret stack detail")),
        Contributor("healthy", healthy("healthy")),
    )
    components = health.component_health()
    assert [item.component_id for item in components] == [
        "healthy",
        "health_contributor.broken",
    ]
    failure = components[-1]
    assert failure.state == "unavailable"
    assert "secret" not in (failure.last_error or "")


def test_timeout_does_not_block_other_contributors() -> None:
    health = runtime(
        Contributor("slow", healthy("slow"), delay=0.2),
        Contributor("fast", healthy("fast")),
        timeout=0.01,
    )
    started = monotonic()
    components = health.component_health()
    assert monotonic() - started < 0.1
    assert {item.component_id for item in components} == {
        "fast",
        "health_contributor.slow",
    }
    failure = next(item for item in components if item.component_id.endswith("slow"))
    assert failure.metadata["timed_out"] is True


def test_invalid_result_and_duplicate_component_are_isolated() -> None:
    duplicate = HealthContribution(
        components=(healthy("same").components[0], healthy("same", 1).components[0])
    )
    invalid = runtime(Contributor("invalid", {"not": "a contribution"})).component_health()
    duplicated = runtime(Contributor("duplicate", duplicate)).component_health()
    assert invalid[0].component_id == "health_contributor.invalid"
    assert [item.component_id for item in duplicated] == [
        "same",
        "health_contributor.duplicate",
    ]


def test_optional_missing_contributor_is_not_degraded() -> None:
    registry = HealthContributorRegistry()
    registry.register(None, contributor_id="optional_camera", optional=True)
    component = HealthRuntime(registry, Events()).component_health()[0]
    assert component.state == "not_configured"
    assert component.degraded is False
    assert component.recommendations == []


def test_correlation_id_is_forwarded_in_context() -> None:
    contexts: list[HealthCheckContext] = []
    health = runtime(Contributor("capture", HealthContribution(), contexts=contexts))
    correlation = new_correlation("health-test", correlation_id="health-correlation")
    with correlation_scope(correlation):
        health.component_health()
    assert contexts[0].correlation_id == "health-correlation"
