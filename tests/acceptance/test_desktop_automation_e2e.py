from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.desktop_automation.errors import ActionFailed, ProviderUnavailable, TargetNotFound
from synapse.desktop_automation.models import (
    ApplicationInfo,
    AutomationAction,
    Bounds,
    ElementSelector,
    UIElement,
    VerificationSpec,
    WindowInfo,
)
from synapse.desktop_automation.providers.common import find_in_tree
from synapse.desktop_automation.runtime import DesktopRuntime
from synapse.policies.models import PolicyRule

from .world_attention_support import DomainFixture, FixedDecisionRuntime, loop

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConformanceProvider:
    name = "conformance_accessibility"
    semantic = True
    fallback_kind = None

    def __init__(self) -> None:
        self.windows = [
            WindowInfo(
                "window:1",
                "app:10",
                10,
                "Generic document",
                "normal",
                True,
                "monitor:1",
                "workspace:1",
                Bounds(10, 20, 800, 600),
                self.name,
            )
        ]
        self.elements = [
            _element("button:1", "window:1", "submit", "button", "button", "Submit"),
            _element("textbox:1", "window:1", "subject", "textbox", "edit", "Subject", value=""),
        ]
        self.clipboard = "original"
        self.fail_focus = 0
        self.fail_provider = False
        self.disappear_on_action = False
        self.close_window_on_action = False

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "available": not self.fail_provider, "semantic": True}

    def list_applications(self) -> list[ApplicationInfo]:
        return [
            ApplicationInfo(
                item.application_id,
                "GenericApp",
                item.pid,
                "generic-app",
                "running",
                item.foreground,
                len([window for window in self.windows if window.pid == item.pid]),
                self.name,
            )
            for item in self.windows[:1]
        ]

    def list_windows(self) -> list[WindowInfo]:
        if self.fail_provider:
            raise ProviderUnavailable("provider failure")
        return list(self.windows)

    def accessibility_tree(self, window_id: str, max_nodes: int = 500) -> UIElement:
        if self.fail_provider:
            raise ProviderUnavailable("provider failure")
        if not any(window.window_id == window_id for window in self.windows):
            raise TargetNotFound("window closed")
        children = [element for element in self.elements if element.window_id == window_id]
        return _element("root", window_id, "root", "window", "window", "Root", children=children)

    def find_elements(self, selector: ElementSelector, limit: int = 20) -> list[UIElement]:
        window_id = selector.window_id or "window:1"
        return find_in_tree(self.accessibility_tree(window_id), selector, limit)

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        if self.fail_provider:
            raise ProviderUnavailable("provider failure")
        if action.kind == "application.launch":
            if not self.windows:
                self.windows.append(
                    WindowInfo(
                        "window:launched",
                        "app:20",
                        20,
                        "Launched application",
                        "normal",
                        True,
                        None,
                        None,
                        Bounds(0, 0, 640, 480),
                        self.name,
                    )
                )
            return {"performed": True}
        if action.kind.startswith("window."):
            if self.fail_focus > 0:
                self.fail_focus -= 1
                raise ActionFailed("focus failed")
            if action.kind == "window.close":
                self.windows = [item for item in self.windows if item.window_id != action.window_id]
            else:
                states = {
                    "window.minimize": "minimized",
                    "window.restore": "normal",
                    "window.maximize": "maximized",
                }
                self.windows = [
                    replace(
                        item,
                        foreground=action.kind == "window.focus"
                        if item.window_id == action.window_id
                        else False,
                        state=states.get(action.kind, item.state)
                        if item.window_id == action.window_id
                        else item.state,
                    )
                    for item in self.windows
                ]
            return {"performed": True}
        if element is None:
            element = self.find_elements(action.selector or ElementSelector(), 1)[0]
        if self.close_window_on_action:
            self.windows.clear()
        if self.disappear_on_action:
            self.elements = [
                item for item in self.elements if item.element_id != element.element_id
            ]
            return {"performed": True}
        if action.kind == "element.set_value":
            self._replace_element(element.element_id, value=str(action.arguments.get("value", "")))
        elif action.kind == "element.focus":
            self._replace_element(element.element_id, focused=True)
        elif action.kind == "element.toggle":
            self._replace_element(element.element_id, toggled=not bool(element.toggled))
        elif action.kind == "element.invoke":
            self.elements.append(
                _element("status:1", element.window_id, "status", "statusbar", "text", "Completed")
            )
        else:
            raise ActionFailed(f"unsupported conformance action: {action.kind}")
        return {"performed": True, "element_id": element.element_id}

    def clipboard_get(self) -> str | None:
        return self.clipboard

    def clipboard_set(self, value: str) -> None:
        self.clipboard = value

    def clipboard_clear(self) -> None:
        self.clipboard = ""

    def _replace_element(self, element_id: str, **updates: Any) -> None:
        self.elements = [
            replace(item, **updates) if item.element_id == element_id else item
            for item in self.elements
        ]


