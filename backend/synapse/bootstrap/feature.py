from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from synapse.bootstrap.lifecycle import LifecycleResource

FeatureValue = TypeVar("FeatureValue")
FeatureDependencies = TypeVar("FeatureDependencies", contravariant=True)


@dataclass(frozen=True)
class FeatureMetadata:
    name: str
    status: str = "ready"
    optional: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuiltFeature(Generic[FeatureValue]):
    value: FeatureValue
    metadata: FeatureMetadata
    lifecycle_resources: tuple[LifecycleResource, ...] = ()
    health_contributors: tuple[Any, ...] = ()
    ports: dict[str, Any] = field(default_factory=dict)


class FeatureBuilder(Protocol[FeatureDependencies, FeatureValue]):
    def __call__(self, dependencies: FeatureDependencies) -> BuiltFeature[FeatureValue]: ...
