from __future__ import annotations

import base64
import ctypes
import os
import tempfile
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib import request

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import load_structured_file


@dataclass(frozen=True)
class ProviderSetting:
    provider_id: str
    display_name: str
    provider_kind: str
    enabled: bool
    endpoint: str
    default_model: str | None = None
    has_api_key: bool = False
    masked_key: str | None = None
    status: str = "unconfigured"
    updated_at: str | None = None
    last_tested_at: str | None = None
    test_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderConnectionTest:
    provider_id: str
    success: bool
    status: str
    message: str
    checked_at: str
    latency_ms: int


PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "lmstudio": {
        "name": "LM Studio",
        "kind": "local",
        "endpoint": "http://127.0.0.1:1234/v1",
        "key": False,
        "storage_id": "lmstudio_local",
        "aliases": ("lmstudio_local",),
    },
    "synapse_local": {
        "name": "Synapse Local Models",
        "kind": "local-filesystem",
        "endpoint": "F:/SynapseRuntime/models",
        "key": False,
    },
    "ollama_local": {
        "name": "Ollama",
        "kind": "local",
        "endpoint": "http://127.0.0.1:11434",
        "key": False,
    },
    "openai": {
        "name": "OpenAI",
        "kind": "cloud",
        "endpoint": "https://api.openai.com/v1",
        "key": True,
    },
    "anthropic": {
        "name": "Anthropic",
        "kind": "cloud",
        "endpoint": "https://api.anthropic.com/v1",
        "key": True,
    },
    "google_gemini": {
        "name": "Google Gemini",
        "kind": "cloud",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta",
        "key": True,
    },
    "groq": {
        "name": "Groq",
        "kind": "cloud",
        "endpoint": "https://api.groq.com/openai/v1",
        "key": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "kind": "cloud",
        "endpoint": "https://openrouter.ai/api/v1",
        "key": True,
    },
    "openai_compatible": {
        "name": "OpenAI Compatible",
        "kind": "external",
        "endpoint": "",
        "key": False,
    },
}


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class ProtectedCredentialStore:
    """Small Windows-alpha credential store backed by the current user's DPAPI key."""

    def __init__(self, path: Path):
        self.path = path

    def get(self, provider_id: str) -> str | None:
        token = load_structured_file(self.path).get("credentials", {}).get(provider_id)
        return self._unprotect(token) if isinstance(token, str) else None

    def set(self, provider_id: str, value: str) -> None:
        raw = load_structured_file(self.path)
        credentials = dict(raw.get("credentials", {}))
        credentials[provider_id] = self._protect(value)
        _atomic_dump(self.path, {"credentials": credentials})

    def clear(self, provider_id: str) -> None:
        raw = load_structured_file(self.path)
        credentials = dict(raw.get("credentials", {}))
        credentials.pop(provider_id, None)
        _atomic_dump(self.path, {"credentials": credentials})

    @staticmethod
    def _protect(value: str) -> str:
        if os.name != "nt":
            raise ValidationError(
                "Secure provider key storage requires Windows DPAPI in this alpha."
            )
        data = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(data)
        source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        output = _DataBlob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
        ):
            raise ValidationError("Windows DPAPI could not protect the provider key.")
        try:
            encrypted = ctypes.string_at(output.pbData, output.cbData)
            return base64.b64encode(encrypted).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)

    @staticmethod
    def _unprotect(token: str) -> str:
        if os.name != "nt":
            raise ValidationError(
                "Secure provider key storage requires Windows DPAPI in this alpha."
            )
        encrypted = base64.b64decode(token)
        buffer = ctypes.create_string_buffer(encrypted)
        source = _DataBlob(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        output = _DataBlob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
        ):
            raise ValidationError("Windows DPAPI could not read the provider key.")
        try:
            return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)


class ProviderSettingsRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        credential_store: Any | None = None,
        http_get: Callable[[str, dict[str, str], float], None] | None = None,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.path = data_dir.resolve("config/provider_settings.yaml")
        self.credentials = credential_store or ProtectedCredentialStore(
            data_dir.resolve("providers/credentials.yaml")
        )
        self.http_get = http_get or self._http_get
        self.model_hub: Any | None = None
        if not self.path.exists():
            self._write(
                {
                    self._storage_provider_id(provider_id): self._default_record(provider_id)
                    for provider_id in PROVIDER_DEFAULTS
                }
            )

    def list_settings(self) -> list[ProviderSetting]:
        return [self.get_setting(provider_id) for provider_id in PROVIDER_DEFAULTS]

    def get_setting(self, provider_id: str) -> ProviderSetting:
        canonical_id = self._canonical_provider_id(provider_id)
        definition = self._definition(canonical_id)
        storage_id = self._storage_provider_id(canonical_id)
        records = self._records()
        record = records.get(storage_id, records.get(canonical_id, self._default_record(canonical_id)))
        key = self.credentials.get(storage_id)
        return ProviderSetting(
            provider_id=canonical_id,
            display_name=definition["name"],
            provider_kind=definition["kind"],
            enabled=bool(record.get("enabled", False)),
            endpoint=str(record.get("endpoint", definition["endpoint"])),
            default_model=record.get("default_model"),
            has_api_key=bool(key),
            masked_key=_mask_key(key),
            status=str(record.get("status", "unconfigured")),
            updated_at=record.get("updated_at"),
            last_tested_at=record.get("last_tested_at"),
            test_message=record.get("test_message"),
            metadata={
                "requires_api_key": definition["key"],
                "storage_id": storage_id,
                "aliases": list(definition.get("aliases", ())),
            },
        )

    def update_setting(
        self,
        provider_id: str,
        *,
        enabled: bool | None = None,
        endpoint: str | None = None,
        default_model: str | None = None,
        api_key: str | None = None,
    ) -> ProviderSetting:
        canonical_id = self._canonical_provider_id(provider_id)
        definition = self._definition(canonical_id)
        storage_id = self._storage_provider_id(canonical_id)
        records = self._records()
        record = dict(records.get(storage_id, self._default_record(canonical_id)))
        if enabled is not None:
            record["enabled"] = enabled
        if endpoint is not None:
            endpoint = endpoint.strip()
            if (
                endpoint
                and definition["kind"] != "local-filesystem"
                and not endpoint.startswith(("http://", "https://"))
            ):
                raise ValidationError("Provider endpoint must use http:// or https://.")
            record["endpoint"] = endpoint
        if default_model is not None:
            record["default_model"] = default_model.strip() or None
        if api_key is not None:
            value = api_key.strip()
            if value:
                self.credentials.set(provider_id, value)
                self.credentials.set(storage_id, value)
        record["updated_at"] = _now()
        record["status"] = self._configuration_status(
            record, definition, bool(self.credentials.get(storage_id))
        )
        records[storage_id] = record
        self._write(records)
        self._sync_lmstudio(canonical_id, record)
        self._refresh_model_hub()
        self.event_bus.emit(
            "provider.settings.updated",
            canonical_id,
            {
                "enabled": record["enabled"],
                "endpoint": record["endpoint"],
                "default_model": record.get("default_model"),
                "has_api_key": bool(self.credentials.get(storage_id)),
            },
        )
        return self.get_setting(canonical_id)

    def clear_key(self, provider_id: str) -> ProviderSetting:
        canonical_id = self._canonical_provider_id(provider_id)
        self._definition(canonical_id)
        storage_id = self._storage_provider_id(canonical_id)
        self.credentials.clear(provider_id)
        self.credentials.clear(storage_id)
        records = self._records()
        record = dict(records.get(storage_id, self._default_record(canonical_id)))
        record["updated_at"] = _now()
        record["status"] = self._configuration_status(record, PROVIDER_DEFAULTS[canonical_id], False)
        records[storage_id] = record
        self._write(records)
        self._refresh_model_hub()
        self.event_bus.emit("provider.settings.key_cleared", canonical_id, {"has_api_key": False})
        return self.get_setting(canonical_id)

    def test_connection(self, provider_id: str) -> ProviderConnectionTest:
        setting = self.get_setting(provider_id)
        if not setting.enabled:
            return self._save_test(provider_id, False, "disabled", "Provider is disabled.", 0)
        definition = self._definition(provider_id)
        key = self.credentials.get(provider_id)
        if definition["key"] and not key:
            return self._save_test(provider_id, False, "unconfigured", "API key is required.", 0)
        if not setting.endpoint:
            return self._save_test(provider_id, False, "unconfigured", "Endpoint is required.", 0)
        headers = {"Accept": "application/json"}
        if key:
            if provider_id == "anthropic":
                headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
            elif provider_id == "google_gemini":
                headers["x-goog-api-key"] = key
            else:
                headers["Authorization"] = f"Bearer {key}"
        url = setting.endpoint.rstrip("/") + (
            "/api/tags" if provider_id == "ollama_local" else "/models"
        )
        started = time.perf_counter()
        try:
            self.http_get(url, headers, 5.0)
            latency = int((time.perf_counter() - started) * 1000)
            return self._save_test(provider_id, True, "available", "Connection succeeded.", latency)
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            return self._save_test(
                provider_id, False, "unavailable", f"Connection failed: {exc}", latency
            )

    def configured_external_count(self) -> int:
        return sum(
            1
            for item in self.list_settings()
            if item.provider_kind != "local" and item.enabled and item.status == "configured"
        )

    def _save_test(
        self, provider_id: str, success: bool, status: str, message: str, latency: int
    ) -> ProviderConnectionTest:
        checked_at = _now()
        records = self._records()
        record = dict(records.get(provider_id, self._default_record(provider_id)))
        record.update({"status": status, "last_tested_at": checked_at, "test_message": message})
        records[provider_id] = record
        self._write(records)
        self._refresh_model_hub()
        result = ProviderConnectionTest(provider_id, success, status, message, checked_at, latency)
        self.event_bus.emit("provider.settings.tested", provider_id, asdict(result))
        return result

    def _records(self) -> dict[str, dict[str, Any]]:
        raw = load_structured_file(self.path)
        return dict(raw.get("providers", {}))

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        _atomic_dump(self.path, {"providers": records, "schema_version": 1})

    def _default_record(self, provider_id: str) -> dict[str, Any]:
        definition = self._definition(provider_id)
        return {
            "enabled": False,
            "endpoint": definition["endpoint"],
            "default_model": None,
            "status": "unconfigured",
            "updated_at": None,
            "last_tested_at": None,
            "test_message": None,
        }

    @staticmethod
    def _configuration_status(
        record: dict[str, Any], definition: dict[str, Any], has_key: bool
    ) -> str:
        if not record.get("enabled"):
            return "disabled"
        if not record.get("endpoint") or (definition["key"] and not has_key):
            return "unconfigured"
        return "configured"

    @staticmethod
    def _definition(provider_id: str) -> dict[str, Any]:
        provider_id = ProviderSettingsRuntime._canonical_provider_id(provider_id)
        try:
            return PROVIDER_DEFAULTS[provider_id]
        except KeyError as exc:
            raise NotFound(f"Provider setting not found: {provider_id}") from exc

    @staticmethod
    def _canonical_provider_id(provider_id: str) -> str:
        for canonical_id, definition in PROVIDER_DEFAULTS.items():
            if provider_id == canonical_id or provider_id in definition.get("aliases", ()):
                return canonical_id
        return provider_id

    @staticmethod
    def _storage_provider_id(provider_id: str) -> str:
        definition = ProviderSettingsRuntime._definition(provider_id)
        storage_id = definition.get("storage_id", provider_id)
        return str(storage_id)

    def _sync_lmstudio(self, provider_id: str, record: dict[str, Any]) -> None:
        if provider_id == "lmstudio":
            path = self.data_dir.resolve("config/lmstudio_provider.yaml")
            raw = load_structured_file(path) if path.exists() else {}
            current = dict(raw.get("lmstudio", raw))
            _atomic_dump(
                path,
                {
                    "lmstudio": {
                        "enabled": bool(record["enabled"]),
                        "base_url": record["endpoint"],
                        "default_model": record.get("default_model"),
                        "timeout_seconds": int(current.get("timeout_seconds", 30)),
                        "max_context_chars": int(current.get("max_context_chars", 18_000)),
                    }
                },
            )

    def _refresh_model_hub(self) -> None:
        if self.model_hub is not None:
            self.model_hub.refresh()

    @staticmethod
    def _http_get(url: str, headers: dict[str, str], timeout: float) -> None:
        with request.urlopen(request.Request(url, headers=headers), timeout=timeout) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")


def _mask_key(value: str | None) -> str | None:
    if not value:
        return None
    suffix = value[-4:] if len(value) >= 4 else value[-1:]
    return f"{'*' * 8}{suffix}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_dump(path: Path, payload: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=True, allow_unicode=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
