from __future__ import annotations

from typing import Any

from synapse.desktop_automation.errors import TargetNotFound


class ApplicationRuntime:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def list(self):
        return self.provider.list_applications()

    def get(self, application_id: str):
        application = next(
            (item for item in self.list() if item.application_id == application_id), None
        )
        if application is None:
            raise TargetNotFound(f"Application not found: {application_id}")
        return application

    def find(self, name: str):
        folded = name.casefold()
        return [
            item
            for item in self.list()
            if folded in item.name.casefold() or folded == item.executable_name.casefold()
        ]
