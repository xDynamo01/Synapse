from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from uuid import uuid4

from synapse.storage.errors import StorageWriteFailed


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    backup: bool = False,
) -> int:
    """Durably replace one file with a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if previous_mode is not None:
            os.chmod(temporary, previous_mode)
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
        return len(content)
    except Exception as exc:
        raise StorageWriteFailed(
            "Atomic storage write failed", details={"file": path.name}
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_text(
    path: Path,
    content: str,
    *,
    backup: bool = False,
) -> int:
    return atomic_write_bytes(path, content.encode("utf-8"), backup=backup)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)
