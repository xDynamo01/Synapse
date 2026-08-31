from pathlib import Path

from .agent_kinds_support import provision, runtime_at


def test_primary_agent_initial_setup_e2e(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    assert runtime.primary_agent.get_state().state == "primary_agent_required"
    provision(runtime, "central")
    profile = runtime.primary_agent.set_primary(runtime.context(), "central")
    bootstrap = runtime.primary_agent.get_primary_interaction_bootstrap()
    assert bootstrap.primary_agent["kind"] == "primary"
    assert bootstrap.conversation["conversation_id"] == profile.conversation_id
    assert bootstrap.voice_status == "not_started"
