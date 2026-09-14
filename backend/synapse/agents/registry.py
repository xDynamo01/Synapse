from __future__ import annotations

from pathlib import Path

from synapse.agents.models import AgentConfig, agent_config_from_mapping, load_agent_config
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound


class AgentRegistry:
    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    @property
    def agents_dir(self) -> Path:
        return self.data_dir.resolve("agents")

    def list_agents(self) -> list[AgentConfig]:
        agents: list[AgentConfig] = []
        for path in sorted(self.agents_dir.iterdir()):
            if not path.is_dir():
                continue
            config_path = path / "CONFIG.yaml"
            if config_path.exists():
                raw = load_agent_config(config_path, path.name)
                agents.append(agent_config_from_mapping(raw, path.name))
        return agents

    def get(self, agent_id: str) -> AgentConfig:
        config_path = self.data_dir.resolve(f"agents/{agent_id}/CONFIG.yaml")
        if not config_path.exists():
            raise NotFound(f"Agent not found: {agent_id}")
        raw = load_agent_config(config_path, agent_id)
        return agent_config_from_mapping(raw, agent_id)

    def ensure_agent_files(self, agent: AgentConfig) -> None:
        base = f"agents/{agent.id}"
        self.data_dir.ensure_file(f"{base}/SOUL.md", f"# {agent.name}\n\n{agent.role}\n")
        self.data_dir.ensure_file(f"{base}/MEMORY.md", f"# {agent.name} Memory\n\n")
        self.data_dir.ensure_file(f"{base}/SKILLS.md", "# Skills\n\n")
        self.data_dir.ensure_file(f"{base}/INBOX.md", "# Inbox\n")

    def personality(self, agent_id: str) -> str:
        agent = self.get(agent_id)
        raw = load_agent_config(self.data_dir.resolve(f"agents/{agent.id}/CONFIG.yaml"), agent.id)
        return str(raw.get("system_prompt") or "")
