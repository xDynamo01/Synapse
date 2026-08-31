from __future__ import annotations

from typing import Any

from synapse.storage.collection import FileCollection
from synapse.storage.contracts import CollectionQuery


class BoundaryRecordStoreAdapter:
    def __init__(self, collection: FileCollection) -> None:
        self.collection = collection

    def put(
        self,
        record_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int | None = None,
        create_only: bool = False,
    ) -> None:
        self.collection.put(
            record_id,
            payload,
            expected_revision=expected_revision,
            create_only=create_only,
        )

    def get(self, record_id: str) -> dict[str, Any]:
        return dict(self.collection.get(record_id).payload)

    def list(self, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
        result: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = self.collection.list(
                CollectionQuery(filters=filters or {}, cursor=cursor, limit=500)
            )
            result.extend(dict(item.payload) for item in page.items)
            if page.next_cursor is None:
                return tuple(result)
            cursor = page.next_cursor
