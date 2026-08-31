from __future__ import annotations

import json
import re
from typing import Any

from synapse.agent_tool_calling.models import (
    AgentToolCallingParseResult,
    AgentToolCallProposal,
)

FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def parse_explicit_json_block(text: str) -> AgentToolCallingParseResult:
    raw_text = text or ""
    blocks = [match.strip() for match in FENCED_JSON.findall(raw_text) if match.strip()]
    stripped = raw_text.strip()
    if not blocks and stripped.startswith(("{", "[")):
        blocks = [stripped]
    if not blocks:
        return AgentToolCallingParseResult(False, [], [], raw_text)

    proposals: list[AgentToolCallProposal] = []
    errors: list[str] = []
    for index, block in enumerate(blocks, start=1):
        try:
            payload = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON block {index}: {exc.msg}")
            continue
        items = payload if isinstance(payload, list) else [payload]
        if not isinstance(items, list):
            errors.append(f"JSON block {index} must be an object or list")
            continue
        for item_index, item in enumerate(items, start=1):
            proposal_payload = item.get("synapse_tool_intent") if isinstance(item, dict) else None
            if proposal_payload is None:
                errors.append(
                    f"JSON block {index} item {item_index} does not contain synapse_tool_intent"
                )
                continue
            proposal_items = (
                proposal_payload if isinstance(proposal_payload, list) else [proposal_payload]
            )
            for proposal_index, raw_proposal in enumerate(proposal_items, start=1):
                proposal, error = _proposal_from_payload(raw_proposal, block)
                if error:
                    errors.append(
                        f"JSON block {index} item {item_index} proposal {proposal_index}: {error}"
                    )
                elif proposal:
                    proposals.append(proposal)
    return AgentToolCallingParseResult(bool(proposals), proposals, errors, raw_text)


def _proposal_from_payload(
    payload: Any,
    raw_text: str,
) -> tuple[AgentToolCallProposal | None, str | None]:
    if not isinstance(payload, dict):
        return None, "proposal must be an object"
    tool_id = payload.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id.strip():
        return None, "tool_id is required"
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        return None, "arguments must be an object"
    confidence = payload.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        return None, "confidence must be numeric"
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return None, "metadata must be an object"
    return (
        AgentToolCallProposal(
            tool_id=tool_id.strip(),
            arguments=arguments,
            reason=str(payload["reason"]) if payload.get("reason") is not None else None,
            confidence=float(confidence) if confidence is not None else None,
            raw_text=raw_text,
            metadata=metadata,
        ),
        None,
    )
