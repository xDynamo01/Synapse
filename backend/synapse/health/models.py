from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ComponentHealth:
    component_id: str
    module: str
    state: str
    configured: bool
    available: bool
    ready: bool
    degraded: bool
    last_check_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    latency_ms: int | None = None
    last_error: str | None = None
    dependencies: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


HealthSeverity = str


@dataclass(frozen=True)
class HealthCheckItem:
    id: str
    label: str
    severity: HealthSeverity
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HomelabHealthSummary:
    runner: dict[str, Any]
    daemon: dict[str, Any]
    scheduler_lock: dict[str, Any]
    pending_jobs: int
    failed_jobs: int
    recurring_jobs_due: int
    unread_critical_notifications: int
    agents_attention: list[dict[str, Any]] = field(default_factory=list)
    approvals_pending: int = 0
    pending_agent_provisioning_requests: int = 0
    pending_admin_action_requests: int = 0
    retention: dict[str, Any] = field(default_factory=dict)
    migrations: dict[str, Any] = field(default_factory=dict)
    decision_runtime_available: bool = False
    capability_count: int = 0
    archived_agents: int = 0
    inactive_agents: int = 0
    delegation_inbox: dict[str, Any] = field(default_factory=dict)
    delegation_execution: dict[str, Any] = field(default_factory=dict)
    delegation_timeout: dict[str, Any] = field(default_factory=dict)
    dead_letter_open_count: int = 0
    recovery_candidates_count: int = 0
    active_missions_count: int = 0
    failed_missions_count: int = 0
    missions_with_critical_context: int = 0
    missions_warning_count: int = 0
    missions_critical_count: int = 0
    provider_runtime_available: bool = False
    providers_unavailable_count: int = 0
    provider_plugin_runtime_available: bool = False
    provider_plugins_unavailable_count: int = 0
    provider_plugins_not_installed_count: int = 0
    lmstudio_available: bool = False
    lmstudio_model_count: int = 0
    model_hub_available: bool = False
    model_catalog_size: int = 0
    model_provider_count: int = 0
    provider_settings_available: bool = False
    configured_external_provider_count: int = 0
    user_agent_count: int = 0
    primary_agent: dict[str, Any] = field(default_factory=dict)
    ephemeral_agents: dict[str, Any] = field(default_factory=dict)
    local_chat_available: bool = False
    voice_runtime_available: bool = False
    voice_provider_unavailable_count: int = 0
    voice_diagnostics: dict[str, Any] = field(default_factory=dict)
    components: list[ComponentHealth] = field(default_factory=list)
    speech_pipeline_runtime_available: bool = False
    speech_pipeline_sessions_count: int = 0
    speech_adapter_runtime_available: bool = False
    speech_adapters_unavailable_count: int = 0
    multimodal_runtime_available: bool = False
    audio_runtime_available: bool = False
    audio_provider_unavailable_count: int = 0
    vision_runtime_available: bool = False
    vision_provider_unavailable_count: int = 0
    perception_runtime_available: bool = False
    perception_signal_count: int = 0
    context_fusion_runtime_available: bool = False
    agent_multimodal_bridge_available: bool = False
    tool_runtime_available: bool = False
    tool_permission_bridge_available: bool = False
    tool_discovery_runtime_available: bool = False
    tool_intent_runtime_available: bool = False
    pending_tool_intents_count: int = 0
    mcp_runtime_available: bool = False
    mcp_registered_servers: int = 0
    mcp_registered_tools: int = 0
    mcp_bridge_runtime_available: bool = False
    mcp_bridged_tools_count: int = 0
    execution_router_available: bool = False
    execution_targets_registered: int = 0
    agent_tool_calling_runtime_available: bool = False
    executable_tool_intents_count: int = 0
    failed_tool_intents_count: int = 0
    tool_count: int = 0
    tool_approval_pending_count: int = 0
    checks: list[HealthCheckItem] = field(default_factory=list)
    status: str = "ok"
