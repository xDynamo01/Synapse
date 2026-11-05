from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from synapse.agents.models import AgentConfig
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.model_router import ModelRouter
from synapse.model_hub.models import ModelCatalogEntry, ModelProviderInfo
from synapse.model_hub.registry import ModelHubRegistry
from synapse.models.adapters import MockModelAdapter
from synapse.system_insight.models import (
    CPUInfo,
    DiskSnapshot,
    DiskVolume,
    GPUInfo,
    HardwareSnapshot,
    MemoryInfo,
    ProcessInfo,
    ProcessSnapshot,
    SystemSnapshot,
)
from synapse.system_insight.runtime import InsightRuntime

from .world_attention_support import DomainFixture, FixedDecisionRuntime, loop

GIB = 1024**3


class SnapshotProvider:
    name = "acceptance"

    def __init__(
        self,
        *,
        gpus: list[GPUInfo] | None = None,
        memory_used: int = 4 * GIB,
        memory_total: int = 32 * GIB,
        cpu_percent: float = 20.0,
    ) -> None:
        self.gpus = gpus or []
        self.memory_used = memory_used
        self.memory_total = memory_total
        self.cpu_percent = cpu_percent

    def collect_system(self) -> SystemSnapshot:
        return SystemSnapshot(
            provider=self.name,
            collected_at="2026-07-13T12:00:00+00:00",
            operating_system="AcceptanceOS",
            os_version="1",
            architecture="x86_64",
            kernel="1",
            hostname="redacted",
            user="redacted",
            uptime_seconds=3600,
            boot_time="2026-07-13T11:00:00+00:00",
            timezone="UTC",
            locale="en_US",
            python_version="3.12",
        )

    def collect_hardware(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            provider=self.name,
            collected_at="2026-07-13T12:00:00+00:00",
            cpu=CPUInfo("Acceptance CPU", "x86_64", 8, 16, self.cpu_percent),
            memory=MemoryInfo(
                total_bytes=self.memory_total,
                available_bytes=self.memory_total - self.memory_used,
                used_bytes=self.memory_used,
                usage_percent=self.memory_used / self.memory_total * 100,
                swap_total_bytes=0,
                swap_used_bytes=0,
                swap_percent=0,
            ),
            gpus=self.gpus,
            limitations=[] if self.gpus else ["gpu_not_detected"],
        )

    def collect_storage(self) -> DiskSnapshot:
        return DiskSnapshot(
            provider=self.name,
            collected_at="2026-07-13T12:00:00+00:00",
            volumes=[DiskVolume("system", "testfs", 100 * GIB, 20 * GIB, 80 * GIB, 20.0)],
        )

    def collect_processes(self, limit: int = 100) -> ProcessSnapshot:
        processes = [ProcessInfo(42, 1, "synapse", 1.0, 128 * 1024**2, 0.4, True)]
        return ProcessSnapshot(self.name, "2026-07-13T12:00:00+00:00", 1, processes[:limit], False)

    def status(self) -> dict[str, object]:
        return {"provider_id": self.name, "status": "available", "active": True}


class FakeModelHub:
    def __init__(
        self,
        models: list[ModelCatalogEntry] | None = None,
        providers: list[ModelProviderInfo] | None = None,
    ) -> None:
        self.registry = ModelHubRegistry()
        self.registry.replace_models(models or [])
        self.registry.replace_providers(providers or [])


def _provider(provider_id: str, *, active: bool = True) -> ModelProviderInfo:
    return ModelProviderInfo(
        provider_id=provider_id,
        display_name=provider_id,
        status="available" if active else "offline",
        endpoint=None,
        active=active,
        default_model=None,
        model_count=1,
        last_refreshed_at="2026-07-13T12:00:00+00:00",
    )


def _model(
    model_id: str,
    provider: str = "local",
    *,
    ram: float = 4,
    vram: float | None = None,
    cpu: bool = True,
    capabilities: list[str] | None = None,
) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        id=model_id,
        name=model_id,
        provider=provider,
        runtime=provider,
        origin="registered",
        type="chat",
        availability_state="available",
        chat_usable=True,
        estimated_ram_gb=ram,
        estimated_vram_gb=vram,
        cpu_compatible=cpu,
        metadata={"capabilities": capabilities or ["chat", "coding", "reasoning"]},
    )


def _insight(provider: SnapshotProvider, hub: FakeModelHub):
    directory = tempfile.TemporaryDirectory()
    data_dir = DataDir(Path(directory.name))
    data_dir.bootstrap()
    insight = InsightRuntime(data_dir, EventBus(data_dir.root), hub, provider)
    return directory, insight


def test_cpu_only_machine_recommends_only_registered_cpu_model() -> None:
    directory, insight = _insight(
        SnapshotProvider(),
        FakeModelHub([_model("cpu-model")], [_provider("local")]),
    )
    with directory:
        report = insight.report(persist=False)

    assert report.hardware.gpus == []
    assert report.models.recommendations[0].model_id == "cpu-model"


def test_amd_rocm_and_nvidia_cuda_are_reported_from_provider_evidence() -> None:
    for gpu, capability in (
        (GPUInfo("Radeon", "amd", "linux", capabilities=["rocm"]), "rocm"),
        (GPUInfo("RTX", "nvidia", "linux", capabilities=["cuda"]), "cuda"),
    ):
        directory, insight = _insight(SnapshotProvider(gpus=[gpu]), FakeModelHub())
        with directory:
            hardware = insight.hardware.inspect()
        assert capability in hardware.gpus[0].capabilities


