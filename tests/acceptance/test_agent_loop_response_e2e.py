from __future__ import annotations

from .world_attention_support import ChatSpy, DomainFixture, FixedDecisionRuntime, loop


def test_agent_loop_routes_response_through_chat_and_verifies_persistence() -> None:
    fixture = DomainFixture()
    try:
        chat = ChatSpy()
        fixture.high_item("respond")
        runtime = loop(fixture, FixedDecisionRuntime("respond", {"message": "Please respond"}), chat_runtime=chat)
        result = runtime.run_cycle("acceptance.response")
        assert result.status == "completed"
        assert result.action_result is not None and result.action_result.verification["verified"]
        assert chat.calls == 1
        assert fixture.attention.get_item(result.attention_item_id).status == "resolved"
    finally:
        fixture.close()
