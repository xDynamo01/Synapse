from __future__ import annotations

import ast
from pathlib import Path

VOICE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "synapse" / "voice"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".")[0])
    return result


def test_sqlite_is_confined_to_voice_adapter() -> None:
    importers = {path.name for path in VOICE_ROOT.glob("*.py") if "sqlite3" in _imports(path)}
    assert importers == {"sqlite_persistence.py"}


def test_voice_persistence_has_no_provider_execution_or_cross_context_runtime_imports() -> None:
    for name in ("persistence_models.py", "persistence_contracts.py", "sqlite_persistence.py"):
        source = (VOICE_ROOT / name).read_text(encoding="utf-8")
        assert "speech_adapters" not in source
        assert "providers.runtime" not in source
        assert "audio.runtime" not in source
        assert "synapse.agents" not in source
        assert "subprocess" not in source


def test_journal_contract_has_no_ambiguous_latest_or_current_api() -> None:
    source = (VOICE_ROOT / "persistence_contracts.py").read_text(encoding="utf-8")
    assert " latest" not in source
    assert " current" not in source
