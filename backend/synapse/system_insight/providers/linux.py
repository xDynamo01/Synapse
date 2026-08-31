from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import cast

from synapse.system_insight.models import GPUInfo
from synapse.system_insight.providers.common import (
    PsutilInsightProvider,
    gpu_vendor,
    nvidia_gpus,
    run_command,
)


class LinuxInsightProvider(PsutilInsightProvider):
    name = "linux"

    def collect_gpus(self) -> list[GPUInfo]:
        nvidia = nvidia_gpus(self.name)
        if nvidia:
            return nvidia
        rocm = _rocm_gpus(self.name)
        if rocm:
            return rocm
        completed = run_command(["lspci"], timeout=3) if shutil.which("lspci") else None
        if completed is None or completed.returncode != 0:
            return []
        results = []
        for line in completed.stdout.splitlines():
            if not any(token in line.lower() for token in ("vga", "3d controller", "display")):
                continue
            name = line.split(": ", 1)[-1].strip()
            capabilities = ["opencl"] if shutil.which("clinfo") else []
            results.append(
                GPUInfo(
                    name=name,
                    vendor=gpu_vendor(name),
                    provider=self.name,
                    capabilities=capabilities,
                    limitations=["vram_and_utilization_unavailable"],
                )
            )
        return results

    def collect_motherboard(self) -> dict[str, str]:
        values = {}
        for key, path in {
            "manufacturer": Path("/sys/class/dmi/id/board_vendor"),
            "model": Path("/sys/class/dmi/id/board_name"),
        }.items():
            try:
                value = path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                continue
            if value:
                values[key] = value[:160]
        return values


def _rocm_gpus(provider: str) -> list[GPUInfo]:
    executable = shutil.which("rocm-smi")
    if not executable:
        return []
    completed = run_command([executable, "--showproductname", "--showmeminfo", "vram", "--json"])
    if completed is None or completed.returncode != 0:
        return []
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    results = []
    for card, details in raw.items() if isinstance(raw, dict) else []:
        if not isinstance(details, dict):
            continue
        name = str(details.get("Card series") or details.get("Card model") or card)
        total = _first_int(details, "VRAM Total Memory (B)")
        used = _first_int(details, "VRAM Total Used Memory (B)")
        results.append(
            GPUInfo(
                name=name,
                vendor="amd",
                provider=provider,
                memory_total_bytes=total,
                memory_used_bytes=used,
                memory_free_bytes=max(0, total - used)
                if total is not None and used is not None
                else None,
                capabilities=["rocm"],
            )
        )
    return results


def _first_int(details: dict[str, object], key: str) -> int | None:
    value = details.get(key)
    try:
        return (
            int(cast(str | bytes | bytearray | int | float, value))
            if value is not None
            else None
        )
    except (TypeError, ValueError):
        return None
