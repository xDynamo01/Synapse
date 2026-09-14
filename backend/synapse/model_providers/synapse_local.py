from __future__ import annotations

import atexit
import json
import os
import re
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Condition
from typing import Any, Iterator
from urllib import request

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.serialization import load_structured_file
from synapse.models.adapters import OpenAICompatibleAdapter
from synapse.models.errors import ModelError
from synapse.models.types import ModelRequest, ModelResponse

MODEL_EXTENSIONS = {".gguf", ".ggml", ".bin"}
MAX_LOG_BYTES = 256 * 1024
MAX_LOG_FILES = 5
MAX_LOG_AGE_SECONDS = 24 * 60 * 60
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class _ManagedServer:
    model: str
    model_path: Path
    base_url: str
    process: subprocess.Popen[str]
    log_handle: Any | None = None
    active: bool = False


class SynapseLocalModelAdapter:
    provider = "synapse_local"

    def __init__(self, data_dir: DataDir, event_bus: EventBus | None = None,
                 *, max_loaded_models: int | None = None) -> None:
        self.data_dir = data_dir
        self.event_bus = event_bus
        self._openai = OpenAICompatibleAdapter()
        self._servers: dict[str, _ManagedServer] = {}
        limit = max_loaded_models
        if limit is None:
            try:
                limit = int(os.environ.get("SYNAPSE_LOCAL_MAX_LOADED_MODELS", "1"))
            except ValueError as exc:
                raise ModelError("provider_misconfigured", "Local model limit must be 1 or 2.") from exc
        if isinstance(limit, bool) or limit not in (1, 2):
            raise ModelError("provider_misconfigured", "Local model limit must be 1 or 2.")
        self.max_loaded_models = limit
        self._condition = Condition()
        self._closed = False
        atexit.register(self.shutdown)

    def generate(self, request_payload: ModelRequest) -> ModelResponse:
        if not request_payload.model:
            raise ModelError("model_not_found", "Synapse Local model is not configured.", status_code=404)
        started = time.monotonic()
        with self._lease(request_payload.model, request_payload.timeout_seconds) as server:
            remaining = request_payload.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise ModelError("generation_timeout", "Local model request deadline expired.", status_code=504)
            return self._generate_on_server(replace(request_payload, timeout_seconds=remaining), server)

    def _generate_on_server(self, request_payload: ModelRequest, server: _ManagedServer) -> ModelResponse:
        routed = ModelRequest(
            **{
                **request_payload.__dict__,
                "provider": "openai_compatible",
                "base_url": server.base_url.rstrip("/") + "/v1",
                "metadata": {
                    **request_payload.metadata,
                    "synapse_local_model_path": str(server.model_path),
                    "synapse_local_server": server.base_url,
                },
            }
        )
        result = self._openai.generate(routed)
        return ModelResponse(
            content=result.content,
            provider=self.provider,
            model=request_payload.model,
            metadata={
                **result.metadata,
                "raw_provider": "synapse_local_llama_server",
                "base_url": server.base_url,
                "model_path": str(server.model_path),
            },
            tool_calls=result.tool_calls,
            finish_reason=result.finish_reason,
            usage=result.usage,
            latency_ms=result.latency_ms,
            warnings=result.warnings,
        )

    def list_models(self, request_payload: ModelRequest) -> list[str]:
        del request_payload
        return [path.stem for path in self._model_files()]

    def stream(self, request_payload: ModelRequest):
        raise ModelError(
            "streaming_not_supported",
            "Synapse Local streaming is not implemented in this adapter yet.",
            status_code=422,
        )

    def cancel(self, generation_id: str) -> None:
        del generation_id
        raise ModelError(
            "generation_cancelled",
            "Synapse Local cancellation is handled by the managed llama-server process.",
            status_code=409,
        )

    @contextmanager
    def _lease(self, model: str, timeout_seconds: float) -> Iterator[_ManagedServer]:
        # Canonicalize filename aliases before reserving a resident process.
        model = self._resolve_model_path(model).stem
        deadline = time.monotonic() + timeout_seconds
        if not self._condition.acquire(timeout=max(0.0, timeout_seconds)):
            raise ModelError("generation_timeout", "Timed out waiting for local model loading.", status_code=504)
        try:
            while True:
                if self._closed:
                    raise ModelError("provider_unavailable", "Local runtime has shut down.", status_code=503)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ModelError("generation_timeout", "Timed out waiting for local model capacity.", status_code=504)
                current = self._servers.get(model)
                if current is not None and not current.active:
                    break
                if current is None:
                    if len(self._servers) < self.max_loaded_models:
                        break
                    idle = next((item for item in self._servers.values() if not item.active), None)
                    if idle is not None:
                        self._stop_server(idle)
                        del self._servers[idle.model]
                        break
                self._condition.wait(timeout=remaining)
            try:
                server = self._ensure_server(model, remaining)
            except Exception:
                self._condition.notify_all()
                raise
            server.active = True
        finally:
            self._condition.release()
        try:
            yield server
        finally:
            with self._condition:
                server.active = False
                self._condition.notify_all()

    @staticmethod
    def _stop_server(server: _ManagedServer) -> None:
        if server.process.poll() is None:
            server.process.terminate()
            try:
                server.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.process.kill()
                server.process.wait(timeout=3)
        if server.log_handle is not None:
            server.log_handle.close()

    def shutdown(self) -> None:
        with self._condition:
            self._closed = True
            for name, server in list(self._servers.items()):
                self._stop_server(server)
                del self._servers[name]
            self._condition.notify_all()

    @staticmethod
    def capabilities() -> set[str]:
        return {"text_generation", "structured_output"}

    def explain_status(self, model: str | None = None, limit: int = 80) -> dict[str, Any]:
        model_name = (model or "").strip()
        if not model_name:
            settings_path = self.data_dir.resolve("model-hub/defaults.yaml")
            settings = load_structured_file(settings_path) if settings_path.exists() else {}
            model_name = str(settings.get("default_chat_model") or "").strip()
        log_path = self._log_path(model_name) if model_name else None
        if log_path:
            self._enforce_log_retention(log_path)
        return {
            "config": {
                "provider_id": self.provider,
                "model_name": model_name or None,
                "log_path": str(log_path) if log_path else None,
            },
            "health": self._server_health(model_name),
            "telemetry": {
                "recent": self._recent_log_entries(log_path, model_name, limit) if log_path else [],
            },
        }

    def _ensure_server(self, model: str, timeout_seconds: float) -> _ManagedServer:
        current = self._servers.get(model)
        if current and current.process.poll() is None and self._health(current.base_url):
            return current
        if current:
            self._stop_server(current)
            del self._servers[model]

        model_path = self._resolve_model_path(model)
        executable = self._resolve_llama_server()
        port = self._free_port()
        base_url = f"http://127.0.0.1:{port}"
        log_dir = self.data_dir.resolve("logs/synapse-local-models")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_path(model)
        self._prepare_temporary_log(log_file)
        command = [
            str(executable),
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--parallel",
            "1",
            "--ctx-size",
            "4096",
            "--gpu-layers",
            "auto",
            "--batch-size",
            "512",
            "--ubatch-size",
            "128",
            "--no-webui",
            "--no-ui",
            "--jinja",
            "--reasoning-format",
            "deepseek",
            "--log-file",
            str(log_file),
            "--log-timestamps",
            "--log-prefix",
        ]
        log_handle = log_file.open("a", encoding="utf-8", errors="replace")
        server = None
        try:
            process = subprocess.Popen(
                command,
                cwd=str(executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            server = _ManagedServer(
                model=model,
                model_path=model_path,
                base_url=base_url,
                process=process,
                log_handle=log_handle,
            )
            self._servers[model] = server
            self._wait_until_ready(server, timeout_seconds)
            self._emit(
                "synapse_local.server_started",
                {"model": model, "model_path": str(model_path), "base_url": base_url, "log_file": str(log_file)},
            )
            return server
        except Exception:
            if server is not None:
                self._stop_server(server)
                self._servers.pop(model, None)
            try:
                log_handle.close()
            except OSError:
                pass
            raise

    def _wait_until_ready(self, server: _ManagedServer, timeout_seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, min(timeout_seconds, 120.0))
        last_error = ""
        while time.monotonic() < deadline:
            if server.process.poll() is not None:
                raise ModelError(
                    "provider_unavailable",
                    f"Synapse Local llama-server exited while loading {server.model}.",
                    status_code=503,
                )
            if self._health(server.base_url):
                return
            try:
                with request.urlopen(server.base_url.rstrip("/") + "/v1/models", timeout=1.0) as response:
                    json.loads(response.read().decode("utf-8"))
                    return
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.5)
        raise ModelError(
            "generation_timeout",
            f"Synapse Local llama-server did not become ready for {server.model}: {last_error}",
            status_code=504,
        )

    @staticmethod
    def _health(base_url: str) -> bool:
        try:
            with request.urlopen(base_url.rstrip("/") + "/health", timeout=1.0) as response:
                return 200 <= response.status < 500
        except Exception:
            return False

    def _resolve_model_path(self, model: str) -> Path:
        for path in self._model_files():
            if path.stem == model or path.name == model:
                return path
        raise ModelError("model_not_found", f"Synapse Local model file not found: {model}", status_code=404)

    def _model_files(self) -> list[Path]:
        paths: list[Path] = []
        for root in self._model_roots():
            if not root.is_dir():
                continue
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS
            )
        return paths

    def _model_roots(self) -> list[Path]:
        roots: list[Path] = []
        env_root = os.environ.get("SYNAPSE_MODELS_DIR")
        if env_root:
            roots.append(Path(env_root).expanduser())
        settings_path = self.data_dir.resolve("config/provider_settings.yaml")
        settings = load_structured_file(settings_path) if settings_path.exists() else {}
        providers = settings.get("providers", {}) if isinstance(settings, dict) else {}
        synapse_local = providers.get("synapse_local") if isinstance(providers, dict) else None
        if isinstance(synapse_local, dict):
            endpoint = str(synapse_local.get("endpoint") or "").strip()
            if endpoint:
                roots.append(Path(endpoint).expanduser())
        return self._unique_existing(roots)

    def _resolve_llama_server(self) -> Path:
        configured = os.environ.get("SYNAPSE_LLAMA_SERVER_PATH")
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured).expanduser())
        user_profile = Path(os.environ.get("USERPROFILE") or Path.home())
        discovered = list(
            (user_profile / ".lmstudio" / "extensions" / "backends").glob(
                "llama.cpp-*/*llama-server.exe"
            )
        )
        candidates.extend(sorted(discovered, key=self._backend_score, reverse=True))
        for candidate in candidates:
            if candidate.is_file() and self._executable_starts(candidate):
                return candidate
        raise ModelError(
            "provider_misconfigured",
            "llama-server.exe was not found. Set SYNAPSE_LLAMA_SERVER_PATH or install an LM Studio llama.cpp backend.",
            status_code=503,
        )

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _backend_score(path: Path) -> tuple[int, tuple[int, ...], float]:
        parent = path.parent.name.lower()
        version_parts: list[int] = []
        for token in parent.replace("_", "-").split("-"):
            if token and all(part.isdigit() for part in token.split(".")):
                version_parts = [int(part) for part in token.split(".")]
        backend_bonus = 3 if "vulkan" not in parent and "cuda" not in parent else 2 if "vulkan" in parent else 1
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        return (backend_bonus, tuple(version_parts), modified)

    @staticmethod
    def _executable_starts(path: Path) -> bool:
        try:
            process = subprocess.run(
                [str(path), "--version"],
                cwd=str(path.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return process.returncode == 0

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)[:120]

    def _log_path(self, model: str) -> Path:
        return self.data_dir.resolve("logs/synapse-local-models") / f"{self._safe_name(model)}.log"

    def _prepare_temporary_log(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._prune_log_directory(log_path.parent)
        try:
            log_path.write_text("", encoding="utf-8")
        except OSError:
            pass

    def _enforce_log_retention(self, log_path: Path) -> None:
        self._prune_log_directory(log_path.parent)
        self._trim_log_file(log_path)

    def _prune_log_directory(self, log_dir: Path) -> None:
        try:
            logs = [path for path in log_dir.glob("*.log") if path.is_file()]
        except OSError:
            return
        now = time.time()
        for path in logs:
            try:
                if now - path.stat().st_mtime > MAX_LOG_AGE_SECONDS:
                    path.unlink()
            except OSError:
                pass
        try:
            logs = sorted(
                [path for path in log_dir.glob("*.log") if path.is_file()],
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in logs[MAX_LOG_FILES:]:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _trim_log_file(log_path: Path) -> None:
        try:
            size = log_path.stat().st_size
        except OSError:
            return
        if size <= MAX_LOG_BYTES:
            return
        try:
            with log_path.open("rb") as handle:
                handle.seek(-MAX_LOG_BYTES, os.SEEK_END)
                data = handle.read()
            newline = data.find(b"\n")
            if newline > 0:
                data = data[newline + 1 :]
            log_path.write_bytes(data)
        except OSError:
            pass

    def _server_health(self, model: str) -> dict[str, Any]:
        current = self._servers.get(model) if model else None
        if not current:
            return {"status": "idle", "running": False}
        running = current.process.poll() is None
        return {
            "status": "ready" if running and self._health(current.base_url) else "unavailable",
            "running": running,
            "base_url": current.base_url if running else None,
            "model_path": str(current.model_path),
        }

    @staticmethod
    def _recent_log_entries(log_path: Path, model: str, limit: int) -> list[dict[str, Any]]:
        if not log_path.exists():
            return []
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in lines[-max(1, min(limit, 200)) :]:
            cleaned = ANSI_ESCAPE.sub("", line).strip()
            if not cleaned:
                continue
            entries.append(
                {
                    "provider_id": SynapseLocalModelAdapter.provider,
                    "model_name": model,
                    "status": "debug",
                    "current_operation": cleaned,
                    "raw_line": cleaned,
                }
            )
        return entries

    @staticmethod
    def _unique_existing(roots: list[Path]) -> list[Path]:
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root).lower()
            if key not in seen:
                unique.append(root)
                seen.add(key)
        return unique

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_bus is not None:
            self.event_bus.emit(event_type, self.provider, payload)
