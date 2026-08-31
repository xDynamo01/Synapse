from __future__ import annotations

from synapse.capabilities.models import Capability
from synapse.core.exceptions import NotFound, ValidationError


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if capability.capability_id in self._capabilities:
            raise ValidationError(f"Capability already registered: {capability.capability_id}")
        self._capabilities[capability.capability_id] = capability

    def list_capabilities(self) -> list[Capability]:
        return [self._capabilities[key] for key in sorted(self._capabilities)]

    def get(self, capability_id: str) -> Capability:
        capability = self._capabilities.get(capability_id)
        if capability is None:
            raise NotFound(f"Capability not found: {capability_id}")
        return capability

    def capability_for_tool(self, tool_name: str) -> Capability | None:
        for capability in self._capabilities.values():
            tools = capability.metadata.get("tools", [])
            if tool_name in set(tools):
                return capability
        return None


def builtin_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for capability in _builtin_capabilities():
        registry.register(capability)
    return registry


def _builtin_capabilities() -> list[Capability]:
    return [
        Capability(
            "memory.read",
            "Read Memory",
            "Read persisted memory records.",
            "memory",
            "low",
            ["memory.read"],
            ["memory"],
        ),
        Capability(
            "memory.write",
            "Write Memory",
            "Write persisted memory records.",
            "memory",
            "medium",
            ["memory.write"],
            ["memory"],
        ),
        Capability(
            "filesystem.read",
            "Read Files",
            "Read or search files inside DATA_DIR.",
            "filesystem",
            "low",
            ["filesystem.read"],
            ["file"],
            metadata={"tools": ["read_file", "list_directory", "search_files"]},
        ),
        Capability(
            "filesystem.write",
            "Write Files",
            "Write files inside DATA_DIR.",
            "filesystem",
            "high",
            ["filesystem.write"],
            ["file"],
            required_approval_level="high",
            metadata={"tools": ["write_file"]},
        ),
        Capability(
            "task.create",
            "Create Tasks",
            "Create persistent tasks.",
            "scheduling",
            "low",
            ["tasks.create"],
            ["job"],
            metadata={"tools": ["create_task"]},
        ),
        Capability(
            "task.update",
            "Update Tasks",
            "Update persistent tasks.",
            "scheduling",
            "medium",
            ["tasks.update"],
            ["job"],
            metadata={"tools": ["update_task"]},
        ),
        Capability(
            "agent.message",
            "Message Agents",
            "Send structured agent-to-agent messages.",
            "agent_coordination",
            "medium",
            ["agents.message"],
            ["agent_message"],
            metadata={"tools": ["send_agent_message"]},
        ),
        Capability(
            "agent.task.delegation",
            "Delegate Agent Tasks",
            "Create persistent delegation tasks assigned to another agent.",
            "agent_coordination",
            "medium",
            ["delegation.create"],
            ["job", "agent_message"],
        ),
        Capability(
            "notification.read",
            "Read Notifications",
            "Read local notifications.",
            "notification",
            "low",
            ["notifications.read"],
            ["notification"],
        ),
        Capability(
            "notification.manage",
            "Manage Notifications",
            "Update or delete local notifications.",
            "notification",
            "medium",
            ["notifications.delete"],
            ["notification"],
        ),
        Capability(
            "approval.review",
            "Review Approvals",
            "Approve or reject pending approval requests.",
            "approval",
            "high",
            ["approvals.approve", "approvals.reject"],
            ["approval"],
            required_approval_level="high",
        ),
        Capability(
            "scheduler.enqueue",
            "Enqueue Jobs",
            "Create scheduler jobs.",
            "scheduling",
            "medium",
            ["jobs.create"],
            ["job"],
        ),
        Capability(
            "scheduler.run",
            "Run Scheduler",
            "Run pending scheduler jobs.",
            "scheduling",
            "high",
            ["jobs.run"],
            ["job"],
        ),
        Capability(
            "daemon.health",
            "Check Daemon Health",
            "Inspect daemon and homelab health state.",
            "system",
            "low",
            ["system.health"],
            ["job", "notification", "approval"],
        ),
        Capability(
            "audio.session",
            "Manage Audio Sessions",
            "Create and inspect local audio session contracts.",
            "audio",
            "low",
            ["audio.session"],
            ["chat_session"],
        ),
        Capability(
            "audio.input",
            "Use Audio Input",
            "Request audio input through a provider boundary.",
            "audio",
            "high",
            ["audio.input"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "audio.output",
            "Use Audio Output",
            "Request audio output through a provider boundary.",
            "audio",
            "medium",
            ["audio.output"],
            ["chat_session"],
        ),
        Capability(
            "speech_to_text",
            "Speech To Text",
            "Transcribe speech through a provider boundary.",
            "audio",
            "high",
            ["audio.input"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "text_to_speech",
            "Text To Speech",
            "Synthesize speech through a provider boundary.",
            "audio",
            "medium",
            ["audio.output"],
            ["chat_session"],
        ),
        Capability(
            "voice_analysis",
            "Voice Analysis",
            "Analyze voice signals through a provider boundary.",
            "audio",
            "high",
            ["audio.input"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "vision.session",
            "Manage Vision Sessions",
            "Create and inspect local vision session contracts.",
            "vision",
            "low",
            ["vision.session"],
            ["chat_session"],
        ),
        Capability(
            "vision.frame",
            "Capture Vision Frames",
            "Request vision frames through a provider boundary.",
            "vision",
            "high",
            ["vision.frame"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "vision",
            "Vision Analysis",
            "Analyze frames through a vision provider boundary.",
            "vision",
            "high",
            ["vision.frame"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "face_tracking",
            "Face Tracking",
            "Track face observations through a provider boundary.",
            "vision",
            "high",
            ["vision.frame"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "body_tracking",
            "Body Tracking",
            "Track body observations through a provider boundary.",
            "vision",
            "high",
            ["vision.frame"],
            ["chat_session"],
            required_approval_level="high",
        ),
        Capability(
            "voice.output",
            "Voice Output",
            "Resolve voice output provider metadata.",
            "audio",
            "medium",
            ["audio.output"],
            ["chat_session"],
        ),
    ]
