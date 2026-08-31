from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def pytest(*paths: str) -> None:
    run([sys.executable, "-m", "pytest", "-q", *paths])


def mypy(path: str, cache_name: str) -> None:
    run(
        [
            sys.executable,
            "-m",
            "mypy",
            path,
            "--cache-dir",
            str(CACHE / "mypy" / cache_name),
        ]
    )


def ruff() -> None:
    run([sys.executable, "-m", "ruff", "check", "backend", "tests", "scripts"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run explicit Synapse quality gates.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--skills", action="store_true")
    group.add_argument("--architecture", action="store_true")
    group.add_argument("--global", dest="global_suite", action="store_true")
    group.add_argument("--mypy-only", action="store_true")
    group.add_argument("--ruff-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.skills:
            skill_tests = sorted(str(path) for path in (ROOT / "tests").glob("test_skills*.py"))
            pytest(*skill_tests)
            mypy("backend/synapse/skills", "skills")
        elif args.architecture:
            pytest("tests/architecture")
        elif args.global_suite:
            pytest()
            mypy("backend/synapse", "global")
            ruff()
        elif args.mypy_only:
            mypy("backend/synapse/skills", "skills")
            mypy("backend/synapse", "global")
        elif args.ruff_only:
            ruff()
        else:
            pytest("tests/test_clean_workspace.py")
            ruff()
        return 0
    except subprocess.CalledProcessError as exc:
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
