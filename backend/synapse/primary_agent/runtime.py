from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any

from synapse.agents.models import AgentKind
from synapse.core.permissions import PermissionContext
from synapse.health.contracts import HealthContribution
from synapse.health.contributors.base import check, checks, component
from synapse.primary_agent.errors import (
    PrimaryAgentConflict,
    PrimaryAgentMisconfigured,
    PrimaryAgentRequired,
)
from synapse.primary_agent.models import (
    PrimaryAgentProfile,
    PrimaryAgentState,
    PrimaryInteractionBootstrap,
    PrimaryInteractionResult,
    now_iso,
)
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound, StorageRevisionConflict


class PrimaryAgentRuntime:
    """Owns the workspace-to-primary binding, never agent execution itself."""

    skill_context: Any | None = None
    project_context: Any | None = None

    def __init__(
        self,
        data_dir: Any,
        events: Any,
        agents: Any,
        conversations: Any,
        *,
        attention: Any | None = None,
        approvals: Any | None = None,
        missions: Any | None = None,
        notifications: Any | None = None,
        health: Any | None = None,
        agent_loop: Any | None = None,
        voice: Any | None = None,
    ) -> None:
        self.events = events
        self.agents = agents
        self.conversations = conversations
        self.attention = attention
        self.approvals = approvals
        self.missions = missions
        self.notifications = notifications
        self.health = health
        self.agent_loop = agent_loop
        self.voice = voice
        self.collection = FileCollection(
            collection_id="primary_agent_profiles",
            root=data_dir.resolve("primary_agents"),
            current_schema_version=1,
            validator=_validate_profile,
            revision=lambda payload: int(payload.get("revision", 1)),
            recovery_policy="fail_closed",
            events=events,
        )

    def get_state(self, workspace_id: str = "default") -> PrimaryAgentState:
        try:
            profile = self._get_profile(workspace_id)
        except StorageRecordNotFound:
            agents = self.agents.list_agents()
            state = "primary_agent_required" if not agents else "primary_selection_required"
            return PrimaryAgentState(state, None)
        try:
            agent = self.agents.get(profile.agent_id)
            conversation = self.conversations.get_conversation(profile.conversation_id)
            if agent.kind is not AgentKind.PERSISTENT:
                raise PrimaryAgentMisconfigured("Primary profile must reference a persistent agent")
            if profile.status not in {"active", "paused"} or conversation.status == "archived":
                raise PrimaryAgentMisconfigured("Primary profile is not operational")
        except Exception as exc:
            return PrimaryAgentState("misconfigured", profile, str(exc))
        return PrimaryAgentState("configured", profile)

    def get_primary(self, workspace_id: str = "default") -> PrimaryAgentProfile:
        state = self.get_state(workspace_id)
        if state.profile is None:
            raise PrimaryAgentRequired(state.state)
        if state.state != "configured":
            raise PrimaryAgentMisconfigured(state.reason or state.state)
        return state.profile

    def set_primary(
        self,
        context: PermissionContext,
        agent_id: str,
        workspace_id: str = "default",
        *,
        replace_existing: bool = False,
    ) -> PrimaryAgentProfile:
        agent = self.agents.get(agent_id)
        if agent.kind is not AgentKind.PERSISTENT:
            raise PrimaryAgentMisconfigured("Primary agent must reference a persistent agent")
        existing = None
        try:
            existing = self._get_profile(workspace_id)
        except StorageRecordNotFound:
            pass
        if existing and existing.agent_id != agent_id and not replace_existing:
            raise PrimaryAgentConflict("Workspace already has a primary agent")
        if existing and existing.agent_id == agent_id:
            return existing
        conversation = self.conversations.create_conversation(
            context,
            [agent_id],
            title=f"Primary conversation — {agent.name}",
            metadata={"purpose": "primary_interaction", "workspace_id": workspace_id},
        )
        profile = PrimaryAgentProfile(
            agent_id=agent_id,
            workspace_id=workspace_id,
            status="active",
            assigned_at=now_iso(),
            conversation_id=conversation.conversation_id,
            last_active_at=now_iso(),
            revision=1 if existing is None else existing.revision + 1,
            metadata={"assignment": "explicit"},
        )
        try:
            self.collection.put(
                workspace_id,
                asdict(profile),
                expected_revision=existing.revision if existing else None,
                create_only=existing is None,
            )
        except StorageRevisionConflict as exc:
            raise PrimaryAgentConflict("Primary assignment changed concurrently") from exc
        event = "primary_agent.replaced" if existing else "primary_agent.assigned"
        self.events.emit(
            event,
            context.actor_id,
            {"workspace_id": workspace_id, "agent_id": agent_id, "revision": profile.revision},
        )
        return profile

    def replace_primary(
        self, context: PermissionContext, agent_id: str, workspace_id: str = "default"
    ) -> PrimaryAgentProfile:
        return self.set_primary(context, agent_id, workspace_id, replace_existing=True)

    def resume_interaction(
        self, context: PermissionContext, workspace_id: str = "default"
    ) -> PrimaryInteractionResult:
        profile = self.get_primary(workspace_id)
        conversation = self.conversations.get_conversation(profile.conversation_id)
        changed = profile.status != "active" or conversation.status == "paused"
        if conversation.status == "paused":
            conversation = self.conversations.resume_conversation(context, profile.conversation_id)
        if changed:
            profile = replace(
                profile,
                status="active",
                last_active_at=now_iso(),
                revision=profile.revision + 1,
            )
            self.collection.put(
                workspace_id, asdict(profile), expected_revision=profile.revision - 1
            )
            self.events.emit(
                "primary_interaction.resumed",
                context.actor_id,
                {"workspace_id": workspace_id, "agent_id": profile.agent_id},
            )
        return PrimaryInteractionResult(profile, conversation.status, changed)

    def pause_interaction(
        self, context: PermissionContext, workspace_id: str = "default"
    ) -> PrimaryInteractionResult:
        profile = self.get_primary(workspace_id)
        conversation = self.conversations.get_conversation(profile.conversation_id)
        changed = profile.status != "paused" or conversation.status == "active"
        if conversation.status == "active":
            conversation = self.conversations.pause_conversation(context, profile.conversation_id)
        if changed:
            profile = replace(profile, status="paused", revision=profile.revision + 1)
            self.collection.put(
                workspace_id, asdict(profile), expected_revision=profile.revision - 1
            )
            self.events.emit(
                "primary_interaction.paused",
                context.actor_id,
                {"workspace_id": workspace_id, "agent_id": profile.agent_id},
            )
        return PrimaryInteractionResult(profile, conversation.status, changed)

    def get_primary_interaction_bootstrap(
        self, workspace_id: str = "default", project_id: str | None = None
    ) -> PrimaryInteractionBootstrap:
        state = self.get_state(workspace_id)
        if state.profile is None or state.state != "configured":
            return PrimaryInteractionBootstrap(
                primary_agent=None,
                conversation=None,
                agent_status=state.state,
                interaction_status="not_configured",
                voice_status="not_started",
                proactive_mode="policy_governed",
                pending_attention_count=0,
                pending_approvals_count=0,
                active_missions=[],
                unread_notifications=0,
                health_summary={},
                capabilities=[],
                resume_token=None,
                warnings=[state.reason] if state.reason else [],
            )
        profile = state.profile
        agent = self.agents.get(profile.agent_id)
        conversation = self.conversations.get_conversation(profile.conversation_id)
        attention = self.attention.list_items("pending") if self.attention else []
        approvals = self.approvals.list_pending() if self.approvals else []
        missions = self.missions.list_missions() if self.missions else []
        active = [item for item in missions if item.status in {"planned", "running", "paused"}]
        unread = self.notifications.list_unread() if self.notifications else []
        loop_status = asdict(self.agent_loop.status()) if self.agent_loop else {}
        skill_context = self.skill_context
        project_context = self.project_context
        return PrimaryInteractionBootstrap(
            primary_agent={
                "agent_id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "kind": AgentKind.PRIMARY.value,
            },
            conversation=asdict(conversation),
            agent_status="ready",
            interaction_status=profile.status,
            voice_status="not_started",
            proactive_mode=profile.proactive_mode,
            pending_attention_count=len(attention),
            pending_approvals_count=len(approvals),
            active_missions=[
                {"mission_id": item.mission_id, "status": item.status} for item in active
            ],
            unread_notifications=len(unread),
            health_summary={"agent_loop": loop_status.get("status", loop_status.get("mode"))},
            capabilities=list(agent.skills),
            resume_token=f"{workspace_id}:{profile.revision}:{conversation.revision}",
            assigned_skills=(
                list(skill_context.assignment_summaries(profile.agent_id)) if skill_context else []
            ),
            available_skills=(
                [asdict(item) for item in skill_context.list(status="active")[:10]]
                if skill_context
                else []
            ),
            project_context=(
                asdict(project_context.read_project_context(project_id, budget=2000))
                if project_id and project_context
                else None
            ),
            warnings=[],
        )

    def health_snapshot(self, workspace_id: str = "default") -> dict[str, Any]:
        state = self.get_state(workspace_id)
        return {
            "state": state.state,
            "configured": state.profile is not None,
            "ready": state.state == "configured",
            "conversation_available": state.state == "configured",
            "agent_id": state.profile.agent_id if state.profile else None,
        }

    def collect_health(self, context: Any) -> HealthContribution:
        snapshot = self.health_snapshot()
        return HealthContribution(
            components=(component(0, "primary_agent", self, []),),
            summary={"primary_agent": snapshot},
            checks=checks(
                check(
                    0,
                    "primary_agent.configured",
                    not snapshot["configured"],
                    "info",
                    "Primary agent is not configured.",
                    snapshot,
                ),
                check(
                    1,
                    "primary_agent.misconfigured",
                    snapshot["configured"] and not snapshot["ready"],
                    "warning",
                    "Primary agent configuration is invalid.",
                    snapshot,
                ),
            ),
        )

    def _get_profile(self, workspace_id: str) -> PrimaryAgentProfile:
        return PrimaryAgentProfile(**self.collection.get(workspace_id).payload)


def _validate_profile(payload: Mapping[str, Any]) -> None:
    required = {"agent_id", "workspace_id", "status", "conversation_id", "revision"}
    if not required <= payload.keys():
        raise ValueError("primary agent profile is incomplete")
    if payload["status"] not in {"active", "paused"}:
        raise ValueError("primary agent profile status is invalid")
