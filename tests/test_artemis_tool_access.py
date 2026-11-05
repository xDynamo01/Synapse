from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from factories.agents import seed_test_agent
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file
from synapse.models.types import ModelResponse
from synapse.tools.models import ToolExecutionRequest


@pytest.fixture(scope="module")
def artemis(tmp_path_factory):
    root = tmp_path_factory.mktemp("artemis-tool-access")
    settings = Settings(Path(__file__).resolve().parents[1], root / "data", "127.0.0.1", 0, "local_owner")
    create_runtime(settings)
    seed_test_agent(settings.data_dir, "artemis", role="primary_agent", extra={"permissions": []})
    seed_test_agent(settings.data_dir, "test_recipient")
    dump_structured_file(settings.data_dir / "config/filesystem_tools.yaml", {"all_disks": True})
    return create_runtime(settings)


def request(name, **arguments):
    return ToolExecutionRequest(tool_id=name, arguments=arguments, caller="artemis", caller_type="agent", agent_id="artemis")


def approved(runtime, call):
    pending = runtime.tool_runtime.execute(call)
    assert pending.status == "awaiting_approval", pending
    approval_id = pending.metadata["approval_id"]
    runtime.approvals.approve(runtime.context(), approval_id)
    result = runtime.tool_runtime.execute(replace(call, approval_id=approval_id))
    assert result.success, result
    return result


def test_real_file_crud_outside_data_directory(artemis, tmp_path):
    target = tmp_path / "todo.txt"
    call = request("write_file", path=str(target), content="Comprar pão\n")
    pending = artemis.tool_runtime.execute(call)
    assert pending.status == "awaiting_approval", pending
    assert not target.exists()
    artemis.approvals.approve(artemis.context(), pending.metadata["approval_id"])
    assert artemis.tool_runtime.execute(replace(call, approval_id=pending.metadata["approval_id"])).success
    assert target.read_text(encoding="utf-8") == "Comprar pão\n"
    read = artemis.tool_runtime.execute(request("read_file", path=str(target)))
    assert read.success and read.output["content"] == "Comprar pão\n"
    listing = artemis.tool_runtime.execute(request("list_directory", path=str(tmp_path)))
    assert listing.success and {"name": "todo.txt", "type": "file"} in listing.output["entries"]
    search = artemis.tool_runtime.execute(request("search_files", path=str(tmp_path), query="pão", pattern="*.txt"))
    assert search.success and search.output["results"]
    approved(artemis, request("edit_file", path=str(target), old_text="pão", new_text="leite"))
    assert target.read_text(encoding="utf-8") == "Comprar leite\n"
    pending_delete = artemis.tool_runtime.execute(request("delete_file", path=str(target)))
    assert pending_delete.status == "awaiting_approval" and target.exists()
    artemis.approvals.approve(artemis.context(), pending_delete.metadata["approval_id"])
    deleted = artemis.tool_runtime.execute(replace(request("delete_file", path=str(target)), approval_id=pending_delete.metadata["approval_id"]))
    assert deleted.success and not target.exists()


def test_disk_inventory(artemis):
    result = artemis.tool_runtime.execute(request("list_disks"))
    assert result.success, result
    assert str(artemis.data_dir.root.anchor) in result.output["roots"]


@pytest.mark.parametrize("name", ["health.summary", "readiness.summary", "provider.summary", "tool.summary", "memory_index"])
def test_read_only_tools(artemis, name):
    result = artemis.tool_runtime.execute(request(name))
    assert result.success, result


def test_summary_tools(artemis):
    conversation = artemis.conversations.create_conversation(artemis.context(), ["artemis"], title="Tool fixture")
    mission = artemis.missions.create_mission(title="Tool fixture", owner_agent_id="artemis")
    for call in [request("agent.summary", agent_id="artemis"), request("conversation.summary", conversation_id=conversation.conversation_id), request("mission.summary", mission_id=mission.mission_id)]:
        result = artemis.tool_runtime.execute(call)
        assert result.success, result


def test_tasks_and_agent_message(artemis):
    task = approved(artemis, request("create_task", title="Disposable todo", description="Tool test"))
    approved(artemis, request("update_task", task_id=task.output["id"], note="Verified"))
    approved(artemis, request("send_agent_message", from_agent_id="artemis", to_agent_id="test_recipient", body="Isolated integration fixture"))


def test_memory_tools(artemis):
    saved = approved(artemis, request("remember", content="Tool validation marker Aurora"))
    recalled = artemis.tool_runtime.execute(request("recall", query="Aurora"))
    assert recalled.success and saved.output["memory_id"] in str(recalled.output), recalled
    approved(artemis, request("consolidate_memory", content="Explicitly requested disposable memory"))


