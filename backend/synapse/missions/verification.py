from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    status: str
    checks: list[VerificationCheck]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    verifier: str = "synapse.result_verifier.v1"
    verified_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ResultVerifier:
    def verify(
        self, result: dict[str, Any] | None, policy: dict[str, Any] | None = None
    ) -> VerificationResult:
        policy = policy or {"checks": ["non_empty"]}
        checks: list[VerificationCheck] = []
        for name in policy.get("checks", ["non_empty"]):
            checks.append(self._check(name, result or {}, policy))
        errors = [check.error or f"{check.name} failed" for check in checks if not check.passed]
        return VerificationResult(
            status="passed" if checks and not errors else "failed", checks=checks, errors=errors
        )

    def _check(
        self, name: str, result: dict[str, Any], policy: dict[str, Any]
    ) -> VerificationCheck:
        if name == "non_empty":
            output = result.get("output")
            passed = output is not None and (not isinstance(output, str) or bool(output.strip()))
            return VerificationCheck(name, passed, error=None if passed else "Output is empty.")
        if name == "json_schema":
            output = result.get("output")
            try:
                value = json.loads(output) if isinstance(output, str) else output
                required = policy.get("json_schema", {}).get("required", [])
                passed = isinstance(value, dict) and all(key in value for key in required)
            except json.JSONDecodeError:
                passed = False
            return VerificationCheck(
                name, passed, error=None if passed else "Output does not satisfy JSON schema."
            )
        if name == "artifact_exists":
            path = Path(str(result.get("artifact", "")))
            passed = path.is_file()
            return VerificationCheck(
                name, passed, {"path": str(path)}, None if passed else "Artifact does not exist."
            )
        if name == "file_checksum":
            path = Path(str(result.get("artifact", "")))
            expected = policy.get("checksum")
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            passed = actual is not None and actual == expected
            return VerificationCheck(
                name, passed, {"sha256": actual}, None if passed else "Artifact checksum mismatch."
            )
        if name in {"command_exit_code", "tests_passed", "tool_confirmation", "reviewer_approval"}:
            key = {
                "command_exit_code": "exit_code",
                "tests_passed": "tests_passed",
                "tool_confirmation": "tool_confirmed",
                "reviewer_approval": "reviewer_approved",
            }[name]
            expected = 0 if key == "exit_code" else True
            passed = result.get(key) == expected
            return VerificationCheck(
                name, passed, error=None if passed else f"Missing verified evidence: {key}."
            )
        return VerificationCheck(name, False, error=f"Unsupported verification check: {name}")
