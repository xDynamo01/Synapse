from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.serialization import dump_structured_file, load_structured_file


@dataclass(frozen=True)
class DaemonStatus:
    running: bool = False
    last_tick_at: str | None = None
    total_ticks: int = 0
    last_error: str | None = None
    last_jobs_run: list[dict[str, Any]] = field(default_factory=list)
    started_at: str | None = None
    stopped_at: str | None = None


class DaemonStatusStore:
    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def load(self) -> DaemonStatus:
        path = self.data_dir.resolve("daemon/status.yaml")
        if not path.exists():
            return DaemonStatus()
        raw = load_structured_file(path)
        return DaemonStatus(**raw)

    def save(self, status: DaemonStatus) -> DaemonStatus:
        dump_structured_file(self.data_dir.resolve("daemon/status.yaml"), asdict(status))
        return status
