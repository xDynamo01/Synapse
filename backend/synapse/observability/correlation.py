from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Iterator
from uuid import uuid4


@dataclass(frozen=True)
class CorrelationContext:
    correlation_id: str
    source: str
    causation_id: str | None = None
    parent_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    job_id: str | None = None
    approval_id: str | None = None

    def child(
        self,
        source: str,
        causation_id: str | None = None,
        parent_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        job_id: str | None = None,
        approval_id: str | None = None,
    ) -> "CorrelationContext":
        return CorrelationContext(
            correlation_id=self.correlation_id,
            source=source,
            causation_id=causation_id if causation_id is not None else self.causation_id,
            parent_id=parent_id if parent_id is not None else self.parent_id,
            session_id=session_id if session_id is not None else self.session_id,
            agent_id=agent_id if agent_id is not None else self.agent_id,
            task_id=task_id if task_id is not None else self.task_id,
            job_id=job_id if job_id is not None else self.job_id,
            approval_id=approval_id if approval_id is not None else self.approval_id,
        )

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


_current_correlation: ContextVar[CorrelationContext | None] = ContextVar(
    "synapse_correlation",
    default=None,
)


def new_correlation(
    source: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    parent_id: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
    job_id: str | None = None,
    approval_id: str | None = None,
) -> CorrelationContext:
    return CorrelationContext(
        correlation_id=correlation_id or str(uuid4()),
        source=source,
        causation_id=causation_id,
        parent_id=parent_id,
        session_id=session_id,
        agent_id=agent_id,
        task_id=task_id,
        job_id=job_id,
        approval_id=approval_id,
    )


def current_correlation() -> CorrelationContext | None:
    return _current_correlation.get()


def current_correlation_fields() -> dict[str, str | None]:
    context = current_correlation()
    if not context:
        return {
            "correlation_id": None,
            "causation_id": None,
            "parent_id": None,
            "source": None,
        }
    return {
        "correlation_id": context.correlation_id,
        "causation_id": context.causation_id,
        "parent_id": context.parent_id,
        "source": context.source,
    }


@contextmanager
def correlation_scope(context: CorrelationContext) -> Iterator[CorrelationContext]:
    token = _current_correlation.set(context)
    try:
        yield context
    finally:
        _current_correlation.reset(token)
