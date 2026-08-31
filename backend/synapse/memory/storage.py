from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from synapse.memory.errors import MemoryError
from synapse.memory.models import MemoryRecord
from synapse.storage.atomic import atomic_write_text
from synapse.storage.locking import CollectionLock


class MemoryStorage(Protocol):
    def load(self) -> list[MemoryRecord]: ...
    def save(self, records: list[MemoryRecord]) -> None: ...


class FileMemoryStorage:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = CollectionLock(path.with_name(".memory-records.lock"))

    def load(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("schema_version") != self.SCHEMA_VERSION or not isinstance(
                raw.get("records"), list
            ):
                raise ValueError("unsupported memory schema")
            return [MemoryRecord(**item) for item in raw["records"]]
        except Exception as exc:
            raise MemoryError(
                "persistence_failed", "memory storage is corrupt", status_code=500
            ) from exc

    def save(self, records: list[MemoryRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "records": [asdict(item) for item in records],
        }
        try:
            text = json.dumps(payload, indent=2, sort_keys=True)
            with self.lock.acquire():
                atomic_write_text(self.path, text, backup=self.path.exists())
        except Exception as exc:
            raise MemoryError(
                "persistence_failed", "memory storage write failed", status_code=500
            ) from exc
