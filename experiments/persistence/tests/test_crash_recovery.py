import signal
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter

import psutil

from storage import Storage
from tests.crash_writer import payload_for_version


def test_forced_termination_before_and_after_acknowledgement(scratch):
    storage = Storage(scratch / "records.sqlite")
    storage.initialize()
    storage.append_record("crash", 1, payload_for_version(1))
    acknowledged = [1]
    uncommitted = []
    commit_times = []
    recovered_times = []
    peak_disk_bytes = 0
    peak_writer_rss = 0
    started = perf_counter()
    wal = storage.path.with_name("records.sqlite-wal")

    with ThreadPoolExecutor(max_workers=1) as pipes:
        for version in range(2, 122):
            with closing(sqlite3.connect(storage.path, autocommit=True)) as settled:
                assert settled.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
            assert not wal.exists() or wal.stat().st_size == 0

            phase = "before" if version % 2 == 0 else "after"
            expected = payload_for_version(version) if phase == "after" else None
            # A Windows virtualenv executable can be a launcher for another PID.
            command = [
                sys._base_executable, "-B", "-m", "tests.crash_writer",
                str(storage.path), str(version), phase,
            ]
            with subprocess.Popen(
                command, cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
            ) as writer:
                try:
                    receipt = pipes.submit(writer.stdout.readline).result(timeout=15).strip()
                    assert receipt.startswith(f"{phase} "), receipt
                    _, writer_pid, elapsed = receipt.split()
                    assert int(writer_pid) == writer.pid
                    assert writer.poll() is None
                    memory = psutil.Process(writer.pid).memory_info()
                    peak_writer_rss = max(peak_writer_rss, getattr(memory, "peak_wset", memory.rss))

                    assert wal.stat().st_size > 32
                    peak_disk_bytes = max(
                        peak_disk_bytes,
                        sum(file.stat().st_size for file in scratch.glob("records.sqlite*")),
                    )
                    # The current row is still absent from the main database image.
                    with closing(sqlite3.connect(
                        f"{storage.path.as_uri()}?mode=ro&immutable=1", uri=True,
                    )) as main_file:
                        assert main_file.execute(
                            "SELECT count(*) FROM records WHERE version = ?", (version,),
                        ).fetchone() == (0,)

                    assert storage.read_record("crash", version) == expected
                    assert storage.read_record("crash", acknowledged[-1]) == payload_for_version(
                        acknowledged[-1],
                    )
                    assert writer.poll() is None, "Writer exited before the kill request"
                    writer.kill()
                    if sys.platform == "win32":
                        # Pinned CPython caches the exit code if TerminateProcess was rejected.
                        assert writer.returncode is None, "Windows rejected the kill request"
                        expected_exit = 1
                    else:
                        expected_exit = -signal.SIGKILL
                    assert writer.wait(timeout=15) == expected_exit
                except BaseException:
                    if writer.poll() is None:
                        writer.kill()
                    writer.wait(timeout=15)
                    raise

            recovery_started = perf_counter()
            recovered = Storage(storage.path)
            recovered.initialize()
            recovered.check_integrity()
            assert recovered.read_record("crash", version) == expected
            assert recovered.read_record("crash", 1) == payload_for_version(1)
            recovered_times.append(perf_counter() - recovery_started)
            if phase == "after":
                commit_times.append(float(elapsed))
                acknowledged.append(version)
            else:
                uncommitted.append(version)

    verified_pre_commit = len(uncommitted)
    verified_acknowledged = len(acknowledged) - 1
    verified_kills = verified_pre_commit + verified_acknowledged
    assert (verified_pre_commit, verified_acknowledged) == (60, 60)
    for version in acknowledged:
        assert storage.read_record("crash", version) == payload_for_version(version)
    for version in uncommitted:
        assert storage.read_record("crash", version) is None

    print(
        f"Forced terminations={verified_kills} pre_commit={verified_pre_commit} "
        f"acknowledged={verified_acknowledged} acknowledged_loss=0 partial_visibility=0 "
        f"integrity_pass={verified_kills}"
    )
    print(
        f"elapsed_seconds={perf_counter() - started:.3f} "
        f"append_p50_ms={1000 * median(commit_times):.3f} "
        f"append_p95_ms={1000 * quantiles(commit_times, n=20, method='inclusive')[18]:.3f} "
        f"recover_check_p50_ms={1000 * median(recovered_times):.3f} "
        f"recover_check_p95_ms={1000 * quantiles(recovered_times, n=20, method='inclusive')[18]:.3f} "
        f"writer_resident_high_bytes={peak_writer_rss} "
        f"database_files_high_bytes={peak_disk_bytes}"
    )
