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

MODEL_HASH = "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"
VOICES_HASH = "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"


class KokoroTextToSpeechAdapter:
    """Dora only. No network, subprocess authority or heavyweight imports here."""

    def __init__(self, manifest: SpeechAdapterManifest, data_dir: DataDir,
                 execution: SpeechExecutionPort | None = None) -> None:
        self._manifest = manifest
        self._data = data_dir
        self._execution = execution
        self._lock = threading.Lock()
        self._verified: dict[Path, tuple[int, int]] = {}

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def _paths(self) -> tuple[Path, Path, Path, Path]:
        root = self._data.resolve("voice")
        settings = load_structured_file(root / "kokoro-runtime.json")
        configured_root = settings.get("root")
        if isinstance(configured_root, str) and configured_root:
            root = Path(configured_root).resolve()
        python = root / "runtimes/kokoro" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return (python, packaged_resources_root() / "voice/kokoro/runner.py",
                root / "models/kokoro/kokoro-v1.0.int8.onnx",
                root / "models/kokoro/voices-v1.0.bin")

    def _verify(self) -> bool:
        python, runner, model, voices = self._paths()
        if not all(p.is_file() for p in (python, runner, model, voices)):
            return False
        for path, digest in ((model, MODEL_HASH), (voices, VOICES_HASH)):
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if self._verified.get(path) != stamp:
                with path.open("rb") as source:
                    if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                        return False
                self._verified[path] = stamp
        return True

    def health(self) -> SpeechAdapterHealth:
        ready = self._execution is not None and self._verify()
        return SpeechAdapterHealth(
            adapter_id=self._manifest.adapter_id, provider_id="kokoro",
            status="available" if ready else "unavailable",
            checked_at=datetime.now(UTC).isoformat(),
            message="Kokoro local assets verified." if ready else "Kokoro local runtime is missing or invalid.",
            metadata={"adapter_type": "tts", "engine": "kokoro", "voice": "pf_dora"},
        )

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        text = request.text.strip()
        if not text or len(text) > 20000:
            raise ValidationError("Invalid Kokoro speech input length.")
        if request.voice_id not in {None, "pf_dora"}:
            raise ValidationError("Kokoro supports only Dora (pt-BR).")
        if request.language not in {None, "pt", "pt-BR", "pt-br"}:
            raise ValidationError("Kokoro Dora is configured for pt-BR only.")
        if request.speed not in {None, 1.0}:
            raise ValidationError("Kokoro Dora uses the original voice speed.")
        if not self._lock.acquire(blocking=False):
            raise ValidationError("Kokoro is already synthesizing speech.")
        output: Path | None = None
        try:
            if self._execution is None or not self._verify():
                raise ValidationError("Kokoro local runtime is unavailable.")
            python, runner, model, voices = self._paths()
            root = self._data.resolve("voice/synthesis")
            root.mkdir(parents=True, exist_ok=True)
            output = root / f"kokoro-{uuid.uuid4().hex}.wav"
            output.touch(exist_ok=False)
            started = perf_counter()
            output_ref = f"artifact://voice-synthesis/{output.name}"
            execution_request = SpeechExecutionRequest.create(
                tool_reference="tool://kokoro",
                argv=(str(python), "-I", str(runner), "--model", str(model), "--voices",
                      str(voices), "--output_file", str(output)),
                stdin=SpeechExecutionStdin(reference=f"transient://voice-text/{request.session_id}",
                                         checksum=hashlib.sha256(text.encode()).hexdigest(), text=text),
                working_directory_reference="workspace://voice/synthesis",
                timeout_seconds=90.0, environment_references=(),
                input_artifact_references=("artifact://kokoro-model/v1.0-int8",),
                expected_output_artifact_references=(output_ref,),
                correlation_reference=f"voice-session://{request.session_id}",
                policy_reference="policy://speech-adapter/kokoro-local-v1",
                capability_reference="capability://voice/text-to-speech",
            )
            ledger = SpeechExecutionResultLedger()
            ledger.register_request(execution_request)
            result = ledger.accept_result(self._execution.execute(execution_request))
            if result.outcome is not SpeechExecutionOutcome.EXITED or result.exit_code != 0:
                raise ValidationError(f"Kokoro synthesis did not complete: {result.outcome.value}.")
            if output_ref not in result.produced_artifact_references:
                raise ValidationError("Kokoro did not report speech output.")
            with wave.open(str(output), "rb") as wav:
                frames, rate = wav.getnframes(), wav.getframerate()
                if frames <= 0 or rate != 24000 or wav.getnchannels() != 1:
                    raise ValidationError("Kokoro produced invalid speech output.")
            return TextToSpeechResult(
                output_ref=f"inline://tts/{request.session_id}", provider_id="kokoro",
                voice_id="pf_dora", audio_base64=base64.b64encode(output.read_bytes()).decode("ascii"),
                audio_format="audio/wav", duration_ms=round(frames / rate * 1000),
                sample_rate=rate, latency_ms=round((perf_counter() - started) * 1000),
                metadata={"engine": "kokoro", "output_verified": True, "process_exited": True},
            )
        finally:
            if output is not None:
                output.unlink(missing_ok=True)
            self._lock.release()
