from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.core.serialization import load_structured_file


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    host: str
    port: int
    default_actor_id: str

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[3]
        data_dir_value = os.environ.get("SYNAPSE_DATA_DIR", "./data")
        data_dir = Path(data_dir_value)
        if not data_dir.is_absolute():
            data_dir = project_root / data_dir

        return cls(
            project_root=project_root,
            data_dir=data_dir.resolve(),
            host=os.environ.get("SYNAPSE_HOST", "127.0.0.1"),
            port=int(os.environ.get("SYNAPSE_PORT", "8717")),
            default_actor_id=os.environ.get("SYNAPSE_DEFAULT_ACTOR_ID", "local_owner"),
        )


class ConfigStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def load(self, name: str) -> dict[str, Any]:
        path = self.data_dir / "config" / name
        return load_structured_file(path)

    def load_system(self) -> dict[str, Any]:
        return self.load("system.yaml")
