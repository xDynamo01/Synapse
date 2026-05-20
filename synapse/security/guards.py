from __future__ import annotations

import re
import time
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"([A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^'\"\s]+)"),
]


def mask_secret(value: str) -> str:
    if not value:
        return value
    masked = value
    for pattern in SECRET_PATTERNS:
        masked = pattern.sub(lambda m: m.group(0)[:8] + "***", masked)
    return masked


def safe_log(message: str) -> str:
    return mask_secret(message)


def validate_file_path(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return path


class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max(1, max_per_minute)
        self._events: list[float] = []

    def allow(self) -> bool:
        now = time.time()
        self._events = [event for event in self._events if now - event < 60]
        if len(self._events) >= self.max_per_minute:
            return False
        self._events.append(now)
        return True
