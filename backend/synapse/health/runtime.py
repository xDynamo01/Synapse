from __future__ import annotations

from dataclasses import MISSING, asdict, fields
from datetime import UTC, datetime
from queue import Empty, Queue
from threading import Thread
from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.models import ComponentHealth, HealthCheckItem, HomelabHealthSummary
from synapse.health.registry import HealthContributorRegistry, RegisteredHealthContributor
from synapse.observability.correlation import current_correlation


class HealthRuntime:
    """Neutral collector and aggregator over explicitly registered contributors."""

    def __init__(
        self,
        registry: HealthContributorRegistry,
        event_bus: Any,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "event_bus", event_bus)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)

    def __getattr__(self, name: str) -> Any:
        return self.registry.dependency(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"registry", "event_bus", "timeout_seconds"}:
            object.__setattr__(self, name, value)
            return
        self.registry.replace_dependency(name, value)

    def component_health(self) -> list[ComponentHealth]:
        contributions = self._collect()
        return self._components(contributions)

    def module_health(self, module: str) -> list[ComponentHealth]:
        return [item for item in self.component_health() if item.module == module]

    def dependency_graph(self) -> dict[str, list[str]]:
        return {item.component_id: item.dependencies for item in self.component_health()}

    def diagnostics(self) -> dict[str, Any]:
        components = self.component_health()
        return {
            "components": [asdict(item) for item in components],
            "dependency_graph": {item.component_id: item.dependencies for item in components},
            "recommendations": [
                recommendation for item in components for recommendation in item.recommendations
            ],
        }

    def operational_metrics(self) -> dict[str, Any]:
        contributions = self._collect()
        gauges: dict[str, int] = {}
        for _, contribution in contributions:
            gauges.update(contribution.metrics)
        return {"gauges": gauges, "event_metrics": self.event_bus.metrics()}

    def summary(self) -> HomelabHealthSummary:
        contributions = self._collect()
        payload = self._summary_defaults()
        ordered_checks: list[tuple[int, HealthCheckItem]] = []
        for _, contribution in contributions:
            payload.update(contribution.summary)
            ordered_checks.extend(contribution.checks)
        checks = [item for _, item in sorted(ordered_checks, key=lambda pair: pair[0])]
        if not checks:
            checks = [HealthCheckItem("system.ok", "System", "ok", "No health concerns detected.")]
        payload["components"] = self._components(contributions)
        payload["checks"] = checks
        payload["status"] = self._status(checks)
        summary = HomelabHealthSummary(**payload)
        self.event_bus.emit("health.checked", "health", asdict(summary))
        return summary

    def _collect(self) -> list[tuple[RegisteredHealthContributor, HealthContribution]]:
        correlation = current_correlation()
        context = HealthCheckContext(
            timestamp=datetime.now(UTC).isoformat(),
            correlation_id=correlation.correlation_id if correlation else None,
            mode="standard",
            timeout_budget_seconds=self.timeout_seconds,
            metadata={},
        )
        return [
            (registration, self._collect_one(registration, context))
            for registration in self.registry.list_contributors()
        ]

    def _collect_one(
        self,
        registration: RegisteredHealthContributor,
        context: HealthCheckContext,
    ) -> HealthContribution:
        if registration.contributor is None:
            return self._failure_contribution(
                registration,
                "not_configured" if registration.optional else "unavailable",
                "Contributor is not registered.",
                timed_out=False,
            )
        contributor = registration.contributor
        queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def collect() -> None:
            try:
                queue.put((True, contributor.collect_health(context)))
            except Exception as exc:
                queue.put((False, exc))

        Thread(target=collect, daemon=True).start()
        try:
            succeeded, value = queue.get(timeout=context.timeout_budget_seconds)
        except Empty:
            return self._failure_contribution(
                registration,
                "unavailable",
                "Health contributor timed out.",
                timed_out=True,
            )
        if not succeeded:
            return self._failure_contribution(
                registration,
                "unavailable",
                "Health contributor failed.",
                timed_out=False,
            )
        if not isinstance(value, HealthContribution):
            return self._failure_contribution(
                registration,
                "unavailable",
                "Health contributor returned an invalid result.",
                timed_out=False,
            )
        return value

    def _components(
        self,
        contributions: list[tuple[RegisteredHealthContributor, HealthContribution]],
    ) -> list[ComponentHealth]:
        ordered: list[tuple[int, ComponentHealth]] = []
        seen: set[str] = set()
        for registration, contribution in contributions:
            for order, item in contribution.components:
                if not isinstance(item, ComponentHealth) or item.component_id in seen:
                    failure = self._failure_contribution(
                        registration,
                        "unavailable",
                        "Contributor returned an invalid or duplicate component ID.",
                        timed_out=False,
                    )
                    ordered.extend(failure.components)
                    continue
                seen.add(item.component_id)
                ordered.append((order, item))
        return [item for _, item in sorted(ordered, key=lambda pair: pair[0])]

    @staticmethod
    def _summary_defaults() -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for item in fields(HomelabHealthSummary):
            if item.default is not MISSING:
                payload[item.name] = item.default
            elif item.default_factory is not MISSING:
                payload[item.name] = item.default_factory()
            elif "dict" in str(item.type):
                payload[item.name] = {}
            elif "list" in str(item.type):
                payload[item.name] = []
            elif "int" in str(item.type):
                payload[item.name] = 0
            else:
                payload[item.name] = None
        return payload

    @staticmethod
    def _failure_contribution(
        registration: RegisteredHealthContributor,
        state: str,
        message: str,
        *,
        timed_out: bool,
    ) -> HealthContribution:
        optional = registration.optional
        component_id = f"health_contributor.{registration.contributor_id}"
        component = ComponentHealth(
            component_id=component_id,
            module="synapse.health",
            state=state,
            configured=registration.contributor is not None,
            available=False,
            ready=optional and state == "not_configured",
            degraded=not optional,
            last_error=message,
            recommendations=[]
            if optional
            else [f"Restore {registration.contributor_id} health contributor."],
            metadata={"optional": optional, "timed_out": timed_out},
        )
        severity = "info" if optional else "warning"
        check = HealthCheckItem(
            id=f"health_contributor.{registration.contributor_id}.failed",
            label=f"Health Contributor {registration.contributor_id}".title(),
            severity=severity,
            summary=message,
            metadata={"optional": optional, "timed_out": timed_out},
        )
        return HealthContribution(
            components=((10_000, component),),
            checks=((10_000, check),),
        )

    @staticmethod
    def _status(checks: list[HealthCheckItem]) -> str:
        severities = {check.severity for check in checks}
        if "critical" in severities:
            return "critical"
        if "warning" in severities:
            return "warning"
        if "info" in severities:
            return "info"
        return "ok"
