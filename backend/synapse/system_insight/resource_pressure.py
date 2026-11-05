from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.serialization import load_structured_file
from synapse.system_insight.models import (
    CapacityDecision,
    DiskSnapshot,
    Evidence,
    HardwareSnapshot,
    PressureMetric,
    ResourcePressure,
)

_LEVELS = {"unknown": -1, "low": 0, "moderate": 1, "high": 2, "critical": 3}


class ResourcePressureRuntime:
    def __init__(self, data_dir: DataDir, hardware: Any, disk: Any):
        self.data_dir = data_dir
        self.hardware = hardware
        self.disk = disk

    def inspect(
        self,
        hardware: HardwareSnapshot | None = None,
        storage: DiskSnapshot | None = None,
    ) -> ResourcePressure:
        hardware = hardware or self.hardware.inspect()
        storage = storage or self.disk.inspect()
        thresholds = self._thresholds()
        memory_ratio = _ratio(hardware.memory.used_bytes, hardware.memory.total_bytes)
        cpu_ratio = _percent_ratio(hardware.cpu.usage_percent)
        disk_ratio = max(
            (_ratio(volume.used_bytes, volume.total_bytes) for volume in storage.volumes),
            default=None,
            key=lambda value: -1.0 if value is None else value,
        )
        vram_values = [
            _ratio(gpu.memory_used_bytes, gpu.memory_total_bytes)
            for gpu in hardware.gpus
            if gpu.memory_total_bytes
        ]
        vram_ratio = max((value for value in vram_values if value is not None), default=None)
        metrics = {
            "memory": self._metric("memory", memory_ratio, thresholds),
            "vram": self._metric("vram", vram_ratio, thresholds),
            "cpu": self._metric("cpu", cpu_ratio, thresholds),
            "disk": self._metric("disk", disk_ratio, thresholds),
        }
        known = [item for item in metrics.values() if item.ratio is not None]
        overall = max(known, key=lambda item: _LEVELS[item.level]).level if known else "unknown"
        saturation = max((item.ratio or 0.0 for item in known), default=0.0)
        recommendations = [
            f"Reduce {item.name} load; measured utilization is {(item.ratio or 0) * 100:.1f}%."
            for item in known
            if item.level in {"high", "critical"}
        ]
        limitations = []
        if vram_ratio is None:
            limitations.append("vram_pressure_unavailable")
        if not storage.volumes:
            limitations.append("disk_pressure_unavailable")
        return ResourcePressure(
            checked_at=datetime.now(UTC).isoformat(),
            overall_level=overall,
            memory=metrics["memory"],
            vram=metrics["vram"],
            cpu=metrics["cpu"],
            disk=metrics["disk"],
            saturation=round(saturation, 4),
            recommendations=recommendations,
            limitations=limitations,
        )

    def assess_capacity(self, workload: str) -> CapacityDecision:
        storage = None
        if workload in {"ephemeral_agent", "ephemeral_swarm"}:
            storage = self.disk.inspect_path(self.data_dir.resolve("."))
        pressure = self.inspect(storage=storage)
        # "high" is advisory; only measured critical saturation removes capacity.
        # This prevents a transient busy sample from flapping operational runtimes.
        sufficient = pressure.overall_level != "critical"
        evidence = [
            Evidence("resource_pressure", name, metric.ratio, "ratio", pressure.checked_at)
            for name, metric in {
                "memory": pressure.memory,
                "vram": pressure.vram,
                "cpu": pressure.cpu,
                "disk": pressure.disk,
            }.items()
            if metric.ratio is not None
        ]
        return CapacityDecision(
            workload=workload,
            sufficient=sufficient,
            reason=(
                "Measured pressure is within configured limits."
                if sufficient
                else f"Measured resource pressure is {pressure.overall_level}."
            ),
            pressure_level=pressure.overall_level,
            evidence=evidence,
            recommended_concurrency=1 if pressure.overall_level in {"moderate", "high"} else None,
        )

    def agent_loop_guidance(self) -> dict[str, Any]:
        decision = self.assess_capacity("agent_loop")
        return {
            "sufficient": decision.sufficient,
            "maximum_disposition": None if decision.sufficient else "record_only",
            "reason": decision.reason,
            "evidence": decision.evidence,
        }

    def _metric(
        self,
        name: str,
        ratio: float | None,
        thresholds: dict[str, float],
    ) -> PressureMetric:
        level = "unknown" if ratio is None else _level(ratio, thresholds)
        evidence = [] if ratio is None else [Evidence("platform_provider", name, ratio, "ratio")]
        return PressureMetric(name=name, ratio=ratio, level=level, evidence=evidence)

    def _thresholds(self) -> dict[str, float]:
        defaults = {"moderate": 0.70, "high": 0.85, "critical": 0.95}
        path = self.data_dir.resolve("config/insight_policy.yaml")
        if not path.exists():
            return defaults
        raw = load_structured_file(path).get("resource_pressure", {})
        values = {key: float(raw.get(key, value)) for key, value in defaults.items()}
        if not 0 < values["moderate"] < values["high"] < values["critical"] <= 1:
            return defaults
        return values


def _ratio(used: int | None, total: int | None) -> float | None:
    if used is None or not total:
        return None
    return min(1.0, max(0.0, used / total))


def _percent_ratio(value: float | None) -> float | None:
    return None if value is None else min(1.0, max(0.0, value / 100.0))


def _level(value: float, thresholds: dict[str, float]) -> str:
    if value >= thresholds["critical"]:
        return "critical"
    if value >= thresholds["high"]:
        return "high"
    if value >= thresholds["moderate"]:
        return "moderate"
    return "low"
