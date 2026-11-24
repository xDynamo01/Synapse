"""Create deterministic, inventoried Synapse distributions (integrity is not origin authentication)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROGRAMS = ("synapse-backend", "synapse-maintenance", "synapse-desktop-slint", "synapse-image-decoder", "synapse-page-analyzer")
FORMAT = 2
CONTRACT = {"core_api": 1, "worker_protocol": [4, 5], "storage_min": 0, "storage_max": 16,
            "frontend": "slint", "python": "3.14", "remote_inference": False}
EXCLUDED = {"__pycache__", "site-packages", "test", "tests", "idlelib", "ensurepip", "turtledemo"}


def digest(content):
    return hashlib.sha256(content).hexdigest()


def safe_name(name):
    return (bool(re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", name))
            and all(part not in (".", "..") and not part.endswith(".")
                    and part.split(".")[0].upper() not in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
                    for part in name.split("/")))


def source_fingerprint():
    # Include untracked product source and local modifications; commit alone is insufficient.
    paths = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    inventory = {}
    for name in sorted(set(paths)):
        path = ROOT / name
        if path.is_file() and (name.startswith(("backend/", "tools/release/")) or name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "Synapse-JARVIS-LICENSE.txt")):
            inventory[name] = digest(path.read_bytes())
    return {"sha256": digest(json.dumps(inventory, sort_keys=True).encode()), "files": inventory}


def runtime_files(runtime):
    if not runtime or not (runtime / "python.exe").is_file():
        raise ValueError("Windows package requires --python-runtime (complete CPython 3.14 directory)")
    probe = subprocess.run([runtime / "python.exe", "-I", "-B", "-c", "import sys,socket,ssl,sqlite3,hashlib,urllib.request,asyncio; assert sys.version_info[:2] == (3,14)"], capture_output=True)
    if probe.returncode:
        raise ValueError("Python runtime is incomplete or not CPython 3.14")
    # Prune developer packages before traversal. A local installation can contain
    # hundreds of thousands of unrelated ML environment files under site-packages.
    for directory, folders, names in os.walk(runtime, followlinks=False):
        base = Path(directory)
        for name in list(folders):
            path = base / name
            if name.casefold() in EXCLUDED or (base == runtime and name not in ("Lib", "DLLs")):
                folders.remove(name)
            elif path.is_symlink() or path.is_junction():
                raise ValueError("Python runtime must not contain links")
        folders.sort()
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(runtime)
            if path.is_symlink() or path.is_junction():
                raise ValueError("Python runtime must not contain links")
            if not path.is_file() or path.suffix.casefold() in (".pyc", ".pyo", ".pth") or name.casefold() in ("sitecustomize.py", "usercustomize.py"):
                continue
            # A closed allowlist prevents copying an arbitrary developer environment.
            if len(relative.parts) == 1 and not (name in ("python.exe", "python3.dll", "python314.dll", "LICENSE.txt") or re.fullmatch(r"vcruntime[0-9_]+\.dll", name)):
                continue
            yield "runtime/" + relative.as_posix(), path


def check_runtime_files(folder):
    if not folder:
        raise ValueError("Windows package requires --check-runtime for isolated generated-code checks")
    manifest_path = folder / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("cpython") != "323c59a5e348347be2ce2b7ea55fcb30bf68b2d3" or manifest.get("dependencies") != {"zlib-ng-2.2.4": "a502e047655c31db29601def76ad6539acacf43d", "sqlite-3.50.4.0": "ef547e549b49a2822214ef7880c0ca212b32929e"}:
        raise ValueError("Unrecognized pinned isolated checker runtime provenance")
    if not {"python.exe", "python314.dll", "DLLs/_sqlite3.pyd"} <= set(manifest["files"]):
        raise ValueError("Isolated checker runtime incomplete")
    yield "check-runtime/runtime-manifest.json", manifest_path
    for name, expected in sorted(manifest["files"].items()):
        if not safe_name(name):
            raise ValueError("Invalid checker runtime path")
        path = folder / "runtime" / name
        if path.is_symlink() or digest(path.read_bytes()) != expected:
            raise ValueError("Checker runtime checksum mismatch: " + name)
        yield "check-runtime/runtime/" + name, path


def files(target, system, python_runtime=None, check_runtime=None):
    extension = ".exe" if system == "windows" else ""
    for program in PROGRAMS:
        yield program + extension, target / (program + extension)
    license_path = ROOT / "Synapse-JARVIS-LICENSE.txt"
    if license_path.is_file():
        yield "Synapse-JARVIS-LICENSE.txt", license_path
    modules = ROOT / "backend/python"
    for path in sorted((modules / "synapse_ai").rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield "python/" + path.relative_to(modules).as_posix(), path
    for name in ("pyproject.toml", "requirements-voice.txt", "provision_voice.py"):
        yield "python/" + name, modules / name
    if system == "windows":
        yield from runtime_files(python_runtime)
        yield from check_runtime_files(check_runtime)
        for name in ("install-windows.ps1", "start-windows.ps1", "distribution-common.ps1", "diagnose.py"):
            yield name, ROOT / "tools/release" / name


def build(target, output, version, python_runtime=None, check_runtime=None):
    if not re.fullmatch(r"0\.3\.\d+(?:-rc\.\d+)?", version):
        raise ValueError("Expected a Synapse 0.3 version")
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    architecture = {"AMD64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"format": FORMAT, "version": version, "platform": system, "architecture": architecture,
                "commit": commit, "source_tree": source_fingerprint(), "compatibility": CONTRACT, "sha256": {}}
    payloads = {}
    for name, path in files(target, system, python_runtime, check_runtime):
        if not path.is_file() or path.is_symlink() or not safe_name(name):
            raise ValueError(f"Missing or invalid package input: {path}")
        payloads[name] = path.read_bytes()
        manifest["sha256"][name] = digest(payloads[name])
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"synapse-{version}-{system}-{architecture}.zip"
    payloads["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in sorted(payloads.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = ((stat.S_IFREG | (0o755 if "/" not in name else 0o644)) << 16)
            package.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
    verify(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{digest(archive.read_bytes())}  {archive.name}\n")
    print(archive)
    return archive


def verify(archive, trusted_sha256=None):
    if trusted_sha256 and digest(archive.read_bytes()) != trusted_sha256.lower():
        raise ValueError("Archive differs from independently trusted digest")
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len({name.casefold() for name in names}) != len(names) or any(not safe_name(name) for name in names):
            raise ValueError("Invalid or duplicate package entries")
        manifest = json.loads(package.read("manifest.json"))
        checksums = manifest["sha256"]
        if set(names) != set(checksums) | {"manifest.json"}:
            raise ValueError("Package entries differ from manifest")
        extension = ".exe" if manifest["platform"] == "windows" else ""
        legacy = "format" not in manifest
        required = {name + extension for name in (("synapse-backend", "synapse-desktop", "synapse-image-decoder", "synapse-page-analyzer") if legacy else PROGRAMS)}
        required.add("python/synapse_ai/__init__.py")
        if not legacy:
            if manifest["format"] != FORMAT or manifest["compatibility"] != CONTRACT:
                raise ValueError("Unsupported compatibility contract")
            source = manifest["source_tree"]
            if source["sha256"] != digest(json.dumps(source["files"], sort_keys=True).encode()):
                raise ValueError("Source tree fingerprint mismatch")
            if manifest["platform"] == "windows":
                required |= {"check-runtime/runtime-manifest.json", "check-runtime/runtime/python.exe", "runtime/python.exe", "runtime/python314.dll", "runtime/Lib/socket.py", "runtime/DLLs/_socket.pyd", "runtime/DLLs/_ssl.pyd", "runtime/DLLs/_sqlite3.pyd", "distribution-common.ps1", "diagnose.py", "start-windows.ps1", "install-windows.ps1"}
        if not required <= set(checksums):
            raise ValueError("Package incomplete: " + ", ".join(sorted(required - set(checksums))))
        if not legacy and manifest["platform"] == "windows":
            checker = json.loads(package.read("check-runtime/runtime-manifest.json"))
            if checker.get("cpython") != "323c59a5e348347be2ce2b7ea55fcb30bf68b2d3" or checker.get("dependencies") != {"zlib-ng-2.2.4": "a502e047655c31db29601def76ad6539acacf43d", "sqlite-3.50.4.0": "ef547e549b49a2822214ef7880c0ca212b32929e"}:
                raise ValueError("Unsupported checker provenance")
            if not {"python.exe", "python314.dll", "DLLs/_sqlite3.pyd"} <= set(checker["files"]):
                raise ValueError("Incomplete checker runtime")
            for name, expected in checker["files"].items():
                if not safe_name(name) or checksums.get("check-runtime/runtime/" + name) != expected:
                    raise ValueError("Checker inventory mismatch")
            if {name.removeprefix("check-runtime/runtime/") for name in checksums if name.startswith("check-runtime/runtime/")} != set(checker["files"]):
                raise ValueError("Unexpected checker runtime file")
        for name, expected in checksums.items():
            if not re.fullmatch(r"[a-f0-9]{64}", expected) or digest(package.read(name)) != expected:
                raise ValueError(f"Package checksum mismatch: {name}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True, dest="command")
    create = commands.add_parser("build")
    create.add_argument("--target", type=Path, default=ROOT / "target/release")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--version", required=True)
    create.add_argument("--python-runtime", type=Path)
    create.add_argument("--check-runtime", type=Path)
    inspect = commands.add_parser("verify")
    inspect.add_argument("archive", type=Path)
    inspect.add_argument("--trusted-sha256")
    args = parser.parse_args()
    if args.command == "build":
        build(args.target, args.output, args.version, args.python_runtime, args.check_runtime)
    else:
        print(json.dumps(verify(args.archive, args.trusted_sha256), indent=2))


if __name__ == "__main__":
    main()
