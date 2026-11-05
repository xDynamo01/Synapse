from synapse.core.exceptions import ValidationError
from synapse.core.execution_policy import ResourcePolicy
from synapse.missions.models import SwarmDescriptor
from synapse.missions.runtime import MissionRuntime
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter
from synapse.swarm.runtime import SwarmRuntime


class ResourcePolicyAdapter:
    def __init__(self, local: SynapseLocalModelAdapter, swarm: SwarmRuntime, missions: MissionRuntime):
        self.local, self.swarm, self.missions = local, swarm, missions

    def apply(self, policy: ResourcePolicy) -> None:
        self.local.set_resource_policy(policy)

    def coordinators(self, mission_id: str) -> list[SwarmDescriptor]:
        return [item for item in self.swarm.list(mission_id)
                if item.status not in {"completed", "cancelled", "failed"}
                or item.metadata.get("resource_transition", "STABLE") != "STABLE"
                or self.local.has_reservation(item.swarm_id)]

    def concurrency(self, mission_id: str, requested: int) -> int:
        attached = self.coordinators(mission_id)
        if attached:
            if any(item.status != "running" or item.metadata.get("resource_transition", "STABLE") != "STABLE"
                   for item in attached):
                raise ValidationError("Swarm must be active and its resource transition complete before dispatch.")
            return requested
        return min(requested, 1) if self.local.resource_policy == ResourcePolicy.ECONOMICAL else requested

    def status(self) -> dict[str, object]:
        swarms = [item for item in self.swarm.list() if item.status in {"running", "paused"}]
        local = self.local.residency_status()
        return {**local, "available": True,
                "execution_regime": "SWARM" if swarms or local["reservations"] or local["recovery_owners"] else "NORMAL",
                "swarms": [{"swarm_id": item.swarm_id, "status": item.status} for item in swarms],
                "missions": [{"mission_id": item.mission_id, "status": item.status}
                             for item in self.missions.list_missions()
                             if item.status in {"running", "blocked", "paused"}],
                "policy_effects_deferred": bool(swarms or local["reservations"])}
