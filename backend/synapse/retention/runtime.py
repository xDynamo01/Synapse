from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from synapse.core.events import EventBus
from synapse.core.serialization import load_structured_file
from synapse.retention.models import (
    RetentionCleanupResult,
    RetentionDomain,
    RetentionPolicySummary,
    RetentionRegistryStatus,
)
from synapse.retention.registry import RetentionRegistry


class RetentionRuntime:
    def __init__(self, registry: RetentionRegistry, event_bus: EventBus) -> None:
        self.registry = registry
        self.event_bus = event_bus

    def list_domains(self) -> list[RetentionDomain]:
        return [registered.domain for registered in self.registry.list_domains()]

    def get_domain(self, domain_id: str) -> RetentionDomain:
        return self.registry.get(domain_id).domain

    def retention_status(self) -> RetentionRegistryStatus:
        summaries = [
            self._summary(registered.domain.domain_id)
            for registered in self.registry.list_domains()
        ]
        return RetentionRegistryStatus(
            domains=summaries,
            total_domains=len(summaries),
            enabled_domains=len([item for item in summaries if item.enabled]),
        )

    def cleanup_domain(self, domain_id: str, dry_run: bool = True) -> RetentionCleanupResult:
        registered = self.registry.get(domain_id)
        dry_run = True if dry_run and registered.domain.supports_dry_run else False
        self.event_bus.emit(
            "retention.cleanup.started",
            "retention",
            {"domain_id": domain_id, "dry_run": dry_run},
        )
        try:
            raw_result = registered.cleanup(dry_run)
            result = self._normalize_result(domain_id, dry_run, raw_result)
            self.event_bus.emit(
                "retention.cleanup.completed",
                "retention",
                asdict(result),
            )
            return result
        except Exception as exc:
            result = RetentionCleanupResult(
                domain_id=domain_id,
                dry_run=dry_run,
                success=False,
                errors=[str(exc) or type(exc).__name__],
            )
            self.event_bus.emit(
                "retention.cleanup.failed",
                "retention",
                {**asdict(result), "error_type": type(exc).__name__},
            )
            raise

    def cleanup_all(self, dry_run: bool = True) -> list[RetentionCleanupResult]:
        return [
            self.cleanup_domain(registered.domain.domain_id, dry_run=dry_run)
            for registered in self.registry.list_domains()
        ]

    def _summary(self, domain_id: str) -> RetentionPolicySummary:
        registered = self.registry.get(domain_id)
        status = registered.status()
        policy = self._policy(registered.policy_source)
        enabled = bool(
            status.get("enabled", policy.get("enabled", True))
            if isinstance(status, dict)
            else policy.get("enabled", True)
        )
        return RetentionPolicySummary(
            domain_id=registered.domain.domain_id,
            enabled=enabled,
            policy_path=registered.domain.policy_path,
            default_dry_run=registered.domain.default_dry_run,
            policy=policy,
            status=status if isinstance(status, dict) else {"status": status},
        )

    @staticmethod
    def _normalize_result(
        domain_id: str,
        dry_run: bool,
        raw_result: Any,
    ) -> RetentionCleanupResult:
        raw = asdict(raw_result) if hasattr(raw_result, "__dataclass_fields__") else raw_result
        raw = raw if isinstance(raw, dict) else {"result": raw}
        return RetentionCleanupResult(
            domain_id=domain_id,
            dry_run=bool(raw.get("dry_run", dry_run)),
            success=not raw.get("errors"),
            scanned=int(raw.get("scanned", raw.get("total_requests", 0) or 0)),
            deleted=int(raw.get("deleted", 0) or 0),
            preserved=int(raw.get("preserved", raw.get("remaining", 0) or 0)),
            candidates=[str(item) for item in raw.get("candidates", [])],
            errors=[str(item) for item in raw.get("errors", [])],
            raw_result=raw,
        )

    @staticmethod
    def _policy(policy_path: str) -> dict[str, Any]:
        raw = load_structured_file(Path(policy_path))
        if not isinstance(raw, dict):
            return {}
        if len(raw) == 1:
            only_value = next(iter(raw.values()))
            if isinstance(only_value, dict):
                return only_value
        return raw
