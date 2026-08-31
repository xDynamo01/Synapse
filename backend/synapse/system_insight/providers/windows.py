from __future__ import annotations

import json
import shutil
from typing import cast

from synapse.system_insight.models import GPUInfo
from synapse.system_insight.providers.common import (
    PsutilInsightProvider,
    gpu_vendor,
    nvidia_gpus,
    run_command,
)


class WindowsInsightProvider(PsutilInsightProvider):
    name = "windows"

    def collect_gpus(self) -> list[GPUInfo]:
        nvidia = nvidia_gpus(self.name)
        if nvidia:
            return nvidia
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return []
        completed = run_command(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress",
            ],
            timeout=5,
        )
        if completed is None or completed.returncode != 0 or not completed.stdout.strip():
            return []
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return []
        controllers = raw if isinstance(raw, list) else [raw]
        results: list[GPUInfo] = []
        for controller in controllers:
            if not isinstance(controller, dict) or not controller.get("Name"):
                continue
            name = str(controller["Name"])
            total = _positive_int(controller.get("AdapterRAM"))
            capabilities = _windows_capabilities(name)
            results.append(
                GPUInfo(
                    name=name,
                    vendor=gpu_vendor(name),
                    provider=self.name,
                    driver=str(controller.get("DriverVersion") or "") or None,
                    memory_total_bytes=total,
                    capabilities=capabilities,
                    limitations=["dynamic_vram_metrics_unavailable"],
                )
            )
        return results

    def collect_motherboard(self) -> dict[str, str]:
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return {}
        completed = run_command(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product | ConvertTo-Json -Compress",
            ],
            timeout=4,
        )
        if completed is None or completed.returncode != 0:
            return {}
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            key: str(value)[:160]
            for key, value in {
                "manufacturer": raw.get("Manufacturer"),
                "model": raw.get("Product"),
            }.items()
            if value
        }


def _positive_int(value: object) -> int | None:
    try:
        result = (
            int(cast(str | bytes | bytearray | int | float, value))
            if value is not None
            else 0
        )
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _windows_capabilities(name: str) -> list[str]:
    vendor = gpu_vendor(name)
    capabilities: list[str] = []
    if vendor == "nvidia" and shutil.which("nvidia-smi"):
        capabilities.append("cuda")
    if vendor == "amd" and (shutil.which("rocminfo") or shutil.which("rocm-smi")):
        capabilities.append("rocm")
    if shutil.which("clinfo"):
        capabilities.append("opencl")
    return capabilities
