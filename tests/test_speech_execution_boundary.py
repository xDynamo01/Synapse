from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import wave
from dataclasses import replace
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.audio.models import AudioOutputRequest
from synapse.bootstrap.adapters.speech_execution import LocalSpeechExecutionPort
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.speech_adapters.execution import (
    SpeechExecutionOutcome,
    SpeechExecutionRequest,
    SpeechExecutionResult,
    SpeechExecutionResultLedger,
    SpeechExecutionStdin,
)
from synapse.speech_adapters.models import SpeechAdapterManifest
from synapse.speech_adapters.piper_tts import PiperTextToSpeechAdapter


def _manifest() -> SpeechAdapterManifest:
    return SpeechAdapterManifest(
        adapter_id="piper_tts_adapter",
        provider_id="piper",
        adapter_type="tts",
        name="Piper",
        description="test",
        version="1",
        supported_languages=["pt-BR"],
        supports_streaming=False,
        supports_file_input=False,
        supports_realtime=False,
        requires_gpu=False,
        requires_network=False,
    )


def _request() -> SpeechExecutionRequest:
    text = "hello"
    stdin = SpeechExecutionStdin(
        "transient://text/1",
        hashlib.sha256(text.encode()).hexdigest(),
        text,
    )
    return SpeechExecutionRequest.create(
        tool_reference="tool://piper",
        argv=("piper", "--model", "model.onnx"),
        stdin=stdin,
        working_directory_reference="workspace://voice/synthesis",
        timeout_seconds=10,
        environment_references=("secret-ref://piper/license",),
        input_artifact_references=("artifact://model/1",),
        expected_output_artifact_references=("artifact://audio/1",),
        correlation_reference="voice-session://1",
        policy_reference="policy://speech/piper",
        capability_reference="capability://voice/tts",
    )


def _result(
    request: SpeechExecutionRequest,
    outcome: SpeechExecutionOutcome = SpeechExecutionOutcome.EXITED,
    *,
    exit_code: int | None = 0,
    artifacts: tuple[str, ...] = (),
    termination_proved: bool = False,
) -> SpeechExecutionResult:
    return SpeechExecutionResult.create(
        request_id=request.request_id,
        request_fingerprint=request.fingerprint,
        outcome=outcome,
        accepted=True,
        started=True,
        exit_code=exit_code,
        termination_proved=termination_proved,
        produced_artifact_references=artifacts,
    )


def _wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\x00\x00" * 160)
    return output.getvalue()


class ControlledExecutor:
    def __init__(
        self,
        outcome: SpeechExecutionOutcome = SpeechExecutionOutcome.EXITED,
        exit_code: int | None = 0,
        *,
        report_artifact: bool = True,
        output: bytes | None = None,
        termination_proved: bool = False,
    ) -> None:
        self.outcome = outcome
        self.exit_code = exit_code
        self.report_artifact = report_artifact
        self.output = _wav_bytes() if output is None else output
        self.termination_proved = termination_proved
        self.requests: list[SpeechExecutionRequest] = []

    def execute(self, request: SpeechExecutionRequest) -> SpeechExecutionResult:
        self.requests.append(request)
        artifact_ref = request.expected_output_artifact_references[0]
        if self.outcome is SpeechExecutionOutcome.EXITED and self.exit_code == 0:
            output_index = request.argv.index("--output_file") + 1
            Path(request.argv[output_index]).write_bytes(self.output)
        return _result(
            request,
            self.outcome,
            exit_code=self.exit_code,
            artifacts=(artifact_ref,) if self.report_artifact else (),
            termination_proved=self.termination_proved,
        )


def _adapter(root: Path, executor: ControlledExecutor | None) -> PiperTextToSpeechAdapter:
    executable = root / "piper.exe"
    model = root / "voice.onnx"
    executable.write_bytes(b"not executed")
    model.write_bytes(b"model")
    data_root = root / "data"
    settings_path = data_root / "voice" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"piper": {"executable": str(executable), "model": str(model)}}),
        encoding="utf-8",
    )
    return PiperTextToSpeechAdapter(_manifest(), DataDir(data_root), executor)


def test_request_is_structured_deterministic_and_never_implicit_shell() -> None:
    first = _request()
    second = _request()
    assert first.argv == ("piper", "--model", "model.onnx")
    assert first.shell is False
    assert first.request_id == second.request_id
    assert first.fingerprint == second.fingerprint
    assert "hello" not in repr(first.stdin)
    with pytest.raises(ValueError, match="shell"):
        replace(first, shell=True)


