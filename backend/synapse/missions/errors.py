from __future__ import annotations

from synapse.core.exceptions import NotFound, ValidationError


class MissionNotFound(NotFound):
    code = "mission_not_found"


class MissionInvalidState(ValidationError):
    code = "mission_invalid_state"


class PlanInvalid(ValidationError):
    code = "plan_invalid"


class DependencyCycle(PlanInvalid):
    code = "dependency_cycle"


class DependencyMissing(PlanInvalid):
    code = "dependency_missing"


class WorkerNotFound(NotFound):
    code = "worker_not_found"


class NoWorkerAvailable(ValidationError):
    code = "no_worker_available"


class VerificationFailed(ValidationError):
    code = "verification_failed"


class AttemptNotFound(NotFound):
    code = "attempt_not_found"


class AttemptInvalidState(ValidationError):
    code = "attempt_invalid_state"


class AttemptConflict(ValidationError):
    code = "attempt_conflict"


class WorkerAssignmentMismatch(ValidationError):
    code = "worker_assignment_mismatch"


class SwarmNotFound(NotFound):
    code = "swarm_not_found"


class SwarmInvalidStrategy(ValidationError):
    code = "swarm_invalid_strategy"
