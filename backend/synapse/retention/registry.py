from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from synapse.core.exceptions import NotFound, ValidationError
from synapse.retention.models import RetentionDomain

CleanupCallable = Callable[[bool], Any]
StatusCallable = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredRetentionDomain:
    domain: RetentionDomain
    cleanup: CleanupCallable
    status: StatusCallable
    policy_source: str


class RetentionRegistry:
    def __init__(self) -> None:
        self._domains: dict[str, RegisteredRetentionDomain] = {}

    def register(
        self,
        *,
        domain_id: str,
        description: str,
        policy_path: str,
        supports_dry_run: bool,
        default_dry_run: bool,
        cleanup: CleanupCallable,
        status: StatusCallable,
    ) -> None:
        if domain_id in self._domains:
            raise ValidationError(f"Retention domain already registered: {domain_id}")
        self._domains[domain_id] = RegisteredRetentionDomain(
            domain=RetentionDomain(
                domain_id=domain_id,
                description=description,
                policy_path=_safe_policy_reference(policy_path),
                supports_dry_run=supports_dry_run,
                default_dry_run=default_dry_run,
            ),
            cleanup=cleanup,
            status=status,
            policy_source=policy_path,
        )

    def list_domains(self) -> list[RegisteredRetentionDomain]:
        return [self._domains[key] for key in sorted(self._domains)]

    def get(self, domain_id: str) -> RegisteredRetentionDomain:
        domain = self._domains.get(domain_id)
        if not domain:
            raise NotFound(f"Retention domain not found: {domain_id}")
        return domain


def _safe_policy_reference(policy_path: str) -> str:
    normalized = policy_path.replace("\\", "/")
    marker = "/config/"
    if marker in normalized:
        return f"config/{normalized.rsplit(marker, 1)[1]}"
    return normalized if not normalized.startswith(("/", "\\")) else "config:registered"
