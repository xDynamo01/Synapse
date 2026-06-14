class SynapseError(Exception):
    """Base exception for runtime errors."""


class PermissionDenied(SynapseError):
    """Raised when a subject attempts an action without permission."""


class NotFound(SynapseError):
    """Raised when a runtime entity cannot be found."""


class ValidationError(SynapseError):
    """Raised when caller input is invalid."""


class ToolExecutionError(SynapseError):
    """Raised when a tool cannot complete its work."""

