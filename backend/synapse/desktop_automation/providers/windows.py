from __future__ import annotations

import json
import shutil
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

_WINDOW_SCRIPT = r"""
Add-Type @'
using System; using System.Text; using System.Runtime.InteropServices;
public class NativeDesktop {
 public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc p, IntPtr l);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int p);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 public struct RECT { public int Left,Top,Right,Bottom; }
}
'@
$fg=[NativeDesktop]::GetForegroundWindow(); $items=New-Object Collections.ArrayList
[NativeDesktop]::EnumWindows({param($h,$l)
 if(-not [NativeDesktop]::IsWindowVisible($h)){return $true}
 $s=New-Object Text.StringBuilder 1024; [void][NativeDesktop]::GetWindowText($h,$s,$s.Capacity)
 if([string]::IsNullOrWhiteSpace($s.ToString())){return $true}
 $pidValue=0; [void][NativeDesktop]::GetWindowThreadProcessId($h,[ref]$pidValue)
 $r=New-Object NativeDesktop+RECT; [void][NativeDesktop]::GetWindowRect($h,[ref]$r)
 $state=if([NativeDesktop]::IsIconic($h)){'minimized'}elseif([NativeDesktop]::IsZoomed($h)){'maximized'}else{'normal'}
 [void]$items.Add([pscustomobject]@{handle=$h.ToInt64();pid=$pidValue;title=$s.ToString();state=$state;foreground=($h-eq$fg);left=$r.Left;top=$r.Top;width=$r.Right-$r.Left;height=$r.Bottom-$r.Top})
 return $true
},[IntPtr]::Zero)|Out-Null
$items|ConvertTo-Json -Compress
"""

_TREE_SCRIPT = r"""
Add-Type -AssemblyName UIAutomationClient
$request=[Console]::In.ReadToEnd() | ConvertFrom-Json
$handle=[IntPtr]([Convert]::ToInt64($request.window_id,16))
$root=[Windows.Automation.AutomationElement]::FromHandle($handle)
if($null-eq$root){throw 'window_not_accessible'}
$walker=[Windows.Automation.TreeWalker]::ControlViewWalker
function Node($e,$depth){
 $patternMap=@{'Invoke'=[Windows.Automation.InvokePattern]::Pattern;'Value'=[Windows.Automation.ValuePattern]::Pattern;'SelectionItem'=[Windows.Automation.SelectionItemPattern]::Pattern;'ExpandCollapse'=[Windows.Automation.ExpandCollapsePattern]::Pattern;'Toggle'=[Windows.Automation.TogglePattern]::Pattern;'RangeValue'=[Windows.Automation.RangeValuePattern]::Pattern;'Scroll'=[Windows.Automation.ScrollPattern]::Pattern;'Text'=[Windows.Automation.TextPattern]::Pattern;'Grid'=[Windows.Automation.GridPattern]::Pattern;'Table'=[Windows.Automation.TablePattern]::Pattern}
 $patterns=@(); foreach($p in $patternMap.Keys){try{$obj=$null;if($e.TryGetCurrentPattern($patternMap[$p],[ref]$obj)){$patterns+=$p.ToLower()}}catch{}}
 $value=$null;try{$vp=$e.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern);$value=$vp.Current.Value}catch{}
 $r=$e.Current.BoundingRectangle
 $children=@(); if($depth-lt $request.depth){$c=$walker.GetFirstChild($e);while($null-ne$c-and$children.Count-lt$request.child_limit){$children+=Node $c ($depth+1);$c=$walker.GetNextSibling($c)}}
 [pscustomobject]@{automation_id=$e.Current.AutomationId;role=$e.Current.LocalizedControlType;control_type=$e.Current.ControlType.ProgrammaticName.Replace('ControlType.','');name=$e.Current.Name;description=$e.Current.HelpText;value=$value;enabled=$e.Current.IsEnabled;focused=$e.Current.HasKeyboardFocus;selected=$null;expanded=$null;toggled=$null;range_value=$null;left=[int]$r.X;top=[int]$r.Y;width=[int]$r.Width;height=[int]$r.Height;patterns=$patterns;children=$children}
}
Node $root 0|ConvertTo-Json -Depth 20 -Compress
"""

