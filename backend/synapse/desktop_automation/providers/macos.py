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

_WINDOWS_JXA = r"""
ObjC.import('stdlib');
const se=Application('System Events');let out=[];
for(const p of se.applicationProcesses.whose({visible:true})()){
 let pid=p.unixId();let front=p.frontmost();
 let windows=p.windows();for(let index=0;index<windows.length;index++){let w=windows[index];
  let pos=w.position(),size=w.size();out.push({pid:pid,index:index,title:w.name(),foreground:front,left:pos[0],top:pos[1],width:size[0],height:size[1]});
 }
}
JSON.stringify(out)
"""

_TREE_JXA = r"""
const req=__req;
const se=Application('System Events');const p=se.applicationProcesses.whose({unixId:req.pid})()[0];
function node(e,d){let role='unknown',name='',desc='',value=null;try{role=e.role()}catch(x){}try{name=e.name()}catch(x){}try{desc=e.description()}catch(x){}try{value=e.value()}catch(x){}
let children=[];if(d<req.depth){try{for(const c of e.uiElements().slice(0,req.limit)){children.push(node(c,d+1))}}catch(x){}}
return {automation_id:null,role:role,control_type:role,name:name,description:desc,value:value,enabled:true,focused:false,patterns:[],children:children};}
const w=p.windows()[req.index];JSON.stringify(node(w,0))
"""

_ACTION_JXA = r"""
const r=__req;const se=Application('System Events');const p=se.applicationProcesses.whose({unixId:r.pid})()[0];
function find(e){let role='',name='';try{role=e.role()}catch(x){}try{name=e.name()}catch(x){}
if((!r.role||String(role).toLowerCase()==String(r.role).toLowerCase())&&(!r.name||String(name).toLowerCase()==String(r.name).toLowerCase()))return e;
try{for(const c of e.uiElements()){const hit=find(c);if(hit)return hit}}catch(x){}return null;}
const e=find(p.windows()[r.index]);if(!e)throw Error('element_not_found');
if(r.kind=='element.set_value'){e.value=r.value}
else if(r.kind=='element.focus'){e.attributes.byName('AXFocused').value=true}
else if(r.kind=='element.expand'){e.attributes.byName('AXExpanded').value=true}
else if(r.kind=='element.collapse'){e.attributes.byName('AXExpanded').value=false}
else {let done=false;for(const n of ['AXPress','AXConfirm','AXPick']){try{e.actions.byName(n).perform();done=true;break}catch(x){}}if(!done)throw Error('action_unsupported')}
JSON.stringify({performed:true})
"""


