from __future__ import annotations

from pathlib import Path

from synapse.core.exceptions import ValidationError

REQUIRED_DIRECTORIES = (
    "config",
    "memory",
    "agents",
    "projects",
    "skills",
    "tasks/active",
    "tasks/completed",
    "tasks/failed",
    "logs",
    "library",
    "chats",
    "devices/trusted",
    "devices/untrusted",
    "devices/revoked",
)


SEED_FILES = {
    "memory/USER.md": "# User Memory\n\nPersistent facts about the user belong here.\n",
    "memory/MEMORY.md": "# Global Memory\n\nPersistent system-wide memory belongs here.\n",
    "memory/SYSTEM.md": "# System Memory\n\nDurable operating notes for Synapse belong here.\n",
    "agents/orchestrator/SOUL.md": (
        "# Orchestrator\n\n"
        "The orchestrator coordinates agents, tasks, memory, and tools while respecting permissions.\n"
    ),
    "agents/orchestrator/MEMORY.md": "# Orchestrator Memory\n\n",
    "agents/orchestrator/SKILLS.md": (
        "# Orchestrator Skills\n\n"
        "- coordinate_tasks\n- route_messages\n- use_core_tools\n"
    ),
    "agents/orchestrator/INBOX.md": "# Inbox\n",
}


class DataDir:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in REQUIRED_DIRECTORIES:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        for relative_path, content in SEED_FILES.items():
            self.ensure_file(relative_path, content)

    def ensure_file(self, relative_path: str, content: str) -> Path:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        return path

    def resolve(self, relative_path: str | Path) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            path = candidate.resolve()
        else:
            path = (self.root / candidate).resolve()

        if not path.is_relative_to(self.root):
            raise ValidationError(f"Path escapes DATA_DIR: {relative_path}")
        return path

    def append_text(self, relative_path: str, text: str) -> Path:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
        return path

