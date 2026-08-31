from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synapse.model_hub.models import LLMRecommendation


@dataclass(frozen=True)
class Evidence:
    source: str
    metric: str
    value: Any
    unit: str | None = None
    observed_at: str | None = None


@dataclass(frozen=True)
class SystemSnapshot:
    provider: str
    collected_at: str
    operating_system: str
    os_version: str
    architecture: str
    kernel: str
    hostname: str
    user: str
    uptime_seconds: float | None
    boot_time: str | None
    timezone: str
    locale: str | None
    python_version: str
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CPUInfo:
    model: str
    architecture: str
    physical_cores: int | None
    logical_threads: int
    usage_percent: float | None
    frequency_mhz: float | None = None
    temperature_celsius: float | None = None
    cache_bytes: int | None = None


@dataclass(frozen=True)
class MemoryInfo:
    total_bytes: int
    available_bytes: int
    used_bytes: int
    usage_percent: float
    swap_total_bytes: int
    swap_used_bytes: int
    swap_percent: float
    compression_bytes: int | None = None


@dataclass(frozen=True)
class GPUInfo:
    name: str
    vendor: str
    provider: str
    driver: str | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    memory_free_bytes: int | None = None
    usage_percent: float | None = None
    temperature_celsius: float | None = None
    clock_mhz: float | None = None
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HardwareSnapshot:
    provider: str
    collected_at: str
    cpu: CPUInfo
    memory: MemoryInfo
    gpus: list[GPUInfo]
    motherboard: dict[str, str] = field(default_factory=dict)
    sensors: list[dict[str, Any]] = field(default_factory=list)
    batteries: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiskVolume:
    volume_id: str
    filesystem: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    usage_percent: float
    removable: bool | None = None


@dataclass(frozen=True)
class DiskSnapshot:
    provider: str
    collected_at: str
    volumes: list[DiskVolume]
    io: dict[str, int | float | None] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int | None
    name: str
    cpu_percent: float
    memory_bytes: int
    memory_percent: float
    synapse_process: bool = False


@dataclass(frozen=True)
class ProcessSnapshot:
    provider: str
    collected_at: str
    total_processes: int
    processes: list[ProcessInfo]
    truncated: bool
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PressureMetric:
    name: str
    ratio: float | None
    level: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(frozen=True)
class ResourcePressure:
    checked_at: str
    overall_level: str
    memory: PressureMetric
    vram: PressureMetric
    cpu: PressureMetric
    disk: PressureMetric
    saturation: float
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CapacityDecision:
    workload: str
    sufficient: bool
    reason: str
    pressure_level: str
    evidence: list[Evidence] = field(default_factory=list)
    recommended_concurrency: int | None = None


@dataclass(frozen=True)
class ModelRecommendation:
    task: str
    model_id: str | None
    provider_id: str | None
    status: str
    reason: str
    estimated_ram_gb: float | None = None
    estimated_vram_gb: float | None = None
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(frozen=True)
class ModelCapabilityReport:
    checked_at: str
    available_models: int
    online_providers: int
    providers: list[dict[str, Any]]
    recommendations: list[ModelRecommendation]
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiagnosticFinding:
    code: str
    severity: str
    summary: str
    evidence: list[Evidence]
    recommendation: str | None = None


@dataclass(frozen=True)
class DiagnosticsReport:
    generated_at: str
    status: str
    findings: list[DiagnosticFinding]
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InsightReport:
    generated_at: str
    system: SystemSnapshot
    hardware: HardwareSnapshot
    storage: DiskSnapshot
    pressure: ResourcePressure
    models: ModelCapabilityReport
    diagnostics: DiagnosticsReport
    providers: list[dict[str, Any]]
    health: dict[str, Any]
    readiness: dict[str, Any]
    integrations: dict[str, bool]
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SystemInsight:
    mode: str
    checked_at: str
    operating_system: str
    os_version: str
    architecture: str
    cpu: str
    logical_processors: int
    memory_total_bytes: int | None
    memory_available_bytes: int | None
    disk_total_bytes: int
    disk_free_bytes: int
    python_version: str
    git_available: bool
    git_version: str | None
    gpu: str | None
    gpu_memory_total_bytes: int | None
    gpu_memory_free_bytes: int | None
    lmstudio_available: bool
    lmstudio_model_count: int
    lmstudio_message: str | None
    real_checks: list[str] = field(default_factory=list)
    planned_checks: list[str] = field(default_factory=list)
    llm_recommendations: list[LLMRecommendation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
