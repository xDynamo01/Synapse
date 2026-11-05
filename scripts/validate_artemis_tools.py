"""Exercise real tool handlers against disposable files on each mounted disk."""
from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import wave
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

def main() -> None:
    from synapse.bootstrap import create_runtime
    from synapse.core.config import Settings
    from synapse.core.serialization import dump_structured_file
    from synapse.desktop_automation.models import AutomationAction
    from synapse.tools.models import ToolExecutionRequest

    report: dict = {"scope": "Real handlers, isolated runtime; no model inference", "tools": {}, "disks": {}}
    with tempfile.TemporaryDirectory(prefix="synapse-artemis-tools-") as folder:
        data = Path(folder) / "data"
        settings = Settings(ROOT, data, "127.0.0.1", 0, "local_owner")
        create_runtime(settings)
        for agent_id, role in [("artemis", "primary_agent"), ("fixture", "worker")]:
            dump_structured_file(data / "agents" / agent_id / "CONFIG.yaml", {"id": agent_id, "name": agent_id, "role": role, "permissions": []})
        dump_structured_file(data / "config/filesystem_tools.yaml", {"all_disks": True})
        runtime = create_runtime(settings)
        report["inventory"] = [asdict(tool) for tool in runtime.tool_runtime.registry.list_registered_tools()]

        def call(name: str, arguments: dict | None = None, *, approve: bool = False):
            request = ToolExecutionRequest(tool_id=name, arguments=arguments or {}, caller="artemis", caller_type="agent", agent_id="artemis")
            result = runtime.tool_runtime.execute(request)
            waited = result.status == "awaiting_approval"
            if approve and waited:
                approval_id = result.metadata["approval_id"]
                runtime.approvals.approve(runtime.context(), approval_id)
                result = runtime.tool_runtime.execute(replace(request, approval_id=approval_id))
            report["tools"][name] = {"success": result.success, "status": result.status, "error": result.error, "approval_observed": waited, "output_status": result.output.get("status")}
            return result

        disks = call("list_disks").output["roots"]
        for root_text in disks:
            root = Path(root_text)
            if root != Path(root.anchor):
                continue
            listing = call("list_directory", {"path": str(root)})
            row = {"listing": listing.success, "error": listing.error}
            report["disks"][str(root)] = row
            scratch = root / f"SynapseToolCheck-{uuid4().hex}"
            target = scratch / "todo.txt"
            # No pre-existing paths are changed or removed.
            assert scratch.parent == root and not scratch.exists()
            created = call("write_file", {"path": str(target), "content": "Comprar pão\n"}, approve=True)
            row["create"] = created.success
            row["write_error"] = created.error
            if not created.success:
                if scratch.exists() and not any(scratch.iterdir()):
                    scratch.rmdir()
                continue
            read = call("read_file", {"path": str(target)})
            row["read"] = read.success and read.output.get("content") == "Comprar pão\n"
            searched = call("search_files", {"path": str(scratch), "pattern": "*.txt", "query": "pão"})
            row["search"] = searched.success and bool(searched.output.get("results"))
            edited = call("edit_file", {"path": str(target), "old_text": "pão", "new_text": "leite"}, approve=True)
            row["edit"] = edited.success and target.read_text(encoding="utf-8") == "Comprar leite\n"
            deleted = call("delete_file", {"path": str(target)}, approve=True)
            row["delete"] = deleted.success and not target.exists()
            if not any(scratch.iterdir()):
                scratch.rmdir()
        for name in ("health.summary", "readiness.summary", "provider.summary", "tool.summary", "memory_index"):
            call(name)
        call("agent.summary", {"agent_id": "artemis"})
        conversation = runtime.conversations.create_conversation(runtime.context(), ["artemis"], title="Disposable tool verification")
        mission = runtime.missions.create_mission(title="Disposable tool verification", owner_agent_id="artemis")
        call("conversation.summary", {"conversation_id": conversation.conversation_id})
        call("mission.summary", {"mission_id": mission.mission_id})
        task = call("create_task", {"title": "Disposable todo"}, approve=True)
        if task.success:
            call("update_task", {"task_id": task.output["id"], "note": "Checked"}, approve=True)
        call("send_agent_message", {"from_agent_id": "artemis", "to_agent_id": "fixture", "body": "Isolated tool verification"}, approve=True)
        call("remember", {"content": "Disposable Artemis tool verification"}, approve=True)
        call("recall", {"query": "Artemis"})
        call("consolidate_memory", {"content": "Explicitly requested disposable verification"}, approve=True)
        search = call("web_search", {"query": "Python documentation"})
        report["tools"]["web_search"]["service_result"] = search.output
        recording = runtime.voice.create_recording(transcript="Disposable transcript")
        call("voice.transcribe", {"recording_id": recording.recording_id})
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * 16000)
        spoken_fixture = ROOT / "artifacts/reports/artemis-spoken-fixture.wav"
        payload = spoken_fixture.read_bytes() if spoken_fixture.exists() else audio.getvalue()
        transcribed = call("audio.transcribe", {"audio_base64": base64.b64encode(payload).decode("ascii"), "audio_format": "audio/wav", "language": "en", "model": "tiny"})
        report["tools"]["audio.transcribe"]["service_result"] = transcribed.output
        report["tools"]["audio.transcribe"]["speech_fixture"] = spoken_fixture.exists()
        # Desktop executes only a dry-run plan. Report it as such, never as live input.
        plan = runtime.desktop.create_plan("artemis", "Disposable dry-run", [AutomationAction("window.focus", window_id="tool-test-no-window")], dry_run=True)
        call("desktop:runtime:preview", {"plan_id": plan.id})
        call("desktop:runtime:execute", {"plan_id": plan.id})
        cancelled = runtime.desktop.create_plan("artemis", "Disposable cancellation", [AutomationAction("window.focus", window_id="tool-test-no-window")], dry_run=True)
        call("desktop:runtime:cancel", {"plan_id": cancelled.id})
        call("desktop:runtime:recover", {"plan_id": cancelled.id})
        report["tools"]["desktop:runtime:recover"]["expected_rejection"] = "Cancelled plans cannot be recovered"
        report["untested"] = sorted({tool["tool_id"] for tool in report["inventory"]} - report["tools"].keys())
    destination = ROOT / "artifacts/reports/artemis-real-tools.json"
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(destination), "disks": report["disks"], "tools": report["tools"], "untested": report["untested"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