def test_result_ledger_accepts_late_duplicate_and_rejects_contradiction() -> None:
    request = _request()
    ledger = SpeechExecutionResultLedger()
    ledger.register_request(request)
    result = _result(request, artifacts=("artifact://audio/1",))
    assert ledger.accept_result(result) is result
    assert ledger.accept_result(result) is result
    contradictory = _result(request, exit_code=7)
    with pytest.raises(ValueError, match="Contradictory"):
        ledger.accept_result(contradictory)


def test_timeout_does_not_imply_termination_proof() -> None:
    request = _request()
    result = _result(
        request,
        SpeechExecutionOutcome.TIMEOUT_OBSERVED,
        exit_code=None,
    )
    assert result.started is True
    assert result.termination_proved is False


def test_piper_has_no_operational_fallback_when_boundary_is_unavailable() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        adapter = _adapter(Path(temporary), None)
        assert adapter.health().status == "degraded"
        with pytest.raises(ValidationError, match="execution boundary"):
            adapter.synthesize(AudioOutputRequest(session_id="s1", text="hello"))


def test_piper_reports_missing_executable_and_uses_packaged_default_voice_factually() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        data_root = root / "data"
        settings_path = data_root / "voice" / "settings.yaml"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(
            json.dumps({"piper": {"executable": str(root / "missing.exe")}}),
            encoding="utf-8",
        )
        adapter = PiperTextToSpeechAdapter(_manifest(), DataDir(data_root), ControlledExecutor())
        assert adapter.health().status == "unavailable"
        with pytest.raises(ValidationError, match="executable is unavailable"):
            adapter.synthesize(AudioOutputRequest(session_id="s1", text="hello"))

        executable = root / "piper.exe"
        executable.write_bytes(b"not executed")
        settings_path.write_text(
            json.dumps({"piper": {"executable": str(executable)}}),
            encoding="utf-8",
        )
        assert adapter.health().status == "available"
        result = adapter.synthesize(AudioOutputRequest(session_id="s1", text="hello"))
        assert result.voice_id == "synapse-bryce"


def test_piper_fake_executor_success_requires_reported_and_valid_artifact() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        executor = ControlledExecutor()
        adapter = _adapter(Path(temporary), executor)
        result = adapter.synthesize(AudioOutputRequest(session_id="s1", text="hello"))
        request = executor.requests[0]
        assert request.shell is False
        assert request.stdin is not None and request.stdin.text == "hello"
        assert result.duration_ms == 10
        assert result.metadata["process_exited"] is True
        assert result.metadata["output_verified"] is True


def test_local_speech_execution_port_runs_packaged_piper_without_shell() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        adapter = PiperTextToSpeechAdapter(
            _manifest(),
            DataDir(Path(temporary) / "data"),
            LocalSpeechExecutionPort(),
        )

        result = adapter.synthesize(AudioOutputRequest(session_id="s1", text="hello from synapse"))

        assert result.provider_id == "piper"
        assert result.voice_id == "synapse-bryce"
        assert result.audio_format == "audio/wav"
        assert result.duration_ms is not None and result.duration_ms > 0
        assert result.metadata["output_verified"] is True


@pytest.mark.parametrize(
    ("executor", "message"),
    [
        (ControlledExecutor(exit_code=2), "exit code 2"),
        (ControlledExecutor(report_artifact=False), "expected output artifact"),
        (ControlledExecutor(output=b"invalid"), "valid WAV"),
        (
            ControlledExecutor(
                SpeechExecutionOutcome.TIMEOUT_OBSERVED,
                None,
                report_artifact=False,
            ),
            "Termination remains unverified",
        ),
        (
            ControlledExecutor(
                SpeechExecutionOutcome.UNAVAILABLE,
                None,
                report_artifact=False,
            ),
            "execution is unavailable",
        ),
    ],
)
def test_piper_rejects_unverified_execution_results(
    executor: ControlledExecutor, message: str
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        adapter = _adapter(Path(temporary), executor)
        with pytest.raises(ValidationError, match=message):
            adapter.synthesize(AudioOutputRequest(session_id="s1", text="hello"))


def test_piper_source_contains_no_process_execution_api() -> None:
    source = (PROJECT_ROOT / "backend/synapse/speech_adapters/piper_tts.py").read_text()
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "Popen" not in source
