from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetentionDomain:
    domain_id: str
    description: str
    policy_path: str
    supports_dry_run: bool
    default_dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetentionPolicySummary:
    domain_id: str
    enabled: bool
    policy_path: str
    default_dry_run: bool
    policy: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetentionCleanupRequest:
    domain_id: str
    dry_run: bool = True


@dataclass(frozen=True)
class RetentionCleanupResult:
    domain_id: str
    dry_run: bool
    success: bool
    scanned: int = 0
    deleted: int = 0
    preserved: int = 0
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_result: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetentionRegistryStatus:
    domains: list[RetentionPolicySummary]
    total_domains: int
    enabled_domains: int
