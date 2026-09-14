"""Single registration point for HTTP bounded-context routers."""

from fastapi import APIRouter

from synapse.api.routers import (
    agent_kinds_router,
    agents_router,
    automation_router,
    conversations_router,
    desktop_automation_router,
    desktop_commands_router,
    frontend_boundary_router,
    intelligence_boundary_router,
    maintenance_router,
    memory_router,
    missions_router,
    models_router,
    operational_projection_router,
    perception_router,
    platform_router,
    project_governance_router,
    project_knowledge_router,
    skills_router,
    system_router,
    tools_router,
    voice_router,
    world_attention_loop_router,
)
from synapse.api.routers.mom import router as mom_router

DOMAIN_ROUTERS = (
    mom_router,
    system_router,
    skills_router,
    project_governance_router,
    operational_projection_router,
    intelligence_boundary_router,
    world_attention_loop_router,
    desktop_automation_router,
    desktop_commands_router,
    frontend_boundary_router,
    agents_router,
    agent_kinds_router,
    conversations_router,
    memory_router,
    models_router,
    project_knowledge_router,
    tools_router,
    missions_router,
    voice_router,
    perception_router,
    automation_router,
    platform_router,
    maintenance_router,
)

router = APIRouter()
for domain_router in DOMAIN_ROUTERS:
    # FastAPI's deferred nested-router object is not recursively expanded when
    # this compatibility aggregate is included by another router/application.
    # The domain routers already own their paths, response metadata and tags;
    # registering their route objects here preserves that exact contract.
    router.routes.extend(domain_router.routes)

__all__ = ["DOMAIN_ROUTERS", "router"]
