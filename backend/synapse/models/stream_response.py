"""Assemble an SSE completion while delivering text as it arrives."""

import json
from collections.abc import Iterable

from synapse.models.errors import ModelError
from synapse.models.streaming import emit_text


def read_stream(lines: Iterable[bytes]) -> dict[str, object]:
    content: list[str] = []
    reasoning: list[str] = []
    calls: dict[int, dict[str, str]] = {}
    result: dict[str, object] = {}
    finish: str | None = None
    for encoded in lines:
        line = encoded.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        raw = json.loads(data)
        if not isinstance(raw, dict) or raw.get("error"):
            raise ModelError("provider_response_invalid", "Invalid model stream response")
        for key in ("id", "model", "usage"):
            if raw.get(key) is not None:
                result[key] = raw[key]
        for choice in raw.get("choices", []):
            if choice.get("index", 0) != 0:
                continue
            delta = choice.get("delta") or {}
            text = delta.get("content") or ""
            if text:
                content.append(text)
                emit_text(text)
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            for item in delta.get("tool_calls") or []:
                call = calls.setdefault(item["index"], {"id": "", "name": "", "arguments": ""})
                if item.get("id"):
                    call["id"] = item["id"]
                function = item.get("function") or {}
                for key in ("name", "arguments"):
                    call[key] += function.get(key) or ""
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
    if finish is None:
        raise ModelError("provider_response_invalid", "Model stream ended before completion")
    result["choices"] = [{"finish_reason": finish, "message": {
        "content": "".join(content), "reasoning_content": "".join(reasoning),
        "tool_calls": [{"id": call["id"], "type": "function", "function": {
            "name": call["name"], "arguments": call["arguments"],
        }} for _, call in sorted(calls.items())],
    }}]
    return result
