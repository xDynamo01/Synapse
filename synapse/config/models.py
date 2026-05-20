from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = DATA_DIR / "synapse_config.json"
DB_PATH = DATA_DIR / "synapse.db"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class ProviderConfig:
    name: str
    type: str = "openai_compatible"
    base_url: str = "http://localhost:11434/v1"
    model: str = "gemma4:e4b"
    api_key_env: str = ""
    api_key: str = ""
    timeout_seconds: int = 120
    enabled: bool = True

    def resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return _env(self.api_key_env)
        return ""


@dataclass
class AppConfig:
    active_provider: str = "ollama"
    active_model: str = "gemma4:e4b"
    fallback_providers: list[str] = field(default_factory=lambda: ["lmstudio"])
    max_history_turns: int = 12
    max_tokens_response: int = 2048
    summary_every_n_turns: int = 8
    max_file_bytes: int = 2_000_000
    max_file_chars: int = 24_000
    rate_limit_per_minute: int = 20
    providers: dict[str, ProviderConfig] = field(default_factory=dict)

    def provider(self, name: str | None = None) -> ProviderConfig:
        provider_name = name or self.active_provider
        if provider_name not in self.providers:
            raise KeyError(f"Provider not configured: {provider_name}")
        cfg = self.providers[provider_name]
        if not cfg.model:
            cfg.model = self.active_model
        return cfg


def default_config() -> AppConfig:
    return AppConfig(
        providers={
            "ollama": ProviderConfig(
                name="ollama",
                type="ollama",
                base_url=_env("SYNAPSE_OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                model=_env("SYNAPSE_OLLAMA_MODEL", "gemma4:e4b"),
            ),
            "lmstudio": ProviderConfig(
                name="lmstudio",
                type="openai_compatible",
                base_url=_env("SYNAPSE_LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
                model=_env("SYNAPSE_LMSTUDIO_MODEL", "local-model"),
            ),
            "openai": ProviderConfig(
                name="openai",
                type="openai_compatible",
                base_url="https://api.openai.com/v1",
                model=_env("OPENAI_MODEL", "gpt-4.1-mini"),
                api_key_env="OPENAI_API_KEY",
                enabled=False,
            ),
            "anthropic": ProviderConfig(
                name="anthropic",
                type="anthropic",
                base_url="https://api.anthropic.com/v1",
                model=_env("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                api_key_env="ANTHROPIC_API_KEY",
                enabled=False,
            ),
            "groq": ProviderConfig(
                name="groq",
                type="openai_compatible",
                base_url="https://api.groq.com/openai/v1",
                model=_env("GROQ_MODEL", "llama-3.1-8b-instant"),
                api_key_env="GROQ_API_KEY",
                enabled=False,
            ),
            "gemini": ProviderConfig(
                name="gemini",
                type="openai_compatible",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model=_env("GEMINI_MODEL", "gemini-1.5-flash"),
                api_key_env="GEMINI_API_KEY",
                enabled=False,
            ),
        }
    )


def _config_to_dict(config: AppConfig) -> dict[str, Any]:
    data = asdict(config)
    data["providers"] = {name: asdict(provider) for name, provider in config.providers.items()}
    for provider in data["providers"].values():
        provider["api_key"] = ""
    return data


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = default_config()
    if not path.exists():
        save_config(config, path)
        return config
    raw = json.loads(path.read_text(encoding="utf-8"))
    providers = config.providers
    for name, pdata in raw.get("providers", {}).items():
        merged = asdict(providers.get(name, ProviderConfig(name=name)))
        merged.update(pdata)
        providers[name] = ProviderConfig(**merged)
    raw.pop("providers", None)
    base = asdict(config)
    base.update(raw)
    base["providers"] = providers
    return AppConfig(**base)


def save_config(config: AppConfig, path: Path = CONFIG_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_config_to_dict(config), indent=2, ensure_ascii=False), encoding="utf-8")
