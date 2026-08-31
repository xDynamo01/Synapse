from __future__ import annotations


def parse_command_line(text: str) -> tuple[str, str, str]:
    """Apply the legacy common parsing without eagerly parsing domain arguments."""
    command_line = text.strip()
    command, _, rest = command_line.partition(" ")
    return command_line, command.lower(), rest.strip()
