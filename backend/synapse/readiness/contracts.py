from __future__ import annotations

from typing import Protocol

from synapse.readiness.models import ReadinessSummary


class ReadinessSnapshotSource(Protocol):
    def evaluate(self) -> ReadinessSummary: ...
