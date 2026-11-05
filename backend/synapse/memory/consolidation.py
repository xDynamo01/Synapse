"""Selective, bounded background consolidation over the canonical MemoryStore."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import Protocol

from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.memory.errors import MemoryError
from synapse.memory.models import MemoryRecord


class ConsolidationStore(Protocol):
    event_bus: EventBus

    def create(
        self,
        context: PermissionContext,
        *,
        scope: str,
        owner_id: str,
        source: str,
        content: str,
        workspace_id: str | None = None,
        kind: str = "fact",
        verified: bool = False,
        supersedes: str | None = None,
        expected_revision: int | None = None,
    ) -> MemoryRecord: ...


@dataclass(frozen=True)
class MemoryCandidate:
    content: str
    source: str
    kind: str
    owner_id: str
    workspace_id: str | None = None
    explicitly_requested: bool = False
    verified: bool = False
    supersedes: str | None = None
    expected_revision: int | None = None


class MemoryConsolidator:
    def __init__(self, store: ConsolidationStore):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory-consolidation")
        self.capacity = BoundedSemaphore(32)

    def submit(
        self, context: PermissionContext, candidate: MemoryCandidate
    ) -> Future[MemoryRecord | None]:
        if not self.capacity.acquire(blocking=False):
            raise MemoryError(
                "consolidation_busy", "Memory consolidation queue is full", status_code=503
            )
        try:
            future = self.executor.submit(self.consolidate, context, candidate)
        except BaseException:
            self.capacity.release()
            raise
        future.add_done_callback(self._completed)
        return future

    def _completed(self, future: Future[MemoryRecord | None]) -> None:
        self.capacity.release()
        self.store.event_bus.emit(
            "memory_consolidation_finished",
            "memory",
            {"status": "failed" if future.exception() else "completed"},
        )

    def consolidate(
        self, context: PermissionContext, candidate: MemoryCandidate
    ) -> MemoryRecord | None:
        # No message-to-fact heuristic and no inferred confirmation.
        if candidate.kind not in {"fact", "decision", "summary", "episode", "result", "reference"}:
            return None
        if not candidate.explicitly_requested and not candidate.verified:
            return None
        if not candidate.source.strip() or not candidate.content.strip():
            return None
        return self.store.create(
            context,
            scope="workspace" if candidate.workspace_id else "agent",
            owner_id=candidate.owner_id,
            workspace_id=candidate.workspace_id,
            source=candidate.source,
            content=candidate.content,
            kind=candidate.kind,
            verified=candidate.verified,
            supersedes=candidate.supersedes,
            expected_revision=candidate.expected_revision,
        )

    def close(self) -> None:
        self.executor.shutdown(wait=True)
