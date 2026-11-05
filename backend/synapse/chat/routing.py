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
               message: str, workspace_id: str,
               recent_intent: str | None = None) -> ChatModelSelection | None: ...


@dataclass(frozen=True)
class PlannedMission:
    mission_id: str
    response: str


class ComplexMissionPort(Protocol):
    def prepare(self, context: PermissionContext, agent_id: str | None, message: str,
                conversation_id: str, project_id: str | None) -> PlannedMission | None: ...
