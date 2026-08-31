from .support import context_graph, cyclic_components

LEGACY_CYCLIC_COMPONENTS = (
    (
        frozenset(
            {
                "agent_tool_calling", "agents", "approvals", "avatar", "chat",
                "commands", "context", "context_fusion", "conversations", "daemon",
                "dead_letter", "decisions", "delegation", "delegation_execution",
                "delegation_inbox", "delegation_recovery", "embodiment",
                "execution_router", "health", "mcp_bridge", "mission_control",
                "missions", "model_hub", "model_providers", "models", "policies",
                "readiness", "scheduler", "speech_pipeline", "tool_discovery",
                "tool_intents", "tools", "voice", "workers",
            }
        ),
        157,
    ),
    (frozenset({"audio", "multimodal", "perception", "speech_adapters"}), 6),
    (frozenset({"attention", "world_state"}), 2),
)


def test_no_new_bounded_context_cycle_is_introduced() -> None:
    current = cyclic_components(context_graph())
    violations = []
    for members, edge_count in current:
        baselines = [item for item in LEGACY_CYCLIC_COMPONENTS if members <= item[0]]
        if not baselines or edge_count > baselines[0][1]:
            violations.append((sorted(members), edge_count))
    assert not violations, (
        "New bounded-context cycle detected; origin/destination edges must remain within "
        f"the explicit Phase 1 baseline: {violations}"
    )