def test_no_models_and_multiple_providers_are_honest() -> None:
    directory, insight = _insight(
        SnapshotProvider(),
        FakeModelHub([], [_provider("online"), _provider("offline", active=False)]),
    )
    with directory:
        report = insight.model_capabilities.inspect()

    assert report.available_models == 0
    assert report.online_providers == 1
    assert all(item.status == "unavailable" for item in report.recommendations)
    assert "no_registered_models" in report.limitations


def test_registered_model_remains_visible_when_current_resources_are_low() -> None:
    directory, insight = _insight(
        SnapshotProvider(memory_used=15 * GIB, memory_total=16 * GIB),
        FakeModelHub(
            [_model("installed-local-model", ram=4, provider="synapse_local")],
            [_provider("synapse_local")],
        ),
    )
    with directory:
        report = insight.model_capabilities.inspect()

    assert report.available_models == 1
    assert report.online_providers == 1
    assert report.recommendations[0].model_id == "installed-local-model"
    assert report.recommendations[0].provider_id == "synapse_local"
    assert report.recommendations[0].status == "limited"


def test_multimodal_projector_is_not_recommended_as_chat_model() -> None:
    directory, insight = _insight(
        SnapshotProvider(memory_used=15 * GIB, memory_total=16 * GIB),
        FakeModelHub(
            [
                _model(
                    "synapse-local:repo/mmproj-model.gguf",
                    provider="synapse_local",
                    ram=1,
                    capabilities=[],
                ),
                _model("synapse-local:repo/chat-model.gguf", provider="synapse_local", ram=4),
            ],
            [_provider("synapse_local")],
        ),
    )
    with directory:
        report = insight.model_capabilities.inspect()

    assert report.recommendations[0].model_id == "synapse-local:repo/chat-model.gguf"


def test_vram_drop_changes_recommendation_to_smaller_registered_model() -> None:
    gpu = GPUInfo(
        "RTX",
        "nvidia",
        "acceptance",
        memory_total_bytes=16 * GIB,
        memory_used_bytes=2 * GIB,
        memory_free_bytes=14 * GIB,
        capabilities=["cuda"],
    )
    provider = SnapshotProvider(gpus=[gpu])
    directory, insight = _insight(
        provider,
        FakeModelHub(
            [
                _model("small", ram=4, vram=2, cpu=False),
                _model("large", ram=12, vram=12, cpu=False),
            ],
            [_provider("local")],
        ),
    )
    with directory:
        before = insight.model_capabilities.recommend("chat")
        provider.gpus = [replace(gpu, memory_used_bytes=14 * GIB, memory_free_bytes=2 * GIB)]
        after = insight.model_capabilities.recommend("chat")

    assert before.model_id == "large"
    assert after.model_id == "small"


def test_agent_loop_reduces_autonomy_under_critical_measured_pressure() -> None:
    fixture = DomainFixture()
    try:
        provider = SnapshotProvider(memory_used=31 * GIB, memory_total=32 * GIB)
        insight = InsightRuntime(fixture.data_dir, fixture.events, FakeModelHub(), provider)
        fixture.high_item("notify")
        runtime = loop(fixture, FixedDecisionRuntime("notify"), insight_runtime=insight)

        result = runtime.run_cycle("acceptance")

        assert result.disposition == "record_only"
        assert result.action_result is not None
        assert result.action_result.side_effects == []
        assert result.action_result.evidence == [{"disposition": "record_only"}]
    finally:
        fixture.close()


def test_mission_is_deferred_when_capacity_is_critically_insufficient() -> None:
    directory = tempfile.TemporaryDirectory()
    try:
        runtime = create_runtime(
            Settings(
                project_root=Path(__file__).resolve().parents[2],
                data_dir=Path(directory.name) / "data",
                host="127.0.0.1",
                port=8717,
                default_actor_id="local_owner",
            )
        )
        insight = InsightRuntime(
            runtime.data_dir,
            runtime.events,
            FakeModelHub(),
            SnapshotProvider(memory_used=127 * GIB, memory_total=128 * GIB),
        )
        runtime.missions.resource_pressure = insight.resource_pressure
        mission = runtime.missions.create_mission(
            "Capacity guarded mission",
            metadata={"resource_pressure_guard": True},
        )

        result = runtime.missions.dispatch_ready_tasks(mission.mission_id)

        assert result.skipped[0]["reason"] == "resource_pressure"
    finally:
        directory.cleanup()


def test_model_router_switches_to_smaller_registered_model() -> None:
    gpu = GPUInfo(
        "RTX",
        "nvidia",
        "acceptance",
        memory_total_bytes=8 * GIB,
        memory_used_bytes=6 * GIB,
        memory_free_bytes=2 * GIB,
        capabilities=["cuda"],
    )
    directory, insight = _insight(
        SnapshotProvider(gpus=[gpu]),
        FakeModelHub(
            [_model("small", ram=4, vram=2, cpu=False), _model("large", ram=12, vram=8, cpu=False)],
            [_provider("local")],
        ),
    )
    with directory:
        router = ModelRouter(
            {"models": {"default_provider": "local", "providers": {"local": {"model": "large"}}}},
            adapters={"local": MockModelAdapter()},
        )
        router.model_capabilities = insight.model_capabilities
        selection = router.resolve_selection(AgentConfig("agent", "Agent", "tester"))

    assert selection.model_id == "small"
    assert selection.source == "resource_recommendation"


def test_diagnostics_are_evidence_based_and_persisted_report_omits_process_list() -> None:
    provider = SnapshotProvider(memory_used=31 * GIB, memory_total=32 * GIB)
    directory, insight = _insight(provider, FakeModelHub())
    with directory:
        report = insight.report()
        persisted = next(insight.snapshots_root.glob("*.yaml")).read_text(encoding="utf-8")

    assert report.diagnostics.findings
    assert all(finding.evidence for finding in report.diagnostics.findings)
    assert "synapse_process" not in persisted
    assert "redacted" in persisted
