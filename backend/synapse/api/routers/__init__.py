from synapse.api.routers.agent_kinds import router as agent_kinds_router
from synapse.api.routers.agents import router as agents_router
from synapse.api.routers.automation import router as automation_router
from synapse.api.routers.conversations import router as conversations_router
from synapse.api.routers.desktop_automation import router as desktop_automation_router
from synapse.api.routers.desktop_commands import router as desktop_commands_router
from synapse.api.routers.frontend_boundary import router as frontend_boundary_router
from synapse.api.routers.intelligence_boundary import router as intelligence_boundary_router
from synapse.api.routers.maintenance import router as maintenance_router
from synapse.api.routers.memory import router as memory_router
from synapse.api.routers.missions import router as missions_router
from synapse.api.routers.models import router as models_router
from synapse.api.routers.operational_projection import router as operational_projection_router
from synapse.api.routers.perception import router as perception_router
from synapse.api.routers.platform import router as platform_router
from synapse.api.routers.project_governance import router as project_governance_router
from synapse.api.routers.skills import router as skills_router
from synapse.api.routers.system import router as system_router
from synapse.api.routers.tools import router as tools_router
from synapse.api.routers.voice import router as voice_router
from synapse.api.routers.world_attention_loop import router as world_attention_loop_router

__all__ = [
    "system_router",
    "skills_router",
    "world_attention_loop_router",
    "desktop_automation_router",
    "desktop_commands_router",
    "frontend_boundary_router",
    "agents_router",
    "agent_kinds_router",
    "maintenance_router",
    "conversations_router",
    "memory_router",
    "models_router",
    "operational_projection_router",
    "tools_router",
    "missions_router",
    "voice_router",
    "perception_router",
    "automation_router",
    "platform_router",
    "project_governance_router",
    "intelligence_boundary_router",
]