class MacOSAccessibilityProvider:
    name = "macos_accessibility"
    semantic = True
    fallback_kind = None

    def __init__(self) -> None:
        self.osascript = shutil.which("osascript")

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "available": bool(self.osascript), "semantic": True}

    def list_windows(self) -> list[WindowInfo]:
        rows = self._jxa(_WINDOWS_JXA)
        windows = []
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            pid = int(row.get("pid", 0))
            process_index = int(row.get("index", index))
            windows.append(
                WindowInfo(
                    window_id=f"ax:{pid}:{process_index}",
                    application_id=f"app:{pid}",
                    pid=pid,
                    title=str(row.get("title", ""))[:240],
                    state="normal",
                    foreground=bool(row.get("foreground")),
                    monitor=None,
                    workspace=None,
                    bounds=Bounds(
                        int(row.get("left", 0)),
                        int(row.get("top", 0)),
                        int(row.get("width", 0)),
                        int(row.get("height", 0)),
                    ),
                    provider=self.name,
                )
            )
        return windows

    def list_applications(self):
        return process_applications(self.name, self.list_windows())

    def accessibility_tree(self, window_id: str, max_nodes: int = 500) -> UIElement:
        pid, index = _window_parts(window_id)
        raw = self._jxa(
            _TREE_JXA,
            {"pid": pid, "index": index, "depth": 7, "limit": max(1, min(max_nodes, 500))},
        )
        if not isinstance(raw, dict):
            raise TargetNotFound("Window has no macOS accessibility tree")
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
            except TargetNotFound:
                continue
        raise TargetNotFound("No macOS accessibility element matched")

    def perform(self, action: AutomationAction, element: UIElement | None = None) -> dict[str, Any]:
        if action.kind == "application.launch":
            application = str(action.application or "").strip()
            if not application or any(token in application for token in ("/", "\\", ":", "..")):
                raise ActionFailed("Application launch accepts a generic name, not a private path")
            completed = run_command(["open", "-a", application[:160]])
            if completed.returncode != 0:
                raise ActionFailed("Application launch failed")
            return {"performed": True}
        if action.kind.startswith("window."):
            pid, index = _window_parts(action.window_id or "")
            operation = {
                "window.focus": "set frontmost to true",
                "window.minimize": f'set value of attribute "AXMinimized" of window {index + 1} to true',
                "window.restore": f'set value of attribute "AXMinimized" of window {index + 1} to false',
                "window.close": f'perform action "AXClose" of window {index + 1}',
                "window.maximize": f'perform action "AXZoomWindow" of window {index + 1}',
            }.get(action.kind)
            if not operation:
                raise ActionFailed(f"Unsupported macOS window action: {action.kind}")
            script = f'tell application "System Events" to tell first application process whose unix id is {pid} to {operation}'
            completed = self._run(["-e", script])
            if completed.returncode != 0:
                raise ActionFailed("macOS accessibility action failed")
            return {"performed": True}
        if action.kind.startswith("element."):
            selector = action.selector or ElementSelector()
            window_id = selector.window_id or (element.window_id if element else "")
            pid, index = _window_parts(window_id)
            return self._jxa(
                _ACTION_JXA,
                {
                    "pid": pid,
                    "index": index,
                    "kind": action.kind,
                    "role": selector.role,
                    "name": selector.name,
                    "value": action.arguments.get("value"),
                },
            )
        raise ActionFailed(f"Unsupported macOS accessibility action: {action.kind}")

    def clipboard_get(self) -> str | None:
        completed = run_command(["pbpaste"])
        return completed.stdout if completed.returncode == 0 else None

    def clipboard_set(self, value: str) -> None:
        completed = run_command(["pbcopy"], input_text=value)
        if completed.returncode != 0:
            raise ActionFailed("Clipboard write failed")

    def clipboard_clear(self) -> None:
        self.clipboard_set("")

    def _jxa(self, script: str, payload: dict[str, Any] | None = None) -> Any:
        input_script = script
        if payload is not None:
            input_script = f"const __req={json.dumps(payload, ensure_ascii=False)};" + script
        if not self.osascript:
            raise ProviderUnavailable("osascript is unavailable")
        completed = run_command(
            [self.osascript, "-l", "JavaScript", "-"],
            input_text=input_script,
        )
        if completed.returncode != 0:
            raise ProviderUnavailable(completed.stderr.strip()[:240] or "Accessibility denied")
        return json.loads(completed.stdout.strip() or "null")

    def _run(self, arguments: list[str]):
        if not self.osascript:
            raise ProviderUnavailable("osascript is unavailable")
        return run_command([self.osascript, *arguments])

    def _element(self, raw: dict[str, Any], window_id: str) -> UIElement:
        role = str(raw.get("role") or "unknown")
        name = str(raw.get("name") or "")[:240] or None
        children = [
            self._element(item, window_id)
            for item in raw.get("children", [])
            if isinstance(item, dict)
        ]
        return UIElement(
            element_id=stable_id(window_id, role, name),
            window_id=window_id,
            automation_id=None,
            role=role,
            control_type=role,
            name=name,
            description=str(raw.get("description") or "")[:240] or None,
            value=str(raw.get("value"))[:4096] if raw.get("value") is not None else None,
            enabled=bool(raw.get("enabled", True)),
            focused=bool(raw.get("focused", False)),
            selected=None,
            expanded=None,
            toggled=None,
            range_value=None,
            bounds=None,
            patterns=[str(item) for item in raw.get("patterns", [])],
            children=children,
            provider=self.name,
        )


def _window_parts(window_id: str) -> tuple[int, int]:
    parts = window_id.split(":")
    if len(parts) != 3 or parts[0] != "ax":
        raise TargetNotFound("Invalid macOS window identifier")
    return int(parts[1]), int(parts[2])
