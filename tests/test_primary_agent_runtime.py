from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from synapse.agents.models import AgentKind
from synapse.agents.provisioning import AgentCreateRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def runtime_at(data_dir: Path):
    fresh = not data_dir.exists()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    create_runtime(settings)
    if fresh:
        shutil.rmtree(data_dir / "agents", ignore_errors=True)
    dump_structured_file(
        data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    return create_runtime(settings)


def provision(runtime, agent_id: str, name: str | None = None):
    return runtime.provisioning.create_agent(
        AgentCreateRequest(
            agent_id=agent_id,
            display_name=name or agent_id.title(),
            role="project_agent",
            preferred_tools=["health.summary"],
        ),
        context=runtime.context(),
    )


def test_primary_initial_setup_bootstrap_pause_resume_and_restart() -> None:
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "data"
        runtime = runtime_at(data_dir)
        shutil.rmtree(data_dir / "agents", ignore_errors=True)
        (data_dir / "agents").mkdir(parents=True)
        assert runtime.primary_agent.get_state().state == "primary_agent_required"

        provision(runtime, "central")
        assert runtime.agents.get("central").kind is AgentKind.PERSISTENT
        assert runtime.primary_agent.get_state().state == "primary_selection_required"

        profile = runtime.primary_agent.set_primary(runtime.context(), "central")
        bootstrap = runtime.primary_agent.get_primary_interaction_bootstrap()

        assert bootstrap.primary_agent == {
            "agent_id": "central",
            "name": "Central",
            "role": "project_agent",
            "kind": "primary",
        }
        assert bootstrap.conversation["conversation_id"] == profile.conversation_id
        assert bootstrap.voice_status == "not_started"
        assert runtime.conversations.list_conversation_messages(profile.conversation_id) == []
        assert runtime.voice.list_sessions() == []

        paused = runtime.primary_agent.pause_interaction(runtime.context())
        assert paused.profile.status == "paused"
        resumed = runtime.primary_agent.resume_interaction(runtime.context())
        assert resumed.profile.status == "active"

        restarted = runtime_at(data_dir)
        recovered = restarted.primary_agent.get_primary_interaction_bootstrap()
        assert recovered.conversation["conversation_id"] == profile.conversation_id
        assert restarted.conversations.list_conversation_messages(profile.conversation_id) == []
        assert restarted.voice.list_sessions() == []


def test_primary_is_unique_replaceable_and_protected_from_admin_removal() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = runtime_at(Path(directory) / "data")
        provision(runtime, "central")
        provision(runtime, "project")
        first = runtime.primary_agent.set_primary(runtime.context(), "central")

        with pytest.raises(ValidationError):
            runtime.primary_agent.set_primary(runtime.context(), "project")
        with pytest.raises(ValidationError):
            runtime.admin.deactivate_agent("central", runtime.context())
        with pytest.raises(ValidationError):
            runtime.admin.archive_agent("central", runtime.context())

        replacement = runtime.primary_agent.replace_primary(runtime.context(), "project")
        assert replacement.agent_id == "project"
        assert replacement.revision == first.revision + 1
        assert runtime.primary_agent.get_primary().agent_id == "project"


def test_primary_missing_or_corrupt_reference_is_not_silently_replaced() -> None:
    with tempfile.TemporaryDirectory() as directory:
        data_dir = Path(directory) / "data"
        runtime = runtime_at(data_dir)
        provision(runtime, "central")
        runtime.primary_agent.set_primary(runtime.context(), "central")
        (data_dir / "agents" / "central" / "CONFIG.yaml").unlink()

        state = runtime.primary_agent.get_state()
        assert state.state == "misconfigured"
        assert state.profile.agent_id == "central"
        assert runtime.primary_agent.get_primary_interaction_bootstrap().primary_agent is None
