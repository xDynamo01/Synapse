from __future__ import annotations

from .world_attention_support import DomainFixture, FixedDecisionRuntime, ToolSpy, loop


def test_agent_loop_routes_reversible_tool_and_verifies_result() -> None:
    fixture = DomainFixture()
    try:
        tool = ToolSpy()
        fixture.high_item("execute_reversible_action")
        runtime = loop(fixture, FixedDecisionRuntime("execute_reversible_action", {"tool_id": "test", "arguments": {}}), tool_runtime=tool)
        result = runtime.run_cycle("acceptance.tool")
        assert result.action_result is not None and result.action_result.verification["verified"]
        assert result.action_result.output_reference["call_id"] == "call-1"
        assert tool.calls == 1
    finally:
        fixture.close()
