from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.serialization import load_structured_file
from synapse.health.contracts import HealthSnapshotSource
from synapse.health.models import HomelabHealthSummary
from synapse.readiness.models import ReadinessCheck, ReadinessState, ReadinessSummary

DEFAULT_POLICY: dict[str, Any] = {
    "require_daemon": False,
    "require_scheduler": True,
    "require_capabilities": True,
    "pending_approvals_state": "action_required",
    "failed_jobs_state": "degraded",
    "critical_notifications_state": "action_required",
    "stale_lock_state": "action_required",
    "require_world_state": True,
    "require_policy": True,
    "require_observability": True,
}

STATE_RANK: dict[str, int] = {
    "ready": 0,
    "degraded": 1,
    "action_required": 2,
    "not_ready": 3,
}


class ReadinessRuntime:
    def __init__(self, data_dir: DataDir, health: HealthSnapshotSource):
        self.data_dir = data_dir
        self.health = health

    def evaluate(self) -> ReadinessSummary:
        health = self.health.summary()
        policy = self.load_policy()
        checks = self._checks(health, policy)
        state = self._summary_state(checks)
        return ReadinessSummary(
            state=state,
            checks=checks or [ReadinessCheck("system.ready", "ready", "System is ready.")],
            health_status=health.status,
            policy=policy,
        )

    def explain(self) -> dict[str, Any]:
        summary = self.evaluate()
        return {
            "state": summary.state,
            "health_status": summary.health_status,
            "checks": [asdict(check) for check in summary.checks],
        }

    def blocking_issues(self) -> list[ReadinessCheck]:
        return [
            check
            for check in self.evaluate().checks
            if check.state in {"action_required", "not_ready"}
        ]

    def recommended_actions(self) -> list[str]:
        actions: list[str] = []
        for check in self.evaluate().checks:
            action = self._recommended_action(check)
            if action and action not in actions:
                actions.append(action)
        return actions

    def load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/readiness_policy.yaml"))
        policy_raw = raw.get("readiness", raw)
        policy = dict(DEFAULT_POLICY)
        policy.update(policy_raw)
        return policy

    def _checks(
        self,
        health: HomelabHealthSummary,
        policy: dict[str, Any],
    ) -> list[ReadinessCheck]:
        checks: list[ReadinessCheck] = []
        components = {item.component_id: item for item in health.components}
        for component_id, policy_key in (
            ("world_state", "require_world_state"),
            ("policy", "require_policy"),
            ("observability", "require_observability"),
        ):
            component = components.get(component_id)
            if policy.get(policy_key) and (component is None or not component.ready):
                checks.append(
                    ReadinessCheck(
                        id=f"{component_id}.not_ready",
                        state="not_ready",
                        summary=f"Required component {component_id} is not ready.",
                        metadata=asdict(component) if component else {},
                    )
                )
        if policy.get("require_daemon") and not bool(health.daemon.get("running", False)):
            checks.append(
                ReadinessCheck(
                    id="daemon.stopped",
                    state="degraded",
                    summary="Daemon is required by policy but is not running.",
                    metadata=health.daemon,
                )
            )

        if policy.get("require_scheduler") and health.scheduler_lock.get("stale"):
            checks.append(
                ReadinessCheck(
                    id="scheduler.lock_stale",
                    state=str(policy.get("stale_lock_state", "action_required")),
                    summary="Scheduler lock appears stale.",
                    metadata=health.scheduler_lock,
                )
            )

        if health.failed_jobs > 0:
            checks.append(
                ReadinessCheck(
                    id="jobs.failed",
                    state=str(policy.get("failed_jobs_state", "degraded")),
                    summary=f"{health.failed_jobs} failed job(s) need review.",
                    metadata={"failed_jobs": health.failed_jobs},
                )
            )

        if health.unread_critical_notifications > 0:
            checks.append(
                ReadinessCheck(
                    id="notifications.critical_unread",
                    state=str(policy.get("critical_notifications_state", "action_required")),
                    summary=(
                        f"{health.unread_critical_notifications} unread critical notification(s)."
                    ),
                    metadata={
                        "unread_critical_notifications": health.unread_critical_notifications
                    },
                )
            )

        pending_approval_total = (
            health.approvals_pending
            + health.pending_agent_provisioning_requests
            + health.pending_admin_action_requests
        )
        if pending_approval_total > 0:
            checks.append(
                ReadinessCheck(
                    id="approvals.pending",
                    state=str(policy.get("pending_approvals_state", "action_required")),
                    summary=f"{pending_approval_total} approval-related item(s) pending.",
                    metadata={
                        "approvals_pending": health.approvals_pending,
                        "pending_agent_provisioning_requests": (
                            health.pending_agent_provisioning_requests
                        ),
                        "pending_admin_action_requests": health.pending_admin_action_requests,
                    },
                )
            )

        if not health.migrations.get("available", False):
            checks.append(
                ReadinessCheck(
                    id="migrations.unavailable",
                    state="degraded",
                    summary="Migration runtime is unavailable.",
                    metadata=health.migrations,
                )
            )

        if not health.delegation_inbox.get("available", False):
            checks.append(
                ReadinessCheck(
                    id="delegation_inbox.unavailable",
                    state="degraded",
                    summary="Delegation inbox runtime is unavailable.",
                    metadata=health.delegation_inbox,
                )
            )
        if health.delegation_inbox.get("corrupted_agents"):
            checks.append(
                ReadinessCheck(
                    id="delegation_inbox.corrupted",
                    state="action_required",
                    summary="Delegation inbox corruption detected; rebuild is required.",
                    metadata=health.delegation_inbox,
                )
            )
        if int(health.delegation_inbox.get("rebuild_failures", 0)) > 0:
            checks.append(
                ReadinessCheck(
                    id="delegation_inbox.rebuild_failed",
                    state="action_required",
                    summary="Delegation inbox rebuild failures need review.",
                    metadata=health.delegation_inbox,
                )
            )

        if int(health.delegation_execution.get("failed_recent", 0)) >= 3:
            checks.append(
                ReadinessCheck(
                    id="delegation_execution.failed_recent",
                    state="degraded",
                    summary="Multiple recent delegation executions failed.",
                    metadata=health.delegation_execution,
                )
            )
        if int(health.delegation_timeout.get("timeout_candidates", 0)) >= 3:
            checks.append(
                ReadinessCheck(
                    id="delegation_timeout.candidates",
                    state="degraded",
                    summary="Multiple delegation timeout candidates need review.",
                    metadata=health.delegation_timeout,
                )
            )
        if health.dead_letter_open_count >= 3:
            checks.append(
                ReadinessCheck(
                    id="dead_letter.open",
                    state="degraded",
                    summary="Multiple dead letter entries need review.",
                    metadata={"open_count": health.dead_letter_open_count},
                )
            )
        if health.recovery_candidates_count >= 3:
            checks.append(
                ReadinessCheck(
                    id="recovery.candidates",
                    state="degraded",
                    summary="Multiple delegation recovery candidates need review.",
                    metadata={"candidate_count": health.recovery_candidates_count},
                )
            )
        if health.failed_missions_count >= 3:
            checks.append(
                ReadinessCheck(
                    id="missions.failed",
                    state="degraded",
                    summary="Multiple failed missions need review.",
                    metadata={"failed_missions_count": health.failed_missions_count},
                )
            )
        if health.missions_with_critical_context > 0:
            checks.append(
                ReadinessCheck(
                    id="missions.context_critical",
                    state="degraded",
                    summary="Critical mission context detected.",
                    metadata={
                        "missions_with_critical_context": health.missions_with_critical_context
                    },
                )
            )
        if health.missions_warning_count > 0 or health.missions_critical_count > 0:
            checks.append(
                ReadinessCheck(
                    id="missions.require_attention",
                    state="degraded",
                    summary="Mission supervision found missions requiring attention.",
                    metadata={
                        "missions_warning_count": health.missions_warning_count,
                        "missions_critical_count": health.missions_critical_count,
                    },
                )
            )

        checks.append(
            ReadinessCheck(
                id="providers.ready",
                state=(
                    "ready"
                    if health.provider_runtime_available and health.providers_unavailable_count == 0
                    else "degraded"
                ),
                summary=(
                    "Provider runtime is available."
                    if health.provider_runtime_available
                    else "Provider runtime is unavailable."
                ),
                metadata={
                    "providers_unavailable_count": health.providers_unavailable_count,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="provider_plugins.ready",
                state=(
                    "ready"
                    if health.provider_plugin_runtime_available
                    and health.provider_plugins_unavailable_count == 0
                    else "degraded"
                ),
                summary=(
                    "Provider plugin runtime is available."
                    if health.provider_plugin_runtime_available
                    else "Provider plugin runtime is unavailable."
                ),
                metadata={
                    "provider_plugins_unavailable_count": (
                        health.provider_plugins_unavailable_count
                    ),
                    "provider_plugins_not_installed_count": (
                        health.provider_plugins_not_installed_count
                    ),
                },
            )
        )
        lmstudio_enabled_but_unavailable = any(
            check.id == "lmstudio.unavailable" for check in health.checks
        )
        checks.append(
            ReadinessCheck(
                id="lmstudio.ready",
                state="degraded" if lmstudio_enabled_but_unavailable else "ready",
                summary=(
                    "LM Studio is available or disabled."
                    if not lmstudio_enabled_but_unavailable
                    else "LM Studio is enabled but unavailable."
                ),
                metadata={
                    "lmstudio_available": health.lmstudio_available,
                    "lmstudio_model_count": health.lmstudio_model_count,
                },
            )
        )
        local_chat_enabled_but_unavailable = any(
            check.id == "local_chat.unavailable" for check in health.checks
        )
        checks.append(
            ReadinessCheck(
                id="local_chat.ready",
                state="degraded" if local_chat_enabled_but_unavailable else "ready",
                summary=(
                    "Local chat is available or disabled."
                    if not local_chat_enabled_but_unavailable
                    else "Local chat is enabled but provider is unavailable."
                ),
                metadata={"local_chat_available": health.local_chat_available},
            )
        )
        checks.append(
            ReadinessCheck(
                id="voice.ready",
                state=(
                    "ready"
                    if health.voice_runtime_available
                    and health.voice_provider_unavailable_count == 0
                    else "degraded"
                ),
                summary=(
                    "Voice runtime is available."
                    if health.voice_runtime_available
                    else "Voice runtime is unavailable."
                ),
                metadata={
                    "voice_provider_unavailable_count": health.voice_provider_unavailable_count,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="speech_pipeline.ready",
                state="ready" if health.speech_pipeline_runtime_available else "degraded",
                summary=(
                    "Speech pipeline runtime is available."
                    if health.speech_pipeline_runtime_available
                    else "Speech pipeline runtime is unavailable."
                ),
                metadata={"speech_pipeline_sessions_count": health.speech_pipeline_sessions_count},
            )
        )
        checks.append(
            ReadinessCheck(
                id="speech_adapters.ready",
                state=("ready" if health.speech_adapter_runtime_available else "degraded"),
                summary=(
                    "Speech adapter runtime is available; optional provider health is reported separately."
                    if health.speech_adapter_runtime_available
                    else "Speech adapter runtime is unavailable."
                ),
                metadata={
                    "speech_adapters_unavailable_count": (health.speech_adapters_unavailable_count),
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="multimodal.ready",
                state="ready" if health.multimodal_runtime_available else "degraded",
                summary=(
                    "Multimodal communication runtime is available."
                    if health.multimodal_runtime_available
                    else "Multimodal communication runtime is unavailable."
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                id="audio.ready",
                state=(
                    "ready"
                    if health.audio_runtime_available
                    and health.audio_provider_unavailable_count == 0
                    else "degraded"
                ),
                summary=(
                    "Audio runtime is available."
                    if health.audio_runtime_available
                    else "Audio runtime is unavailable."
                ),
                metadata={
                    "audio_provider_unavailable_count": health.audio_provider_unavailable_count,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="vision.ready",
                state=(
                    "ready"
                    if health.vision_runtime_available
                    and health.vision_provider_unavailable_count == 0
                    else "degraded"
                ),
                summary=(
                    "Vision runtime is available."
                    if health.vision_runtime_available
                    else "Vision runtime is unavailable."
                ),
                metadata={
                    "vision_provider_unavailable_count": health.vision_provider_unavailable_count,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="perception.ready",
                state="ready" if health.perception_runtime_available else "degraded",
                summary=(
                    "Perception runtime is available."
                    if health.perception_runtime_available
                    else "Perception runtime is unavailable."
                ),
                metadata={"perception_signal_count": health.perception_signal_count},
            )
        )
        checks.append(
            ReadinessCheck(
                id="context_fusion.ready",
                state="ready" if health.context_fusion_runtime_available else "degraded",
                summary=(
                    "Context fusion runtime is available."
                    if health.context_fusion_runtime_available
                    else "Context fusion runtime is unavailable."
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                id="agent_multimodal_bridge.ready",
                state="ready" if health.agent_multimodal_bridge_available else "degraded",
                summary=(
                    "Agent multimodal context bridge is available."
                    if health.agent_multimodal_bridge_available
                    else "Agent multimodal context bridge is unavailable."
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                id="tool_runtime.ready",
                state=(
                    "ready"
                    if health.tool_runtime_available and health.tool_count > 0
                    else "degraded"
                ),
                summary=(
                    "Tool Runtime is available."
                    if health.tool_runtime_available
                    else "Tool Runtime is unavailable."
                ),
                metadata={"tool_count": health.tool_count},
            )
        )
        checks.append(
            ReadinessCheck(
                id="tool_permissions.ready",
                state="ready" if health.tool_permission_bridge_available else "degraded",
                summary=(
                    "Tool permission bridge is available."
                    if health.tool_permission_bridge_available
                    else "Tool permission bridge is unavailable."
                ),
                metadata={"tool_approval_pending_count": health.tool_approval_pending_count},
            )
        )
        checks.append(
            ReadinessCheck(
                id="tool_discovery.ready",
                state="ready" if health.tool_discovery_runtime_available else "degraded",
                summary=(
                    "Tool discovery runtime is available."
                    if health.tool_discovery_runtime_available
                    else "Tool discovery runtime is unavailable."
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                id="tool_intents.ready",
                state="ready" if health.tool_intent_runtime_available else "degraded",
                summary=(
                    "Tool intent runtime is available."
                    if health.tool_intent_runtime_available
                    else "Tool intent runtime is unavailable."
                ),
                metadata={"pending_tool_intents_count": health.pending_tool_intents_count},
            )
        )
        checks.append(
            ReadinessCheck(
                id="mcp.ready",
                state="ready" if health.mcp_runtime_available else "degraded",
                summary=(
                    "MCP runtime foundation is available."
                    if health.mcp_runtime_available
                    else "MCP runtime foundation is unavailable."
                ),
                metadata={
                    "registered_servers": health.mcp_registered_servers,
                    "registered_tools": health.mcp_registered_tools,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="mcp_bridge.ready",
                state="ready" if health.mcp_bridge_runtime_available else "degraded",
                summary=(
                    "MCP tool bridge is available."
                    if health.mcp_bridge_runtime_available
                    else "MCP tool bridge is unavailable."
                ),
                metadata={"bridged_tools": health.mcp_bridged_tools_count},
            )
        )
        checks.append(
            ReadinessCheck(
                id="execution_router.ready",
                state="ready" if health.execution_router_available else "degraded",
                summary=(
                    "Execution router is available."
                    if health.execution_router_available
                    else "Execution router is unavailable."
                ),
                metadata={"registered_targets": health.execution_targets_registered},
            )
        )
        checks.append(
            ReadinessCheck(
                id="agent_tool_calling.ready",
                state=("ready" if health.agent_tool_calling_runtime_available else "degraded"),
                summary=(
                    "Agent tool calling bridge is available."
                    if health.agent_tool_calling_runtime_available
                    else "Agent tool calling bridge is unavailable."
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                id="tool_intent_execution.ready",
                state=(
                    "ready"
                    if health.tool_intent_runtime_available
                    and health.execution_router_available
                    and health.tool_runtime_available
                    else "degraded"
                ),
                summary=(
                    "Manual tool intent execution flow is available."
                    if health.tool_intent_runtime_available
                    and health.execution_router_available
                    and health.tool_runtime_available
                    else "Manual tool intent execution flow is unavailable."
                ),
                metadata={
                    "executable_intents": health.executable_tool_intents_count,
                    "failed_intents": health.failed_tool_intents_count,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="model_hub.ready",
                state="ready" if health.model_hub_available else "degraded",
                summary=(
                    "Model Hub runtime is available."
                    if health.model_hub_available
                    else "Model Hub runtime is unavailable."
                ),
                metadata={
                    "catalog_size": health.model_catalog_size,
                    "provider_count": health.model_provider_count,
                },
            )
        )
        checks.append(
            ReadinessCheck(
                id="provider_settings.ready",
                state="ready" if health.provider_settings_available else "degraded",
                summary=(
                    "Provider settings runtime is available."
                    if health.provider_settings_available
                    else "Provider settings runtime is unavailable."
                ),
                metadata={
                    "configured_external_provider_count": (
                        health.configured_external_provider_count
                    )
                },
            )
        )
        if policy.get("require_capabilities") and health.capability_count == 0:
            checks.append(
                ReadinessCheck(
                    id="capabilities.empty",
                    state="not_ready",
                    summary="No capabilities are registered.",
                )
            )

        error_agents = [item for item in health.agents_attention if item.get("state") == "error"]
        if error_agents:
            checks.append(
                ReadinessCheck(
                    id="agents.error",
                    state="degraded",
                    summary=f"{len(error_agents)} agent(s) are in error state.",
                    metadata={"agents": error_agents},
                )
            )
        return checks

    @staticmethod
    def _summary_state(checks: list[ReadinessCheck]) -> ReadinessState:
        state = "ready"
        for check in checks:
            if STATE_RANK.get(check.state, 0) > STATE_RANK[state]:
                state = check.state
        return state

    @staticmethod
    def _recommended_action(check: ReadinessCheck) -> str | None:
        if check.id == "daemon.stopped":
            return "Run /daemon-run-once for a manual cycle or start the daemon in a future service mode."
        if check.id == "scheduler.lock_stale":
            return "Inspect /scheduler-lock and recover the stale local scheduler lock."
        if check.id == "jobs.failed":
            return "Inspect /jobs failed and retry or cancel failed jobs."
        if check.id == "notifications.critical_unread":
            return "Review critical notifications and mark handled when appropriate."
        if check.id == "approvals.pending":
            return "Review pending approvals, provisioning requests, and admin action requests."
        if check.id == "migrations.unavailable":
            return "Check migration runtime bootstrap and DATA_DIR/migrations status."
        if check.id in {"delegation_inbox.unavailable", "delegation_inbox.corrupted"}:
            return "Run /rebuild-all-delegation-inboxes and inspect delegation inbox status."
        if check.id == "delegation_inbox.rebuild_failed":
            return "Inspect recent delegation_inbox.rebuild_failed events and retry rebuild."
        if check.id == "delegation_execution.failed_recent":
            return "Inspect failed delegation executions before increasing automation."
        if check.id == "delegation_timeout.candidates":
            return "Run /delegation-timeout-scan and review timeout candidates."
        if check.id == "dead_letter.open":
            return "Review /dead-letter and restore or close entries."
        if check.id == "recovery.candidates":
            return "Run /recovery-summary and inspect recommended recovery actions."
        if check.id == "missions.failed":
            return "Review failed missions and archive or resolve their linked delegations."
        if check.id == "missions.context_critical":
            return "Run /mission-context for critical missions and review DLQ/recovery items."
        if check.id == "missions.require_attention":
            return "Run /mission-attention and review mission supervision recommendations."
        if check.id == "providers.ready":
            return "Run /provider-health and review unavailable providers or provider policy."
        if check.id == "provider_plugins.ready":
            return "Run /provider-plugin-health and review provider plugin policy or platform compatibility."
        if check.id == "lmstudio.ready":
            return "Start LM Studio locally or disable config/lmstudio_provider.yaml."
        if check.id == "local_chat.ready":
            return "Review config/local_chat_policy.yaml and LM Studio provider status."
        if check.id == "voice.ready":
            return "Inspect /voice-sessions and provider health before adding real TTS providers."
        if check.id == "speech_pipeline.ready":
            return "Check speech pipeline bootstrap before adding real STT/TTS providers."
        if check.id == "speech_adapters.ready":
            return "Inspect /speech-adapter-health before enabling real speech adapters."
        if check.id == "multimodal.ready":
            return (
                "Check multimodal runtime bootstrap before adding voice or vision stages."
            )
        if check.id == "audio.ready":
            return "Run /audio-devices and /provider-health before adding real audio providers."
        if check.id == "vision.ready":
            return "Run /vision-cameras and /provider-health before adding real vision providers."
        if check.id == "perception.ready":
            return "Check perception runtime bootstrap before adding context fusion."
        if check.id == "context_fusion.ready":
            return (
                "Check context fusion runtime bootstrap before injecting fused context into agents."
            )
        if check.id == "agent_multimodal_bridge.ready":
            return "Check worker/context fusion bootstrap before injecting multimodal context into agents."
        if check.id == "tool_runtime.ready":
            return "Check Tool Runtime bootstrap and registered seed tools."
        if check.id == "tool_permissions.ready":
            return "Check Tool Permission Bridge bootstrap before enabling agent tool use."
        if check.id == "tool_discovery.ready":
            return "Check Tool Discovery Runtime bootstrap before exposing tools to agents."
        if check.id == "tool_intents.ready":
            return "Check Tool Intent Runtime bootstrap before accepting proposed tool use."
        if check.id == "mcp.ready":
            return "Check MCP Runtime bootstrap and local manifest registry."
        if check.id == "mcp_bridge.ready":
            return "Check MCP Tool Bridge bootstrap and synchronize the MCP registry."
        if check.id == "execution_router.ready":
            return "Check Execution Router bootstrap and registered target runtimes."
        if check.id == "agent_tool_calling.ready":
            return "Check Agent Tool Calling Bridge bootstrap and safe policy configuration."
        if check.id == "tool_intent_execution.ready":
            return "Check Tool Intent, Execution Router, and Tool Runtime availability."
        if check.id == "capabilities.empty":
            return "Bootstrap or repair the capability registry before operating agents."
        if check.id == "agents.error":
            return "Inspect agent presence/lifecycle and resolve error states."
        return None