class ConformanceInputProvider:
    name = "conformance_input"

    def __init__(self) -> None:
        self.calls = 0

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        self.calls += 1
        return {"performed": element is not None, "fallback": True}


class VisualConformanceProvider:
    semantic = False

    def __init__(self, kind: str) -> None:
        self.name = f"fallback_{kind}"
        self.fallback_kind = kind

    def health(self):
        return {"provider": self.name, "available": True, "semantic": False}

    def list_applications(self):
        return []

    def list_windows(self):
        return []

    def accessibility_tree(self, window_id: str, max_nodes: int = 500):
        raise TargetNotFound("visual only")

    def find_elements(self, selector: ElementSelector, limit: int = 20):
        return [
            _element(
                f"{self.name}:1",
                "visual:screen",
                None,
                "visual_candidate",
                "visual_candidate",
                selector.name or "candidate",
                bounds=Bounds(100, 100, 80, 30),
                provider=self.name,
            )
        ]

    def perform(self, action: AutomationAction, element: UIElement | None = None):
        raise ActionFailed("visual provider only locates")


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
    for actor in ("desktop-test", "mission-test", "agent-loop-test"):
        runtime.policies.create_rule(_rule(actor, "allow"))
    runtime.policies.create_rule(_rule("approval-test", "require_approval"))
    runtime.devices.register_device("desktop-approver", True, ["approve_actions"])
    try:
        yield runtime
    finally:
        directory.cleanup()


@pytest.fixture
def desktop(base_runtime):
    provider = ConformanceProvider()
    input_provider = ConformanceInputProvider()
    runtime = DesktopRuntime(
        base_runtime.data_dir,
        base_runtime.events,
        base_runtime.policies,
        base_runtime.approvals,
        base_runtime.audit,
        base_runtime.vision,
        provider=provider,
        input_provider=input_provider,
        visual_providers=[],
    )
    return runtime, provider, input_provider


def test_open_application(base_runtime, desktop) -> None:
    runtime, provider, _input = desktop
    provider.windows.clear()
    plan = runtime.create_plan(
        "desktop-test",
        "Launch generic application",
        [AutomationAction("application.launch", application="generic-app")],
    )
    waiting = runtime.execute(plan.id)
    assert waiting.status == "awaiting_approval"
    approval = runtime.governance.approvals.approve(
        base_runtime.context(device_id="desktop-approver"),
        waiting.approval_id,
    )
    assert approval.status == "approved"
    assert runtime.execute(plan.id).status == "completed"
    assert provider.windows


def test_find_window(desktop) -> None:
    runtime, _provider, _input = desktop
    assert runtime.windows.find("document")[0].window_id == "window:1"


def test_find_button(desktop) -> None:
    runtime, _provider, _input = desktop
    _provider_port, elements = runtime.ui_automation.find(
        ElementSelector(role="button", name="Submit")
    )
    assert elements[0].automation_id == "submit"


def test_find_textbox(desktop) -> None:
    runtime, _provider, _input = desktop
    _provider_port, elements = runtime.ui_automation.find(ElementSelector(control_type="edit"))
    assert elements[0].role == "textbox"


