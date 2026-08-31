from __future__ import annotations

import importlib.util
import shutil
import subprocess
from typing import Any

from synapse.desktop_automation.errors import ActionFailed, ProviderUnavailable, TargetNotFound
from synapse.desktop_automation.models import (
    AutomationAction,
    Bounds,
    ElementSelector,
    UIElement,
    WindowInfo,
)
from synapse.desktop_automation.providers.common import (
    find_in_tree,
    process_applications,
    run_command,
    stable_id,
)


class LinuxATSPIProvider:
    name = "linux_atspi"
    semantic = True
    fallback_kind = None

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": importlib.util.find_spec("pyatspi") is not None,
            "window_discovery": bool(shutil.which("wmctrl")),
            "semantic": True,
        }

    def list_windows(self) -> list[WindowInfo]:
        executable = shutil.which("wmctrl")
        if not executable:
            raise ProviderUnavailable("wmctrl is unavailable")
        completed = run_command([executable, "-lpGx"])
        if completed.returncode != 0:
            raise ProviderUnavailable("Window manager did not expose a window list")
        windows = []
        for line in completed.stdout.splitlines():
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            handle, workspace, pid, left, top, width, height, _window_class, title = parts
            windows.append(
                WindowInfo(
                    window_id=f"x11:{handle.removeprefix('0x')}",
                    application_id=f"app:{pid}",
                    pid=int(pid),
                    title=title[:240],
                    state="normal",
                    foreground=False,
                    monitor=None,
                    workspace=workspace,
                    bounds=Bounds(int(left), int(top), int(width), int(height)),
                    provider=self.name,
                )
            )
        return windows

    def list_applications(self):
        return process_applications(self.name, self.list_windows())

    def accessibility_tree(self, window_id: str, max_nodes: int = 500) -> UIElement:
        window = next((item for item in self.list_windows() if item.window_id == window_id), None)
        if window is None:
            raise TargetNotFound("Window not found")
        pyatspi = self._atspi()
        desktop = pyatspi.Registry.getDesktop(0)
        for application in desktop:
            try:
                if int(application.get_process_id()) != window.pid:
                    continue
            except Exception:
                continue
            for child in application:
                if str(getattr(child, "name", "")) == window.title:
                    budget = [max(1, min(max_nodes, 500))]
                    return self._element(child, window_id, budget)
        raise TargetNotFound("Window has no AT-SPI accessibility tree")

    def find_elements(self, selector: ElementSelector, limit: int = 20) -> list[UIElement]:
        window_ids = (
            [selector.window_id]
            if selector.window_id
            else [w.window_id for w in self.list_windows()]
        )
        for window_id in window_ids:
            if not window_id:
                continue
            try:
                return find_in_tree(self.accessibility_tree(window_id), selector, limit)
            except TargetNotFound:
                continue
        raise TargetNotFound("No AT-SPI element matched")

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        if action.kind == "application.launch":
            application = _safe_application(action.application)
            subprocess.Popen(
                [application],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {"performed": True}
        if action.kind.startswith("window."):
            executable = shutil.which("wmctrl")
            if not executable or not action.window_id:
                raise ProviderUnavailable("wmctrl is unavailable")
            handle = "0x" + action.window_id.removeprefix("x11:")
            flags = {
                "window.focus": ["-ia", handle],
                "window.minimize": ["-ir", handle, "-b", "add,hidden"],
                "window.restore": ["-ir", handle, "-b", "remove,hidden"],
                "window.maximize": ["-ir", handle, "-b", "add,maximized_vert,maximized_horz"],
                "window.close": ["-ic", handle],
            }.get(action.kind)
            if not flags:
                raise ActionFailed(f"Unsupported window action: {action.kind}")
            completed = run_command([executable, *flags])
            if completed.returncode != 0:
                raise ActionFailed("Window manager action failed")
            return {"performed": True}
        target = element or self.find_elements(action.selector or ElementSelector(), 1)[0]
        accessible = self._resolve_accessible(target)
        if action.kind in {
            "element.invoke",
            "element.toggle",
            "element.select",
            "element.expand",
            "element.collapse",
        }:
            interface = accessible.queryAction()
            desired = {
                "element.invoke": ("click", "press", "activate"),
                "element.toggle": ("toggle", "click"),
                "element.select": ("select", "click"),
                "element.expand": ("expand",),
                "element.collapse": ("collapse",),
            }[action.kind]
            for index in range(interface.nActions):
                if interface.getName(index).casefold() in desired:
                    interface.doAction(index)
                    return {"performed": True, "element_id": target.element_id}
        if action.kind == "element.set_value":
            accessible.queryEditableText().setTextContents(str(action.arguments.get("value", "")))
            return {"performed": True, "element_id": target.element_id}
        if action.kind == "element.focus":
            accessible.grabFocus()
            return {"performed": True, "element_id": target.element_id}
        raise ActionFailed(f"AT-SPI action is unsupported: {action.kind}")

    def clipboard_get(self) -> str | None:
        command = _clipboard_command(read=True)
        completed = run_command(command)
        return completed.stdout if completed.returncode == 0 else None

    def clipboard_set(self, value: str) -> None:
        completed = run_command(_clipboard_command(read=False), input_text=value)
        if completed.returncode != 0:
            raise ActionFailed("Clipboard write failed")

    def clipboard_clear(self) -> None:
        self.clipboard_set("")

    def _atspi(self):
        if importlib.util.find_spec("pyatspi") is None:
            raise ProviderUnavailable("Python AT-SPI bindings are unavailable")
        import pyatspi

        return pyatspi

    def _element(self, accessible: Any, window_id: str, budget: list[int]) -> UIElement:
        budget[0] -= 1
        role = str(accessible.getRoleName() or "unknown")
        bounds = None
        try:
            extents = accessible.queryComponent().getExtents(0)
            bounds = Bounds(extents.x, extents.y, extents.width, extents.height)
        except Exception:
            pass
        children = []
        if budget[0] > 0:
            for child in accessible:
                if budget[0] <= 0:
                    break
                children.append(self._element(child, window_id, budget))
        name = str(getattr(accessible, "name", "") or "")[:240] or None
        value = None
        try:
            text = accessible.queryText()
            value = str(text.getText(0, min(text.characterCount, 4096)))
        except Exception:
            pass
        return UIElement(
            element_id=stable_id(window_id, role, name, bounds),
            window_id=window_id,
            automation_id=None,
            role=role,
            control_type=role,
            name=name,
            description=str(getattr(accessible, "description", "") or "")[:240] or None,
            value=value,
            enabled=True,
            focused=False,
            selected=None,
            expanded=None,
            toggled=None,
            range_value=None,
            bounds=bounds,
            patterns=[],
            children=children,
            provider=self.name,
        )

    def _resolve_accessible(self, target: UIElement):
        root = self.accessibility_tree(target.window_id)
        if not find_in_tree(root, ElementSelector(name=target.name, role=target.role), 1):
            raise TargetNotFound("AT-SPI element disappeared")
        window = next(item for item in self.list_windows() if item.window_id == target.window_id)
        pyatspi = self._atspi()
        desktop = pyatspi.Registry.getDesktop(0)
        queue = [item for app in desktop if int(app.get_process_id()) == window.pid for item in app]
        while queue:
            item = queue.pop(0)
            if str(item.getRoleName()) == target.role and str(
                getattr(item, "name", "") or ""
            ) == str(target.name or ""):
                return item
            queue.extend(list(item))
        raise TargetNotFound("AT-SPI element disappeared")


def _safe_application(value: str | None) -> str:
    application = str(value or "").strip()
    if not application or any(token in application for token in ("/", "\\", ":", "..")):
        raise ActionFailed("Application launch accepts a command name, not a private path")
    return application[:160]


def _clipboard_command(*, read: bool) -> list[str]:
    if shutil.which("wl-paste") and shutil.which("wl-copy"):
        return ["wl-paste", "--no-newline"] if read else ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard", "-o" if read else "-i"]
    raise ProviderUnavailable("No supported clipboard command is available")
