from dataclasses import dataclass
from typing import Protocol

from synapse.core.permissions import PermissionContext


@dataclass(frozen=True)
class ChatModelSelection:
    agent_id: str
    provider: str
    model: str
    operation: str
    revision: int


class PrimaryModelRoutingPort(Protocol):
    def select(self, context: PermissionContext, agent_id: str | None,
               message: str, workspace_id: str) -> ChatModelSelection | None: ...
