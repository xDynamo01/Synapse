from pathlib import Path

import pytest

from synapse.ephemeral_agents.errors import EphemeralAgentError
from synapse.ephemeral_agents.models import EphemeralAgentSpec

from .agent_kinds_support import provision, runtime_at


def test_ephemeral_agent_policy_e2e(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    provision(runtime, "central", tools=["read"])
    bounded = EphemeralAgentSpec(
        mission_id="mission-policy",
        parent_agent_id="central",
        role="bounded",
        objective="Use only inherited tools",
        allowed_tools=["read", "delete"],
        denied_tools=["delete"],
        autonomy_ceiling="manual",
        risk_ceiling="low",
        created_by="mission",
        correlation_id="policy-trace",
    )
    instance = runtime.ephemeral_agents.create_instance(bounded, authority="mission")
    assert instance.tool_scope == ["read"]
    elevated = EphemeralAgentSpec(
        **{**bounded.__dict__, "spec_id": "elevated", "autonomy_ceiling": "autonomous"}
    )
    with pytest.raises(EphemeralAgentError):
        runtime.ephemeral_agents.create_instance(elevated, authority="mission")
