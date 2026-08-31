from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

import psutil

from synapse.desktop_automation.errors import ProviderUnavailable, TargetNotFound
from synapse.desktop_automation.models import ApplicationInfo, ElementSelector, UIElement


def run_command(
    command: list[str], timeout: float = 8.0, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "check": False,
        "input": input_text,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    try:
        return subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderUnavailable(type(exc).__name__) from exc


def process_applications(provider: str, windows: list[Any]) -> list[ApplicationInfo]:
    by_pid: dict[int, list[Any]] = {}
    for window in windows:
        by_pid.setdefault(window.pid, []).append(window)
    processes: dict[int, tuple[str, str]] = {}
    for process in psutil.process_iter(["pid", "name", "status"]):
        try:
            pid = int(process.info["pid"])
            processes[pid] = (
                str(process.info.get("name") or f"process-{pid}"),
                str(process.info.get("status") or "running"),
            )
        except (psutil.Error, OSError, TypeError, ValueError):
            continue
    for pid in by_pid:
        processes.setdefault(pid, (f"process-{pid}", "running"))
    results: list[ApplicationInfo] = []
    for pid, (name, state) in list(processes.items())[:500]:
        owned = by_pid.get(pid, [])
        executable_name = Path(name).name[:160]
        results.append(
            ApplicationInfo(
                application_id=f"app:{pid}",
                name=Path(name).stem[:160],
                pid=pid,
                executable_name=executable_name,
                state=state,
                foreground=any(item.foreground for item in owned),
                window_count=len(owned),
                provider=provider,
            )
        )
    return sorted(results, key=lambda item: (not item.foreground, item.name.lower(), item.pid))


def stable_id(*values: object) -> str:
    payload = "|".join(str(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:24]


def flatten(root: UIElement) -> list[UIElement]:
    pending = [root]
    values: list[UIElement] = []
    while pending:
        current = pending.pop(0)
        values.append(current)
        pending[0:0] = current.children
    return values


def matches(element: UIElement, selector: ElementSelector) -> bool:
    comparisons = (
        (selector.automation_id, element.automation_id),
        (selector.role, element.role),
        (selector.control_type, element.control_type),
        (selector.name, element.name),
        (selector.description, element.description),
        (selector.value, element.value),
        (selector.window_id, element.window_id),
    )
    return all(
        expected is None or str(actual or "").casefold() == str(expected).casefold()
        for expected, actual in comparisons
    )


def find_in_tree(root: UIElement, selector: ElementSelector, limit: int = 20) -> list[UIElement]:
    found = [element for element in flatten(root) if matches(element, selector)]
    if not found:
        raise TargetNotFound("No accessible element matched the semantic selector")
    return found[: max(1, min(limit, 100))]
