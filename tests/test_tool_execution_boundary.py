from __future__ import annotations

import json
import threading
import time

from synapse.tools.models import ToolDefinition, ToolExecutionRequest
from synapse.tools.runtime import ToolRuntime
from test_tool_runtime_v1 import runtime_in_tempdir

VISIBLE_TEST_TOOLS = {
    "agent.summary",
    "audio.transcribe",
    "conversation.summary",
    "danger.mock",
    "health.summary",
    "mission.summary",
    "provider.summary",
    "readiness.summary",
    "tool.summary",
    "voice.transcribe",
}
LEGACY_TOOLS = {
    "create_task",
    "list_directory",
    "read_file",
    "search_files",
    "send_agent_message",
    "update_task",
    "web_search",
    "write_file",
}


def test_one_catalog_contains_runtime_legacy_and_desktop_descriptors() -> None:
    directory, _, runtime = runtime_in_tempdir()
    try:
        assert runtime.tools.tools is runtime.tool_runtime
        assert {tool.tool_id for tool in runtime.tool_runtime.list_tools()} == VISIBLE_TEST_TOOLS
        registered = {
            tool.tool_id for tool in runtime.tool_runtime.registry.list_registered_tools()
        }
        assert LEGACY_TOOLS <= registered
        assert {
            "desktop:runtime:preview",
            "desktop:runtime:execute",
            "desktop:runtime:cancel",
            "desktop:runtime:recover",
        } <= registered
    finally:
        directory.cleanup()


def test_legacy_facade_executes_through_canonical_history() -> None:
    directory, settings, runtime = runtime_in_tempdir()
    try:
        runtime.data_dir.resolve("memory/boundary.txt").write_text("boundary", encoding="utf-8")
        result = runtime.tools.execute(
            "read_file", runtime.context(), {"path": "memory/boundary.txt"}
        )
        records = [
            json.loads(line)
            for line in (settings.data_dir / "tools/execution_log.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert result["content"] == "boundary"
        assert records[-1]["tool"] == "read_file"
        assert runtime.tool_runtime.execution_counts["read_file"] == 1
    finally:
        directory.cleanup()


def test_timeout_verification_redaction_and_restart_idempotency() -> None:
    directory, settings, runtime = runtime_in_tempdir()
    try:
        runtime.tool_runtime.register(
            ToolDefinition(
                tool_id="test.slow",
                display_name="Slow",
                description="Timeout fixture.",
                category="test",
                input_schema={
                    "type": "object",
                    "properties": {"token": {"type": "string"}},
                    "additionalProperties": False,
                },
                timeout_default=0.005,
            ),
            lambda request: time.sleep(0.05) or {"token": request.arguments["token"]},
        )
        request = ToolExecutionRequest(
            tool_id="test.slow",
            arguments={"token": "sk-super-secret-value"},
            caller="local_owner",
            idempotency_key="stable-timeout",
        )
        first = runtime.tool_runtime.execute(request)
        assert first.status == "timed_out"
        assert runtime.tool_runtime.verification(first.call_id or "")["verified"] is False

        raw_log = (settings.data_dir / "tools/execution_log.jsonl").read_text(
            encoding="utf-8"
        )
        assert "sk-super-secret-value" not in raw_log
        assert "[REDACTED]" in raw_log

        restarted = ToolRuntime(
            runtime.data_dir,
            runtime.events,
            registry=runtime.tool_runtime.registry,
            permission_bridge=runtime.tool_runtime.permission_bridge,
        )
        replay = restarted.execute(request)
        assert replay.call_id == first.call_id
        assert replay.status == "timed_out"
        assert restarted.verification(replay.call_id or "")["verified"] is False
    finally:
        directory.cleanup()


def test_conflicting_duplicate_descriptor_is_rejected() -> None:
    directory, _, runtime = runtime_in_tempdir()
    try:
        runtime.tool_runtime.register(
            ToolDefinition("test.duplicate", "One", "One", "test"),
            lambda request: {},
        )
        try:
            runtime.tool_runtime.register(
                ToolDefinition("test.duplicate", "Two", "Two", "test"),
                lambda request: {},
            )
        except Exception as exc:
            assert "Conflicting tool id" in str(exc)
        else:
            raise AssertionError("conflicting duplicate tool id was accepted")
    finally:
        directory.cleanup()


def test_active_cancellation_is_canonical_and_idempotent() -> None:
    directory, _, runtime = runtime_in_tempdir()
    try:
        started = threading.Event()
        released = threading.Event()

        class CancellableAdapter:
            def __call__(self, request):
                started.set()
                released.wait(1)
                return {"finished": True}

            def cancel(self, request):
                released.set()
                return {"cancelled": True}

        runtime.tool_runtime.register(
            ToolDefinition(
                "test.cancellable",
                "Cancellable",
                "Cancellation fixture.",
                "test",
                supports_cancel=True,
            ),
            CancellableAdapter(),
        )
        request = ToolExecutionRequest(
            tool_id="test.cancellable", caller="local_owner", id="cancel-call"
        )
        thread = threading.Thread(target=runtime.tool_runtime.execute, args=(request,))
        thread.start()
        assert started.wait(1)
        first = runtime.tool_runtime.cancel("cancel-call")
        second = runtime.tool_runtime.cancel("cancel-call")
        thread.join(1)
        assert first.status == "cancelled"
        assert second == first
        assert runtime.tool_runtime.get_result("cancel-call").status == "cancelled"
    finally:
        directory.cleanup()
