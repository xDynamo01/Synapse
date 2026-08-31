from datetime import UTC, datetime, timedelta
from pathlib import Path

from synapse.ephemeral_agents.models import EphemeralAgentSpec, EphemeralAgentState

from .agent_kinds_support import provision, runtime_at


def test_ephemeral_agent_restart_cleanup_e2e(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    runtime = runtime_at(data_dir, clean=True)
    provision(runtime, "central")
    instance = runtime.ephemeral_agents.create_instance(
        EphemeralAgentSpec(
            mission_id="mission-restart",
            parent_agent_id="central",
            role="temporary",
            objective="Recover safely",
            autonomy_ceiling="manual",
            risk_ceiling="low",
            created_by="mission",
            correlation_id="restart-trace",
            lease_duration=1,
        ),
        authority="mission",
    )
    restarted = runtime_at(data_dir)
    reconciled = restarted.ephemeral_agents.reconcile(
        datetime.now(UTC) + timedelta(minutes=1)
    )
    assert reconciled[0].state is EphemeralAgentState.DESTROYED
    assert restarted.ephemeral_agents.reconcile() == []
    assert restarted.ephemeral_agents.contexts.list_all() == ()
    assert not (data_dir / "agents" / instance.ephemeral_agent_id).exists()
