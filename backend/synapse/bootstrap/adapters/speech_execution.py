from __future__ import annotations

import subprocess
from pathlib import Path

from synapse.speech_adapters.execution import (
    SpeechExecutionOutcome,
    SpeechExecutionRequest,
    SpeechExecutionResult,
)


class LocalSpeechExecutionPort:
    """Local process boundary for governed speech tools.

    The speech adapter constructs a structured request. This boundary executes
    that exact argv without shell expansion and reports only observed facts.
    """

    def execute(self, request: SpeechExecutionRequest) -> SpeechExecutionResult:
        output_path = _expected_output_path(request.argv)
        try:
            completed = subprocess.run(
                request.argv,
                input=request.stdin.text if request.stdin else None,
                text=True,
                capture_output=True,
                timeout=request.timeout_seconds,
                shell=False,
                check=False,
            )
        except FileNotFoundError:
            return _result(request, SpeechExecutionOutcome.UNAVAILABLE, started=False)
        except subprocess.TimeoutExpired:
            return _result(request, SpeechExecutionOutcome.TIMEOUT_OBSERVED, started=True)
        except OSError:
            return _result(request, SpeechExecutionOutcome.UNAVAILABLE, started=False)
        except subprocess.SubprocessError:
            return _result(request, SpeechExecutionOutcome.FAILED, started=True)

        produced: tuple[str, ...] = ()
        if output_path is not None and output_path.is_file() and output_path.stat().st_size > 0:
            produced = request.expected_output_artifact_references
        return _result(
            request,
            SpeechExecutionOutcome.EXITED,
            started=True,
            exit_code=completed.returncode,
            termination_proved=True,
            produced_artifact_references=produced,
        )


def _expected_output_path(argv: tuple[str, ...]) -> Path | None:
    try:
        index = argv.index("--output_file") + 1
    except ValueError:
        return None
    if index >= len(argv):
        return None
    return Path(argv[index])


def _result(
    request: SpeechExecutionRequest,
    outcome: SpeechExecutionOutcome,
    *,
    started: bool,
    exit_code: int | None = None,
    termination_proved: bool = False,
    produced_artifact_references: tuple[str, ...] = (),
) -> SpeechExecutionResult:
    return SpeechExecutionResult.create(
        request_id=request.request_id,
        request_fingerprint=request.fingerprint,
        outcome=outcome,
        accepted=True,
        started=started,
        exit_code=exit_code,
        termination_proved=termination_proved,
        produced_artifact_references=produced_artifact_references,
    )
