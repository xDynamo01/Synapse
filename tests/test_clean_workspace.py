from __future__ import annotations

from pathlib import Path, PureWindowsPath

import pytest
from scripts.clean_workspace import (
    UnsafeCleanupPath,
    clean_workspace,
    discover_candidates,
    validate_candidate,
)


def test_dry_run_preserves_allowed_cache(tmp_path: Path) -> None:
    cache = tmp_path / ".mypy_cache_slice"
    cache.mkdir()
    (cache / "cache.db").write_text("generated", encoding="utf-8")

    candidates = clean_workspace(tmp_path, dry_run=True)

    assert [candidate.path for candidate in candidates] == [cache]
    assert cache.exists()


def test_allowed_cache_is_removed(tmp_path: Path) -> None:
    cache = tmp_path / ".cache"
    cache.mkdir()
    coverage = tmp_path / ".coverage"
    coverage.write_text("generated", encoding="utf-8")

    clean_workspace(tmp_path, dry_run=False)

    assert not cache.exists()
    assert not coverage.exists()


def test_path_outside_root_is_refused(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-cache"
    with pytest.raises(UnsafeCleanupPath, match="outside"):
        validate_candidate(tmp_path, outside)


def test_symlink_is_never_followed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    link = tmp_path / ".cache"
    link.mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link or original(self))

    assert discover_candidates(tmp_path) == []
    assert link.exists()


def test_protected_source_directory_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "backend"
    source.mkdir()
    with pytest.raises(UnsafeCleanupPath, match="protected"):
        validate_candidate(tmp_path, source)


def test_unknown_directory_is_ignored(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown"
    unknown.mkdir()

    assert discover_candidates(tmp_path) == []


def test_artifacts_require_explicit_option(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "temporary"
    artifact.mkdir(parents=True)

    assert discover_candidates(tmp_path) == []
    candidates = discover_candidates(tmp_path, include_artifacts=True)

    assert [candidate.path for candidate in candidates] == [artifact]


def test_repeated_execution_is_idempotent(tmp_path: Path) -> None:
    cache = tmp_path / ".pytest_cache"
    cache.mkdir()

    assert len(clean_workspace(tmp_path, dry_run=False)) == 1
    assert clean_workspace(tmp_path, dry_run=False) == []


def test_windows_path_shape_is_not_treated_as_relative_escape() -> None:
    path = PureWindowsPath(r"C:\workspace\.cache\mypy")
    assert path.parts[:2] == ("C:\\", "workspace")


def test_source_files_are_never_discovered(tmp_path: Path) -> None:
    source = tmp_path / "backend" / "synapse"
    source.mkdir(parents=True)
    module = source / "runtime.py"
    module.write_text("value = 1\n", encoding="utf-8")

    clean_workspace(tmp_path, dry_run=False)

    assert module.read_text(encoding="utf-8") == "value = 1\n"
