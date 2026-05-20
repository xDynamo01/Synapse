from __future__ import annotations

import json
from pathlib import Path

from synapse.agents.models import Agent
from synapse.config.models import DATA_DIR


DEFAULT_ARTEMIS = Agent(
    name="Artemis",
    description="Agente padrao do Synapse para assistencia pessoal local-first.",
    system_prompt=(
        "Voce e Artemis, agente padrao do Synapse. Responda em portugues do Brasil, "
        "seja direto, seguro e util. Preserve privacidade, nao execute acoes perigosas "
        "sem confirmacao e explique limites quando necessario."
    ),
    tools=["file_analysis"],
    memory_scope="shared",
)


class AgentManager:
    def __init__(self, path: Path = DATA_DIR / "agents.json"):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.agents: dict[str, Agent] = {}
        self.active_name = "Artemis"
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.agents = {DEFAULT_ARTEMIS.name: DEFAULT_ARTEMIS}
            self.save()
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.active_name = raw.get("active", "Artemis")
        self.agents = {item["name"]: Agent.from_dict(item) for item in raw.get("agents", [])}
        if "Artemis" not in self.agents:
            self.agents["Artemis"] = DEFAULT_ARTEMIS

    def save(self) -> None:
        data = {"active": self.active_name, "agents": [agent.to_dict() for agent in self.agents.values()]}
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def active(self) -> Agent:
        return self.agents[self.active_name]

    def list_agents(self) -> list[Agent]:
        return list(self.agents.values())

    def create(self, name: str, description: str = "", system_prompt: str = "") -> Agent:
        if not name:
            raise ValueError("Agent name is required")
        agent = Agent(
            name=name,
            description=description or f"Agente {name}",
            system_prompt=system_prompt or f"Voce e {name}, um agente especializado do Synapse.",
            tools=["file_analysis"],
        )
        self.agents[name] = agent
        self.save()
        return agent

    def delete(self, name: str) -> None:
        if name == "Artemis":
            raise ValueError("Artemis is the default agent and cannot be deleted")
        self.agents.pop(name, None)
        if self.active_name == name:
            self.active_name = "Artemis"
        self.save()

    def switch(self, name: str) -> Agent:
        if name not in self.agents:
            raise KeyError(f"Agent not found: {name}")
        self.active_name = name
        self.save()
        return self.active()
