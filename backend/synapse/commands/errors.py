class CommandRegistryError(ValueError):
    """Base error for invalid command registration."""


class DuplicateCommandError(CommandRegistryError):
    """Raised when a command name or alias is registered more than once."""


class UnknownCommandError(LookupError):
    """Raised only when a resolved handler cannot dispatch its own command."""