def test_primary_has_tools_without_manual_permission_and_cannot_self_approve(artemis):
    context = PermissionContext("artemis", "agent")
    assert artemis.permissions.is_allowed(context, "filesystem.write").allowed
    assert not artemis.permissions.is_allowed(context, "approvals.approve").allowed
    loaded = artemis.context_loader.load(artemis.context(), "artemis")
    with patch.object(artemis.models, "generate", return_value=ModelResponse(content="Catalog test", provider="mock", model="test")):
        result = artemis.agent_runtime.run(artemis.context(), "artemis", loaded, "List tools")
    expected = {tool.tool_id for tool in artemis.tool_runtime.registry.list_registered_tools() if tool.enabled}
    assert expected <= {tool["name"] for tool in result.tools}
    catalog = {tool.tool_id: tool for tool in artemis.agent_runtime.available_tools("artemis").tools}
    assert catalog["read_file"].available
    assert catalog["edit_file"].requires_approval
    assert catalog["delete_file"].requires_approval


def test_control_plane_files_cannot_be_overwritten(artemis):
    from synapse.core.exceptions import ValidationError
    from synapse.tools.filesystem_access import resolve_tool_path
    with pytest.raises(ValidationError, match="Control-plane"):
        resolve_tool_path(artemis.data_dir, "config/permissions.yaml", mutation=True)


def test_explicit_deny_still_wins(artemis):
    artemis.permissions.denies["agent:artemis"] = {"filesystem.read"}
    try:
        result = artemis.tool_runtime.execute(request("read_file", path="config/system.yaml"))
        assert not result.success
    finally:
        artemis.permissions.denies.pop("agent:artemis")


def test_full_catalog_fits_small_local_model_default_budget(artemis):
    from synapse.models.adapters import build_chat_messages
    from synapse.models.types import ModelRequest
    loaded = artemis.context_loader.load(artemis.context(), "artemis")
    captured = []
    def inference(call):
        build_chat_messages(call)
        captured.append(call)
        return ModelResponse(content="Budget verified", provider="synapse_local", model="small")
    with patch.object(artemis.models.adapters["synapse_local"], "generate", side_effect=inference):
        artemis.agent_runtime.run(artemis.context(), "artemis", loaded, "List disks", model_request=ModelRequest(
            agent_id="artemis", provider="synapse_local", model="small", user_message="List disks",
            context=loaded.to_dict(), metadata={"context_window": 4096},
        ))
    assert captured[0].max_tokens == 256
    assert captured[0].metadata["context_budget"]["input_tokens"] + 256 <= 4096


def test_desktop_adapters_preserve_execution_and_recovery(artemis):
    from acceptance.test_desktop_automation_e2e import (
        ConformanceInputProvider,
        ConformanceProvider,
        _rule,
    )
    from synapse.bootstrap.adapters.tool_execution import register_desktop_tool_adapters
    from synapse.desktop_automation.models import AutomationAction
    from synapse.desktop_automation.runtime import DesktopRuntime
    provider = ConformanceProvider()
    desktop = DesktopRuntime(artemis.data_dir, artemis.events, artemis.policies, artemis.approvals,
                             artemis.audit, artemis.vision, provider=provider,
                             input_provider=ConformanceInputProvider(), visual_providers=[])
    artemis.policies.create_rule(_rule("artemis", "allow"))
    register_desktop_tool_adapters(artemis.tool_runtime, desktop)
    plan = desktop.create_plan("artemis", "Focus test fixture", [AutomationAction("window.focus", window_id="window:1", max_attempts=1)])
    preview = artemis.tool_runtime.execute(request("desktop:runtime:preview", plan_id=plan.id))
    assert preview.success and preview.output["status"] == "previewed"
    provider.fail_focus = 1
    failure = artemis.tool_runtime.execute(request("desktop:runtime:execute", plan_id=plan.id))
    assert failure.output["status"] == "failed"
    recovered = artemis.tool_runtime.execute(request("desktop:runtime:recover", plan_id=plan.id))
    assert recovered.success and recovered.output["status"] == "completed"
    pending = desktop.create_plan("artemis", "Cancel test fixture", [AutomationAction("window.focus", window_id="window:1")])
    cancelled = artemis.tool_runtime.execute(request("desktop:runtime:cancel", plan_id=pending.id))
    assert cancelled.success and cancelled.output["status"] == "cancelled"


def test_agent_without_agent_id_cannot_bypass_approval(artemis, tmp_path):
    result = artemis.tool_runtime.execute(replace(request("write_file", path=str(tmp_path / "blocked.txt"), content="test"), agent_id=None))
    assert result.status == "awaiting_approval", result
    assert not (tmp_path / "blocked.txt").exists()
