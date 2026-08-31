from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.model_hub.models import LLMRecommendation
from synapse.system_insight.diagnostics import DiagnosticsRuntime
from synapse.system_insight.disk import DiskRuntime
from synapse.system_insight.hardware import HardwareRuntime
from synapse.system_insight.model_capability import ModelCapabilityRuntime
from synapse.system_insight.models import InsightReport, SystemInsight
from synapse.system_insight.process import ProcessRuntime
from synapse.system_insight.providers import PlatformInsightProvider, platform_provider
from synapse.system_insight.resource_pressure import ResourcePressureRuntime
from synapse.system_insight.system import SystemRuntime


class InsightRuntime:
    """Read-only operational insight facade composed from bounded runtimes."""

    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        model_hub: Any,
        provider: PlatformInsightProvider | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.provider = provider or platform_provider()
        self.system = SystemRuntime(self.provider, events)
        self.hardware = HardwareRuntime(self.provider, events)
        self.disk = DiskRuntime(self.provider, events)
        self.processes = ProcessRuntime(self.provider, events)
        self.resource_pressure = ResourcePressureRuntime(data_dir, self.hardware, self.disk)
        self.model_capabilities = ModelCapabilityRuntime(model_hub, self.hardware)
        self.diagnostics = DiagnosticsRuntime(self.processes)
        self.health_runtime: Any | None = None
        self.readiness_runtime: Any | None = None
        self.provider_catalog: Any | None = None
        self.snapshots_root = data_dir.resolve("insight/snapshots")
        self.diagnostics_root = data_dir.resolve("insight/diagnostics")
        self.cache_root = data_dir.resolve("insight/cache")
        for path in (self.snapshots_root, self.diagnostics_root, self.cache_root):
            path.mkdir(parents=True, exist_ok=True)

    def discover_provider_manifests(self) -> tuple[Any, ...]:
        """Cross-domain discovery for diagnostics without becoming an execution registry."""
        if self.provider_catalog is None:
            return ()
        return self.provider_catalog.list()

    def report(self, *, persist: bool = True) -> InsightReport:
        system = self.system.inspect()
        hardware = self.hardware.inspect()
        storage = self.disk.inspect()
        pressure = self.resource_pressure.inspect(hardware, storage)
        models = self.model_capabilities.inspect(hardware)
        process_snapshot = self.processes.inspect(limit=100)
        diagnostics = self.diagnostics.inspect(hardware, pressure, models, process_snapshot)
        provider_statuses = [self.provider.status(), *models.providers]
        report = InsightReport(
            generated_at=datetime.now(UTC).isoformat(),
            system=system,
            hardware=hardware,
            storage=storage,
            pressure=pressure,
            models=models,
            diagnostics=diagnostics,
            providers=provider_statuses,
            health=self._health_view(),
            readiness=self._readiness_view(),
            integrations={
                "agent_loop": True,
                "mission_runtime": True,
                "model_router": True,
                "voice": False,
                "vision": False,
            },
            limitations=sorted(
                set(
                    [
                        *system.limitations,
                        *hardware.limitations,
                        *storage.limitations,
                        *pressure.limitations,
                        *models.limitations,
                        *diagnostics.limitations,
                    ]
                )
            ),
        )
        if persist:
            self._persist(report)
        self.events.emit(
            "insight.report_generated",
            "system_insight",
            {
                "provider": self.provider.name,
                "diagnostic_status": diagnostics.status,
                "pressure_level": pressure.overall_level,
                "available_models": models.available_models,
            },
        )
        return report

    def inspect(self) -> SystemInsight:
        """Compatibility projection for the established `/system/insight` contract."""
        report = self.report(persist=False)
        first_gpu = report.hardware.gpus[0] if report.hardware.gpus else None
        lmstudio = next(
            (
                provider
                for provider in report.models.providers
                if provider.get("provider_id") == "lmstudio"
            ),
            {},
        )
        recommendations = [
            LLMRecommendation(
                category=item.task,
                model_name=item.model_id or "No registered model",
                status=item.status,
                reason=item.reason,
                runtime_suggested=item.provider_id or "unavailable",
                estimated_ram_gb=item.estimated_ram_gb,
                estimated_vram_gb=item.estimated_vram_gb,
                model_id=item.model_id,
                provider=item.provider_id,
                source="registered_capabilities",
            )
            for item in report.models.recommendations
        ]
        return SystemInsight(
            mode="complete" if not report.limitations else "partial",
            checked_at=report.generated_at,
            operating_system=report.system.operating_system,
            os_version=report.system.os_version,
            architecture=report.system.architecture,
            cpu=report.hardware.cpu.model,
            logical_processors=report.hardware.cpu.logical_threads,
            memory_total_bytes=report.hardware.memory.total_bytes,
            memory_available_bytes=report.hardware.memory.available_bytes,
            disk_total_bytes=sum(item.total_bytes for item in report.storage.volumes),
            disk_free_bytes=sum(item.free_bytes for item in report.storage.volumes),
            python_version=report.system.python_version,
            git_available=False,
            git_version=None,
            gpu=first_gpu.name if first_gpu else None,
            gpu_memory_total_bytes=first_gpu.memory_total_bytes if first_gpu else None,
            gpu_memory_free_bytes=first_gpu.memory_free_bytes if first_gpu else None,
            lmstudio_available=bool(lmstudio.get("active")),
            lmstudio_model_count=int(lmstudio.get("model_count", 0)),
            lmstudio_message=None,
            real_checks=[
                "os",
                "system",
                "cpu",
                "memory",
                "storage",
                "processes",
                "providers",
                "models",
            ],
            planned_checks=[],
            llm_recommendations=recommendations,
            metadata={
                "provider": self.provider.name,
                "gpu_vendor": first_gpu.vendor if first_gpu else None,
                "limitations": report.limitations,
            },
        )

    def provider_statuses(self) -> list[dict[str, Any]]:
        report = self.model_capabilities.inspect()
        return [self.provider.status(), *report.providers]

    def agent_loop_guidance(self) -> dict[str, Any]:
        return self.resource_pressure.agent_loop_guidance()

    def mission_capacity(self) -> Any:
        return self.resource_pressure.assess_capacity("mission")

    def health(self, component: str | None = None) -> dict[str, Any]:
        status = self.provider.status()
        details: dict[str, Any] = {
            "status": "healthy" if status.get("status") == "available" else "degraded",
            "provider": self.provider.name,
            "read_only": True,
            "optional_resources_do_not_block_readiness": True,
        }
        if component == "model_availability":
            try:
                models = self.model_capabilities.model_hub.registry.list_models()
                providers = self.model_capabilities.model_hub.registry.list_providers()
            except Exception:
                models, providers = [], []
            details.update(
                {
                    "available_models": len(models),
                    "online_providers": sum(1 for provider in providers if provider.active),
                    "optional": True,
                }
            )
        return details

    def latest_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        paths = sorted(self.snapshots_root.glob("*.yaml"), reverse=True)[: max(0, min(limit, 100))]
        return [load_structured_file(path) for path in paths]

    def _persist(self, report: InsightReport) -> None:
        stamp = report.generated_at.replace(":", "-").replace("+", "_")
        dump_structured_file(self.snapshots_root / f"{stamp}.yaml", asdict(report))
        dump_structured_file(
            self.diagnostics_root / "latest.yaml",
            asdict(report.diagnostics),
        )
        paths = sorted(self.snapshots_root.glob("*.yaml"), reverse=True)
        for path in paths[self._snapshot_limit() :]:
            path.unlink(missing_ok=True)

    def _snapshot_limit(self) -> int:
        path = self.data_dir.resolve("config/insight_policy.yaml")
        if not path.exists():
            return 48
        raw = load_structured_file(path).get("persistence", {})
        return max(1, min(int(raw.get("max_snapshots", 48)), 500))

    def _health_view(self) -> dict[str, Any]:
        if self.health_runtime is None:
            return {"status": "not_bound"}
        summary = self.health_runtime.summary()
        return {"status": summary.status}

    def _readiness_view(self) -> dict[str, Any]:
        if self.readiness_runtime is None:
            return {"state": "not_bound"}
        summary = self.readiness_runtime.evaluate()
        return {"state": summary.state}


class SystemInsightRuntime(InsightRuntime):
    """Compatibility name for the canonical InsightRuntime composition root."""
