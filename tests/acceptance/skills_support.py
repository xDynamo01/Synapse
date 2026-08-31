from pathlib import Path

from synapse.bootstrap.adapters.skills import SkillRecordStoreAdapter
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.skills.runtime import SkillsRuntime
from synapse.storage.collection import FileCollection


def runtime(root: Path) -> SkillsRuntime:
    data_dir = DataDir(root)
    data_dir.bootstrap()
    events = EventBus(root)
    stores = {
        name: SkillRecordStoreAdapter(
            FileCollection(
                collection_id=f"skill_{name}",
                root=root / "skills" / name,
                current_schema_version=1,
                events=events,
            )
        )
        for name in ("assignments", "leases", "installations")
    }
    return SkillsRuntime(
        data_dir,
        events,
        assignments=stores["assignments"],
        leases=stores["leases"],
        installations=stores["installations"],
    )


def package(root: Path, skill_id: str, *, dependencies="[]", conflicts="[]", tools="[]") -> Path:
    path = root / "skills" / "candidates" / skill_id
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"# {skill_id}\n\nReusable workflow.\n", encoding="utf-8")
    (path / "manifest.yaml").write_text(
        f"""skill_id: {skill_id}
name: {skill_id}
version: 1.0.0
description: Professional reusable workflow
summary: Deterministic workflow
authorship: [synapse]
status: active
scopes: [system, agent, project, mission, task]
supported_agent_kinds: [primary, persistent, ephemeral]
activation: {{keywords: [{skill_id}]}}
requirements: {{}}
dependencies: {dependencies}
conflicts: {conflicts}
tools: {tools}
capabilities: []
providers: []
resources: []
references: []
scripts: []
context_policy: {{max_tokens: 1000}}
permissions: []
compatibility: {{agent_skills: partial}}
metadata: {{tags: [workflow]}}
""",
        encoding="utf-8",
    )
    return path
