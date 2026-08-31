from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


class UnsafeCleanupPath(ValueError):
    """Raised when a cleanup candidate is outside the explicit allowlist."""


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    reason: str


ROOT_CACHE_DIRECTORY_NAMES = {
    ".cache",
    ".hypothesis",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "htmlcov",
}
ROOT_CACHE_FILE_NAMES = {".coverage", "coverage.xml"}
SOURCE_ROOTS = ("apps", "backend", "scripts", "tests")
OPTIONAL_ARTIFACTS = (
    Path("artifacts/linkedin"),
    Path("artifacts/reports/generated"),
    Path("artifacts/temporary"),
)
PROTECTED_TOP_LEVEL = {
    ".git",
    ".venv",
    ".venv-release",
    "apps",
    "backend",
    "data",
    "docs",
    "tests",
}


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def _relative_to_root(root: Path, candidate: Path) -> Path:
    root_resolved = _resolved(root)
    candidate_resolved = _resolved(candidate)
    try:
        return candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafeCleanupPath(f"path is outside repository root: {candidate}") from exc


def _is_allowed_relative(relative: Path, *, include_artifacts: bool) -> bool:
    if not relative.parts:
        return False
    if len(relative.parts) == 1:
        name = relative.name
        return (
            name in ROOT_CACHE_DIRECTORY_NAMES
            or name in ROOT_CACHE_FILE_NAMES
            or name.startswith(".mypy_cache")
        )
    if relative.name == "__pycache__" and relative.parts[0] in SOURCE_ROOTS:
        return True
    return include_artifacts and relative in OPTIONAL_ARTIFACTS


def validate_candidate(root: Path, candidate: Path, *, include_artifacts: bool = False) -> Path:
    relative = _relative_to_root(root, candidate)
    if candidate.is_symlink():
        raise UnsafeCleanupPath(f"refusing symlink: {relative}")
    if relative.parts and relative.parts[0] in PROTECTED_TOP_LEVEL and relative.name != "__pycache__":
        raise UnsafeCleanupPath(f"refusing protected path: {relative}")
    if not _is_allowed_relative(relative, include_artifacts=include_artifacts):
        raise UnsafeCleanupPath(f"path is not allowlisted: {relative}")
    return relative


def _pycache_directories(root: Path) -> list[Path]:
    found: list[Path] = []
    for source_name in SOURCE_ROOTS:
        source = root / source_name
        if not source.is_dir() or source.is_symlink():
            continue
        for current, dirs, _files in os.walk(source, followlinks=False):
            current_path = Path(current)
            dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
            if current_path.name == "__pycache__":
                found.append(current_path)
                dirs[:] = []
    return found


def discover_candidates(root: Path, *, include_artifacts: bool = False) -> list[CleanupCandidate]:
    root = _resolved(root)
    candidates: list[CleanupCandidate] = []
    for child in root.iterdir():
        if child.is_symlink():
            continue
        is_allowlisted_directory = child.is_dir() and (
            child.name in ROOT_CACHE_DIRECTORY_NAMES or child.name.startswith(".mypy_cache")
        )
        is_allowlisted_file = child.is_file() and child.name in ROOT_CACHE_FILE_NAMES
        if is_allowlisted_directory or is_allowlisted_file:
            candidates.append(CleanupCandidate(child, "generated tool cache"))
    candidates.extend(
        CleanupCandidate(path, "Python bytecode cache") for path in _pycache_directories(root)
    )
    if include_artifacts:
        for relative in OPTIONAL_ARTIFACTS:
            path = root / relative
            if path.exists() and not path.is_symlink():
                candidates.append(CleanupCandidate(path, "optional generated artifacts"))
    unique = {candidate.path: candidate for candidate in candidates}
    return sorted(unique.values(), key=lambda item: (len(item.path.parts), str(item.path)))


def clean_workspace(
    root: Path,
    *,
    dry_run: bool,
    include_artifacts: bool = False,
) -> list[CleanupCandidate]:
    root = _resolved(root)
    candidates = discover_candidates(root, include_artifacts=include_artifacts)
    for candidate in candidates:
        relative = validate_candidate(
            root,
            candidate.path,
            include_artifacts=include_artifacts,
        )
        action = "would remove" if dry_run else "removing"
        print(f"{action}: {relative} ({candidate.reason})")
    if dry_run:
        return candidates
    for candidate in sorted(candidates, key=lambda item: len(item.path.parts), reverse=True):
        if candidate.path.is_dir():
            shutil.rmtree(candidate.path)
        elif candidate.path.exists():
            candidate.path.unlink()
    return candidates


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely remove generated Synapse workspace files.")
    parser.add_argument("--dry-run", action="store_true", help="show candidates without removing them")
    parser.add_argument(
        "--include-artifacts",
        action="store_true",
        help="also remove allowlisted generated artifact directories",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        candidates = clean_workspace(
            root,
            dry_run=args.dry_run,
            include_artifacts=args.include_artifacts,
        )
    except (OSError, UnsafeCleanupPath) as exc:
        print(f"cleanup refused: {exc}", file=sys.stderr)
        return 1
    print(f"{'found' if args.dry_run else 'removed'} {len(candidates)} allowlisted paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
