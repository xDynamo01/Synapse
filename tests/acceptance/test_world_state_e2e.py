from __future__ import annotations

from datetime import UTC, datetime, timedelta

from synapse.world_state.models import WorldStateUpdate
from synapse.world_state.runtime import WorldStateRuntime

from .world_attention_support import DomainFixture


def test_world_state_update_ttl_restart_and_provenance() -> None:
    fixture = DomainFixture()
    try:
        now = datetime.now(UTC)
        update = WorldStateUpdate(
            id="observation-1", source="perception", entity_type="environment_state",
            entity_id="screen_summary", operation="set", values={"summary": "Editor visible"},
            timestamp=now.isoformat(), expires_at=(now + timedelta(seconds=1)).isoformat(),
            provenance={"observation_id": "p-1"}, sensitivity="sensitive",
        )
        assert fixture.world_state.apply_state_update(update).revision == 1
        assert fixture.world_state.apply_state_update(update).revision == 1
        restarted = WorldStateRuntime(fixture.data_dir, fixture.events)
        assert restarted.get_entity("environment_state", "screen_summary")["summary"] == "Editor visible"
        assert restarted.history()[0].provenance == {"observation_id": "p-1"}
        expired = restarted.expire_state(now + timedelta(seconds=2))
        assert "screen_summary" not in expired.environment_state
        assert expired.revision == 2
    finally:
        fixture.close()
