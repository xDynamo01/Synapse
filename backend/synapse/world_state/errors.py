from __future__ import annotations

from synapse.core.exceptions import NotFound, SynapseError, ValidationError


class WorldStateError(SynapseError):
    code = "world_state_error"
    status_code = 400

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class WorldStateNotFound(NotFound, WorldStateError):
    code = "world_state_not_found"
    status_code = 404


class WorldStateConflict(WorldStateError):
    code = "world_state_conflict"
    status_code = 409


class InvalidStateUpdate(ValidationError, WorldStateError):
    code = "invalid_state_update"
    status_code = 422


class StateSourceUnavailable(WorldStateError):
    code = "state_source_unavailable"
    status_code = 503
