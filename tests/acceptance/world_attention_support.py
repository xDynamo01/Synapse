from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from synapse.agent_loop.runtime import AgentLoopRuntime
from synapse.attention.models import AttentionEvent, Decision
from synapse.attention.runtime import AttentionRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.world_state.runtime import WorldStateRuntime


class DomainFixture:
    def __init__(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.data_dir = DataDir(Path(self.directory.name))
        self.data_dir.bootstrap()
        self.events = EventBus(self.data_dir.root)
        self.world_state = WorldStateRuntime(self.data_dir, self.events)
        self.attention = AttentionRuntime(self.data_dir, self.events)

    def close(self) -> None:
        self.directory.cleanup()

    def high_item(self, disposition: str, selected_action: dict[str, Any] | None = None):
        return self.attention.ingest_event(AttentionEvent(
            type="acceptance.event", source="acceptance", title="Acceptance attention",
            summary="An acceptance event needs handling.", severity="high", urgency=1.0,
            suggested_dispositions=[disposition],
            metadata={"selected_action": selected_action or {}, "selected_agent": "artemis"},
        ), self.world_state.snapshot())


class FixedDecisionRuntime:
    def __init__(self, disposition: str, action: dict[str, Any] | None = None) -> None:
        self.disposition = disposition
        self.action = action

    def decide(self, item, world_state):
        return Decision(
            attention_item_id=item.id, disposition=self.disposition, reason="acceptance allow",
            policy_result={"allowed": True}, autonomy_level="autonomous_limited", risk="low",
            selected_agent="artemis", selected_action=self.action,
        )


def loop(fixture: DomainFixture, decisions: Any, **ports: Any) -> AgentLoopRuntime:
    return AgentLoopRuntime(
        fixture.data_dir, fixture.events, fixture.world_state, fixture.attention, decisions,
        default_actor_id="local_owner", **ports,
    )


@dataclass
class FakeMessage:
    role: str = "assistant"


@dataclass
class FakeSession:
    id: str = "session-1"
    messages: list[FakeMessage] = field(default_factory=lambda: [FakeMessage()])


class ChatSpy:
    def __init__(self) -> None:
        self.calls = 0
        self.session = FakeSession()

    def send_message(self, *args, **kwargs):
        self.calls += 1
        return SimpleNamespace(session=self.session)

    def get_session(self, session_id):
        return self.session


class ToolSpy:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return SimpleNamespace(
            success=True, status="completed", call_id="call-1", tool_id=request.tool_id,
            output={"ok": True}, side_effects=["reversible_test_effect"], error=None,
        )


class MissionSpy:
    def __init__(self) -> None:
        self.calls = 0
        self.mission = SimpleNamespace(mission_id="mission-1")

    def create_mission(self, **kwargs):
        self.calls += 1
        return self.mission

    def get_mission(self, mission_id):
        return self.mission
