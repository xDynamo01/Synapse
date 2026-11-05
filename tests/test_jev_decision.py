from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from synapse.core.exceptions import ValidationError
from synapse.decision import DecisionCandidate, JevDecisionClient, JevDecisionError


class Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def candidates() -> list[DecisionCandidate]:
    return [
        DecisionCandidate("settings.voice", "Open voice settings."),
        DecisionCandidate("settings.models", "Open model settings."),
    ]


def test_jev_choice_is_validated_and_returns_only_a_candidate_id() -> None:
    payload = {
        "model": "jev-1.13.0",
        "answers": {
            "selection": {
                "type": "choice",
                "choice": "settings.voice",
                "confidence": 0.94,
                "probabilities": {"settings.voice": 0.94, "settings.models": 0.06},
            }
        },
        "usage": {"input_tokens": 12, "output_tokens": 0},
    }
    client = JevDecisionClient(api_key="secret")
    with patch("synapse.decision.jev.request.urlopen", return_value=Response(payload)):
        result = client.choose("abra as configurações de voz", candidates())
    assert result.candidate_id == "settings.voice"
    assert result.confidence == 0.94
    assert result.model == "jev-1.13.0"


def test_jev_never_accepts_unknown_or_duplicate_candidates() -> None:
    client = JevDecisionClient(api_key="secret")
    with pytest.raises(ValidationError):
        client.choose("open settings", [DecisionCandidate("bad id", "Invalid")])
    with pytest.raises(ValidationError):
        client.choose("open settings", [DecisionCandidate("same", "One"), DecisionCandidate("same", "Two")])


def test_jev_is_optional_without_a_key() -> None:
    client = JevDecisionClient()
    assert not client.configured
    with pytest.raises(JevDecisionError, match="not configured"):
        client.choose("open settings", candidates())
