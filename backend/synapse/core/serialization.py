from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_structured_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def dump_structured_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)
    except Exception:
        text = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