_ACTION_SCRIPT = r"""
Add-Type -AssemblyName UIAutomationClient
$r=[Console]::In.ReadToEnd()|ConvertFrom-Json
$handle=[IntPtr]([Convert]::ToInt64($r.window_id,16));$root=[Windows.Automation.AutomationElement]::FromHandle($handle)
$conditions=@()
if($r.selector.automation_id){$conditions+=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::AutomationIdProperty,[string]$r.selector.automation_id)}
if($r.selector.name){$conditions+=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty,[string]$r.selector.name)}
if($r.selector.control_type){$types=@{'Button'=[Windows.Automation.ControlType]::Button;'Edit'=[Windows.Automation.ControlType]::Edit;'CheckBox'=[Windows.Automation.ControlType]::CheckBox;'List'=[Windows.Automation.ControlType]::List;'ListItem'=[Windows.Automation.ControlType]::ListItem;'Tree'=[Windows.Automation.ControlType]::Tree;'TreeItem'=[Windows.Automation.ControlType]::TreeItem;'Tab'=[Windows.Automation.ControlType]::Tab;'TabItem'=[Windows.Automation.ControlType]::TabItem;'ToolBar'=[Windows.Automation.ControlType]::ToolBar;'StatusBar'=[Windows.Automation.ControlType]::StatusBar;'Menu'=[Windows.Automation.ControlType]::Menu;'MenuItem'=[Windows.Automation.ControlType]::MenuItem;'Window'=[Windows.Automation.ControlType]::Window;'Text'=[Windows.Automation.ControlType]::Text;'Document'=[Windows.Automation.ControlType]::Document;'Table'=[Windows.Automation.ControlType]::Table};$control=$types[[string]$r.selector.control_type];if($control){$conditions+=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty,$control)}}
$condition=if($conditions.Count-eq0){[Windows.Automation.Condition]::TrueCondition}elseif($conditions.Count-eq1){$conditions[0]}else{New-Object Windows.Automation.AndCondition($conditions)}
$e=$root.FindFirst([Windows.Automation.TreeScope]::Descendants,$condition);if($null-eq$e){throw 'element_not_found'}
switch($r.kind){
 'element.invoke' {$p=$e.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern);$p.Invoke()}
 'element.set_value' {$p=$e.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern);$p.SetValue([string]$r.value)}
 'element.toggle' {$p=$e.GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern);$p.Toggle()}
 'element.select' {$p=$e.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern);$p.Select()}
 'element.expand' {$p=$e.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern);$p.Expand()}
 'element.collapse' {$p=$e.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern);$p.Collapse()}
 'element.focus' {$e.SetFocus()}
 default {throw 'unsupported_semantic_action'}
}
[pscustomobject]@{performed=$true;automation_id=$e.Current.AutomationId;name=$e.Current.Name}|ConvertTo-Json -Compress
"""

_WINDOW_ACTION_SCRIPT = r"""
Add-Type @'
using System; using System.Runtime.InteropServices;
public class WindowActions { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l); }
'@
$r=[Console]::In.ReadToEnd()|ConvertFrom-Json;$h=[IntPtr]([Convert]::ToInt64($r.window_id,16));$ok=$false
switch($r.kind){'window.focus'{$ok=[WindowActions]::SetForegroundWindow($h)}'window.minimize'{$ok=[WindowActions]::ShowWindow($h,6)}'window.restore'{$ok=[WindowActions]::ShowWindow($h,9)}'window.maximize'{$ok=[WindowActions]::ShowWindow($h,3)}'window.close'{$ok=[WindowActions]::PostMessage($h,16,[IntPtr]::Zero,[IntPtr]::Zero)}}
if(-not$ok){throw 'window_action_failed'};'{"performed":true}'
"""