def test_execute_complete_verified_sequence(desktop) -> None:
    runtime, _provider, _input = desktop
    textbox = ElementSelector(automation_id="subject", window_id="window:1")
    button = ElementSelector(automation_id="submit", window_id="window:1")
    plan = runtime.create_plan(
        "desktop-test",
        "Fill and invoke",
        [
            AutomationAction("window.focus", window_id="window:1"),
            AutomationAction("element.set_value", textbox, arguments={"value": "Hello"}),
            AutomationAction(
                "element.invoke",
                button,
                verification=VerificationSpec(
                    "element.exists",
                    ElementSelector(automation_id="status", window_id="window:1"),
                    True,
                ),
            ),
        ],
    )
    result = runtime.execute(plan.id)
    assert result.status == "completed"
    assert all(item.verification.verified for item in result.actions)
    persisted = "\n".join(
        [
            (runtime.planner.root / f"{plan.id}.yaml").read_text(encoding="utf-8"),
            (runtime.planner.results_root / f"{plan.id}.yaml").read_text(encoding="utf-8"),
        ]
    )
    assert "Hello" not in persisted


def test_focus_failure_is_not_assumed_success(desktop) -> None:
    runtime, provider, _input = desktop
    provider.fail_focus = 3
    plan = runtime.create_plan(
        "desktop-test",
        "Focus",
        [AutomationAction("window.focus", window_id="window:1", max_attempts=2)],
    )
    assert runtime.execute(plan.id).status == "failed"


def test_provider_failure_aborts(desktop) -> None:
    runtime, provider, _input = desktop
    provider.fail_provider = True
    plan = runtime.create_plan(
        "desktop-test",
        "Focus",
        [AutomationAction("window.focus", window_id="window:1", max_attempts=1)],
    )
    assert runtime.execute(plan.id).status == "failed"


@pytest.mark.parametrize("fallback_kind", ["ocr", "vision"])
def test_visual_fallbacks_are_last_resort(base_runtime, fallback_kind: str) -> None:
    provider = ConformanceProvider()
    provider.fail_provider = True
    input_provider = ConformanceInputProvider()
    runtime = DesktopRuntime(
        base_runtime.data_dir,
        base_runtime.events,
        base_runtime.policies,
        base_runtime.approvals,
        base_runtime.audit,
        base_runtime.vision,
        provider=provider,
        input_provider=input_provider,
        visual_providers=[VisualConformanceProvider(fallback_kind)],
    )
    plan = runtime.create_plan(
        "desktop-test",
        "Fallback",
        [
            AutomationAction(
                "input.click",
                ElementSelector(name="Submit"),
                verification=VerificationSpec("action.performed", expected=True),
            )
        ],
    )
    result = runtime.execute(plan.id)
    assert result.status == "completed"
    assert result.actions[0].provider == f"fallback_{fallback_kind}"
    assert input_provider.calls == 1


def test_approval_denied(base_runtime, desktop) -> None:
    runtime, _provider, _input = desktop
    plan = runtime.create_plan(
        "approval-test",
        "Approval",
        [AutomationAction("application.launch", application="generic-app")],
    )
    waiting = runtime.execute(plan.id)
    assert waiting.status == "awaiting_approval"
    base_runtime.devices.register_device("approver", True, ["approve_actions"])
    base_runtime.approvals.reject(base_runtime.context(device_id="approver"), waiting.approval_id)
    assert runtime.execute(plan.id).status == "denied"


def test_cancellation(desktop) -> None:
    runtime, _provider, _input = desktop
    plan = runtime.create_plan(
        "desktop-test", "Cancel", [AutomationAction("window.focus", window_id="window:1")]
    )
    runtime.cancel(plan.id)
    assert runtime.execute(plan.id).status == "cancelled"


def test_clipboard_is_restored_after_failure(desktop) -> None:
    runtime, provider, _input = desktop
    provider.clipboard = "original"
    provider.disappear_on_action = True
    plan = runtime.create_plan(
        "desktop-test",
        "Restore clipboard",
        [
            AutomationAction("clipboard.set", arguments={"value": "temporary"}),
            AutomationAction(
                "element.invoke",
                ElementSelector(automation_id="submit", window_id="window:1"),
                verification=VerificationSpec(
                    "element.exists",
                    ElementSelector(automation_id="submit", window_id="window:1"),
                    True,
                ),
            ),
        ],
    )
    assert runtime.execute(plan.id).status == "failed"
    assert provider.clipboard == "original"


def test_element_disappears_during_execution(desktop) -> None:
    runtime, provider, _input = desktop
    provider.disappear_on_action = True
    selector = ElementSelector(automation_id="submit", window_id="window:1")
    plan = runtime.create_plan(
        "desktop-test",
        "Disappearing element",
        [
            AutomationAction(
                "element.invoke",
                selector,
                verification=VerificationSpec("element.exists", selector, True),
            )
        ],
    )
    assert runtime.execute(plan.id).status == "failed"


