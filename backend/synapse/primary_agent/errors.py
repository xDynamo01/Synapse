from synapse.core.exceptions import NotFound, ValidationError


class PrimaryAgentRequired(NotFound):
    pass


class PrimaryAgentMisconfigured(ValidationError):
    pass


class PrimaryAgentConflict(ValidationError):
    pass
