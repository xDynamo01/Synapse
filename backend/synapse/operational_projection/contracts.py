"""Read ports exposed by the operational projection composition."""

from typing import Protocol

from .models import ProjectActivitySnapshot
from .stream import ActivityResume


class OperationalProjectionReadPort(Protocol):
    def snapshot(self, project_id: str, observed_at: str) -> ProjectActivitySnapshot: ...

    def resume(
        self, project_id: str, cursor: str | None, observed_at: str
    ) -> ActivityResume: ...
