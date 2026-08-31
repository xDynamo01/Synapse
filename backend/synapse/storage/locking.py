from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from synapse.storage.errors import StorageLockTimeout


class CollectionLock:
    """Collection-grained local and cross-process lock with explicit reentrancy."""

    _registry_guard = threading.Lock()
    _process_locks: dict[str, threading.RLock] = {}

    def __init__(
        self,
        lock_path: Path,
        *,
        timeout_seconds: float = 5.0,
        stale_after_seconds: float = 60.0,
        reentrant: bool = True,
    ) -> None:
        self.lock_path = lock_path
        self.timeout_seconds = timeout_seconds
        self.stale_after_seconds = stale_after_seconds
        self.reentrant = reentrant
        self._owner_thread: int | None = None
        self._depth = 0
        key = str(lock_path.resolve(strict=False))
        with self._registry_guard:
            self._process_lock = self._process_locks.setdefault(key, threading.RLock())

    @contextmanager
    def acquire(self) -> Iterator[None]:
        started = time.monotonic()
        if not self._process_lock.acquire(timeout=self.timeout_seconds):
            raise self._timeout()
        thread_id = threading.get_ident()
        nested = self._owner_thread == thread_id
        try:
            if nested:
                if not self.reentrant:
                    raise self._timeout()
                self._depth += 1
            else:
                self._acquire_file(started)
                self._owner_thread = thread_id
                self._depth = 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    self._owner_thread = None
                    self.lock_path.unlink(missing_ok=True)
        finally:
            self._process_lock.release()

    def _acquire_file(self, started: float) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                descriptor = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    payload = json.dumps(
                        {
                            "pid": os.getpid(),
                            "thread": threading.get_ident(),
                            "acquired_at": datetime.now(UTC).isoformat(),
                        },
                        sort_keys=True,
                    ).encode("utf-8")
                    os.write(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                return
            except FileExistsError:
                if self._is_stale():
                    self.lock_path.unlink(missing_ok=True)
                    continue
                if time.monotonic() - started >= self.timeout_seconds:
                    raise self._timeout()
                time.sleep(0.01)

    def _is_stale(self) -> bool:
        try:
            return time.time() - self.lock_path.stat().st_mtime > self.stale_after_seconds
        except FileNotFoundError:
            return False

    def _timeout(self) -> StorageLockTimeout:
        return StorageLockTimeout(
            "Storage collection lock timed out",
            details={"lock": self.lock_path.name, "timeout_seconds": self.timeout_seconds},
        )
