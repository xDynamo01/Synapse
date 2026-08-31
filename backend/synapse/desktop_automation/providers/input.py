from __future__ import annotations

import ctypes
import json
import os
import shutil
from typing import Any

from synapse.desktop_automation.errors import ActionFailed, ProviderUnavailable
from synapse.desktop_automation.models import AutomationAction, UIElement
from synapse.desktop_automation.providers.common import run_command


class WindowsInputProvider:
    name = "windows_input"

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        if os.name != "nt":
            raise ProviderUnavailable("Windows input is unavailable")
        if action.kind in {"input.click", "element.invoke", "element.focus"}:
            x, y = _element_center(element)
            user32 = ctypes.windll.user32
            if not user32.SetCursorPos(x, y):
                raise ActionFailed("Pointer positioning failed")
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            return {"performed": True, "fallback": "element_relative_pointer"}
        if action.kind == "input.scroll":
            x, y = _element_center(element)
            user32 = ctypes.windll.user32
            if not user32.SetCursorPos(x, y):
                raise ActionFailed("Pointer positioning failed")
            delta = max(-1200, min(1200, int(action.arguments.get("delta", 0))))
            user32.mouse_event(0x0800, 0, 0, delta, 0)
            return {"performed": True, "fallback": "element_relative_scroll"}
        if action.kind == "input.drag_drop":
            x, y = _element_center(element)
            target = action.arguments.get("target_bounds", {})
            tx = int(target.get("left", 0)) + int(target.get("width", 0)) // 2
            ty = int(target.get("top", 0)) + int(target.get("height", 0)) // 2
            user32 = ctypes.windll.user32
            user32.SetCursorPos(x, y)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.SetCursorPos(tx, ty)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            return {"performed": True, "fallback": "element_relative_drag_drop"}
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            raise ProviderUnavailable("PowerShell input fallback is unavailable")
        if action.kind == "input.type":
            value = str(action.arguments.get("value", ""))
            script = "Add-Type -AssemblyName System.Windows.Forms;$v=[Console]::In.ReadToEnd();[Windows.Forms.SendKeys]::SendWait($v)"
            completed = run_command(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                input_text=value,
            )
        elif action.kind == "input.hotkey":
            keys = str(action.arguments.get("keys", ""))
            completed = run_command(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Add-Type -AssemblyName System.Windows.Forms;$v=[Console]::In.ReadToEnd();[Windows.Forms.SendKeys]::SendWait($v)",
                ],
                input_text=keys,
            )
        else:
            raise ActionFailed(f"Unsupported Windows input fallback: {action.kind}")
        if completed.returncode != 0:
            raise ActionFailed("Windows input fallback failed")
        return {"performed": True, "fallback": "keyboard"}


class LinuxInputProvider:
    name = "linux_input"

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        executable = shutil.which("xdotool")
        if not executable:
            raise ProviderUnavailable("xdotool is unavailable")
        if action.kind in {"input.click", "element.invoke", "element.focus"}:
            x, y = _element_center(element)
            args = ["mousemove", str(x), str(y), "click", "1"]
        elif action.kind == "input.type":
            args = ["type", "--clearmodifiers", "--file", "-"]
        elif action.kind == "input.hotkey":
            args = ["key", "--clearmodifiers", str(action.arguments.get("keys", ""))]
        elif action.kind == "input.scroll":
            delta = max(-20, min(20, int(action.arguments.get("delta", 0))))
            button = "4" if delta > 0 else "5"
            args = ["click", "--repeat", str(abs(delta)), button]
        elif action.kind == "input.drag_drop":
            x, y = _element_center(element)
            target = action.arguments.get("target_bounds", {})
            tx = int(target.get("left", 0)) + int(target.get("width", 0)) // 2
            ty = int(target.get("top", 0)) + int(target.get("height", 0)) // 2
            args = [
                "mousemove",
                str(x),
                str(y),
                "mousedown",
                "1",
                "mousemove",
                str(tx),
                str(ty),
                "mouseup",
                "1",
            ]
        else:
            raise ActionFailed(f"Unsupported Linux input fallback: {action.kind}")
        completed = run_command(
            [executable, *args],
            input_text=(
                str(action.arguments.get("value", "")) if action.kind == "input.type" else None
            ),
        )
        if completed.returncode != 0:
            raise ActionFailed("Linux input fallback failed")
        return {"performed": True, "fallback": "xdotool"}


