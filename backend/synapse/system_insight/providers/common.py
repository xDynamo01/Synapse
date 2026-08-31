from __future__ import annotations

import locale
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

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


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def run_command(
    command: list[str], timeout: float = 4.0
) -> subprocess.CompletedProcess[str] | None:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    try:
        return subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


def gpu_vendor(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("nvidia", "geforce", "quadro", "rtx", "gtx")):
        return "nvidia"
    if any(token in lowered for token in ("amd", "radeon", "ati")):
        return "amd"
    if "intel" in lowered:
        return "intel"
    if "apple" in lowered:
        return "apple"
    return "unknown"


def nvidia_gpus(provider: str) -> list[GPUInfo]:
    completed = run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.used,memory.free,"
            "utilization.gpu,temperature.gpu,clocks.current.graphics",
            "--format=csv,noheader,nounits",
        ]
    )
    if completed is None or completed.returncode != 0:
        return []
    results: list[GPUInfo] = []
    for line in completed.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 8 or not parts[0]:
            continue
        numeric = [_number(item) for item in parts[2:]]
        results.append(
            GPUInfo(
                name=parts[0],
                vendor="nvidia",
                provider=provider,
                driver=parts[1] or None,
                memory_total_bytes=_mib(numeric[0]),
                memory_used_bytes=_mib(numeric[1]),
                memory_free_bytes=_mib(numeric[2]),
                usage_percent=numeric[3],
                temperature_celsius=numeric[4],
                clock_mhz=numeric[5],
                capabilities=["cuda"],
            )
        )
    return results


def _number(value: str) -> float | None:
    try:
        return float(value) if value not in {"", "N/A", "[Not Supported]"} else None
    except ValueError:
        return None


def _mib(value: float | None) -> int | None:
    return int(value * 1024 * 1024) if value is not None else None


