from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from synapse.core.data_dir import DataDir
from synapse.observability.correlation import current_correlation


@dataclass(frozen=True)
class AgentAuditRecord:
    agent_id: str
    action: str
    status: str
    actor_agent_id: str | None = None
    actor_type: str | None = None
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class AgentAuditQuery:
    agent_id: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class AgentAuditSummary:
    agent_id: str
    total_records: int
    successes: int
    failures: int
    blocked: int
    last_action: str | None = None
    last_timestamp: str | None = None


class AgentAuditRuntime:
    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def append_record(
        self,
        agent_id: str,
        action: str,
        status: str = "success",
        actor_agent_id: str | None = None,
        actor_type: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AgentAuditRecord:
        correlation = current_correlation()
        record = AgentAuditRecord(
            agent_id=agent_id,
            action=action,
            status=status,
            actor_agent_id=actor_agent_id,
            actor_type=actor_type,
            reason=reason,
            details=details or {},
            correlation_id=correlation.correlation_id if correlation else None,
            causation_id=correlation.causation_id if correlation else None,
        )
        return self._append(self._path(agent_id), record)

    def append_provisioning_record(
        self,
        agent_id: str,
        action: str,
        status: str = "success",
        actor_agent_id: str | None = None,
        actor_type: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AgentAuditRecord:
        correlation = current_correlation()
        record = AgentAuditRecord(
            agent_id=agent_id,
            action=action,
            status=status,
            actor_agent_id=actor_agent_id,
            actor_type=actor_type,
            reason=reason,
            details=details or {},
            correlation_id=correlation.correlation_id if correlation else None,
            causation_id=correlation.causation_id if correlation else None,
        )
        path = self._provisioning_path(agent_id)
        return self._append(path, record)

    @staticmethod
    def _append(path, record: AgentAuditRecord) -> AgentAuditRecord:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record

    def list_agent_audit(self, agent_id: str, limit: int = 50) -> list[AgentAuditRecord]:
        records = [
            *self._read_records(self._provisioning_path(agent_id)),
            *self._read_records(self._path(agent_id)),
        ]
        records.sort(key=lambda item: item.timestamp)
        return records[-limit:]

    def list_recent_audit(self, limit: int = 100) -> list[AgentAuditRecord]:
        records: list[AgentAuditRecord] = []
        for path in sorted(self.data_dir.resolve("agents").glob("*/AUDIT.jsonl")):
            records.extend(self._read_records(path))
        for path in sorted(self.data_dir.resolve("agent_provisioning/audit").glob("*.jsonl")):
            records.extend(self._read_records(path))
        records.sort(key=lambda item: item.timestamp)
        return records[-limit:]

    def get_agent_audit_summary(self, agent_id: str) -> AgentAuditSummary:
        records = self.list_agent_audit(agent_id, limit=100_000)
        last = records[-1] if records else None
        return AgentAuditSummary(
            agent_id=agent_id,
            total_records=len(records),
            successes=len([item for item in records if item.status == "success"]),
            failures=len([item for item in records if item.status == "failed"]),
            blocked=len([item for item in records if item.status == "blocked"]),
            last_action=last.action if last else None,
            last_timestamp=last.timestamp if last else None,
        )

    def _path(self, agent_id: str):
        return self.data_dir.resolve(f"agents/{agent_id}/AUDIT.jsonl")

    def _provisioning_path(self, agent_id: str):
        return self.data_dir.resolve(f"agent_provisioning/audit/{agent_id}.jsonl")

    def _read_records(self, path) -> list[AgentAuditRecord]:
        if not path.exists():
            return []
        records: list[AgentAuditRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            raw.setdefault("actor_agent_id", None)
            raw.setdefault("actor_type", None)
            raw.setdefault("reason", None)
            raw.setdefault("details", {})
            raw.setdefault("correlation_id", None)
            raw.setdefault("causation_id", None)
            records.append(AgentAuditRecord(**raw))
        return records
