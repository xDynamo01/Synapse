from __future__ import annotations

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext, PermissionManager

GLOBAL_MEMORY_FILES = {"USER.md", "MEMORY.md", "SYSTEM.md"}


class MemoryStore:
    def __init__(self, data_dir: DataDir, permissions: PermissionManager, event_bus: EventBus):
        self.data_dir = data_dir
        self.permissions = permissions
        self.event_bus = event_bus

    def read_global(self, context: PermissionContext, name: str) -> str:
        self.permissions.require(context, "filesystem.read")
        if name not in GLOBAL_MEMORY_FILES:
            raise ValidationError(f"Unknown global memory file: {name}")
        return self.data_dir.resolve(f"memory/{name}").read_text(encoding="utf-8")

    def append_global(self, context: PermissionContext, name: str, text: str) -> None:
        self.permissions.require(context, "filesystem.write")
        if name not in GLOBAL_MEMORY_FILES:
            raise ValidationError(f"Unknown global memory file: {name}")
        self.data_dir.append_text(f"memory/{name}", f"\n{text}\n")
        self.event_bus.emit("memory.global.appended", context.actor_id, {"file": name})

    def read_agent_memory(self, context: PermissionContext, agent_id: str) -> str:
        self.permissions.require(context, "filesystem.read")
        return self.data_dir.resolve(f"agents/{agent_id}/MEMORY.md").read_text(encoding="utf-8")

    def append_agent_memory(self, context: PermissionContext, agent_id: str, text: str) -> None:
        self.permissions.require(context, "filesystem.write")
        self.data_dir.append_text(f"agents/{agent_id}/MEMORY.md", f"\n{text}\n")
        self.event_bus.emit(
            "memory.agent.appended",
            context.actor_id,
            {"agent_id": agent_id},
        )