class PsutilInsightProvider:
    name = "psutil"

    def collect_system(self) -> SystemSnapshot:
        boot_timestamp = psutil.boot_time()
        boot_time = datetime.fromtimestamp(boot_timestamp, UTC)
        now = datetime.now(UTC)
        timezone = datetime.now().astimezone().tzname() or "unknown"
        locale_name = locale.getlocale()[0]
        return SystemSnapshot(
            provider=self.name,
            collected_at=now.isoformat(),
            operating_system=platform.system() or "unknown",
            os_version=platform.version() or "unknown",
            architecture=platform.machine() or "unknown",
            kernel=platform.release() or "unknown",
            hostname="[REDACTED]",
            user="[REDACTED]",
            uptime_seconds=max(0.0, (now - boot_time).total_seconds()),
            boot_time=boot_time.isoformat(),
            timezone=timezone,
            locale=locale_name,
            python_version=platform.python_version(),
            limitations=["hostname_redacted", "user_redacted"],
        )

    def collect_hardware(self) -> HardwareSnapshot:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        frequencies = psutil.cpu_freq()
        temperatures, sensors = self._temperatures()
        battery = psutil.sensors_battery()
        batteries = []
        if battery is not None:
            batteries.append(
                {
                    "percent": float(battery.percent),
                    "plugged": bool(battery.power_plugged),
                    "seconds_left": None if battery.secsleft < 0 else int(battery.secsleft),
                }
            )
        cpu_temperature = next((item["current_celsius"] for item in sensors), None)
        cpu = CPUInfo(
            model=platform.processor().strip() or "unknown",
            architecture=platform.machine() or "unknown",
            physical_cores=psutil.cpu_count(logical=False),
            logical_threads=psutil.cpu_count(logical=True) or 0,
            usage_percent=float(psutil.cpu_percent(interval=0.0)),
            frequency_mhz=float(frequencies.current) if frequencies else None,
            temperature_celsius=cpu_temperature,
        )
        memory_info = MemoryInfo(
            total_bytes=int(memory.total),
            available_bytes=int(memory.available),
            used_bytes=int(memory.used),
            usage_percent=float(memory.percent),
            swap_total_bytes=int(swap.total),
            swap_used_bytes=int(swap.used),
            swap_percent=float(swap.percent),
        )
        gpus = self.collect_gpus()
        limitations: list[str] = []
        if not gpus:
            limitations.append("gpu_not_detected")
        if not temperatures:
            limitations.append("temperature_sensors_unavailable")
        return HardwareSnapshot(
            provider=self.name,
            collected_at=now_iso(),
            cpu=cpu,
            memory=memory_info,
            gpus=gpus,
            motherboard=self.collect_motherboard(),
            sensors=sensors,
            batteries=batteries,
            limitations=limitations,
        )

    def collect_storage(self) -> DiskSnapshot:
        volumes: list[DiskVolume] = []
        for index, partition in enumerate(psutil.disk_partitions(all=False), start=1):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (OSError, PermissionError):
                continue
            volumes.append(
                DiskVolume(
                    volume_id=f"volume-{index}",
                    filesystem=partition.fstype or "unknown",
                    total_bytes=int(usage.total),
                    used_bytes=int(usage.used),
                    free_bytes=int(usage.free),
                    usage_percent=float(usage.percent),
                    removable=self._is_removable(partition),
                )
            )
        counters = psutil.disk_io_counters()
        io: dict[str, int | float | None] = {
            "read_bytes": int(counters.read_bytes) if counters else None,
            "write_bytes": int(counters.write_bytes) if counters else None,
            "read_count": int(counters.read_count) if counters else None,
            "write_count": int(counters.write_count) if counters else None,
        }
        return DiskSnapshot(
            provider=self.name,
            collected_at=now_iso(),
            volumes=volumes,
            io=io,
            limitations=[] if counters else ["disk_io_unavailable"],
        )

    def collect_processes(self, limit: int = 100) -> ProcessSnapshot:
        current_pid = os.getpid()
        processes: list[ProcessInfo] = []
        total = 0
        for process in psutil.process_iter(
            ["pid", "ppid", "name", "cpu_percent", "memory_info", "memory_percent"]
        ):
            total += 1
            try:
                info = process.info
                memory_info = info.get("memory_info")
                name = str(info.get("name") or "unknown")[:160]
                processes.append(
                    ProcessInfo(
                        pid=int(info["pid"]),
                        parent_pid=int(info["ppid"]) if info.get("ppid") is not None else None,
                        name=name,
                        cpu_percent=float(info.get("cpu_percent") or 0.0),
                        memory_bytes=int(memory_info.rss) if memory_info else 0,
                        memory_percent=float(info.get("memory_percent") or 0.0),
                        synapse_process=int(info["pid"]) == current_pid
                        or "synapse" in name.lower(),
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, TypeError, ValueError):
                continue
        processes.sort(key=lambda item: (item.memory_bytes, item.cpu_percent), reverse=True)
        bounded = processes[: max(1, min(limit, 500))]
        return ProcessSnapshot(
            provider=self.name,
            collected_at=now_iso(),
            total_processes=total,
            processes=bounded,
            truncated=len(processes) > len(bounded),
            limitations=["command_lines_and_paths_redacted"],
        )

    def collect_gpus(self) -> list[GPUInfo]:
        return nvidia_gpus(self.name)

    def collect_motherboard(self) -> dict[str, str]:
        return {}

    def status(self) -> dict[str, object]:
        return {"provider": self.name, "status": "available", "read_only": True}

    def _temperatures(self) -> tuple[dict[str, list[Any]], list[dict[str, Any]]]:
        try:
            temperatures = psutil.sensors_temperatures(fahrenheit=False)
        except (AttributeError, OSError):
            temperatures = {}
        sensors: list[dict[str, Any]] = []
        for group, entries in temperatures.items():
            for entry in entries[:8]:
                if entry.current is None:
                    continue
                sensors.append(
                    {
                        "group": str(group)[:80],
                        "label": str(entry.label or "sensor")[:80],
                        "current_celsius": float(entry.current),
                        "high_celsius": float(entry.high) if entry.high is not None else None,
                    }
                )
        return temperatures, sensors[:32]

    @staticmethod
    def _is_removable(partition: Any) -> bool | None:
        options = str(getattr(partition, "opts", "")).lower()
        if "removable" in options:
            return True
        device = Path(str(getattr(partition, "device", ""))).name.lower()
        if device.startswith(("loop", "ram")):
            return False
        return None