class MacOSInputProvider:
    name = "macos_input"

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        executable = shutil.which("osascript")
        if not executable:
            raise ProviderUnavailable("osascript is unavailable")
        if action.kind == "input.type":
            payload = json.dumps(str(action.arguments.get("value", "")))
            script = f'tell application "System Events" to keystroke {payload}'
        elif action.kind == "input.hotkey":
            key, modifiers = _mac_hotkey(str(action.arguments.get("keys", "")))
            modifier_text = ", ".join(f"{item} down" for item in modifiers)
            script = (
                f'tell application "System Events" to keystroke {json.dumps(key)} '
                f"using {{{modifier_text}}}"
            )
        elif action.kind in {
            "input.click",
            "input.scroll",
            "input.drag_drop",
            "element.invoke",
            "element.focus",
        }:
            click = shutil.which("cliclick")
            if not click:
                raise ProviderUnavailable("cliclick is unavailable for pointer fallback")
            x, y = _element_center(element)
            if action.kind in {"input.click", "element.invoke", "element.focus"}:
                arguments = [f"c:{x},{y}"]
            elif action.kind == "input.scroll":
                arguments = [f"m:{x},{y}", f"w:{int(action.arguments.get('delta', 0))}"]
            else:
                target = action.arguments.get("target_bounds", {})
                tx = int(target.get("left", 0)) + int(target.get("width", 0)) // 2
                ty = int(target.get("top", 0)) + int(target.get("height", 0)) // 2
                arguments = [f"dd:{x},{y}", f"du:{tx},{ty}"]
            completed = run_command([click, *arguments])
            if completed.returncode != 0:
                raise ActionFailed("macOS pointer fallback failed")
            return {"performed": True, "fallback": "cliclick"}
        else:
            raise ActionFailed("macOS pointer fallback is unavailable without an element action")
        completed = run_command([executable, "-"], input_text=script)
        if completed.returncode != 0:
            raise ActionFailed("macOS input fallback failed")
        return {"performed": True, "fallback": "system_events"}


def platform_input_provider(system_name: str):
    mapping = {
        "Windows": WindowsInputProvider,
        "Linux": LinuxInputProvider,
        "Darwin": MacOSInputProvider,
    }
    provider_type = mapping.get(system_name)
    if provider_type is None:
        raise ProviderUnavailable(f"No input provider for platform: {system_name}")
    return provider_type()


def _element_center(element: UIElement | None) -> tuple[int, int]:
    if element is None or element.bounds is None:
        raise ActionFailed("Element-relative input requires current measured bounds")
    if element.bounds.width <= 0 or element.bounds.height <= 0:
        raise ActionFailed("Element bounds are not actionable")
    return (
        element.bounds.left + element.bounds.width // 2,
        element.bounds.top + element.bounds.height // 2,
    )


def _mac_hotkey(value: str) -> tuple[str, list[str]]:
    aliases = {
        "cmd": "command",
        "command": "command",
        "shift": "shift",
        "alt": "option",
        "option": "option",
        "ctrl": "control",
        "control": "control",
    }
    parts = [item.strip().casefold() for item in value.split("+") if item.strip()]
    if len(parts) < 2 or parts[-1] in aliases or any(item not in aliases for item in parts[:-1]):
        raise ActionFailed("Invalid semantic macOS hotkey")
    return parts[-1], [aliases[item] for item in parts[:-1] if item in aliases]