class WindowsUIAutomationProvider:
    name = "windows_uia"
    semantic = True
    fallback_kind = None

    def __init__(self) -> None:
        self.powershell = shutil.which("powershell") or shutil.which("pwsh")

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "available": bool(self.powershell), "semantic": True}

    def list_windows(self) -> list[WindowInfo]:
        raw = self._json(_WINDOW_SCRIPT)
        rows = raw if isinstance(raw, list) else ([] if raw is None else [raw])
        return [self._window(row) for row in rows if isinstance(row, dict)]

    def list_applications(self):
        return process_applications(self.name, self.list_windows())

    def accessibility_tree(self, window_id: str, max_nodes: int = 500) -> UIElement:
        raw = self._json(
            _TREE_SCRIPT,
            {
                "window_id": _handle(window_id),
                "depth": 8,
                "child_limit": max(1, min(max_nodes, 500)),
            },
            timeout=12,
        )
        if not isinstance(raw, dict):
            raise TargetNotFound("Window has no accessible UI tree")
        return self._element(raw, window_id)

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
            except (ProviderUnavailable, TargetNotFound):
                continue
        raise TargetNotFound("No Windows UI Automation element matched")

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        if action.kind == "application.launch":
            application = _safe_application(action.application)
            script = "$r=[Console]::In.ReadToEnd()|ConvertFrom-Json;Start-Process -FilePath $r.application;'{\"performed\":true}'"
            return self._json(script, {"application": application})
        if action.kind.startswith("window."):
            return self._json(
                _WINDOW_ACTION_SCRIPT,
                {"kind": action.kind, "window_id": _handle(action.window_id or "")},
            )
        if action.kind.startswith("element."):
            selector = action.selector or ElementSelector()
            window_id = selector.window_id or (element.window_id if element else None)
            if not window_id:
                raise TargetNotFound("Element action requires a window")
            return self._json(
                _ACTION_SCRIPT,
                {
                    "kind": action.kind,
                    "window_id": _handle(window_id),
                    "selector": {
                        "automation_id": selector.automation_id
                        or (element.automation_id if element else None),
                        "name": selector.name or (element.name if element else None),
                        "control_type": selector.control_type
                        or (element.control_type if element else None),
                    },
                    "value": action.arguments.get("value"),
                },
            )
        raise ActionFailed(f"Unsupported Windows semantic action: {action.kind}")

    def clipboard_get(self) -> str | None:
        raw = self._invoke(
            "Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.Clipboard]::GetText()"
        )
        return raw.stdout.rstrip("\r\n") if raw.returncode == 0 else None

    def clipboard_set(self, value: str) -> None:
        script = "Add-Type -AssemblyName System.Windows.Forms;$r=[Console]::In.ReadToEnd();[Windows.Forms.Clipboard]::SetText($r)"
        self._invoke(script, input_text=value)

    def clipboard_clear(self) -> None:
        self._invoke(
            "Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.Clipboard]::Clear()"
        )

    def _json(self, script: str, payload: Any | None = None, timeout: float = 8.0) -> Any:
        completed = self._invoke(
            script,
            json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            timeout,
        )
        if completed.returncode != 0:
            raise ActionFailed(completed.stderr.strip()[:240] or "Windows provider failed")
        text = completed.stdout.strip()
        return json.loads(text) if text else None

    def _invoke(self, script: str, input_text: str | None = None, timeout: float = 8.0):
        if not self.powershell:
            raise ProviderUnavailable("PowerShell is unavailable")
        return run_command(
            [self.powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            timeout,
            input_text,
        )

    def _window(self, raw: dict[str, Any]) -> WindowInfo:
        handle = int(raw.get("handle", 0))
        pid = int(raw.get("pid", 0))
        return WindowInfo(
            window_id=f"win:{handle:x}",
            application_id=f"app:{pid}",
            pid=pid,
            title=str(raw.get("title", ""))[:240],
            state=str(raw.get("state", "unknown")),
            foreground=bool(raw.get("foreground")),
            monitor=None,
            workspace=None,
            bounds=Bounds(
                int(raw.get("left", 0)),
                int(raw.get("top", 0)),
                int(raw.get("width", 0)),
                int(raw.get("height", 0)),
            ),
            provider=self.name,
        )

    def _element(self, raw: dict[str, Any], window_id: str) -> UIElement:
        bounds = Bounds(
            int(raw.get("left", 0)),
            int(raw.get("top", 0)),
            int(raw.get("width", 0)),
            int(raw.get("height", 0)),
        )
        children = [
            self._element(item, window_id)
            for item in raw.get("children", [])
            if isinstance(item, dict)
        ]
        return UIElement(
            element_id=stable_id(
                window_id,
                raw.get("automation_id"),
                raw.get("control_type"),
                raw.get("name"),
                bounds,
            ),
            window_id=window_id,
            automation_id=str(raw.get("automation_id") or "") or None,
            role=str(raw.get("role") or "unknown"),
            control_type=str(raw.get("control_type") or "unknown"),
            name=str(raw.get("name") or "")[:240] or None,
            description=str(raw.get("description") or "")[:240] or None,
            value=str(raw.get("value")) if raw.get("value") is not None else None,
            enabled=bool(raw.get("enabled", True)),
            focused=bool(raw.get("focused", False)),
            selected=raw.get("selected"),
            expanded=raw.get("expanded"),
            toggled=raw.get("toggled"),
            range_value=raw.get("range_value"),
            bounds=bounds,
            patterns=[str(item) for item in raw.get("patterns", [])],
            children=children,
            provider=self.name,
        )


def _handle(window_id: str) -> str:
    value = window_id.removeprefix("win:")
    if not value or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise TargetNotFound("Invalid window identifier")
    return value


def _safe_application(value: str | None) -> str:
    application = str(value or "").strip()
    if not application or any(token in application for token in ("/", "\\", ":", "..")):
        raise ActionFailed("Application launch accepts an executable name, not a private path")
    return application[:160]
