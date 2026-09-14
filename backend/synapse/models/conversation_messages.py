"""Ordered conversation messages shared by text and voice inference."""

from collections.abc import Mapping, Sequence


def conversation_messages(
    system: str,
    history: Sequence[Mapping[str, object]],
    current: str,
    *,
    history_char_budget: int = 8000,
) -> list[dict[str, str]]:
    """Keep recent dialogue roles; history cannot introduce system instructions."""
    recent: list[dict[str, str]] = []
    remaining = max(0, history_char_budget)
    for item in reversed(history):
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        if len(content) > remaining:
            break
        recent.append({"role": str(role), "content": content})
        remaining -= len(content)
    recent.reverse()
    # A retained suffix must not start with an orphaned assistant response.
    while recent and recent[0]["role"] != "user":
        recent.pop(0)
    return [{"role": "system", "content": system}, *recent, {"role": "user", "content": current}]
