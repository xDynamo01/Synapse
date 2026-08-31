from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synapse.bootstrap.adapters.coding_sessions import DeferredCodingSessionsRuntime
from synapse.bootstrap.adapters.operational_projection import OperationalProjectionRuntime
from synapse.bootstrap.adapters.private_evals import DeferredPrivateEvalsRuntime
from synapse.bootstrap.adapters.repository_runtime import DeferredRepositoryRuntime
from synapse.bootstrap.adapters.sandbox import DeferredSandboxRuntime
from synapse.bootstrap.adapters.skills_phase2 import DeferredSkillsPhase2Runtime
from synapse.bootstrap.lifecycle import LifecycleManager
from synapse.core.config import ConfigStore, Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.deployment_composition import DeploymentRuntime


@dataclass
class RuntimeContainer:
    """Typed application facade container; construction belongs to bootstrap."""

    settings: Settings
    data_dir: DataDir
    config: ConfigStore
    events: EventBus
    operational_projection: OperationalProjectionRuntime
    permissions: PermissionManager
    models: Any
    agents: Any
    identities: Any
    audit: Any
    admin_policy: Any
    admin: Any
    provisioning: Any
    provisioning_policy: Any
    agent_runtime: Any
    primary_agent: Any
    communication: Any
    conversations: Any
    dead_letter: Any
    delegation: Any
    delegation_execution: Any
    delegation_autonomy: Any
    delegation_retry: Any
    delegation_timeout: Any
    delegation_scheduling: Any
    delegation_inbox: Any
    delegation_recovery: Any
    missions: Any
    planner: Any
    worker_registry: Any
    worker_scheduler: Any
    result_verifier: Any
    attempts: Any
    worker_execution: Any
    worker_execution_adapter: Any
    mission_recovery: Any
    mission_trace: Any
    mission_dispatcher: Any
    swarm: Any
    ephemeral_agents: Any
    workforce_planner: Any
    mission_context: Any
    mission_supervision: Any
    mission_control: Any
    presence: Any
    lifecycle: Any
    notifications: Any
    devices: Any
    approvals: Any
    approval_resume: Any
    policies: Any
    memory: Any
    context_loader: Any
    tasks: Any
    tools: Any
    tool_runtime: Any
    tool_discovery: Any
    tool_intents: Any
    mcp: Any
    mcp_bridge: Any
    execution_router: Any
    agent_tool_calling: Any
    tool_router: Any
    worker: Any
    scheduler: Any
    daemon: Any
    runner_identity: Any
    health: Any
    readiness: Any
    migrations: Any
    capabilities: Any
    decisions: Any
    deployment: DeploymentRuntime
    private_evals: DeferredPrivateEvalsRuntime
    coding_sessions: DeferredCodingSessionsRuntime
    skills_phase2: DeferredSkillsPhase2Runtime
    sandbox: DeferredSandboxRuntime
    repository_runtime: DeferredRepositoryRuntime
    world_state: Any
    attention: Any
    attention_decisions: Any
    agent_loop: Any
    agent_event_stream: Any
    retention: Any
    maintenance: Any
    providers: Any
    provider_catalog: Any
    provider_settings: Any
    provider_plugins: Any
    lmstudio: Any
    model_hub: Any
    system_insight: Any
    desktop: Any
    voice: Any
    multimodal: Any
    audio: Any
    vision: Any
    capture: Any
    perception: Any
    context_fusion: Any
    skills: Any
    project_governance: Any
    intelligence_boundary: Any
    speech_adapters: Any
    speech_pipeline: Any
    commands: Any
    chat: Any
    application_lifecycle: LifecycleManager = field(default_factory=LifecycleManager)
    bootstrap_metadata: dict[str, Any] = field(default_factory=dict)

    def context(
        self,
        actor_id: str | None = None,
        actor_type: str = "user",
        device_id: str | None = None,
    ) -> PermissionContext:
        return PermissionContext(
            actor_id=actor_id or self.settings.default_actor_id,
            actor_type=actor_type,
            device_id=device_id,
        )
