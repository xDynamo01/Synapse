from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from acceptance.test_desktop_automation_e2e import (
    ConformanceInputProvider,
    ConformanceProvider,
    _rule,
)
from synapse.api.routes import router
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.desktop_automation.models import (
    AutomationAction,
    Bounds,
    ElementSelector,
    VerificationSpec,
)
from synapse.desktop_automation.providers.factory import platform_desktop_provider
from synapse.desktop_automation.providers.linux import LinuxATSPIProvider
from synapse.desktop_automation.providers.macos import MacOSAccessibilityProvider
from synapse.desktop_automation.providers.windows import WindowsUIAutomationProvider
from synapse.desktop_automation.runtime import DesktopRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def base_runtime():
    directory = tempfile.TemporaryDirectory()
    runtime = create_runtime(
        Settings(
            project_root=PROJECT_ROOT,
            data_dir=Path(directory.name) / "data",
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
    )
    runtime.policies.create_rule(_rule("desktop-unit", "allow"))
    try:
        yield runtime
    finally:
        directory.cleanup()


@pytest.fixture
def desktop(base_runtime):
    provider = ConformanceProvider()
    runtime = DesktopRuntime(
        base_runtime.data_dir,
        base_runtime.events,
        base_runtime.policies,
        base_runtime.approvals,
        base_runtime.audit,
        base_runtime.vision,
        provider=provider,
        input_provider=ConformanceInputProvider(),
        visual_providers=[],
    )
    return runtime, provider


def test_windows_provider_parses_real_window_shape() -> None:
    provider = WindowsUIAutomationProvider()
    row = {
        "handle": 255,
        "pid": 10,
        "title": "Generic window",
        "state": "normal",
        "foreground": True,
        "left": 1,
        "top": 2,
        "width": 300,
        "height": 200,
    }
    with patch.object(provider, "_json", return_value=[row]):
        window = provider.list_windows()[0]
    assert window.window_id == "win:ff"
    assert window.bounds == Bounds(1, 2, 300, 200)


def test_windows_provider_maps_accessibility_tree() -> None:
    provider = WindowsUIAutomationProvider()
    raw = {
        "automation_id": "root",
        "role": "window",
        "control_type": "Window",
        "name": "Root",
        "enabled": True,
        "focused": True,
        "left": 0,
        "top": 0,
        "width": 400,
        "height": 300,
        "patterns": [],
        "children": [
            {
                "automation_id": "action",
                "role": "button",
                "control_type": "Button",
                "name": "Action",
                "enabled": True,
                "focused": False,
                "left": 10,
                "top": 10,
                "width": 80,
                "height": 20,
                "patterns": ["invoke"],
                "children": [],
            }
        ],
    }
    with patch.object(provider, "_json", return_value=raw):
        root = provider.accessibility_tree("win:ff")
    assert root.children[0].automation_id == "action"
    assert root.children[0].patterns == ["invoke"]


def test_linux_provider_parses_window_manager_output() -> None:
    output = "0x01 2 42 10 20 800 600 generic.Class host Generic window\n"
    completed = subprocess.CompletedProcess(["wmctrl"], 0, stdout=output, stderr="")
    with (
        patch("synapse.desktop_automation.providers.linux.shutil.which", return_value="wmctrl"),
        patch("synapse.desktop_automation.providers.linux.run_command", return_value=completed),
    ):
        window = LinuxATSPIProvider().list_windows()[0]
    assert window.window_id == "x11:01"
    assert window.workspace == "2"
    assert window.bounds.width == 800


def test_macos_provider_parses_accessibility_window_shape() -> None:
    provider = MacOSAccessibilityProvider()
    with patch.object(
        provider,
        "_jxa",
        return_value=[
            {
                "pid": 9,
                "title": "Generic window",
                "foreground": False,
                "left": 5,
                "top": 6,
                "width": 700,
                "height": 500,
            }
        ],
    ):
        window = provider.list_windows()[0]
    assert window.window_id == "ax:9:0"
    assert window.bounds.height == 500


def test_provider_factory_has_isolated_platform_types() -> None:
    assert isinstance(platform_desktop_provider("Windows"), WindowsUIAutomationProvider)
    assert isinstance(platform_desktop_provider("Linux"), LinuxATSPIProvider)
    assert isinstance(platform_desktop_provider("Darwin"), MacOSAccessibilityProvider)


def test_window_move_resize_and_element_index_change_do_not_break_semantic_selector(
    desktop,
) -> None:
    runtime, provider = desktop
    provider.windows[0] = replace(provider.windows[0], bounds=Bounds(400, 300, 1200, 900))
    provider.elements.reverse()
    _selected_provider, elements = runtime.ui_automation.find(
        ElementSelector(automation_id="submit", window_id="window:1")
    )
    assert elements[0].name == "Submit"


def test_dry_run_and_preview_have_no_side_effect(desktop) -> None:
    runtime, provider = desktop
    original = provider.clipboard
    plan = runtime.create_plan(
        "desktop-unit",
        "Dry run",
        [AutomationAction("clipboard.set", arguments={"value": "transient"})],
        dry_run=True,
    )
    preview = runtime.preview(plan.id)
    result = runtime.execute(plan.id)
    assert preview.previews[0].provider_order[0] == provider.name
    assert result.status == "dry_run"
    assert provider.clipboard == original


@pytest.mark.parametrize(
    ("kind", "arguments"),
    [
        ("input.scroll", {"delta": -3}),
        (
            "input.drag_drop",
            {
                "target_selector": {
                    "automation_id": "subject",
                    "window_id": "window:1",
                }
            },
        ),
    ],
)
def test_scroll_and_drag_drop_use_current_semantic_element_bounds(
    desktop, kind: str, arguments: dict[str, Any]
) -> None:
    runtime, _provider = desktop
    plan = runtime.create_plan(
        "desktop-unit",
        kind,
        [
            AutomationAction(
                kind,
                ElementSelector(automation_id="submit", window_id="window:1"),
                arguments=arguments,
                verification=VerificationSpec("action.performed", expected=True),
            )
        ],
    )
    assert runtime.execute(plan.id).status == "completed"


def test_sensitive_value_is_not_persisted_and_password_target_is_denied(desktop) -> None:
    runtime, _provider = desktop
    action = AutomationAction(
        "element.set_value",
        ElementSelector(automation_id="subject", role="password", window_id="window:1"),
        arguments={"value": "never-persist-this"},
    )
    plan = runtime.create_plan("desktop-unit", "Sensitive", [action])
    persisted = (runtime.planner.root / f"{plan.id}.yaml").read_text(encoding="utf-8")
    assert "never-persist-this" not in persisted
    assert runtime.execute(plan.id).status == "denied"


def test_tree_is_bounded_and_process_or_ocr_payload_is_not_persisted(desktop) -> None:
    runtime, _provider = desktop
    tree = runtime.ui_automation.tree("window:1", max_nodes=2)
    assert tree.window_id == "window:1"
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in runtime.planner.root.glob("*.yaml")
    )
    assert "children:" not in persisted
    assert "ocr" not in persisted.casefold()


