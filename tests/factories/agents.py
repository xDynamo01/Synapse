from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from synapse.core.serialization import dump_structured_file, load_structured_file


def create_test_agent_config(
    agent_id: str,
    name: str | None = None,
    role: str = "worker",
    can_delegate: bool = False,
    capabilities: Iterable[str] | Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "id": agent_id,
        "name": name or agent_id.replace("_", " ").title(),
        "role": role,
        "can_delegate": can_delegate,
    }
    if capabilities is not None:
        config["capabilities"] = (
            dict(capabilities)
            if isinstance(capabilities, Mapping)
            else {"allow": list(capabilities), "deny": []}
        )
    if extra:
        config.update(extra)
    return config


def seed_test_agent(
    data_dir: Path,
    agent_id: str,
    *,
    name: str | None = None,
    role: str = "worker",
    can_delegate: bool = False,
    capabilities: Iterable[str] | Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = data_dir / "agents" / agent_id / "CONFIG.yaml"
    existing = load_structured_file(path) if path.exists() else {}
    config = {
        **existing,
        **create_test_agent_config(
            agent_id,
            name=name,
            role=role,
            can_delegate=can_delegate,
            capabilities=capabilities,
            extra=extra,
        ),
    }
    dump_structured_file(path, config)
    return config


def seed_invalid_agent(
    data_dir: Path,
    folder_id: str,
    config: Mapping[str, Any],
) -> Path:
    path = data_dir / "agents" / folder_id / "CONFIG.yaml"
    dump_structured_file(path, dict(config))
    return path


def seed_agent_identity_files(
    data_dir: Path,
    agent_id: str,
    *,
    soul: str | None = None,
    skills: str | None = None,
    memory: str | None = None,
    inbox: str | None = None,
) -> None:
    base = data_dir / "agents" / agent_id
    for filename, content in {
        "SOUL.md": soul,
        "SKILLS.md": skills,
        "MEMORY.md": memory,
        "INBOX.md": inbox,
    }.items():
        if content is not None:
            path = base / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def seed_delegation_pair(
    data_dir: Path,
    delegator_id: str = "artemis",
    delegate_id: str = "researcher",
    *,
    delegator_extra: Mapping[str, Any] | None = None,
    delegate_extra: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    delegator = seed_test_agent(
        data_dir,
        delegator_id,
        name="Artemis" if delegator_id == "artemis" else None,
        role="orchestrator",
        can_delegate=True,
        capabilities=["agent.task.delegation"],
        extra=delegator_extra,
    )
    delegate = seed_test_agent(
        data_dir,
        delegate_id,
        name="Researcher" if delegate_id == "researcher" else None,
        role="research_specialist",
        extra=delegate_extra,
    )
    return delegator, delegate
