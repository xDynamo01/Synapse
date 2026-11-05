"""Independent execution regime and resource preference; no orchestration authority."""
from enum import StrEnum


class ExecutionRegime(StrEnum):
    NORMAL = "NORMAL"
    SWARM = "SWARM"


class ResourcePolicy(StrEnum):
    RESPONSIVE = "RESPONSIVE"
    ECONOMICAL = "ECONOMICAL"
