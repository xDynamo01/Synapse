from synapse.core.exceptions import NotFound, ValidationError


class EphemeralAgentError(ValidationError):
    pass


class EphemeralAgentNotFound(NotFound):
    pass


class EphemeralAgentLimitExceeded(EphemeralAgentError):
    pass


class EphemeralAgentInvalidTransition(EphemeralAgentError):
    pass


class EphemeralAgentResourceUnavailable(EphemeralAgentError):
    pass
