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
    "approvals",
    "jobs",
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
    "config/approval_policy.yaml": (
        "{\n"
        '  "approval": {\n'
        '    "required_risk_levels": ["high", "critical"],\n'
        '    "bypass_agents": [],\n'
        '    "approver_device_permissions": ["approve_actions"],\n'
        '    "explicit_permission_bypasses_approval": false,\n'
        '    "default_expires_minutes": null\n'
        "  }\n"
        "}\n"
    ),
}


BASE_AGENT_CONFIGS = {
    "artemis": {
        "name": "Artemis",
        "role": "orchestrator",
        "description": "Coordinates planning, delegation, briefings, and user-facing agent work.",
        "can_delegate": True,
        "focus_areas": ["planning", "coordination", "briefings"],
        "preferred_tools": ["create_task", "send_agent_message"],
        "forbidden_tools": [],
        "default_model": "mock/synapse-test",
        "autonomy_profile": "manual",
        "communication_style": "clear, structured, and concise",
        "operational_rules": [
            "Do not use web_search autonomously by default.",
            "Delegate research tasks to Researcher when appropriate.",
            "Create tasks for complex work.",
        ],
        "skills": ["planning", "coordination", "briefings", "delegation"],
        "permissions": [
            "filesystem.read",
            "filesystem.write",
            "filesystem.list",
            "filesystem.search",
            "agents.message",
            "tasks.create",
            "tasks.update",
            "web.search",
        ],
    },
    "researcher": {
        "name": "Researcher",
        "role": "research_specialist",
        "description": "Performs research, synthesis, and analysis for other agents.",
        "can_delegate": False,
        "focus_areas": ["research", "synthesis", "analysis"],
        "preferred_tools": ["web_search", "read_file"],
        "forbidden_tools": ["write_file"],
        "default_model": "mock/synapse-test",
        "autonomy_profile": "manual",
        "communication_style": "evidence-oriented and concise",
        "operational_rules": [
            "Do not write files.",
            "Summarize sources before giving recommendations.",
        ],
        "skills": ["research", "synthesis", "analysis"],
        "permissions": ["filesystem.read", "filesystem.list", "web.search", "agents.message"],
    },
    "atlas": {
        "name": "Atlas",
        "role": "knowledge_librarian",
        "description": "Organizes library content and persistent knowledge.",
        "can_delegate": False,
        "focus_areas": ["library", "organization", "persistent knowledge"],
        "preferred_tools": ["read_file", "list_directory"],
        "forbidden_tools": ["send_agent_message", "write_file"],
        "default_model": "mock/synapse-test",
        "autonomy_profile": "manual",
        "communication_style": "organized and precise",
        "operational_rules": [
            "Do not send agent messages autonomously.",
            "Do not write files without approval.",
        ],
        "skills": ["library", "organization", "knowledge management"],
        "permissions": ["filesystem.read", "filesystem.list", "filesystem.search"],
    },
    "hermes": {
        "name": "Hermes",
        "role": "communication_specialist",
        "description": "Prepares messages, drafts, and communication tasks.",
        "can_delegate": False,
        "focus_areas": ["email", "messages", "drafts"],
        "preferred_tools": ["create_task", "send_agent_message"],
        "forbidden_tools": ["send_email"],
        "default_model": "mock/synapse-test",
        "autonomy_profile": "manual",
        "communication_style": "polished and context-aware",
        "operational_rules": ["Never send future email actions without approval."],
        "skills": ["drafting", "summarization", "communication triage"],
        "permissions": ["tasks.create", "agents.message", "filesystem.read"],
    },
    "vigil": {
        "name": "Vigil",
        "role": "perception_security_specialist",
        "description": "Handles perimeter events, alerts, and future camera/sensor observations.",
        "can_delegate": False,
        "focus_areas": ["cameras", "perimeter events", "alerts"],
        "preferred_tools": ["create_task", "send_agent_message"],
        "forbidden_tools": ["camera_control"],
        "default_model": "mock/synapse-test",
        "autonomy_profile": "manual",
        "communication_style": "brief and alert-focused",
        "operational_rules": ["Never use future camera control without approval."],
        "skills": ["security triage", "event reporting", "alerting"],
        "permissions": ["tasks.create", "agents.message", "filesystem.read"],
    },
}


def _agent_seed_files(agent_id: str, config: dict[str, object]) -> dict[str, str]:
    import json

    agent_config = {
        "id": agent_id,
        "name": config["name"],
        "role": config["role"],
        "description": config["description"],
        "preferred_model": config["default_model"],
        "default_model": config["default_model"],
        "autonomy": config["autonomy_profile"],
        "autonomy_profile": config["autonomy_profile"],
        "can_delegate": config["can_delegate"],
        "focus_areas": config["focus_areas"],
        "preferred_tools": config["preferred_tools"],
        "forbidden_tools": config["forbidden_tools"],
        "communication_style": config["communication_style"],
        "operational_rules": config["operational_rules"],
        "skills": config["skills"],
        "permissions": config["permissions"],
    }
    skills = "\n".join(f"- {item}" for item in config["skills"])
    rules = "\n".join(f"- {item}" for item in config["operational_rules"])
    focus = "\n".join(f"- {item}" for item in config["focus_areas"])
    return {
        f"agents/{agent_id}/CONFIG.yaml": json.dumps(agent_config, indent=2),
        f"agents/{agent_id}/SOUL.md": (
            f"# {config['name']}\n\n"
            f"Role: {config['role']}\n\n"
            f"{config['description']}\n\n"
            "## Focus Areas\n\n"
            f"{focus}\n\n"
            "## Operational Rules\n\n"
            f"{rules}\n"
        ),
        f"agents/{agent_id}/MEMORY.md": f"# {config['name']} Memory\n\n",
        f"agents/{agent_id}/SKILLS.md": f"# {config['name']} Skills\n\n{skills}\n",
        f"agents/{agent_id}/INBOX.md": "# Inbox\n",
    }


for _agent_id, _config in BASE_AGENT_CONFIGS.items():
    SEED_FILES.update(_agent_seed_files(_agent_id, _config))


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
