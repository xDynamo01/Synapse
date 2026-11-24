"""Durable ownership record for the managed local provider."""

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import uuid


_DEFAULT_LOCK_ROOT = Path(tempfile.gettempdir()) / "Synapse.ModelProviderLocks"


class OwnershipError(Exception):
    pass


@contextmanager
def ownership(base):
    directory = os.environ.get("SYNAPSE_MODEL_OWNERSHIP_DIR")
    job = os.environ.get("SYNAPSE_MODEL_LEASE_ID")
    if directory is None and job is None:
        yield None
        return
    if not directory or not job or len(job.encode("utf-8")) > 512:
        raise OwnershipError("model_ownership_unavailable")
    root = Path(directory)
    if not root.is_absolute():
        raise OwnershipError("model_ownership_unavailable")
    endpoint_key = sha256(base.encode()).hexdigest()
    try:
        root.mkdir(parents=True, exist_ok=True)
        lock_root = Path(os.environ.get("SYNAPSE_MODEL_LOCK_DIR", _DEFAULT_LOCK_ROOT))
        if not lock_root.is_absolute():
            raise OSError("invalid model lock directory")
        lock_root.mkdir(parents=True, exist_ok=True)
        if lock_root.is_symlink() or (os.name == "nt" and lock_root.is_junction()):
            raise OSError("invalid model lock directory")
        lock_path=lock_root / f"{endpoint_key}.lock"
        if lock_path.is_symlink() or (os.name == "nt" and lock_path.is_junction()):
            raise OSError("invalid model lock file")
        lock = lock_path.open("a+b")
    except OSError:
        raise OwnershipError("model_ownership_unavailable") from None
    with lock:
        try:
            _lock(lock)
        except OSError:
            raise OwnershipError("model_capacity_busy") from None
        # Closing the file releases the process lock, including on hard kill.
        yield Journal(root / f"{endpoint_key}.json", sha256(job.encode()).hexdigest())


def _lock(file):
    if os.name == "nt":
        import msvcrt
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


class Journal:
    def __init__(self, path, lease_id):
        self.path = path
        self.lease_id = lease_id

    def read(self):
        try:
            with self.path.open(encoding="utf-8") as source:
                text = source.read(4097)
            if len(text) > 4096:
                raise ValueError
            record = json.loads(text)
            if (set(record) != {"lease", "model", "kind", "instance", "phase"}
                    or not re.fullmatch(r"[0-9a-f]{64}", record["lease"])
                    or not _label(record["model"]) or record["phase"] not in ("pending", "acquired")):
                raise ValueError
            kind = record["kind"]
            instance = record["instance"]
            if kind == "cli":
                pattern = rf"synapse-{record['lease'][:12]}-[0-9a-f]{{32}}"
                if not re.fullmatch(pattern, instance):
                    raise ValueError
            elif kind != "rest" or (instance is not None and not _label(instance)):
                raise ValueError
            return record
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            raise OwnershipError("model_ownership_unavailable") from None

    def reserve_cli(self, model):
        instance = f"synapse-{self.lease_id[:12]}-{uuid.uuid4().hex}"
        self.write(model, "cli", instance, "pending")
        return instance

    def write(self, model, kind, instance, phase):
        if not _label(model) or (instance is not None and not _label(instance)):
            raise OwnershipError("model_release_uncertain")
        record = {"lease": self.lease_id, "model": model, "kind": kind, "instance": instance, "phase": phase}
        self._atomic(self.path, record)

    def _atomic(self, destination, record):
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False, mode="w",
                                             encoding="utf-8") as output:
                temp = Path(output.name)
                json.dump(record, output, separators=(",", ":"), ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, destination)
            self._sync_directory()
        except OSError:
            raise OwnershipError("model_ownership_unavailable") from None
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self, recovered=None):
        if recovered:
            proof = {
                "lease": recovered["lease"], "endpoint": self.path.stem,
                "instance": recovered["instance"], "kind": recovered["kind"],
            }
            self._atomic(self.path.parent / f"released-{recovered['lease']}.json", proof)
        try:
            self.path.unlink(missing_ok=True)
            self._sync_directory()
        except OSError:
            raise OwnershipError("model_ownership_unavailable") from None

    def _sync_directory(self):
        if os.name != "nt":
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def _label(value):
    return isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 512
