"""Create or verify a versioned Synapse distribution."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROGRAMS = ("synapse-backend", "synapse-desktop", "synapse-image-decoder", "synapse-page-analyzer")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def files(target, system):
    extension = ".exe" if system == "windows" else ""
    for program in PROGRAMS:
        name = program + extension
        yield name, target / name
    modules = ROOT / "backend/python"
    for path in sorted((modules / "synapse_ai").glob("*.py")):
        yield "python/" + path.relative_to(modules).as_posix(), path
    for name in ("pyproject.toml", "requirements-voice.txt", "provision_voice.py"):
        yield "python/" + name, modules / name
    release = ROOT / "tools/release"
    if system == "windows":
        for name in ("install-windows.ps1", "start-windows.ps1"):
            path = release / name
            if path.is_file():
                yield name, path


def build(target, output, version):
    if not re.fullmatch(r"0\.3\.\d+(?:-rc\.\d+)?", version):
        raise ValueError("Expected a Synapse 0.3 version")
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[platform.system()]
    architecture = {"AMD64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"version": version, "platform": system, "architecture": architecture,
                "commit": commit, "sha256": {}}
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"synapse-{version}-{system}-{architecture}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, path in files(target, system):
            data = path.read_bytes()
            manifest["sha256"][name] = digest(data)
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = ((stat.S_IFREG | (0o755 if "/" not in name else 0o644)) << 16)
            package.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
        package.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    verify(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{digest(archive.read_bytes())}  {archive.name}\n")
    print(archive)
    return archive


def verify(archive):
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Duplicate package entries")
        manifest = json.loads(package.read("manifest.json"))
        checksums = manifest["sha256"]
        if set(names) != set(checksums) | {"manifest.json"}:
            raise ValueError("Package entries differ from manifest")
        for name, expected in checksums.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", name) or any(
                part in (".", "..") for part in name.split("/")
            ):
                raise ValueError(f"Invalid package entry: {name}")
            if digest(package.read(name)) != expected:
                raise ValueError(f"Package checksum mismatch: {name}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True, dest="command")
    create = commands.add_parser("build")
    create.add_argument("--target", type=Path, default=ROOT / "target/release")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--version", required=True)
    inspect = commands.add_parser("verify")
    inspect.add_argument("archive", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.target, args.output, args.version)
    else:
        print(json.dumps(verify(args.archive), indent=2))


if __name__ == "__main__":
    main()
