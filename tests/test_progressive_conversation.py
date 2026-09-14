import json
from threading import Event

import pytest

from synapse.chat.streaming import stream_response
from synapse.models.errors import ModelError
from synapse.models.stream_response import read_stream
from synapse.models.streaming import emit_text, text_stream


def sse(payload):
    return ("data: " + json.dumps(payload) + "\n").encode()


def test_first_text_arrives_before_turn_completion():
    release = Event()

    def work():
        emit_text("Olá")
        assert release.wait(3)
        return "Olá"

    stream = stream_response(work)
    try:
        assert next(stream) == ("chunk_received", "Olá")
        release.set()
        assert next(stream) == ("generation_completed", "Olá")
    finally:
        release.set()
        stream.close()


def test_sse_text_and_fragmented_tools_are_assembled_separately():
    received = []
    with text_stream(received.append):
        result = read_stream([
            sse({"choices": [{"delta": {"content": "Olá"}}]}),
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "recall", "arguments": '{"query":'}}]}}]}),
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"Aurora"}'}}]}, "finish_reason": "tool_calls"}]}),
            b"data: [DONE]\n",
        ])
    assert received == ["Olá"]
    message = result["choices"][0]["message"]
    assert message["tool_calls"][0]["function"]["arguments"] == '{"query":"Aurora"}'


def test_truncated_stream_is_not_success():
    with pytest.raises(ModelError):
        read_stream([sse({"choices": [{"delta": {"content": "Partial"}}]})])


def test_voice_result_json_is_not_emitted_as_text():
    assert list(stream_response(lambda: '{"tts":{}}', fallback_text=False)) == [
        ("generation_completed", '{"tts":{}}'),
    ]