def test_canonical_api_plan_preview_execute_and_verify(base_runtime, desktop) -> None:
    runtime, _provider = desktop
    base_runtime.desktop = runtime
    app = FastAPI()
    app.state.runtime = base_runtime
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    assert client.get("/api/applications").status_code == 200
    assert client.get("/api/windows").status_code == 200
    response = client.post(
        "/api/automation/plan",
        headers={"X-Actor-Id": "desktop-unit"},
        json={
            "objective": "API dry run",
            "dry_run": True,
            "actions": [{"kind": "clipboard.set", "arguments": {"value": "api-value"}}],
        },
    )
    assert response.status_code == 200
    plan_id = response.json()["id"]
    assert client.post("/api/automation/preview", json={"plan_id": plan_id}).status_code == 200
    assert (
        client.post("/api/automation/execute", json={"plan_id": plan_id}).json()["status"]
        == "dry_run"
    )
    verification = client.post(
        "/api/automation/verify",
        json={"kind": "window.exists", "window_id": "window:1", "expected": True},
    )
    assert verification.json()["verified"] is True


def test_operational_commands_are_generic(base_runtime, desktop) -> None:
    runtime, _provider = desktop
    base_runtime.commands.desktop = runtime
    assert base_runtime.commands.execute(base_runtime.context(), "/list-apps").status == "ok"
    payload = json.dumps(
        {
            "objective": "Command dry run",
            "dry_run": True,
            "actions": [{"kind": "clipboard.set", "arguments": {"value": "command-value"}}],
        }
    )
    result = base_runtime.commands.execute(base_runtime.context(), f"/automation-plan {payload}")
    assert result.status == "ok"


def test_desktop_health_is_optional_for_readiness(base_runtime, desktop) -> None:
    runtime, _provider = desktop
    base_runtime.health.desktop_automation = runtime
    components = {item.component_id: item for item in base_runtime.health.component_health()}
    assert components["desktop_automation"].ready
    assert all(
        not item.id.startswith("desktop_automation.")
        for item in base_runtime.readiness.evaluate().checks
    )
