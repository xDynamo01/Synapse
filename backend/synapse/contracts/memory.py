from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .base import CONTRACT_VERSION, ContractEvent, now_iso


@dataclass(frozen=True)
class MemoryStoreEntryDTO:
    scope: str
    key: str
    value: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class MemorySnapshotDTO:
    scope: str
    entries: list[MemoryStoreEntryDTO] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=now_iso)
    contract_version: str = CONTRACT_VERSION


@runtime_checkable
class MemoryStore(Protocol):
    def read(self, scope: str) -> MemorySnapshotDTO: ...

    def write(self, entry: MemoryStoreEntryDTO) -> None: ...

    def append(self, entry: MemoryStoreEntryDTO) -> None: ...

    def emit(self, event: ContractEvent) -> None: ...
