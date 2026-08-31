from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from synapse.agents.models import load_agent_config
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError


@dataclass(frozen=True)
class AgentIdentity:
    id: str
    name: str
    role: str
    description: str
    can_delegate: bool
    focus_areas: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    default_model: str | None = None
    autonomy_profile: str = "manual"
    communication_style: str = "concise"
    operational_rules: list[str] = field(default_factory=list)
    soul: str = ""
    skills: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentIdentityRuntime:
    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def load_identity(self, agent_id: str) -> AgentIdentity:
        base = f"agents/{agent_id}"
        config_path = self.data_dir.resolve(f"{base}/CONFIG.yaml")
        if not config_path.exists():
            raise ValidationError(f"Agent config missing: {agent_id}")

        raw = load_agent_config(config_path, agent_id, require_identity=True)
        soul = self._read_optional(f"{base}/SOUL.md")
        skills = self._read_optional(f"{base}/SKILLS.md")
        identity_raw = raw.get("identity", {})

        identity = AgentIdentity(
            id=str(raw.get("id", agent_id)),
            name=str(raw.get("name", raw.get("id", agent_id))),
            role=str(raw.get("role", identity_raw.get("role", ""))),
            description=str(raw.get("description", identity_raw.get("description", ""))),
            can_delegate=bool(raw.get("can_delegate", identity_raw.get("can_delegate", False))),
            focus_areas=self._list_value(
                raw.get("focus_areas", identity_raw.get("focus_areas", []))
            ),
            preferred_tools=self._list_value(
                raw.get("preferred_tools", identity_raw.get("preferred_tools", []))
            ),
            forbidden_tools=self._list_value(
                raw.get("forbidden_tools", identity_raw.get("forbidden_tools", []))
            ),
            default_model=raw.get("default_model", raw.get("preferred_model")),
            autonomy_profile=str(
                raw.get(
                    "autonomy_profile", raw.get("autonomy", identity_raw.get("autonomy", "manual"))
                )
            ),
            communication_style=str(
                raw.get(
                    "communication_style",
                    identity_raw.get("communication_style", "concise"),
                )
            ),
            operational_rules=self._list_value(
                raw.get("operational_rules", identity_raw.get("operational_rules", []))
            ),
            soul=soul,
            skills=skills,
        )
        self.validate(identity)
        return identity

    def validate(self, identity: AgentIdentity) -> None:
        if not identity.id:
            raise ValidationError("Agent identity id is required.")
        if not identity.name:
            raise ValidationError(f"Agent identity name is required: {identity.id}")
        if not identity.role:
            raise ValidationError(f"Agent identity role is required: {identity.id}")

    def _read_optional(self, relative_path: str) -> str:
        path = self.data_dir.resolve(relative_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _list_value(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]
