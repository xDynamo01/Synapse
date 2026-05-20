from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Agent:
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    memory_scope: str = "shared"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Agent":
        return cls(**data)
