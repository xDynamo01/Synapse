from __future__ import annotations

from typing import Protocol

from synapse.system_insight.models import (
    DiskSnapshot,
    HardwareSnapshot,
    ProcessSnapshot,
    SystemSnapshot,
)


class PlatformInsightProvider(Protocol):
    name: str

    def collect_system(self) -> SystemSnapshot: ...

    def collect_hardware(self) -> HardwareSnapshot: ...

    def collect_storage(self) -> DiskSnapshot: ...

    def collect_processes(self, limit: int = 100) -> ProcessSnapshot: ...

    def status(self) -> dict[str, object]: ...
