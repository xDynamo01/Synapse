"""Pause a real SQLite writer for forced termination by its test parent."""

import hashlib
import os
import sys
from contextlib import closing
from pathlib import Path
from time import perf_counter

from storage import RecordPayload, Storage


def payload_for_version(version: int) -> RecordPayload:
    content = f"synthetic version {version}".encode()
    # Exercise pager spill with a synthetic multi-page reference.
    reference = f"fixture:{version}/" + "x" * (32 * 1024)
    return RecordPayload(reference, hashlib.sha256(content).hexdigest())


def pause(phase: str, elapsed: float) -> None:
    print(f"{phase} {os.getpid()} {elapsed:.9f}", flush=True)
    sys.stdin.read(1)


class UncommittedWriter(Storage):
    def _connect(self, mode="rw"):
        connection = super()._connect(mode)
        connection.execute("PRAGMA cache_size = -8")
        connection.execute("PRAGMA cache_spill = ON")

        def pause_before_commit(statement):
            if statement == "COMMIT":
                pause("before", 0)

        connection.set_trace_callback(pause_before_commit)
        return connection


def write_and_pause(path: Path, version: int, phase: str) -> None:
    storage = UncommittedWriter(path) if phase == "before" else Storage(path)
    # Keep the WAL alive after append_record closes its committing connection.
    with closing(storage._connect("ro")) as keeper:
        keeper.execute("SELECT count(*) FROM records").fetchone()
        payload = payload_for_version(version)
        started = perf_counter()
        storage.append_record("crash", version, payload)
        pause("after", perf_counter() - started)


if __name__ == "__main__":
    write_and_pause(Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
