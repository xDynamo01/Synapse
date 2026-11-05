from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


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
        if name == "file_operations":
            root = Path(str(policy.get("root", ""))).resolve()
            observed: list[tuple[str, str]] = []
            listings: dict[int, set[str]] = {}
            for evidence in result.get("evidence", []):
                if not isinstance(evidence, dict) or evidence.get("kind") != "tool_result":
                    continue
                receipt = evidence.get("value", {})
                if not isinstance(receipt, dict) or receipt.get("success") is not True or receipt.get("status") != "executed":
                    continue
                call = receipt.get("request", {})
                output = receipt.get("result", {})
                if not isinstance(call, dict) or not isinstance(output, dict) or not output.get("path"):
                    continue
                path = Path(str(output["path"])).resolve()
                if path.is_relative_to(root):
                    observed.append((str(call.get("name", "")), str(path)))
                    if call.get("name") == "list_directory" and isinstance(output.get("entries"), list):
                        listings[len(observed) - 1] = {str(entry["name"]) for entry in output["entries"]
                                                       if isinstance(entry, dict) and "name" in entry}
            groups = policy.get("tool_groups", [])
            passed = bool(groups) and all(any(name in group for name, _ in observed) for group in groups)
            if policy.get("require_readback"):
                changes = [(index, tool, path) for index, (tool, path) in enumerate(observed) if tool in {"edit_file", "write_file", "delete_file"}]
                passed = passed and bool(changes) and all(
                    (any(tool == "list_directory" and Path(read_path) == Path(path).parent
                         and later in listings and Path(path).name not in listings[later]
                         for later, (tool, read_path) in enumerate(observed) if later > index)
                     if changed_tool == "delete_file" else
                     any(tool == "read_file" and read_path == path for tool, read_path in observed[index + 1:]))
                    for index, changed_tool, path in changes
                )
            return VerificationCheck(name, passed, {"observed": observed},
                                     None if passed else "Required project file operations were not verified by tool receipts.")
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
        if name == "image_integrity":
            path = Path(str(result.get("artifact", "")))
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    image_format = image.format
                    image.verify()
                passed = (width > 0 and height > 0
                          and width == policy.get("width", width)
                          and height == policy.get("height", height)
                          and image_format == policy.get("format", image_format))
                return VerificationCheck(name, passed, {"width": width, "height": height, "format": image_format},
                                         None if passed else "Image dimensions or format mismatch.")
            except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
                return VerificationCheck(name, False, error="Image artifact is invalid or unavailable.")
        if name in {"command_exit_code", "tests_passed", "tool_confirmation", "reviewer_approval"}:
            key = {
                "command_exit_code": "exit_code",
                "tests_passed": "tests_passed",
                "tool_confirmation": "tool_confirmed",
                "reviewer_approval": "reviewer_approved",
            }[name]
            expected = 0 if key == "exit_code" else True
            value = result.get(key)
            passed = type(value) is type(expected) and value == expected
            if policy.get("require_tool_evidence"):
                evidence = result.get("evidence", [])
                passed = any(
                    item.get("kind") == "tool_result"
                    and item.get("value", {}).get("success") is True
                    and item.get("value", {}).get("status") == "completed"
                    and type(item.get("value", {}).get("result", {}).get(key)) is type(expected)
                    and item.get("value", {}).get("result", {}).get(key) == expected
                    for item in evidence if isinstance(item, dict)
                    and isinstance(item.get("value"), dict)
                    and isinstance(item.get("value", {}).get("result"), dict)
                )
            return VerificationCheck(
                name, passed, error=None if passed else f"Missing verified evidence: {key}."
            )
        return VerificationCheck(name, False, error=f"Unsupported verification check: {name}")
