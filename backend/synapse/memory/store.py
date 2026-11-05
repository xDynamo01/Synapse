from __future__ import annotations

import builtins
import hashlib
import re
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.memory.consolidation import MemoryConsolidator
from synapse.memory.errors import MemoryError
from synapse.memory.models import (
    MEMORY_SCOPES,
    MemoryRecord,
    MemoryRetrievalResult,
)
from synapse.memory.storage import FileMemoryStorage, MemoryStorage

GLOBAL_MEMORY_FILES = {"USER.md", "MEMORY.md", "SYSTEM.md"}
WORKING_SCOPES = {"session", "conversation", "working"}


class MemoryStore:
    def response_style(self, context: PermissionContext, message: str) -> str:
        """Persist only explicit, whole-message emoji preferences from a human user.

        Never promote quoted documents, model output or arbitrary prose to instructions.
        The single user-owned record is updated, rather than accumulated per turn.
        """
        if context.actor_type != "user":
            return ""
        records = [
            item
            for item in self.list(context, scope="user", owner_id=context.actor_id)
            if item.source == "explicit_response_style" and "response_style.emoji" in item.tags
        ]
        normalized = "".join(
            char
            for char in unicodedata.normalize("NFKD", message.lower())
            if not unicodedata.combining(char)
        ).strip(" .!")
        preference = None
        if re.fullmatch(
            r"(?:por favor[, ]+)?(?:nao (?:use|usar|utilize|mande|envie)(?: mais)?"
            r"(?: mensagens com)?|nao (?:converse|conversar|responda)(?: mais)? com|"
            r"nao quero|prefiro respostas sem|pare de (?:usar|mandar|enviar)|sem) "
            r"(?:emojis|emotes|emoticons)"
            r"(?: (?:nas|em suas) respostas)?(?:[, ]+por favor)?",
            normalized,
        ):
            preference = "Não use emojis, emotes ou emoticons nas respostas."
        elif re.fullmatch(
            r"(?:por favor[, ]+)?(?:pode|volte a) usar (?:emojis|emotes|emoticons)"
            r"(?: novamente)?",
            normalized,
        ):
            preference = "Emojis são permitidos nas respostas, sem obrigação de usá-los."
        if preference is not None:
            if records:
                if records[0].content != preference:
                    self.update(
                        context,
                        records[0].id,
                        expected_revision=records[0].revision,
                        content=preference,
                    )
            else:
                self.create(
                    context,
                    scope="user",
                    owner_id=context.actor_id,
                    source="explicit_response_style",
                    content=preference,
                    tags=["response_style.emoji"],
                    metadata={"sensitive": True},
                )
            return preference
        return records[0].content if records else ""

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
        self.consolidator = MemoryConsolidator(self)

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
        workspace_id: str | None = None,
        kind: str = "fact",
        verified: bool = False,
        supersedes: str | None = None,
        expected_revision: int | None = None,
    ) -> MemoryRecord:
        with self.storage.transaction():
            self.permissions.require(context, "filesystem.write")
            self._validate(scope, owner_id, content, importance, confidence)
            if scope in WORKING_SCOPES and not expires_at:
                raise MemoryError("invalid_memory", "working memory requires expires_at")
            records = self.storage.load()
            if scope == "workspace" and not workspace_id:
                raise MemoryError("invalid_memory", "workspace memory requires workspace_id")
            if workspace_id:
                self.permissions.require(context, f"memory.workspace:{workspace_id}.write")
            if (
                scope == "working"
                and context.actor_type == "agent"
                and owner_id != context.actor_id
            ):
                raise MemoryError(
                    "access_denied", "working memory belongs to its agent", status_code=403
                )
            if kind not in {
                "fact",
                "decision",
                "summary",
                "episode",
                "result",
                "reference",
                "temporary",
            }:
                raise MemoryError("invalid_memory", "unsupported memory kind")
            checksum = self._checksum(
                scope, owner_id, content + ("\0" + workspace_id if workspace_id else "")
            )
            duplicate = next(
                (
                    item
                    for item in records
                    if item.checksum == checksum
                    and item.status == "active"
                    and item.kind == kind
                    and item.verified == verified
                    and item.workspace_id == workspace_id
                ),
                None,
            )
            if duplicate:
                return duplicate
            if supersedes:
                previous_index = self._index(records, supersedes)
                previous = records[previous_index]
                self._authorize(context, previous)
                if previous.revision != expected_revision or previous.status != "active":
                    raise MemoryError(
                        "revision_mismatch", "memory revision does not match", status_code=409
                    )
                if (previous.scope, previous.owner_id, previous.workspace_id, previous.kind) != (
                    scope,
                    owner_id,
                    workspace_id,
                    kind,
                ):
                    raise MemoryError(
                        "invalid_memory", "replacement must preserve scope, owner and kind"
                    )
                records[previous_index] = replace(
                    previous,
                    status="superseded",
                    revision=previous.revision + 1,
                    updated_at=datetime.now(UTC).isoformat(),
                )
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
                workspace_id=workspace_id,
                kind=kind,
                verified=verified,
                supersedes=supersedes,
                provenance={"source": source, "actor_id": context.actor_id, "verified": verified},
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
        with self.storage.transaction():
            self.permissions.require(context, "filesystem.write")
            records = self.storage.load()
            index = self._index(records, memory_id)
            current = records[index]
            self._authorize(context, current)
            if current.workspace_id:
                self.permissions.require(context, f"memory.workspace:{current.workspace_id}.write")
            if current.revision != expected_revision:
                raise MemoryError(
                    "revision_mismatch",
                    "memory revision does not match",
                    status_code=409,
                    details={"expected": expected_revision, "actual": current.revision},
                )
            if (
                current.kind in {"decision", "summary"}
                and content is not None
                and content != current.content
            ):
                return self.create(
                    context,
                    scope=current.scope,
                    owner_id=current.owner_id,
                    source=current.source,
                    content=content,
                    content_type=current.content_type,
                    confidence=current.confidence,
                    importance=current.importance if importance is None else importance,
                    tags=current.tags if tags is None else tags,
                    metadata=current.metadata if metadata is None else metadata,
                    workspace_id=current.workspace_id,
                    kind=current.kind,
                    verified=current.verified,
                    supersedes=current.id,
                    expected_revision=expected_revision,
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
                checksum=self._checksum(
                    current.scope,
                    current.owner_id,
                    next_content + ("\0" + current.workspace_id if current.workspace_id else ""),
                ),
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
        with self.storage.transaction():
            self.permissions.require(context, "filesystem.write")
            current = self.get(context, memory_id)
            if current.workspace_id:
                self.permissions.require(context, f"memory.workspace:{current.workspace_id}.write")
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
        self.permissions.require(context, "filesystem.read")
        for scope in scopes:
            if scope not in MEMORY_SCOPES:
                raise MemoryError("invalid_scope", f"invalid memory scope: {scope}")
        filters = filters or {}
        workspace_ids = filters.get("workspace_ids", [])
        if not isinstance(workspace_ids, list) or not all(
            isinstance(value, str) for value in workspace_ids
        ):
            raise MemoryError("invalid_scope", "workspace_ids must be a list of identifiers")
        if len(set(workspace_ids)) > 1 and filters.get("cross_workspace") is not True:
            raise MemoryError(
                "access_denied",
                "cross-workspace retrieval requires explicit intent",
                status_code=403,
            )
        for workspace in workspace_ids:
            self.permissions.require(context, f"memory.workspace:{workspace}.read")
        candidates = []
        now = datetime.now(UTC)
        # Keep index selection and offset reads in one snapshot.
        with self.storage.transaction():
            for hits, item in self.storage.candidates(query):
                if (
                    item.status != "active"
                    or item.expires_at
                    and datetime.fromisoformat(item.expires_at) <= now
                ):
                    continue
                workspace = (
                    item.workspace_id
                    or item.project_id
                    or item.metadata.get("project_id")
                    or item.metadata.get("workspace_id")
                )
                project_tags = filters.get("tags", [])
                legacy_project_selection = workspace and f"project:{workspace}" in project_tags
                if workspace and workspace not in workspace_ids and not legacy_project_selection:
                    continue
                if (
                    item.scope not in scopes
                    or owner_ids
                    and item.owner_id not in owner_ids
                    and not workspace
                ):
                    continue
                if filters.get("tags") and not set(filters["tags"]).issubset(item.tags):
                    continue
                try:
                    self._authorize(context, item)
                except MemoryError:
                    continue
                score = hits * 100 + item.importance + (1000 if item.kind == "summary" else 0)
                candidates.append((score, item.updated_at, item.id))
            candidates.sort(reverse=True)
            maximum = max(0, limit if limit is not None else 20)
            records = self.storage.read_selected([key for _, _, key in candidates[:maximum]])
        selected, tokens = [], 0
        for item in records:
            # Headers accelerate discovery; canonical records remain the authorization source.
            self._authorize(context, item)
            workspace = (
                item.workspace_id
                or item.project_id
                or item.metadata.get("project_id")
                or item.metadata.get("workspace_id")
            )
            if (
                workspace
                and workspace not in workspace_ids
                and f"project:{workspace}" not in filters.get("tags", [])
            ):
                continue
            if item.status != "active":
                continue
            estimate = self.estimate_tokens(item.content)
            if budget is not None and tokens + estimate > budget:
                continue
            selected.append(item)
            tokens += estimate
        self.event_bus.emit(
            "memory_retrieved",
            context.actor_id,
            {
                "count": len(selected),
                "scopes": scopes,
                "estimated_tokens": tokens,
                "candidates": len(candidates),
                "content_records_read": len(records),
            },
        )
        return MemoryRetrievalResult(selected, len(candidates), tokens)

    def discover(self, context: PermissionContext) -> builtins.list[dict[str, object]]:
        """Authorized metadata only; does not deserialize canonical record contents."""
        self.permissions.require(context, "filesystem.read")
        result: builtins.list[dict[str, object]] = []
        for _, item in self.storage.candidates(""):
            try:
                self._authorize(context, item)
            except MemoryError:
                continue
            result.append(
                {
                    "id": item.id,
                    "scope": item.scope,
                    "workspace_id": item.workspace_id,
                    "kind": item.kind,
                    "revision": item.revision,
                    "status": item.status,
                    "owner_id": item.owner_id,
                    "reference": f"memory:{item.id}",
                    "permission": f"memory.workspace:{item.workspace_id}.read"
                    if item.workspace_id
                    else "filesystem.read",
                    "availability": "local",
                }
            )
        return result

    def discover_scopes(self, context: PermissionContext) -> builtins.list[dict[str, object]]:
        scopes: dict[tuple[str, str], dict[str, object]] = {}
        for item in self.discover(context):
            identifier = str(item["workspace_id"] or item["owner_id"])
            key = (str(item["scope"]), identifier)
            if key not in scopes:
                scopes[key] = {
                    "id": identifier,
                    "type": item["scope"],
                    "workspace_id": item["workspace_id"],
                    "availability": "local",
                    "permission": item["permission"],
                    "index_reference": f"memory-index:{key[0]}:{identifier}",
                    "active_records": 0,
                }
            if item["status"] == "active":
                count = scopes[key]["active_records"]
                assert isinstance(count, int)
                scopes[key]["active_records"] = count + 1
        return [scopes[key] for key in sorted(scopes)]

    def invalidate(
        self, context: PermissionContext, memory_id: str, *, expected_revision: int
    ) -> MemoryRecord:
        self.permissions.require(context, "filesystem.write")
        with self.storage.transaction():
            current = self.get(context, memory_id)
            if current.workspace_id:
                self.permissions.require(context, f"memory.workspace:{current.workspace_id}.write")
            if current.revision != expected_revision:
                raise MemoryError(
                    "revision_mismatch", "memory revision does not match", status_code=409
                )
            records = self.storage.load()
            invalidated = replace(
                current,
                status="invalidated",
                revision=current.revision + 1,
                updated_at=datetime.now(UTC).isoformat(),
            )
            records[self._index(records, memory_id)] = invalidated
            self.storage.save(records)
            self._emit("memory_invalidated", context, invalidated)
            return invalidated

    def cleanup(self, context: PermissionContext, *, max_working_items: int = 100) -> int:
        with self.storage.transaction():
            now = datetime.now(UTC)
            records = self.storage.load()
            changed = 0
            active_working = [
                item for item in records if item.scope in WORKING_SCOPES and item.status == "active"
            ]
            overflow: set[str] = set()
            for owner in {
                (item.scope, item.owner_id, item.workspace_id) for item in active_working
            }:
                owned = [
                    item
                    for item in active_working
                    if (item.scope, item.owner_id, item.workspace_id) == owner
                ]
                overflow.update(
                    item.id
                    for item in sorted(owned, key=lambda item: item.updated_at, reverse=True)[
                        max_working_items:
                    ]
                )
            for index, item in enumerate(records):
                expired = item.expires_at and datetime.fromisoformat(item.expires_at) <= now
                if item.status == "active" and (expired or item.id in overflow):
                    records[index] = replace(
                        item,
                        status="expired",
                        revision=item.revision + 1,
                        updated_at=now.isoformat(),
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
                    workspace_id=raw.get("workspace_id"),
                    kind=raw.get("kind", "fact"),
                    verified=raw.get("verified", False),
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

    def _authorize(self, context: PermissionContext, record: MemoryRecord) -> None:
        workspace = (
            record.workspace_id
            or record.project_id
            or record.metadata.get("project_id")
            or record.metadata.get("workspace_id")
        )
        if (
            workspace
            and not self.permissions.is_allowed(
                context, f"memory.workspace:{workspace}.read"
            ).allowed
        ):
            raise MemoryError("access_denied", "workspace memory access denied", status_code=403)
        if (
            context.actor_type == "agent"
            and record.scope in {"agent", "working"}
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
