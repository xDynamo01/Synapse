from __future__ import annotations

import json

from synapse.system_insight.models import GPUInfo
from synapse.system_insight.providers.common import PsutilInsightProvider, gpu_vendor, run_command


class MacOSInsightProvider(PsutilInsightProvider):
    name = "macos"

    def collect_gpus(self) -> list[GPUInfo]:
        completed = run_command(["system_profiler", "SPDisplaysDataType", "-json"], timeout=6)
        if completed is None or completed.returncode != 0:
            return []
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return []
        results = []
        for item in raw.get("SPDisplaysDataType", []) if isinstance(raw, dict) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("sppci_model") or item.get("_name") or "unknown")
            vendor = gpu_vendor(name)
            capabilities = ["metal"] if vendor == "apple" or "metal" in str(item).lower() else []
            results.append(
                GPUInfo(
                    name=name,
                    vendor=vendor,
                    provider=self.name,
                    driver=str(item.get("spdisplays_gmux-version") or "") or None,
                    capabilities=capabilities,
                    limitations=["dynamic_vram_metrics_unavailable"],
                )
            )
        return results

    def collect_motherboard(self) -> dict[str, str]:
        completed = run_command(["system_profiler", "SPHardwareDataType", "-json"], timeout=6)
        if completed is None or completed.returncode != 0:
            return {}
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {}
        items = raw.get("SPHardwareDataType", []) if isinstance(raw, dict) else []
        if not items or not isinstance(items[0], dict):
            return {}
        model = items[0].get("machine_model") or items[0].get("machine_name")
        return (
            {"manufacturer": "Apple", "model": str(model)[:160]}
            if model
            else {"manufacturer": "Apple"}
        )
