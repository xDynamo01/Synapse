from __future__ import annotations

import base64
import hashlib
import logging
import os
import shutil
import wave
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

from synapse.audio.models import AudioOutputRequest, TextToSpeechResult
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.package_resources import (
    packaged_resources_root,
    resolve_package_resource_reference,
)
from synapse.core.serialization import load_structured_file
from synapse.speech_adapters.execution import (
    SpeechExecutionOutcome,
    SpeechExecutionPort,
    SpeechExecutionRequest,
    SpeechExecutionResultLedger,
    SpeechExecutionStdin,
)
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest

logger = logging.getLogger(__name__)


class PiperTextToSpeechAdapter:
    def __init__(
        self,
        manifest: SpeechAdapterManifest,
        data_dir: DataDir,
        execution: SpeechExecutionPort | None = None,
    ) -> None:
        self._manifest = manifest
        self._data_dir = data_dir
        self._execution = execution
        self._results = SpeechExecutionResultLedger()

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
        executable = self._resolve_executable()
        model = self._resolve_model(None)
        if executable is None:
            return self._health("unavailable", "Piper executable is not configured or available.")
        if model is None:
            return self._health("unconfigured", "Piper voice model is not configured.")
        if not model.is_file():
            return self._health("unavailable", f"Piper voice model does not exist: {model}")
        if self._execution is None:
            return self._health(
                "degraded",
                "Piper execution boundary is unavailable.",
                {"execution_boundary": "unavailable"},
            )
        return self._health(
            "available",
            "Piper configuration and execution boundary are available.",
            {
                "executable_reference": self._executable_reference(executable),
                "model_reference": f"artifact://piper-model/{model.name}",
                "execution_boundary": "available",
            },
        )

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult:
        text = request.text.strip()
        if not text:
            raise ValidationError("Text is required for speech synthesis.")
        if len(text) > 20_000:
            raise ValidationError("Text exceeds the Piper synthesis limit.")
        if request.speed is not None:
            raise ValidationError("The configured Piper path does not support speed control.")

        executable = self._resolve_executable()
        if executable is None:
            raise ValidationError("Piper executable is unavailable.")
        model = self._resolve_model(request.voice_id)
        if model is None or not model.is_file():
            raise ValidationError("Piper voice model is unavailable.")
        if self._execution is None:
            raise ValidationError("Piper execution boundary is unavailable.")

        output_root = self._data_dir.resolve("voice/synthesis")
        output_root.mkdir(parents=True, exist_ok=True)
        operation_fingerprint = hashlib.sha256(
            f"{request.session_id}\x00{text}".encode("utf-8")
        ).hexdigest()
        output_path = output_root / f"piper-{operation_fingerprint[:24]}.wav"
        if output_path.exists():
            raise ValidationError("Piper output artifact path is already occupied.")
        output_path.touch(exist_ok=False)
        started = perf_counter()
        logger.info(
            "voice_tts_diag:piper_start session_id=%s voice_id=%s output_path=%s",
            request.session_id,
            request.voice_id,
            output_path,
        )
        try:
            stdin = SpeechExecutionStdin(
                reference=f"transient://voice-text/{request.session_id}",
                checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                text=text,
            )
            execution_request = SpeechExecutionRequest.create(
                tool_reference="tool://piper",
                argv=(str(executable), "--model", str(model), "--output_file", str(output_path)),
                stdin=stdin,
                working_directory_reference="workspace://voice/synthesis",
                timeout_seconds=self._timeout_seconds(),
                environment_references=(),
                input_artifact_references=(f"artifact://piper-model/{model.name}",),
                expected_output_artifact_references=(
                    f"artifact://voice-synthesis/{output_path.name}",
                ),
                correlation_reference=f"voice-session://{request.session_id}",
                policy_reference="policy://speech-adapter/piper-local-v1",
                capability_reference="capability://voice/text-to-speech",
            )
            self._results.register_request(execution_request)
            result = self._results.accept_result(self._execution.execute(execution_request))
            if result.outcome is SpeechExecutionOutcome.TIMEOUT_OBSERVED:
                detail = " Termination remains unverified." if not result.termination_proved else ""
                raise ValidationError(f"Piper synthesis timed out.{detail}")
            if result.outcome is SpeechExecutionOutcome.UNAVAILABLE:
                raise ValidationError("Piper execution is unavailable.")
            if result.outcome is SpeechExecutionOutcome.CANCELLATION_OBSERVED:
                raise ValidationError("Piper synthesis cancellation was observed.")
            if result.outcome is SpeechExecutionOutcome.FAILED:
                raise ValidationError("Piper execution failed.")
            if result.exit_code != 0:
                raise ValidationError(f"Piper synthesis failed with exit code {result.exit_code}.")
            expected_ref = f"artifact://voice-synthesis/{output_path.name}"
            if expected_ref not in result.produced_artifact_references:
                raise ValidationError("Piper did not report the expected output artifact.")
            if not output_path.is_file() or output_path.stat().st_size <= 44:
                raise ValidationError("Piper did not produce a valid WAV output.")
            audio_bytes = output_path.read_bytes()
            duration_ms, sample_rate = _wav_metadata(output_path)
            if duration_ms is None:
                raise ValidationError("Piper produced an invalid WAV output.")
            audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
            logger.info(
                "voice_tts_diag:piper_success session_id=%s wav_bytes=%s audio_base64_chars=%s duration_ms=%s sample_rate=%s",
                request.session_id,
                len(audio_bytes),
                len(audio_base64),
                duration_ms,
                sample_rate,
            )
        except Exception:
            logger.exception(
                "voice_tts_diag:piper_error session_id=%s voice_id=%s output_path=%s",
                request.session_id,
                request.voice_id,
                output_path,
            )
            raise
        finally:
            output_path.unlink(missing_ok=True)

        return TextToSpeechResult(
            output_ref=f"inline://tts/{request.session_id}",
            provider_id=self._manifest.provider_id,
            voice_id=self._voice_id_for_model(model) or request.voice_id or model.stem,
            audio_base64=audio_base64,
            audio_format="audio/wav",
            duration_ms=duration_ms,
            latency_ms=int((perf_counter() - started) * 1000),
            sample_rate=sample_rate,
            warnings=[],
            cancelled=False,
            metadata={
                "engine": "piper",
                "model": str(model),
                "sample_rate": sample_rate,
                "language": request.language,
                "warnings": [],
                "cancelled": False,
                "execution_request_id": execution_request.request_id,
                "execution_request_fingerprint": execution_request.fingerprint,
                "execution_result_fingerprint": result.result_fingerprint,
                "process_exited": True,
                "output_verified": True,
            },
        )

    def _settings(self) -> dict[str, object]:
        raw = load_structured_file(self._data_dir.resolve("voice/settings.yaml"))
        return raw.get("piper", {}) if isinstance(raw.get("piper", {}), dict) else {}

    def _resolve_executable(self) -> Path | None:
        configured = os.getenv("SYNAPSE_PIPER_EXECUTABLE") or self._settings().get("executable")
        if configured:
            path = Path(str(configured)).expanduser()
            return path if path.is_file() else None
        packaged = self._packaged_piper_executable()
        if packaged is not None:
            return packaged
        discovered = shutil.which("piper")
        return Path(discovered) if discovered else None

    def _resolve_model(self, voice_id: str | None) -> Path | None:
        settings = self._settings()
        configured = voice_id or os.getenv("SYNAPSE_PIPER_MODEL") or settings.get("model")
        if not configured:
            configured = self._default_voice_pack_model()
            if configured:
                voice_pack_model = self._voice_pack_model(str(configured))
                if voice_pack_model is not None:
                    return voice_pack_model
        else:
            voice_pack_model = self._voice_pack_model(str(configured))
            if voice_pack_model is not None:
                return voice_pack_model
            default_voice = self._default_voice_pack_model()
            if default_voice and str(configured) != default_voice:
                voice_pack_model = self._voice_pack_model(default_voice)
                if voice_pack_model is not None:
                    return voice_pack_model
        if not configured:
            return None
        path = Path(str(configured)).expanduser()
        if not path.is_absolute():
            path = self._data_dir.resolve(f"voice/models/piper/{path}")
        return path

    def _default_voice_pack_model(self) -> str | None:
        for manifest_path in self._voice_pack_manifest_paths():
            raw = load_structured_file(manifest_path)
            for entry in raw.get("voices", []):
                if isinstance(entry, dict) and entry.get("default"):
                    return str(entry.get("voice_id") or entry.get("asset_reference") or "").strip() or None
        return None

    def _voice_pack_model(self, voice_id: str) -> Path | None:
        if not voice_id:
            return None
        for manifest_path in self._voice_pack_manifest_paths():
            raw = load_structured_file(manifest_path)
            for entry in raw.get("voices", []):
                if not isinstance(entry, dict) or str(entry.get("voice_id") or "").strip() != voice_id:
                    continue
                asset_reference = str(entry.get("asset_reference") or "").strip()
                checksum = str(entry.get("checksum") or "").strip().lower()
                if not asset_reference or not checksum:
                    return None
                asset_path = self._resolve_voice_asset_reference(asset_reference, manifest_path.parent)
                if not asset_path.is_file():
                    return None
                observed = hashlib.sha256(asset_path.read_bytes()).hexdigest()
                if observed != checksum:
                    return None
                return asset_path
        return None

    def _voice_id_for_model(self, model_path: Path) -> str | None:
        resolved_model = model_path.resolve()
        for manifest_path in self._voice_pack_manifest_paths():
            raw = load_structured_file(manifest_path)
            for entry in raw.get("voices", []):
                if not isinstance(entry, dict):
                    continue
                asset_reference = str(entry.get("asset_reference") or "").strip()
                if not asset_reference:
                    continue
                asset_path = self._resolve_voice_asset_reference(asset_reference, manifest_path.parent)
                if asset_path.resolve() == resolved_model:
                    return str(entry.get("voice_id") or "").strip() or None
        return None

    def _voice_pack_manifest_paths(self) -> tuple[Path, ...]:
        roots = (
            self._data_dir.resolve("voice/voice-packs"),
            packaged_resources_root() / "voice" / "voice-packs",
        )
        paths: list[Path] = []
        for root in roots:
            if root.exists():
                paths.extend(path for path in sorted(root.glob("*/voice-pack.json"))
                             if load_structured_file(path).get("provider") == "piper")
        return tuple(paths)

    def _resolve_voice_asset_reference(self, reference: str, pack_root: Path) -> Path:
        packaged = resolve_package_resource_reference(reference, "voice")
        if packaged is not None:
            return packaged
        path = Path(reference).expanduser()
        if path.is_absolute():
            return path
        data_candidate = self._data_dir.resolve(reference)
        if data_candidate.exists():
            return data_candidate
        candidate = (pack_root / path).resolve()
        try:
            candidate.relative_to(pack_root.resolve())
            return candidate
        except ValueError:
            return self._data_dir.resolve(reference)

    def _packaged_piper_executable(self) -> Path | None:
        manifest_path = packaged_resources_root() / "voice" / "piper" / "windows-amd64" / "piper-runtime.json"
        if not manifest_path.is_file():
            return None
        raw = load_structured_file(manifest_path)
        reference = str(raw.get("executable_reference") or "").strip()
        checksum = str(raw.get("executable_checksum") or raw.get("checksum_sha256") or "").strip().lower()
        path = resolve_package_resource_reference(reference, "voice") if reference else None
        if path is None or not path.is_file() or not checksum:
            return None
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        return path if observed == checksum else None

    def _executable_reference(self, executable: Path) -> str:
        packaged_root = (packaged_resources_root() / "voice").resolve()
        try:
            relative = executable.resolve().relative_to(packaged_root)
        except ValueError:
            return "tool://piper"
        return f"resource://voice/{relative.as_posix()}"

    def _timeout_seconds(self) -> float:
        value = self._settings().get("timeout_seconds", 60)
        try:
            return max(1.0, min(float(cast(str | float, value)), 300.0))
        except (TypeError, ValueError):
            return 60.0

    def _health(
        self,
        status: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> SpeechAdapterHealth:
        return SpeechAdapterHealth(
            adapter_id=self._manifest.adapter_id,
            provider_id=self._manifest.provider_id,
            status=status,
            checked_at=datetime.now(UTC).isoformat(),
            message=message,
            metadata={"adapter_type": self._manifest.adapter_type, **(metadata or {})},
        )


def _wav_metadata(path: Path) -> tuple[int | None, int | None]:
    try:
        with wave.open(str(path), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            if frame_count <= 0 or sample_rate <= 0:
                return None, sample_rate or None
            return int(round(frame_count / sample_rate * 1000)), sample_rate
    except (OSError, wave.Error):
        return None, None
