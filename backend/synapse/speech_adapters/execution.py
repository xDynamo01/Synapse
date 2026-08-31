from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

EXECUTION_REQUEST_FORMAT = "speech-execution-request-v1"
EXECUTION_RESULT_FORMAT = "speech-execution-result-v1"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_reference(value: str, field_name: str) -> None:
    if not value.strip() or any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError(f"{field_name} must be an opaque single-line reference.")


class SpeechExecutionOutcome(StrEnum):
    EXITED = "exited"
    TIMEOUT_OBSERVED = "timeout_observed"
    CANCELLATION_OBSERVED = "cancellation_observed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SpeechExecutionStdin:
    reference: str
    checksum: str
    text: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_reference(self.reference, "stdin.reference")
        expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.checksum != expected:
            raise ValueError("stdin.checksum does not match the transient payload.")


@dataclass(frozen=True, slots=True)
class SpeechExecutionRequest:
    tool_reference: str
    argv: tuple[str, ...]
    stdin: SpeechExecutionStdin | None
    working_directory_reference: str | None
    timeout_seconds: float
    environment_references: tuple[str, ...]
    input_artifact_references: tuple[str, ...]
    expected_output_artifact_references: tuple[str, ...]
    correlation_reference: str
    policy_reference: str
    capability_reference: str
    shell: bool = False
    format_version: str = EXECUTION_REQUEST_FORMAT
    request_id: str = ""
    fingerprint: str = ""

    @classmethod
    def create(
        cls,
        *,
        tool_reference: str,
        argv: tuple[str, ...],
        stdin: SpeechExecutionStdin | None,
        working_directory_reference: str | None,
        timeout_seconds: float,
        environment_references: tuple[str, ...],
        input_artifact_references: tuple[str, ...],
        expected_output_artifact_references: tuple[str, ...],
        correlation_reference: str,
        policy_reference: str,
        capability_reference: str,
    ) -> SpeechExecutionRequest:
        semantic = {
            "argv": argv,
            "capability_reference": capability_reference,
            "correlation_reference": correlation_reference,
            "environment_references": sorted(environment_references),
            "expected_output_artifact_references": sorted(expected_output_artifact_references),
            "format_version": EXECUTION_REQUEST_FORMAT,
            "input_artifact_references": sorted(input_artifact_references),
            "policy_reference": policy_reference,
            "shell": False,
            "stdin": (stdin.reference, stdin.checksum) if stdin else None,
            "timeout_seconds": timeout_seconds,
            "tool_reference": tool_reference,
            "working_directory_reference": working_directory_reference,
        }
        fingerprint = _digest(semantic)
        return cls(
            tool_reference=tool_reference,
            argv=argv,
            stdin=stdin,
            working_directory_reference=working_directory_reference,
            timeout_seconds=timeout_seconds,
            environment_references=tuple(sorted(environment_references)),
            input_artifact_references=tuple(sorted(input_artifact_references)),
            expected_output_artifact_references=tuple(sorted(expected_output_artifact_references)),
            correlation_reference=correlation_reference,
            policy_reference=policy_reference,
            capability_reference=capability_reference,
            request_id=f"speech-exec-{fingerprint[:24]}",
            fingerprint=fingerprint,
        )

    def __post_init__(self) -> None:
        for field_name, value in (
            ("tool_reference", self.tool_reference),
            ("correlation_reference", self.correlation_reference),
            ("policy_reference", self.policy_reference),
            ("capability_reference", self.capability_reference),
        ):
            _require_reference(value, field_name)
        if self.working_directory_reference is not None:
            _require_reference(self.working_directory_reference, "working_directory_reference")
        if not self.argv or any(not argument or "\x00" in argument for argument in self.argv):
            raise ValueError("argv must contain structured non-empty arguments.")
        if self.shell:
            raise ValueError("Implicit shell execution is forbidden.")
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds is outside the supported boundary.")
        for values, field_name in (
            (self.environment_references, "environment_references"),
            (self.input_artifact_references, "input_artifact_references"),
            (self.expected_output_artifact_references, "expected_output_artifact_references"),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{field_name} must be unique and canonical.")
            for value in values:
                _require_reference(value, field_name)


@dataclass(frozen=True, slots=True)
class SpeechExecutionResult:
    request_id: str
    request_fingerprint: str
    outcome: SpeechExecutionOutcome
    accepted: bool
    started: bool
    exit_code: int | None = None
    termination_proved: bool = False
    stdout_reference: str | None = None
    stderr_reference: str | None = None
    produced_artifact_references: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    format_version: str = EXECUTION_RESULT_FORMAT
    result_fingerprint: str = ""

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        request_fingerprint: str,
        outcome: SpeechExecutionOutcome,
        accepted: bool,
        started: bool,
        exit_code: int | None = None,
        termination_proved: bool = False,
        stdout_reference: str | None = None,
        stderr_reference: str | None = None,
        produced_artifact_references: tuple[str, ...] = (),
        diagnostics: tuple[str, ...] = (),
    ) -> SpeechExecutionResult:
        canonical_artifacts = tuple(sorted(produced_artifact_references))
        canonical_diagnostics = tuple(sorted(diagnostics))
        result = cls(
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            outcome=outcome,
            accepted=accepted,
            started=started,
            exit_code=exit_code,
            termination_proved=termination_proved,
            stdout_reference=stdout_reference,
            stderr_reference=stderr_reference,
            produced_artifact_references=canonical_artifacts,
            diagnostics=canonical_diagnostics,
        )
        semantic = result._semantic()
        return cls(
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            outcome=outcome,
            accepted=accepted,
            started=started,
            exit_code=exit_code,
            termination_proved=termination_proved,
            stdout_reference=stdout_reference,
            stderr_reference=stderr_reference,
            produced_artifact_references=canonical_artifacts,
            diagnostics=canonical_diagnostics,
            result_fingerprint=_digest(semantic),
        )

    def _semantic(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "diagnostics": self.diagnostics,
            "exit_code": self.exit_code,
            "format_version": self.format_version,
            "outcome": self.outcome.value,
            "produced_artifact_references": self.produced_artifact_references,
            "request_fingerprint": self.request_fingerprint,
            "request_id": self.request_id,
            "started": self.started,
            "stderr_reference": self.stderr_reference,
            "stdout_reference": self.stdout_reference,
            "termination_proved": self.termination_proved,
        }

    def __post_init__(self) -> None:
        _require_reference(self.request_id, "request_id")
        if self.outcome is SpeechExecutionOutcome.EXITED and self.exit_code is None:
            raise ValueError("An exited process requires an exit code observation.")
        if self.outcome is not SpeechExecutionOutcome.EXITED and self.exit_code is not None:
            raise ValueError("Only an exited process may carry an exit code.")
        if self.started and not self.accepted:
            raise ValueError("Execution cannot start before request acceptance.")
        if self.termination_proved and not self.started:
            raise ValueError("Termination proof requires an observed start.")
        if self.produced_artifact_references != tuple(
            sorted(set(self.produced_artifact_references))
        ):
            raise ValueError("Produced artifact references must be unique and canonical.")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise ValueError("Diagnostics must be unique and canonical.")
        if self.result_fingerprint and self.result_fingerprint != _digest(self._semantic()):
            raise ValueError("Execution result fingerprint mismatch.")


class SpeechExecutionPort(Protocol):
    def execute(self, request: SpeechExecutionRequest) -> SpeechExecutionResult: ...


class SpeechExecutionResultLedger:
    """Correlate factual results without executing or inferring lifecycle facts."""

    def __init__(self) -> None:
        self._registrations: dict[str, str] = {}
        self._results: dict[str, SpeechExecutionResult] = {}

    def register_request(self, request: SpeechExecutionRequest) -> None:
        existing = self._registrations.get(request.request_id)
        if existing is not None and existing != request.fingerprint:
            raise ValueError("Execution request identity conflict.")
        self._registrations[request.request_id] = request.fingerprint

    def accept_result(self, result: SpeechExecutionResult) -> SpeechExecutionResult:
        expected = self._registrations.get(result.request_id)
        if expected is None:
            raise ValueError("Execution result has no registered request.")
        if expected != result.request_fingerprint:
            raise ValueError("Execution result request fingerprint mismatch.")
        existing = self._results.get(result.request_id)
        if existing is not None:
            if existing.result_fingerprint != result.result_fingerprint:
                raise ValueError("Contradictory execution result.")
            return existing
        self._results[result.request_id] = result
        return result
