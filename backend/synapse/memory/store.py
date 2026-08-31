from __future__ import annotations

import builtins
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.memory.errors import MemoryError
from synapse.memory.models import (
    MEMORY_SCOPES,
    MemoryRecord,
    MemoryRetrievalResult,
)
from synapse.memory.storage import FileMemoryStorage, MemoryStorage

GLOBAL_MEMORY_FILES = {"USER.md", "MEMORY.md", "SYSTEM.md"}
WORKING_SCOPES = {"session", "conversation"}


class MemoryStore:
    def __init__(
        self,
        data_dir: DataDir,
        permissions: PermissionManager,
        event_bus: EventBus,
        storage: MemoryStorage | None = None,
    ):
        self.data_dir = data_dir
        self.permissions = permissions
        self.event_bus = event_bus
        self.storage = storage or FileMemoryStorage(data_dir.resolve("memory/records.json"))

    def create(
        self,
        context: PermissionContext,
        *,
        scope: str,
        owner_id: str,
        source: str,
        content: str,
        content_type: str = "text/plain",
        expires_at: str | None = None,
        confidence: float | None = None,
        importance: int = 50,
        tags: builtins.list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        self.permissions.require(context, "filesystem.write")
        self._validate(scope, owner_id, content, importance, confidence)
        if scope in WORKING_SCOPES and not expires_at:
            raise MemoryError("invalid_memory", "working memory requires expires_at")
        records = self.storage.load()
        checksum = self._checksum(scope, owner_id, content)
        duplicate = next(
            (item for item in records if item.checksum == checksum and item.status == "active"),
            None,
        )
        if duplicate:
            return duplicate
        record = MemoryRecord(
            scope=scope,
            owner_id=owner_id,
            source=source,
            content=content,
            content_type=content_type,
            expires_at=expires_at,
            confidence=confidence,
            importance=importance,
            tags=sorted(set(tags or [])),
            metadata=metadata or {},
            checksum=checksum,
        )
        records.append(record)
        self.storage.save(records)
        self._emit("memory_created", context, record)
        return record

    def get(self, context: PermissionContext, memory_id: str) -> MemoryRecord:
        self.permissions.require(context, "filesystem.read")
        record = self._find(memory_id)
        self._authorize(context, record)
        return record

    def list(
        self,
        context: PermissionContext,
        *,
        scope: str | None = None,
        owner_id: str | None = None,
        include_deleted: bool = False,
    ) -> list[MemoryRecord]:
        self.permissions.require(context, "filesystem.read")
        if scope is not None and scope not in MEMORY_SCOPES:
            raise MemoryError("invalid_scope", f"invalid memory scope: {scope}")
        self.cleanup(context)
        result = []
        for item in self.storage.load():
            if scope and item.scope != scope or owner_id and item.owner_id != owner_id:
                continue
            if not include_deleted and item.status != "active":
                continue
            try:
                self._authorize(context, item)
            except MemoryError:
                continue
            result.append(item)
        return sorted(result, key=lambda item: (item.updated_at, item.id), reverse=True)

    def update(
        self,
        context: PermissionContext,
        memory_id: str,
        *,
        expected_revision: int,
        content: str | None = None,
        importance: int | None = None,
        tags: builtins.list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        self.permissions.require(context, "filesystem.write")
        records = self.storage.load()
        index = self._index(records, memory_id)
        current = records[index]
        self._authorize(context, current)
        if current.revision != expected_revision:
            raise MemoryError(
                "revision_mismatch",
                "memory revision does not match",
                status_code=409,
                details={"expected": expected_revision, "actual": current.revision},
            )
        next_content = current.content if content is None else content
        next_importance = current.importance if importance is None else importance
        self._validate(
            current.scope, current.owner_id, next_content, next_importance, current.confidence
        )
        updated = replace(
            current,
            content=next_content,
            importance=next_importance,
            tags=current.tags if tags is None else sorted(set(tags)),
            metadata=current.metadata if metadata is None else metadata,
            checksum=self._checksum(current.scope, current.owner_id, next_content),
            revision=current.revision + 1,
            updated_at=datetime.now(UTC).isoformat(),
        )
        records[index] = updated
        self.storage.save(records)
        self._emit("memory_updated", context, updated)
        return updated

    def delete(
        self, context: PermissionContext, memory_id: str, *, expected_revision: int
    ) -> MemoryRecord:
        self.permissions.require(context, "filesystem.write")
        current = self.get(context, memory_id)
        if current.revision != expected_revision:
            raise MemoryError(
                "revision_mismatch", "memory revision does not match", status_code=409
            )
        records = self.storage.load()
        index = self._index(records, memory_id)
        deleted = replace(
            current,
            status="deleted",
            revision=current.revision + 1,
            updated_at=datetime.now(UTC).isoformat(),
            content="",
            checksum=self._checksum(current.scope, current.owner_id, ""),
        )
        records[index] = deleted
        self.storage.save(records)
        self._emit("memory_deleted", context, deleted)
        return deleted

    def retrieve_memory(
        self,
        context: PermissionContext,
        query: str,
        scopes: builtins.list[str],
        owner_ids: builtins.list[str] | None = None,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
        budget: int | None = None,
    ) -> MemoryRetrievalResult:
        for scope in scopes:
            if scope not in MEMORY_SCOPES:
                raise MemoryError("invalid_scope", f"invalid memory scope: {scope}")
        filters = filters or {}
        terms = {term.casefold() for term in query.split() if term.strip()}
        candidates = []
        for item in self.list(context):
            if item.scope not in scopes or owner_ids and item.owner_id not in owner_ids:
                continue
            if filters.get("tags") and not set(filters["tags"]).issubset(item.tags):
                continue
            haystack = f"{item.content} {' '.join(item.tags)}".casefold()
            score = sum(term in haystack for term in terms) * 100 + item.importance
            if terms and score == item.importance:
                continue
            candidates.append((score, item.updated_at, item))
        ordered = [
            item
            for _, _, item in sorted(
                candidates, key=lambda value: (value[0], value[1], value[2].id), reverse=True
            )
        ]
        selected, tokens = [], 0
        for item in ordered[: limit or 20]:
            estimate = self.estimate_tokens(item.content)
            if budget is not None and tokens + estimate > budget:
                continue
            selected.append(item)
            tokens += estimate
        self.event_bus.emit(
            "memory_retrieved", context.actor_id, {"count": len(selected), "scopes": scopes}
        )
        return MemoryRetrievalResult(selected, len(ordered), tokens)

    def cleanup(self, context: PermissionContext, *, max_working_items: int = 100) -> int:
        now = datetime.now(UTC)
        records = self.storage.load()
        changed = 0
        active_working = [
            item for item in records if item.scope in WORKING_SCOPES and item.status == "active"
        ]
        overflow = {
            item.id
            for item in sorted(active_working, key=lambda item: item.updated_at, reverse=True)[
                max_working_items:
            ]
        }
        for index, item in enumerate(records):
            expired = item.expires_at and datetime.fromisoformat(item.expires_at) <= now
            if item.status == "active" and (expired or item.id in overflow):
                records[index] = replace(
                    item, status="expired", revision=item.revision + 1, updated_at=now.isoformat()
                )
                changed += 1
                self._emit("memory_expired", context, records[index])
        if changed:
            self.storage.save(records)
        return changed

    def export_records(
        self,
        context: PermissionContext,
        *,
        scopes: builtins.list[str],
        owner_ids: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        records = [
            item
            for item in self.list(context)
            if item.scope in scopes and (not owner_ids or item.owner_id in owner_ids)
        ]
        from dataclasses import asdict

        return {"schema_version": 1, "records": [asdict(item) for item in records]}

    def import_records(
        self, context: PermissionContext, payload: dict[str, Any]
    ) -> builtins.list[MemoryRecord]:
        if payload.get("schema_version") != 1 or not isinstance(
            payload.get("records"), builtins.list
        ):
            raise MemoryError("import_invalid", "invalid memory import")
        imported = []
        for raw in payload["records"]:
            imported.append(
                self.create(
                    context,
                    scope=raw["scope"],
                    owner_id=raw["owner_id"],
                    source=f"import:{raw.get('source', 'unknown')}",
                    content=raw["content"],
                    content_type=raw.get("content_type", "text/plain"),
                    expires_at=raw.get("expires_at"),
                    confidence=raw.get("confidence"),
                    importance=raw.get("importance", 50),
                    tags=raw.get("tags", []),
                    metadata=raw.get("metadata", {}),
                )
            )
        return imported

    @staticmethod
    def estimate_tokens(content: str) -> int:
        return max(1, (len(content) + 3) // 4)

    def read_global(self, context: PermissionContext, name: str) -> str:
        self.permissions.require(context, "filesystem.read")
        if name not in GLOBAL_MEMORY_FILES:
            raise ValidationError(f"Unknown global memory file: {name}")
        path = self.data_dir.resolve(f"memory/{name}")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def append_global(self, context: PermissionContext, name: str, text: str) -> None:
        self.permissions.require(context, "filesystem.write")
        if name not in GLOBAL_MEMORY_FILES:
            raise ValidationError(f"Unknown global memory file: {name}")
        self.data_dir.append_text(f"memory/{name}", f"\n{text}\n")
        self.event_bus.emit("memory.global.appended", context.actor_id, {"file": name})

    def read_agent_memory(self, context: PermissionContext, agent_id: str) -> str:
        self.permissions.require(context, "filesystem.read")
        path = self.data_dir.resolve(f"agents/{agent_id}/MEMORY.md")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def append_agent_memory(self, context: PermissionContext, agent_id: str, text: str) -> None:
        self.permissions.require(context, "filesystem.write")
        self.data_dir.append_text(f"agents/{agent_id}/MEMORY.md", f"\n{text}\n")
        self.event_bus.emit("memory.agent.appended", context.actor_id, {"agent_id": agent_id})

    def _find(self, memory_id: str) -> MemoryRecord:
        records = self.storage.load()
        return records[self._index(records, memory_id)]

    @staticmethod
    def _index(records: builtins.list[MemoryRecord], memory_id: str) -> int:
        for index, item in enumerate(records):
            if item.id == memory_id:
                return index
        raise MemoryError("memory_not_found", f"memory not found: {memory_id}", status_code=404)

    @staticmethod
    def _checksum(scope: str, owner_id: str, content: str) -> str:
        return hashlib.sha256(f"{scope}\0{owner_id}\0{content}".encode()).hexdigest()

    @staticmethod
    def _validate(
        scope: str, owner_id: str, content: str, importance: int, confidence: float | None
    ) -> None:
        if scope not in MEMORY_SCOPES:
            raise MemoryError("invalid_scope", f"invalid memory scope: {scope}")
        if (
            not owner_id.strip()
            or not content.strip()
            or not 0 <= importance <= 100
            or confidence is not None
            and not 0 <= confidence <= 1
        ):
            raise MemoryError("invalid_memory", "invalid memory record")

    @staticmethod
    def _authorize(context: PermissionContext, record: MemoryRecord) -> None:
        if (
            context.actor_type == "agent"
            and record.scope == "agent"
            and context.actor_id != record.owner_id
        ):
            raise MemoryError("access_denied", "agent memory access denied", status_code=403)
        if (
            record.metadata.get("sensitive")
            and context.actor_id != record.owner_id
            and context.actor_type != "system"
        ):
            raise MemoryError(
                "sensitive_memory_denied", "sensitive memory access denied", status_code=403
            )

    def _emit(self, event_type: str, context: PermissionContext, record: MemoryRecord) -> None:
        self.event_bus.emit(
            event_type,
            context.actor_id,
            {
                "memory_id": record.id,
                "scope": record.scope,
                "owner_id": record.owner_id,
                "revision": record.revision,
                "status": record.status,
            },
        )
