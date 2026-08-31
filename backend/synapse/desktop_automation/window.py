from __future__ import annotations

from typing import Any

from synapse.desktop_automation.errors import TargetNotFound


class WindowRuntime:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def list(self, application_id: str | None = None):
        windows = self.provider.list_windows()
        return (
            [item for item in windows if item.application_id == application_id]
            if application_id
            else windows
        )

    def get(self, window_id: str):
        window = next((item for item in self.list() if item.window_id == window_id), None)
        if window is None:
            raise TargetNotFound(f"Window not found: {window_id}")
        return window

    def find(self, title: str):
        folded = title.casefold()
        return [item for item in self.list() if folded in item.title.casefold()]
