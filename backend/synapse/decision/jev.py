from __future__ import annotations

import json
import os
import re
from typing import Mapping, cast
from urllib import request
from urllib.error import HTTPError, URLError

from synapse.core.exceptions import ToolExecutionError, ValidationError
from synapse.decision.models import DecisionCandidate, DecisionResult

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_DEFAULT_MODEL = "jev-latest"
_MAX_CANDIDATES = 255


class JevDecisionError(ToolExecutionError):
    """Jev was unavailable or returned a response outside the contract."""


class JevDecisionClient:
    """Small optional client for TypeSafe's typed choice endpoint.

    The client sends text plus a closed candidate set. It never accepts an
    action, URL, tool name or argument from Jev; the caller owns execution.
    """

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str = _DEFAULT_ENDPOINT,
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.endpoint = endpoint.strip() or _DEFAULT_ENDPOINT
        self.model = model.strip() or _DEFAULT_MODEL
        self.timeout_seconds = max(0.5, timeout_seconds)

    @classmethod
    def from_environment(cls) -> "JevDecisionClient":
        return cls(
            api_key=os.environ.get("JEV_API_KEY"),
            endpoint=os.environ.get("JEV_ENDPOINT", _DEFAULT_ENDPOINT),
            model=os.environ.get("JEV_MODEL", _DEFAULT_MODEL),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def choose(self, state: str, candidates: list[DecisionCandidate]) -> DecisionResult:
        normalized_state = state.strip()
        if not normalized_state or len(normalized_state) > 20_000:
            raise ValidationError("Jev decision state must contain 1-20000 characters.")
        self._validate_candidates(candidates)
        if not self.configured:
            raise JevDecisionError("Jev is not configured; set JEV_API_KEY to enable it.")

        criteria = {candidate.candidate_id: candidate.description for candidate in candidates}
        payload = {
            "model": self.model,
            "state": normalized_state,
            "questions": {
                "selection": {
                    "type": "choice",
                    "instructions": "Choose the single candidate that best matches the user's request.",
                    "criteria": criteria,
                }
            },
        }
        response = self._post(payload)
        return self._parse_response(response, criteria)

    @staticmethod
    def _validate_candidates(candidates: list[DecisionCandidate]) -> None:
        if not candidates or len(candidates) > _MAX_CANDIDATES:
            raise ValidationError("Jev requires between 1 and 255 candidates.")
        ids = [candidate.candidate_id for candidate in candidates]
        if len(set(ids)) != len(ids) or any(not _ID_PATTERN.fullmatch(item) for item in ids):
            raise ValidationError("Jev candidate IDs must be unique and use safe identifier characters.")
        if any(not candidate.description.strip() for candidate in candidates):
            raise ValidationError("Jev candidate descriptions cannot be empty.")

    def _post(self, payload: Mapping[str, object]) -> dict[str, object]:
        http_request = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise JevDecisionError("Jev decision request failed.") from exc
        if not isinstance(parsed, dict):
            raise JevDecisionError("Jev returned an invalid response envelope.")
        return cast(dict[str, object], parsed)

    @staticmethod
    def _parse_response(response: dict[str, object], criteria: dict[str, str]) -> DecisionResult:
        answers = response.get("answers")
        if not isinstance(answers, dict):
            raise JevDecisionError("Jev response has no answers object.")
        answer = answers.get("selection")
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise JevDecisionError("Jev response does not contain a choice answer.")
        candidate_id = answer.get("choice")
        confidence = answer.get("confidence")
        probabilities = answer.get("probabilities")
        if (
            not isinstance(candidate_id, str)
            or candidate_id not in criteria
            or not isinstance(confidence, (int, float))
            or not 0.0 <= float(confidence) <= 1.0
            or not isinstance(probabilities, dict)
        ):
            raise JevDecisionError("Jev returned a choice outside the candidate contract.")
        parsed_probabilities: dict[str, float] = {}
        for key, value in probabilities.items():
            if isinstance(key, str) and isinstance(value, (int, float)):
                parsed_probabilities[key] = float(value)
        if set(parsed_probabilities) != set(criteria):
            raise JevDecisionError("Jev probabilities do not match the candidate set.")
        usage = response.get("usage")
        usage_map = usage if isinstance(usage, dict) else {}
        model = response.get("model")
        return DecisionResult(
            candidate_id=candidate_id,
            confidence=float(confidence),
            probabilities=parsed_probabilities,
            model=model if isinstance(model, str) else _DEFAULT_MODEL,
            input_tokens=(
                int(usage_map["input_tokens"])
                if isinstance(usage_map.get("input_tokens"), int)
                else None
            ),
            output_tokens=(
                int(usage_map["output_tokens"])
                if isinstance(usage_map.get("output_tokens"), int)
                else None
            ),
        )
