from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.api.routes import router
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.system_insight.providers.linux import LinuxInsightProvider
from synapse.system_insight.providers.macos import MacOSInsightProvider
from synapse.system_insight.providers.windows import WindowsInsightProvider


def _runtime(directory: str):
    return create_runtime(
        Settings(
            project_root=PROJECT_ROOT,
            data_dir=Path(directory) / "data",
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
    )


def test_scanner_reports_real_local_values_and_honest_gaps() -> None:
    with tempfile.TemporaryDirectory() as directory:
        insight = _runtime(directory).system_insight.inspect()

    assert insight.mode in {"complete", "partial"}
    assert insight.logical_processors > 0
    assert insight.disk_total_bytes > 0
    assert insight.memory_available_bytes is not None
    assert insight.operating_system
    assert "os" in insight.real_checks
    assert insight.planned_checks == []
    assert insight.llm_recommendations


def test_api_returns_canonical_and_compatibility_views() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = _runtime(directory)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        assert client.get("/api/system/insight").status_code == 200
        report = client.get("/api/insight/report")
        assert report.status_code == 200
        assert report.json()["integrations"]["model_router"] is True
        assert client.get("/api/hardware").json()["provider"]
        assert client.get("/api/processes?limit=2").json()["total_processes"] >= 1


def test_operational_commands_and_optional_health_are_non_destructive() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = _runtime(directory)
        command = runtime.commands.execute(runtime.context(), "/model-recommendations")
        components = {item.component_id: item for item in runtime.health.component_health()}
        readiness = runtime.readiness.evaluate()

    assert command.status == "ok"
    assert "insight" in command.data
    assert components["gpu"].ready
    assert components["model_availability"].ready
    assert components["model_availability"].metadata["optional"] is True
    assert all(not check.id.startswith("gpu.") for check in readiness.checks)


def test_windows_cim_fallback_detects_amd_without_claiming_rocm() -> None:
    payload = json.dumps(
        {"Name": "AMD Radeon RX 7600", "AdapterRAM": 8589934592, "DriverVersion": "1.2"}
    )
    completed = subprocess.CompletedProcess(["powershell"], 0, stdout=payload)
    with (
        patch("synapse.system_insight.providers.windows.nvidia_gpus", return_value=[]),
        patch(
            "synapse.system_insight.providers.windows.shutil.which",
            side_effect=lambda name: "powershell" if name == "powershell" else None,
        ),
        patch("synapse.system_insight.providers.windows.run_command", return_value=completed),
    ):
        gpus = WindowsInsightProvider().collect_gpus()

    assert gpus[0].vendor == "amd"
    assert gpus[0].memory_total_bytes == 8589934592
    assert "rocm" not in gpus[0].capabilities


def test_linux_rocm_provider_reports_measured_vram() -> None:
    payload = json.dumps(
        {
            "card0": {
                "Card series": "AMD Radeon PRO",
                "VRAM Total Memory (B)": "17179869184",
                "VRAM Total Used Memory (B)": "4294967296",
            }
        }
    )
    completed = subprocess.CompletedProcess(["rocm-smi"], 0, stdout=payload)
    with (
        patch("synapse.system_insight.providers.linux.nvidia_gpus", return_value=[]),
        patch(
            "synapse.system_insight.providers.linux.shutil.which",
            side_effect=lambda name: name if name == "rocm-smi" else None,
        ),
        patch("synapse.system_insight.providers.linux.run_command", return_value=completed),
    ):
        gpu = LinuxInsightProvider().collect_gpus()[0]

    assert gpu.capabilities == ["rocm"]
    assert gpu.memory_free_bytes == 12884901888


def test_macos_provider_reports_metal_capability() -> None:
    payload = json.dumps(
        {"SPDisplaysDataType": [{"sppci_model": "Apple M4 GPU", "spdisplays_metal": "Supported"}]}
    )
    completed = subprocess.CompletedProcess(["system_profiler"], 0, stdout=payload)
    with patch("synapse.system_insight.providers.macos.run_command", return_value=completed):
        gpu = MacOSInsightProvider().collect_gpus()[0]

    assert gpu.vendor == "apple"
    assert gpu.capabilities == ["metal"]
