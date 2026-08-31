from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.agent_loop.event_stream import AgentEventStream
from synapse.agent_loop.memory import MemoryCommitPolicy
from synapse.agent_loop.ports import LocalNotificationSink
from synapse.agent_loop.runtime import AgentLoopRuntime
from synapse.attention.decision import DecisionRuntime as AttentionDecisionRuntime
from synapse.attention.runtime import AttentionRuntime
from synapse.bootstrap.adapters.world_state import (
    RuntimeEventStateAdapter,
    WorldStateReadAdapter,
)
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.bootstrap.lifecycle import LifecycleResource
from synapse.health.contributors import WorldHealthContributor
from synapse.world_state.runtime import WorldStateRuntime
from synapse.world_state.sources import register_default_reconcilers


@dataclass(frozen=True)
class WorldFeatureDependencies:
    data_dir: Any
    events: Any
    default_actor_id: str
    platform: Any
    agents: Any
    missions: Any
    automation: Any
    integration: Any
    system_insight: Any
    chat: Any


@dataclass(frozen=True)
class WorldFeature:
    world_state: WorldStateRuntime
    attention: AttentionRuntime
    attention_decisions: AttentionDecisionRuntime
    agent_loop: AgentLoopRuntime
    agent_event_stream: AgentEventStream


class WorldFeatureBuilder:
    metadata = FeatureMetadata("world-state-and-agent-loop")

    def build(self, d: WorldFeatureDependencies) -> BuiltFeature[WorldFeature]:
        p, a, m, au, x = d.platform, d.agents, d.missions, d.automation, d.integration
        world_state = WorldStateRuntime(d.data_dir, d.events)
        world_state_read = WorldStateReadAdapter(world_state)
        attention = AttentionRuntime(d.data_dir, d.events, world_state_read)
        d.events.add_listener(RuntimeEventStateAdapter(world_state, attention).handle_event)
        attention_decisions = AttentionDecisionRuntime(d.data_dir, d.events, au.decisions)
        agent_loop = AgentLoopRuntime(
            d.data_dir,
            d.events,
            world_state,
            attention,
            attention_decisions,
            chat_runtime=d.chat,
            tool_runtime=x.tool_runtime,
            mission_runtime=m.missions,
            approval_runtime=p.approvals,
            notification_sink=LocalNotificationSink(p.notifications),
            insight_runtime=d.system_insight,
            desktop_runtime=a.desktop,
            memory_policy=MemoryCommitPolicy(p.memory),
            default_actor_id=d.default_actor_id,
        )
        stream = AgentEventStream(d.events)
        au.scheduler.agent_loop = agent_loop
        au.daemon.agent_loop = agent_loop
        register_default_reconcilers(
            world_state,
            presence=p.presence,
            lifecycle=p.lifecycle,
            missions=m.missions,
            daemon=au.daemon,
            scheduler=au.scheduler,
        )
        x.health.registry.register(
            WorldHealthContributor(world_state, attention, agent_loop, a.desktop)
        )
        value = WorldFeature(world_state, attention, attention_decisions, agent_loop, stream)
        resource = LifecycleResource(
            name="agent-loop",
            feature=self.metadata.name,
            reason="Own the persisted autonomous-loop operational state for the API lifespan.",
            start=agent_loop.start,
            close=agent_loop.stop,
            required=True,
            metadata={"failure_behavior": "rollback startup and fail the lifespan"},
        )
        return BuiltFeature(
            value,
            self.metadata,
            lifecycle_resources=(resource,),
            health_contributors=(agent_loop,),
            ports={"agent_loop": agent_loop},
        )
