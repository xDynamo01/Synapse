from __future__ import annotations

import base64
import hashlib
import os
import threading
import uuid
import wave
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from synapse.audio.models import AudioOutputRequest, TextToSpeechResult
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.package_resources import packaged_resources_root
from synapse.core.serialization import load_structured_file
from synapse.speech_adapters.execution import (
    SpeechExecutionOutcome,
    SpeechExecutionPort,
    SpeechExecutionRequest,
    SpeechExecutionResultLedger,
    SpeechExecutionStdin,
)
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest


class ChatTTSTextToSpeechAdapter:
    """Optional ChatTTS bridge; model assets and runtime remain user-provided."""

    def __init__(
        self,
        manifest: SpeechAdapterManifest,
        data_dir: DataDir,
        execution: SpeechExecutionPort | None = None,
    ) -> None:
        self._manifest = manifest
        self._data = data_dir
        self._execution = execution
        self._lock = threading.Lock()

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def capabilities(self) -> dict[str, object]:
        return {
            "streaming": False,
            "cancellation": False,
            "speed": False,
            "pitch": False,
            "output_formats": ["audio/wav"],
        }

    def health(self) -> SpeechAdapterHealth:
        python, runner, model_root, configured = self._paths()
        if not configured:
            return self._health(
                "unconfigured",
                "ChatTTS is optional and requires a local runtime and model path.",
                {"engine": "chattts", "model_license": "CC BY-NC 4.0"},
            )
        if not python.is_file() or not runner.is_file() or not model_root.is_dir():
            return self._health(
                "unavailable",
                "ChatTTS runtime, runner or model assets are missing.",
                {"engine": "chattts", "model_path": str(model_root)},
            )
        if self._execution is None:
            return self._health(
                "degraded",
                "ChatTTS is configured but the speech execution boundary is unavailable.",
                {"engine": "chattts"},
            )
        return self._health(
            "available",
            "ChatTTS assets and execution boundary are configured; the package is loaded at synthesis time.",
            {
                "engine": "chattts",
                "model_path": str(model_root),
                "model_license": "CC BY-NC 4.0",
                "supported_languages": ["en-US", "zh-CN"],
            },
        )

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        text = request.text.strip()
        if not text or len(text) > 20_000:
            raise ValidationError("Invalid ChatTTS speech input length.")
        language = (request.language or "en-US").replace("_", "-").lower()
        if language not in {"en-us", "en", "zh-cn", "zh"}:
            raise ValidationError("ChatTTS currently supports English and Chinese only.")
        if request.speed not in {None, 1.0}:
            raise ValidationError("ChatTTS uses the model's original speech speed.")
        if not self._lock.acquire(blocking=False):
            raise ValidationError("ChatTTS is already synthesizing speech.")
        output: Path | None = None
        try:
            python, runner, model_root, configured = self._paths()
            if not configured or not python.is_file() or not runner.is_file() or not model_root.is_dir():
                raise ValidationError("ChatTTS local runtime or model is unavailable.")
            if self._execution is None:
                raise ValidationError("ChatTTS speech execution boundary is unavailable.")
            output_root = self._data.resolve("voice/synthesis")
            output_root.mkdir(parents=True, exist_ok=True)
            output = output_root / f"chattts-{uuid.uuid4().hex}.wav"
            output.touch(exist_ok=False)
            started = perf_counter()
            output_ref = f"artifact://voice-synthesis/{output.name}"
            execution_request = SpeechExecutionRequest.create(
                tool_reference="tool://chattts",
                argv=(
                    str(python), "-I", str(runner),
                    "--model_path", str(model_root),
                    "--device", str(self._settings().get("device", "cpu")),
                    "--output_file", str(output),
                    "--language", "zh" if language.startswith("zh") else "en",
                ),
                stdin=SpeechExecutionStdin(
                    reference=f"transient://voice-text/{request.session_id}",
                    checksum=hashlib.sha256(text.encode()).hexdigest(),
                    text=text,
                ),
                working_directory_reference="workspace://voice/synthesis",
                timeout_seconds=180.0,
                environment_references=(),
                input_artifact_references=("artifact://chattts-model/local",),
                expected_output_artifact_references=(output_ref,),
                correlation_reference=f"voice-session://{request.session_id}",
                policy_reference="policy://speech-adapter/chattts-optional-v1",
                capability_reference="capability://voice/text-to-speech",
            )
            ledger = SpeechExecutionResultLedger()
            ledger.register_request(execution_request)
            result = ledger.accept_result(self._execution.execute(execution_request))
            if result.outcome is not SpeechExecutionOutcome.EXITED or result.exit_code != 0:
                raise ValidationError(f"ChatTTS synthesis did not complete: {result.outcome.value}.")
            if output_ref not in result.produced_artifact_references:
                raise ValidationError("ChatTTS did not report speech output.")
            with wave.open(str(output), "rb") as wav:
                frames, rate = wav.getnframes(), wav.getframerate()
                if frames <= 0 or rate != 24_000 or wav.getnchannels() != 1:
                    raise ValidationError("ChatTTS produced invalid speech output.")
            audio = output.read_bytes()
            return TextToSpeechResult(
                output_ref=f"inline://tts/{request.session_id}",
                provider_id="chattts",
                voice_id=request.voice_id or "random",
                audio_base64=base64.b64encode(audio).decode("ascii"),
                audio_format="audio/wav",
                duration_ms=round(frames / rate * 1000),
                latency_ms=round((perf_counter() - started) * 1000),
                sample_rate=rate,
                metadata={
                    "engine": "chattts",
                    "output_verified": True,
                    "process_exited": True,
                    "model_license": "CC BY-NC 4.0",
                },
            )
        finally:
            if output is not None:
                output.unlink(missing_ok=True)
            self._lock.release()

    def _settings(self) -> dict[str, object]:
        raw = load_structured_file(self._data.resolve("voice/chattts-runtime.json"))
        return raw if isinstance(raw, dict) else {}

    def _paths(self) -> tuple[Path, Path, Path, bool]:
        settings = self._settings()
        root = Path(str(settings.get("root") or self._data.resolve("voice/chattts"))).resolve()
        python_value = settings.get("python") or os.getenv("SYNAPSE_CHAT_TTS_PYTHON")
        python = Path(str(python_value)).expanduser() if python_value else root / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        model_value = settings.get("model_path") or os.getenv("SYNAPSE_CHAT_TTS_MODEL")
        model_root = Path(str(model_value)).expanduser() if model_value else root / "models"
        runner = packaged_resources_root() / "voice/chattts/runner.py"
        configured = bool(settings or python_value or model_value)
        return python.resolve(), runner, model_root.resolve(), configured

    def _health(self, status: str, message: str, metadata: dict[str, object]) -> SpeechAdapterHealth:
        return SpeechAdapterHealth(
            adapter_id=self._manifest.adapter_id,
            provider_id=self._manifest.provider_id,
            status=status,
            checked_at=datetime.now(UTC).isoformat(),
            message=message,
            metadata={"adapter_type": self._manifest.adapter_type, **metadata},
        )
