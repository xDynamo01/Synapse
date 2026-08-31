from pathlib import Path

from .agent_kinds_support import provision, runtime_at


def test_primary_agent_restart_e2e(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir, clean=True)
    provision(runtime, "central")
    profile = runtime.primary_agent.set_primary(runtime.context(), "central")
    restarted = runtime_at(data_dir)
    bootstrap = restarted.primary_agent.get_primary_interaction_bootstrap()
    assert bootstrap.conversation["conversation_id"] == profile.conversation_id
    assert restarted.conversations.list_conversation_messages(profile.conversation_id) == []
    assert restarted.voice.list_sessions() == []