def test_window_closes_during_automation(desktop) -> None:
    runtime, provider, _input = desktop
    provider.close_window_on_action = True
    selector = ElementSelector(automation_id="submit", window_id="window:1")
    plan = runtime.create_plan(
        "desktop-test",
        "Closing window",
        [
            AutomationAction(
                "element.invoke",
                selector,
                verification=VerificationSpec("window.exists", expected=True, window_id="window:1"),
            )
        ],
    )
    assert runtime.execute(plan.id).status == "failed"


def test_retry_succeeds_after_relocation(desktop) -> None:
    runtime, provider, _input = desktop
    provider.fail_focus = 1
    plan = runtime.create_plan(
        "desktop-test",
        "Retry focus",
        [AutomationAction("window.focus", window_id="window:1", max_attempts=2)],
    )
    result = runtime.execute(plan.id)
    assert result.status == "completed"
    assert result.actions[0].attempts == 2


def test_recovery_after_failure(desktop) -> None:
    runtime, provider, _input = desktop
    provider.fail_focus = 1
    plan = runtime.create_plan(
        "desktop-test",
        "Recover focus",
        [AutomationAction("window.focus", window_id="window:1", max_attempts=1)],
    )
    assert runtime.execute(plan.id).status == "failed"
    assert runtime.recover(plan.id).status == "completed"


def test_positive_verification(desktop) -> None:
    runtime, _provider, _input = desktop
    result = runtime.verify(VerificationSpec("window.exists", expected=True, window_id="window:1"))
    assert result.verified


def test_negative_verification(desktop) -> None:
    runtime, _provider, _input = desktop
    result = runtime.verify(
        VerificationSpec("window.exists", expected=True, window_id="window:missing")
    )
    assert not result.verified


def test_mission_executes_through_desktop_port(base_runtime, desktop) -> None:
    runtime, _provider, _input = desktop
    base_runtime.missions.desktop_runtime = runtime
    mission = base_runtime.missions.create_mission("Generic desktop task")
    plan = runtime.create_plan(
        "mission-test",
        "Mission clipboard",
        [AutomationAction("clipboard.set", arguments={"value": "mission"})],
    )
    result = base_runtime.missions.execute_desktop_automation(mission.mission_id, plan.id)
    assert result.status == "completed"


def test_agent_loop_delegates_reversible_desktop_plan(base_runtime, desktop) -> None:
    runtime, _provider, _input = desktop
    base_runtime.missions.desktop_runtime = runtime
    plan = runtime.create_plan(
        "agent-loop-test",
        "Loop clipboard",
        [AutomationAction("clipboard.set", arguments={"value": "loop"})],
    )
    fixture = DomainFixture()
    try:
        fixture.high_item("execute_reversible_action", {"desktop_plan_id": plan.id})
        agent_loop = loop(
            fixture,
            FixedDecisionRuntime("execute_reversible_action", {"desktop_plan_id": plan.id}),
            tool_runtime=base_runtime.tool_runtime,
            desktop_runtime=runtime,
        )
        result = agent_loop.run_cycle("desktop-acceptance")
        assert result.action_result.verification["verified"] is True
    finally:
        fixture.close()


def _element(
    element_id: str,
    window_id: str,
    automation_id: str | None,
    role: str,
    control_type: str,
    name: str,
    *,
    value: str | None = None,
    focused: bool = False,
    toggled: bool | None = None,
    bounds: Bounds | None = None,
    children: list[UIElement] | None = None,
    provider: str = "conformance_accessibility",
) -> UIElement:
    return UIElement(
        element_id,
        window_id,
        automation_id,
        role,
        control_type,
        name,
        None,
        value,
        True,
        focused,
        None,
        None,
        toggled,
        None,
        bounds or Bounds(20, 20, 100, 30),
        ["invoke", "value"],
        children or [],
        provider,
    )


def _rule(actor: str, effect: str) -> PolicyRule:
    return PolicyRule(
        scope="agent",
        subject=actor,
        action="desktop.automation.execute",
        resource="desktop:*",
        effect=effect,
        source="desktop_acceptance",
    )
