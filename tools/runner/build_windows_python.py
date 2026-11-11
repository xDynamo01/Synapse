"""Build the dedicated Windows Python runtime used by native check validation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


CPYTHON = ("v3.14.3", "323c59a5e348347be2ce2b7ea55fcb30bf68b2d3")
DEPENDENCIES = {
    "zlib-ng-2.2.4": "a502e047655c31db29601def76ad6539acacf43d",
    "sqlite-3.50.4.0": "ef547e549b49a2822214ef7880c0ca212b32929e",
}
PROJECTS = ("_freeze_module", "python", "_sqlite3")
RESOURCE_FILES = ("python_exe.rc", "python_nt.rc", "sqlite3.rc")
MANIFEST_LINE = re.compile(rb'(?m)^[12] RT_MANIFEST "python\.manifest"\r?\n')
LIB_IGNORES = shutil.ignore_patterns(
    "test", "tests", "__pycache__", "site-packages", "*.pth", "*.pyc",
    "*.pyo", "sitecustomize.py", "usercustomize.py",
)


def clone(repo: str, tag: str, expected_commit: str, destination: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", tag, repo, str(destination)],
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=destination, text=True,
    ).strip()
    if commit != expected_commit:
        raise ValueError(f"{tag} points to {commit}, expected {expected_commit}")


def build(msbuild: Path, work: Path) -> None:
    work.mkdir(parents=True)
    source = work / "source"
    clone("https://github.com/python/cpython.git", *CPYTHON, source)
    externals = source / "externals"
    externals.mkdir()
    for tag, commit in DEPENDENCIES.items():
        clone("https://github.com/python/cpython-source-deps.git", tag, commit, externals / tag)

    # Windows LPAC denied the side-by-side activation on this offline runtime.
    # Exclude those resources at build time, before producing or hashing binaries.
    for name in RESOURCE_FILES:
        path = source / "PC" / name
        revised, matches = MANIFEST_LINE.subn(b"", path.read_bytes())
        if matches != 1:
            raise ValueError(f"Unexpected manifest declaration in {name}")
        path.write_bytes(revised)

    properties = {
        "Configuration": "Release",
        "Platform": "x64",
        "IncludeExternals": "true",
        "GenerateManifest": "false",
        "EmbedManifest": "false",
        "KillPython": "false",
        "UseMultiToolTask": "false",
        "CL_MPCount": "1",
    }
    for name in PROJECTS:
        project = source / "PCbuild" / f"{name}.vcxproj"
        log = work / f"{name}.log"
        with log.open("wb") as output:
            subprocess.run(
                [str(msbuild), str(project), "/m:1", "/nr:false", "/v:normal",
                 *(f"/p:{key}={value}" for key, value in properties.items())],
                cwd=source, stdout=output, stderr=subprocess.STDOUT, check=True,
            )

    package(source, work)


def package(source: Path, work: Path) -> None:
    runtime = work / "runtime"
    native = runtime / "DLLs"
    native.mkdir(parents=True)
    binaries = source / "PCbuild" / "amd64"
    for name in ("python.exe", "python314.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        shutil.copyfile(binaries / name, runtime / name)
    shutil.copyfile(binaries / "sqlite3.dll", runtime / "sqlite3.dll")
    shutil.copyfile(binaries / "_sqlite3.pyd", native / "_sqlite3.pyd")
    shutil.copyfile(binaries / "LICENSE.txt", runtime / "LICENSE.txt")
    shutil.copyfile(
        source / "externals" / "zlib-ng-2.2.4" / "LICENSE.md",
        runtime / "LICENSE-zlib-ng.txt",
    )
    shutil.copytree(source / "Lib", runtime / "Lib", ignore=LIB_IGNORES)

    files = {}
    for path in sorted(runtime.rglob("*")):
        if path.is_file():
            with path.open("rb") as payload:
                files[path.relative_to(runtime).as_posix()] = hashlib.file_digest(
                    payload, "sha256",
                ).hexdigest()
    manifest = {"cpython": CPYTHON[1], "dependencies": DEPENDENCIES, "files": files}
    (work / "runtime-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    print(runtime / "python.exe")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msbuild", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This runtime is built on Windows.")
    build(args.msbuild.resolve(strict=True), args.work_dir.resolve())


if __name__ == "__main__":
    main()
