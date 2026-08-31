from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from synapse.core.events import EventBus
from synapse.desktop_automation.models import ClipboardSnapshot


class ClipboardRuntime:
    """Transient clipboard custody. Content is never persisted or emitted."""

    def __init__(self, provider: Any, events: EventBus) -> None:
        self.provider = provider
        self.events = events
        self._vault: dict[str, str | None] = {}

    def get(self, *, reveal: bool = False) -> dict[str, Any]:
        content = self.provider.clipboard_get()
        return {
            "content": content if reveal else None,
            "length": len(content or ""),
            "digest": _digest(content),
            "content_type": "text/plain",
        }

    def snapshot(self) -> ClipboardSnapshot:
        content = self.provider.clipboard_get()
        token = str(uuid4())
        self._vault[token] = content
        return ClipboardSnapshot("text/plain", _digest(content), True, token)

    def set(self, value: str) -> dict[str, Any]:
        self.provider.clipboard_set(value)
        self.events.emit(
            "desktop.clipboard_changed",
            "desktop_automation",
            {"length": len(value), "digest": _digest(value)},
        )
        return {"length": len(value), "digest": _digest(value)}

    def clear(self) -> None:
        self.provider.clipboard_clear()
        self.events.emit("desktop.clipboard_cleared", "desktop_automation", {})

    def restore(self, snapshot: ClipboardSnapshot) -> bool:
        if not snapshot.restorable or not snapshot.token or snapshot.token not in self._vault:
            return False
        content = self._vault.pop(snapshot.token)
        if content is None:
            self.provider.clipboard_clear()
        else:
            self.provider.clipboard_set(content)
        self.events.emit(
            "desktop.clipboard_restored",
            "desktop_automation",
            {"digest": snapshot.digest},
        )
        return True


def _digest(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None
