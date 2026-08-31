from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "audio",
    "audio_base64",
    "prompt",
    "transcript",
    "file_content",
}
SECRET_PATTERN = re.compile(r"(?i)(bearer\s+[a-z0-9._-]+|sk-[a-z0-9_-]{8,})")
WINDOWS_ABSOLUTE = re.compile(r"^[a-zA-Z]:[\\/]")


def redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, bytes):
        return {"redacted": True, "size_bytes": len(value)}
    if isinstance(value, str):
        if WINDOWS_ABSOLUTE.match(value) or Path(value).is_absolute():
            return "[REDACTED_PATH]"
        return SECRET_PATTERN.sub("[REDACTED]", value)
    return value


def redaction_self_test(secret: str) -> dict[str, Any]:
    sample = {"api_key": secret, "nested": {"token": secret}, "safe": "visible"}
    result = redact(sample)
    serialized = repr(result)
    return {"safe": secret not in serialized, "sample": result}
