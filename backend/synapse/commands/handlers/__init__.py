from __future__ import annotations

from synapse.commands.services import CommandServices


def build_command_handlers(services: CommandServices):
    # Imports are explicit and local so module loading does not become discovery.
    from synapse.commands.handlers.agent_kinds import AgentKindsCommandHandler
    from synapse.commands.handlers.agents_admin import AgentsAdminCommandHandler
    from synapse.commands.handlers.conversations import ConversationsCommandHandler
    from synapse.commands.handlers.core_operations import CoreOperationsCommandHandler
    from synapse.commands.handlers.delegation import DelegationCommandHandler
    from synapse.commands.handlers.intelligence_boundary import (
        IntelligenceBoundaryCommandHandler,
    )
    from synapse.commands.handlers.maintenance import MaintenanceCommandHandler
    from synapse.commands.handlers.missions_swarm import MissionsSwarmCommandHandler
    from synapse.commands.handlers.models_providers import ModelsProvidersCommandHandler
    from synapse.commands.handlers.perception_vision import PerceptionVisionCommandHandler
    from synapse.commands.handlers.platform_governance import PlatformGovernanceCommandHandler
    from synapse.commands.handlers.project_governance import ProjectGovernanceCommandHandler
    from synapse.commands.handlers.recovery_dead_letter import RecoveryDeadLetterCommandHandler
    from synapse.commands.handlers.skills import SkillsCommandHandler
    from synapse.commands.handlers.system import SystemCommandHandler
    from synapse.commands.handlers.tools_execution import ToolsExecutionCommandHandler
    from synapse.commands.handlers.voice_multimodal import VoiceMultimodalCommandHandler
    from synapse.commands.handlers.workers_recovery import WorkersRecoveryCommandHandler
    from synapse.commands.handlers.world_state import WorldStateCommandHandler

    handlers = (
        SystemCommandHandler(services),
        SkillsCommandHandler(services),
        ProjectGovernanceCommandHandler(services),
        IntelligenceBoundaryCommandHandler(services),
        ToolsExecutionCommandHandler(services),
        AgentsAdminCommandHandler(services),
        AgentKindsCommandHandler(services),
        ConversationsCommandHandler(services),
        RecoveryDeadLetterCommandHandler(services),
        MissionsSwarmCommandHandler(services),
        WorkersRecoveryCommandHandler(services),
        DelegationCommandHandler(services),
        MaintenanceCommandHandler(services),
        PlatformGovernanceCommandHandler(services),
        ModelsProvidersCommandHandler(services),
        VoiceMultimodalCommandHandler(services),
        PerceptionVisionCommandHandler(services),
        CoreOperationsCommandHandler(services),
        WorldStateCommandHandler(services),
    )
    services.bind_handlers(handlers)
    return handlers
