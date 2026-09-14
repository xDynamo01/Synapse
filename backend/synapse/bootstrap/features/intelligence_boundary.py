from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.bootstrap.adapters.intelligence_boundary import BoundaryRecordStoreAdapter
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.health.contributors.intelligence_boundary import (
    IntelligenceBoundaryHealthContributor,
)
from synapse.intelligence_boundary.models import (
    DataClassification,
    ProcessingBoundary,
    ProviderTrustProfile,
    TrustProfileStatus,
)
from synapse.intelligence_boundary.runtime import IntelligenceBoundaryRuntime
from synapse.storage.collection import FileCollection


@dataclass(frozen=True)
class IntelligenceBoundaryFeatureDependencies:
    data_dir: Any
    events: Any
    health: Any


class IntelligenceBoundaryFeatureBuilder:
    metadata = FeatureMetadata("intelligence-trust-boundary", optional=False)

    def build(
        self, dependencies: IntelligenceBoundaryFeatureDependencies
    ) -> BuiltFeature[IntelligenceBoundaryRuntime]:
        root = dependencies.data_dir.resolve("intelligence_boundary")
        stores = {
            name: BoundaryRecordStoreAdapter(
                FileCollection(
                    collection_id=f"intelligence_boundary_{name}",
                    root=root / name,
                    current_schema_version=1,
                    events=dependencies.events,
                    recovery_policy="skip_with_warning",
                )
            )
            for name in (
                "assets",
                "trust_profiles",
                "decisions",
                "manifests",
                "approvals",
                "ledger",
                "settings",
            )
        }
        runtime = IntelligenceBoundaryRuntime(
            stores=stores,
            events=dependencies.events,
            protected_integrations=("models", "tools", "mcp"),
            unguarded_paths=("desktop_automation_ui_uploads",),
        )
        self._seed_local_trust(runtime)
        contributor = IntelligenceBoundaryHealthContributor(runtime)
        dependencies.health.registry.register(contributor)
        return BuiltFeature(
            runtime,
            self.metadata,
            health_contributors=(contributor,),
            ports={
                "egress_gate": runtime,
                "egress_decision": runtime,
                "information_assets": runtime,
                "provider_trust": runtime,
            },
        )

    @staticmethod
    def _seed_local_trust(runtime: IntelligenceBoundaryRuntime) -> None:
        existing = {item.provider_id for item in runtime.list_trust_profiles()}
        for provider_id, boundary in (
            ("mock", ProcessingBoundary.LOCAL_PROCESS),
            ("synapse_local", ProcessingBoundary.LOCAL_PROCESS),
            ("ollama", ProcessingBoundary.LOCAL_NETWORK),
            ("lmstudio", ProcessingBoundary.LOCAL_NETWORK),
            ("lmstudio_local", ProcessingBoundary.LOCAL_NETWORK),
        ):
            if provider_id in existing:
                continue
            runtime.register_trust_profile(
                ProviderTrustProfile(
                    trust_profile_id=f"builtin-{provider_id}",
                    provider_id=provider_id,
                    processing_boundary=boundary,
                    organization_controlled=True,
                    supported_classifications=tuple(DataClassification),
                    verification_level="builtin-local-deployment-profile",
                    status=TrustProfileStatus.ACTIVE,
                    provenance={"source": "composition_root", "claim": "configured local"},
                )
            )
