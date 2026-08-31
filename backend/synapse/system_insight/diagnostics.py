from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from synapse.system_insight.models import (
    DiagnosticFinding,
    DiagnosticsReport,
    Evidence,
    HardwareSnapshot,
    ModelCapabilityReport,
    ProcessSnapshot,
    ResourcePressure,
)


class DiagnosticsRuntime:
    def __init__(self, processes: Any):
        self.processes = processes

    def inspect(
        self,
        hardware: HardwareSnapshot,
        pressure: ResourcePressure,
        models: ModelCapabilityReport,
        processes: ProcessSnapshot | None = None,
    ) -> DiagnosticsReport:
        processes = processes or self.processes.inspect(limit=100)
        findings: list[DiagnosticFinding] = []
        for metric in (pressure.memory, pressure.vram, pressure.cpu, pressure.disk):
            if metric.level not in {"high", "critical"}:
                continue
            findings.append(
                DiagnosticFinding(
                    code=f"resource.{metric.name}_{metric.level}",
                    severity="critical" if metric.level == "critical" else "warning",
                    summary=f"Measured {metric.name} pressure is {metric.level}.",
                    evidence=metric.evidence,
                    recommendation=f"Reduce {metric.name} load before starting additional work.",
                )
            )
        if hardware.memory.swap_total_bytes and hardware.memory.swap_percent >= 50:
            findings.append(
                DiagnosticFinding(
                    code="memory.swap_excessive",
                    severity="warning",
                    summary="Swap usage is above the configured diagnostic threshold.",
                    evidence=[
                        Evidence(
                            hardware.provider,
                            "swap_percent",
                            hardware.memory.swap_percent,
                            "percent",
                            hardware.collected_at,
                        )
                    ],
                    recommendation="Reduce memory load and re-evaluate resource pressure.",
                )
            )
        synapse_memory = sum(
            item.memory_bytes for item in processes.processes if item.synapse_process
        )
        if synapse_memory > max(1024**3, int(hardware.memory.total_bytes * 0.25)):
            findings.append(
                DiagnosticFinding(
                    code="process.synapse_memory_high",
                    severity="warning",
                    summary="Synapse process memory exceeds the evidence-based threshold.",
                    evidence=[
                        Evidence(
                            processes.provider, "synapse_memory_bytes", synapse_memory, "bytes"
                        )
                    ],
                    recommendation="Inspect bounded Synapse process metrics and current workloads.",
                )
            )
        if models.available_models == 0:
            findings.append(
                DiagnosticFinding(
                    code="models.none_available",
                    severity="info",
                    summary="No registered model is currently available.",
                    evidence=[Evidence("model_capability", "available_models", 0, "count")],
                    recommendation="Start or configure a model provider only when model execution is required.",
                )
            )
        limitations = [*hardware.limitations, *pressure.limitations, *models.limitations]
        status = (
            "critical"
            if any(item.severity == "critical" for item in findings)
            else ("warning" if any(item.severity == "warning" for item in findings) else "ok")
        )
        return DiagnosticsReport(
            generated_at=datetime.now(UTC).isoformat(),
            status=status,
            findings=findings,
            limitations=sorted(set(limitations)),
        )
