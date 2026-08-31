from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.bootstrap.adapters.skills import (
    SkillRecordStoreAdapter,
    SkillScriptExecutionAdapter,
)
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.core.serialization import load_structured_file
from synapse.health.contributors.skills import SkillHealthContributor
from synapse.skills.models import SkillAssignment, SkillScope
from synapse.skills.runtime import SkillsRuntime
from synapse.storage.collection import FileCollection


@dataclass(frozen=True)
class SkillsFeatureDependencies:
    data_dir: Any
    events: Any
    tools: Any
    health: Any


class SkillsFeatureBuilder:
    metadata = FeatureMetadata("skills-runtime", optional=True)

    def build(self, d: SkillsFeatureDependencies) -> BuiltFeature[SkillsRuntime]:
        root = d.data_dir.resolve("skills")
        stores = {
            name: SkillRecordStoreAdapter(
                FileCollection(
                    collection_id=f"skill_{name}",
                    root=root / name,
                    current_schema_version=1,
                    events=d.events,
                    recovery_policy="skip_with_warning",
                )
            )
            for name in ("assignments", "leases", "installations")
        }
        runtime = SkillsRuntime(
            d.data_dir,
            d.events,
            assignments=stores["assignments"],
            leases=stores["leases"],
            installations=stores["installations"],
            script_execution=SkillScriptExecutionAdapter(d.tools),
        )
        existing = {item["assignment_id"] for item in runtime.list_assignments()}
        for config_path in sorted(d.data_dir.resolve("agents").glob("*/CONFIG.yaml")):
            configured = load_structured_file(config_path).get("skills", {})
            if not isinstance(configured, dict):
                continue
            for raw in configured.get("assignments", []):
                assignment_id = f"config--{config_path.parent.name}--{raw['skill_id']}"
                if assignment_id in existing:
                    continue
                runtime.assign(
                    SkillAssignment(
                        assignment_id=assignment_id,
                        agent_id=config_path.parent.name,
                        skill_id=str(raw["skill_id"]),
                        version_constraint=str(raw["version"]),
                        scope=SkillScope(str(raw.get("scope", "agent"))),
                        assigned_by="agent_config",
                        metadata=dict(raw.get("metadata") or {}),
                    )
                )
        contributor = SkillHealthContributor(runtime)
        d.health.registry.register(contributor, optional=True)
        return BuiltFeature(
            runtime,
            self.metadata,
            health_contributors=(contributor,),
            ports={"skill_resolution": runtime, "skill_leases": runtime},
        )
