from __future__ import annotations

from datetime import datetime
from pathlib import Path

from synapse.config.models import PROJECT_ROOT
from synapse.security.guards import safe_log


LOG_PATH = PROJECT_ROOT / "logs" / "synapse.log"


def audit(event: str, detail: str = "") -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} | {safe_log(event)} | {safe_log(detail)}\n"
    LOG_PATH.open("a", encoding="utf-8").write(line)
