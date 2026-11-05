from __future__ import annotations

import hashlib
import json
import re
from contextlib import AbstractContextManager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

from synapse.memory.errors import MemoryError
from synapse.memory.models import MemoryRecord
from synapse.storage.atomic import atomic_write_text
from synapse.storage.locking import CollectionLock


class MemoryStorage(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...
    def load(self) -> list[MemoryRecord]: ...
    def save(self, records: list[MemoryRecord]) -> None: ...
    def candidates(self, query: str) -> list[tuple[int, MemoryRecord]]: ...
    def read_selected(self, ids: list[str]) -> list[MemoryRecord]: ...


class FileMemoryStorage:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = CollectionLock(path.with_name(".memory-records.lock"))

    def transaction(self) -> AbstractContextManager[None]:
        return self.lock.acquire()

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

    @staticmethod
    def terms(text: str) -> set[str]:
        # Hashed lexical keys, never document text, in the discovery index.
        return {
            hashlib.sha256(word.encode()).hexdigest()
            for word in re.findall(r"\w+", text.casefold())
        }

    @property
    def index_path(self) -> Path:
        return self.path.with_suffix(".index.json")

    def save(self, records: list[MemoryRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock.acquire():
            # Schema 1 stays JSON-compatible. Offsets address UTF-8 bytes, not characters.
            payload = bytearray(b'{"schema_version":1,"records":[')
            entries = []
            for number, record in enumerate(records):
                if number:
                    payload.extend(b",")
                encoded = json.dumps(asdict(record), ensure_ascii=False).encode("utf-8")
                header = replace(
                    record,
                    content="",
                    source="",
                    provenance={},
                    metadata={
                        key: record.metadata[key]
                        for key in ("sensitive", "project_id", "workspace_id")
                        if key in record.metadata
                    },
                )
                entries.append(
                    {
                        "header": asdict(header),
                        "offset": len(payload),
                        "length": len(encoded),
                        "tokens": max(1, (len(record.content) + 3) // 4),
                        "terms": sorted(self.terms(record.content + " " + " ".join(record.tags))),
                        "tags": sorted(self.terms(" ".join(record.tags))),
                    }
                )
                payload.extend(encoded)
            payload.extend(b"]}")
            try:
                atomic_write_text(self.path, payload.decode("utf-8"), backup=self.path.exists())
                stat = self.path.stat()
                atomic_write_text(
                    self.index_path,
                    json.dumps(
                        {
                            "version": 1,
                            "signature": [stat.st_mtime_ns, stat.st_size],
                            "entries": entries,
                        }
                    ),
                )
            except Exception as exc:
                raise MemoryError(
                    "persistence_failed", "memory storage write failed", status_code=500
                ) from exc

    def _index(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        stat = self.path.stat()
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            entries = raw.get("entries")
            valid_entries = isinstance(entries, list) and all(
                isinstance(entry, dict)
                and isinstance(entry.get("header"), dict)
                and isinstance(entry.get("terms"), list)
                and isinstance(entry.get("offset"), int)
                and isinstance(entry.get("length"), int)
                and 0 <= entry["offset"] < stat.st_size
                and 0 < entry["length"] <= stat.st_size - entry["offset"]
                for entry in entries
            )
            if (
                raw["version"] == 1
                and raw["signature"] == [stat.st_mtime_ns, stat.st_size]
                and valid_entries
            ):
                return entries
        except (OSError, ValueError, KeyError, TypeError):
            pass
        # One-time legacy migration or recovery of a missing/stale derived index.
        # Canonical corruption is never repaired by guessing from an index.
        self.save(self.load())
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        return raw["entries"]

    def candidates(self, query: str) -> list[tuple[int, MemoryRecord]]:
        with self.lock.acquire():
            terms = self.terms(query)
            results = []
            for entry in self._index():
                header = entry["header"]
                if not isinstance(header, dict):
                    raise MemoryError("persistence_failed", "memory index is corrupt")
                keys = entry["terms"]
                if not isinstance(keys, list):
                    raise MemoryError("persistence_failed", "memory index is corrupt")
                score = len(terms.intersection(str(key) for key in keys))
                record = MemoryRecord(**header)
                if not terms or score or record.kind == "summary":
                    results.append((score, record))
            return results

    def read_selected(self, ids: list[str]) -> list[MemoryRecord]:
        with self.lock.acquire():
            selected = set(ids)
            entries = self._index()
            if not entries:
                return []
            results = {}
            with self.path.open("rb") as handle:
                for entry in entries:
                    header = entry["header"]
                    if not isinstance(header, dict) or header["id"] not in selected:
                        continue
                    offset, length = entry["offset"], entry["length"]
                    if not isinstance(offset, int) or not isinstance(length, int):
                        raise MemoryError("persistence_failed", "memory index is corrupt")
                    handle.seek(offset)
                    record = MemoryRecord(**json.loads(handle.read(length)))
                    if any(
                        getattr(record, key) != header.get(key)
                        for key in (
                            "id",
                            "scope",
                            "owner_id",
                            "workspace_id",
                            "project_id",
                            "status",
                            "revision",
                        )
                    ):
                        raise MemoryError(
                            "persistence_failed", "memory index does not match canonical record"
                        )
                    results[record.id] = record
            return [results[key] for key in ids if key in results]
