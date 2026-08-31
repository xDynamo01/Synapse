"""Typed bounded-context builders used by the canonical composition root."""

from synapse.bootstrap.features.agents import AgentFeatureBuilder
from synapse.bootstrap.features.automation import AutomationFeatureBuilder
from synapse.bootstrap.features.foundation import FoundationFeatureBuilder
from synapse.bootstrap.features.integration import IntegrationFeatureBuilder
from synapse.bootstrap.features.interaction import InteractionFeatureBuilder
from synapse.bootstrap.features.missions import MissionFeatureBuilder
from synapse.bootstrap.features.models import ModelFeatureBuilder
from synapse.bootstrap.features.platform import PlatformFeatureBuilder
from synapse.bootstrap.features.world import WorldFeatureBuilder

__all__ = [
    "AgentFeatureBuilder",
    "AutomationFeatureBuilder",
    "FoundationFeatureBuilder",
    "IntegrationFeatureBuilder",
    "InteractionFeatureBuilder",
    "MissionFeatureBuilder",
    "ModelFeatureBuilder",
    "PlatformFeatureBuilder",
    "WorldFeatureBuilder",
]
