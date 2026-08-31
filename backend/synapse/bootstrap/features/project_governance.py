from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.bootstrap.adapters.project_governance import (
    FileProjectDocumentAdapter,
    GovernanceRecordStoreAdapter,
    QualityGateExecutionAdapter,
)
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.health.contributors.project_governance import ProjectGovernanceHealthContributor
from synapse.project_governance.runtime import ProjectGovernanceRuntime
from synapse.storage.collection import FileCollection


@dataclass(frozen=True)
class ProjectGovernanceFeatureDependencies:
    data_dir: Any
    events: Any
    tools: Any
    health: Any


class ProjectGovernanceFeatureBuilder:
    metadata = FeatureMetadata("project-governance-rfc", optional=True)

    def build(
        self, dependencies: ProjectGovernanceFeatureDependencies
    ) -> BuiltFeature[ProjectGovernanceRuntime]:
        root = dependencies.data_dir.resolve("project_governance")
        stores = {
            name: GovernanceRecordStoreAdapter(
                FileCollection(
                    collection_id=f"project_governance_{name}",
                    root=root / name,
                    current_schema_version=1,
                    events=dependencies.events,
                    recovery_policy="skip_with_warning",
                )
            )
            for name in ("projects", "rfcs", "versions", "reviews", "plans", "evidence", "adrs")
        }
        runtime = ProjectGovernanceRuntime(
            events=dependencies.events,
            documents=FileProjectDocumentAdapter(dependencies.data_dir.resolve("projects")),
            stores=stores,
            quality_gates=QualityGateExecutionAdapter(dependencies.tools),
        )
        contributor = ProjectGovernanceHealthContributor(runtime)
        dependencies.health.registry.register(contributor, optional=True)
        return BuiltFeature(
            runtime,
            self.metadata,
            health_contributors=(contributor,),
            ports={
                "project_context": runtime,
                "rfc_gate": runtime,
                "rfc_evidence": runtime,
                "implementation_binding": runtime,
            },
        )
