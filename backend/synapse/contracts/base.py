from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

CONTRACT_VERSION = "v1"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ContractStatus:
    state: str
    message: str | None = None
    contract_version: str = CONTRACT_VERSION
    generated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ContractEvent:
    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    contract_version: str = CONTRACT_VERSION
    generated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ContractError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    contract_version: str = CONTRACT_VERSION
    generated_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ContractResult:
    ok: bool
    value: Any | None = None
    error: ContractError | None = None
    events: list[ContractEvent] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION
    generated_at: str = field(default_factory=now_iso)
