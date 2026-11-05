"""Path authority shared by file tools, including owner-authorized disk access."""
from __future__ import annotations

import os
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file


def authorized_roots(data_dir: DataDir) -> list[Path]:
    policy_path = data_dir.resolve("config/filesystem_tools.yaml")
    policy = load_structured_file(policy_path) if policy_path.exists() else {}
    roots = [data_dir.root.resolve(), *(Path(str(root)).resolve() for root in policy.get("allowed_roots", []))]
    if policy.get("all_disks") is True:
        if os.name == "nt":
            roots.extend(Path(drive) for drive in os.listdrives())
        else:
            roots.append(Path("/"))
    return list(dict.fromkeys(roots))


def resolve_tool_path(data_dir: DataDir, value: str, *, mutation: bool = False) -> Path:
    roots = authorized_roots(data_dir)
    raw = Path(value).expanduser()
    raw = raw if raw.is_absolute() else data_dir.root / raw
    if ".." in raw.parts:
        raise ValidationError("Parent traversal is not permitted by file tools.")
    for part in [raw, *raw.parents]:
        if part.is_symlink() or part.is_junction():
            raise ValidationError("File tools do not follow symbolic links or junctions.")
    path = raw.resolve()
    if not any(path.is_relative_to(root) for root in roots):
        raise ValidationError("Path is outside the authorized project directories.")
    if mutation:
        if any(part.casefold() in {".git", ".ssh", ".codex"} for part in path.parts):
            raise ValidationError("Protected directory cannot be changed by file tools.")
        if path.is_relative_to(data_dir.root.resolve()):
            relative = path.relative_to(data_dir.root.resolve())
            if relative.parts and relative.parts[0] in {"config", "agents", "approvals", "tools", "primary_agents"}:
                raise ValidationError("Control-plane records require their dedicated Synapse tools.")
        if path.is_file() and os.stat(path).st_nlink > 1:
            raise ValidationError("File tools cannot modify hard-linked files.")
    return path
