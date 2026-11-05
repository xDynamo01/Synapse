"""Provider residency boundary; Swarm retains coordination authority."""
from typing import Protocol

from synapse.missions.models import SwarmDescriptor


class SwarmResidencyPort(Protocol):
    def prepare(self, swarm: SwarmDescriptor) -> None: ...
    def release(self, swarm: SwarmDescriptor) -> None: ...
