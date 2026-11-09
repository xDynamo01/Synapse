"""Disposable integration probes. Budgets are engineering calls, not owner SLAs."""
import ctypes
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time

START = 5.0
HEALTHY = 0.5
CANCEL = 1.0
TIMEOUT = 3.0
# Declared before collecting working-set data; synthetic-host ceiling only.
RSS_CEILING = 256 * 1024 * 1024
ROOT = Path(__file__).resolve().parent
EXE = ROOT / "target" / "debug" / ("synapse-boundary-spike.exe" if os.name == "nt" else "synapse-boundary-spike")


def frame(raw):
    return struct.pack(">I", len(raw)) + raw


class OwnedWindowsProcess:
    """Capture identity while the fixture is live; never reopen its PID for cleanup."""
    def __init__(self, pid):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.kernel.WaitForSingleObject.restype = ctypes.c_ulong
        self.kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel.TerminateProcess.restype = ctypes.c_int
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.CloseHandle.restype = ctypes.c_int
        self.handle = self.kernel.OpenProcess(0x101001, False, pid)
        assert self.handle
        try:
            assert self.alive(), "fixture exited before identity capture"
        except BaseException:
            self.close()
            raise

    def alive(self):
        assert self.handle is not None
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        assert result in (0, 258), ctypes.get_last_error()
        return result == 258

    def terminate_and_wait(self):
        if self.alive():
            terminated = self.kernel.TerminateProcess(self.handle, 73)
            # Natural exit can race termination; the retained identity remains safe.
            assert terminated or not self.alive(), ctypes.get_last_error()
        assert self.kernel.WaitForSingleObject(self.handle, int(TIMEOUT * 1000)) == 0

    def close(self):
        if self.handle is not None:
            assert self.kernel.CloseHandle(self.handle)
            self.handle = None


class Driver:
    def __init__(self, candidate, fixture=None):
        self.started = time.perf_counter()
        env = os.environ.copy()
        if fixture is not None:
            env["SYNAPSE_SPIKE_TREE_FIXTURE"] = fixture
        self.p = subprocess.Popen([str(EXE), candidate], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        self.q = queue.Queue(maxsize=8)
        def reader():
            try:
                while True:
                    size = self.p.stdout.read(4)
                    if not size:
                        break
                    n = struct.unpack(">I", size)[0]
                    assert n <= 4096
                    raw = self.p.stdout.read(n)
                    assert len(raw) == n
                    self.q.put(json.loads(raw))
            finally:
                self.q.put(None)
        threading.Thread(target=reader, daemon=True).start()
        self.ready = self.recv(START)
        assert self.ready["kind"] == "ready"
        self.start_ms = round((time.perf_counter() - self.started) * 1000, 3)
        self.worker_process = OwnedWindowsProcess(self.ready["pid"]) if candidate == "worker" and os.name == "nt" else None
        self.n = 0

    def recv(self, budget):
        return self.q.get(timeout=budget)

    def raw(self, raw, budget=HEALTHY):
        started = time.perf_counter()
        self.p.stdin.write(frame(raw))
        self.p.stdin.flush()
        result = self.recv(budget)
        return result, round((time.perf_counter() - started) * 1000, 3)

    def cmd(self, op, job=None, budget=HEALTHY):
        self.n += 1
        result, elapsed = self.raw(json.dumps(dict(v=1, id=self.n, op=op, job=job)).encode(), budget)
        assert result["v"] == 1 and result["id"] == self.n
        return result, elapsed

    def close(self):
        try:
            if self.p.poll() is None:
                self.p.stdin.close()
                try:
                    self.p.wait(timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    self.p.kill()
                    self.p.wait(timeout=TIMEOUT)
                    raise
        finally:
            if self.worker_process is not None:
                self.worker_process.close()

    def worker_alive(self):
        if self.worker_process is not None:
            return self.worker_process.alive()
        try:
            os.kill(self.ready["pid"], 0)
            return True
        except ProcessLookupError:
            return False


def working_set(pid):
    """Windows instantaneous working set; not peak or private/unique memory."""
    if os.name != "nt":
        return None
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "peak_paged", "paged",
                                               "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x410, False, pid)
    assert handle
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        assert ctypes.WinDLL("psapi").GetProcessMemoryInfo(ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb)
        return counters.working
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def run(candidate):
    results = dict(candidate=candidate)
    d = Driver(candidate)
    try:
        results["startup_ms"] = d.start_ms
        results["runtime"] = d.ready["runtime"]
        results["host_working_set_bytes"] = working_set(d.p.pid)
        results["python_working_set_bytes"] = working_set(d.ready["pid"])
        if os.name == "nt":
            results["combined_working_set_bytes"] = results["host_working_set_bytes"] + (
                results["python_working_set_bytes"] if candidate == "worker" else 0)
            assert results["combined_working_set_bytes"] <= RSS_CEILING
        # Positive control: all targeted negatives below differ from a valid status.
        valid, _ = d.raw(b'{"v":1,"id":1,"op":"status","job":"a"}')
        assert valid == dict(v=1, id=1, kind="event", state="unknown", value=None)
        for raw in [b"{", b'{"v":2,"id":1,"op":"status","job":"a"}',
                    b'{"v":1,"id":1,"op":"status","job":"a","extra":1}',
                    b'{"v":1,"id":1,"op":"unknown","job":null}',
                    b'{"v":1,"id":1,"op":"status"}',
                    b'{"v":1,"id":1,"id":2,"op":"status","job":"a"}',
                    b'{"v":1,"id":1,"op":"status","job":null}']:
            response, _ = d.raw(raw)
            assert response == dict(v=1, id=0, kind="error", state="invalid_schema", value=None), (raw, response)
        results["strict_negative_count"] = 7
        results["schema_negatives_have_valid_status_control"] = True
        assert d.cmd("start", "a")[0]["state"] == "running"
        assert d.cmd("start", "a")[0]["state"] == "running"
        assert d.cmd("start", "b")[0]["kind"] == "error"
        time.sleep(1.15)
        r, results["healthy_status_ms"] = d.cmd("status", "a")
        assert r["state"] == "succeeded" and r["value"] == 42
        assert d.cmd("start", "a")[0]["state"] == "succeeded"
        assert d.cmd("start", "b")[0]["state"] == "running"
        r, results["cancel_ack_ms"] = d.cmd("cancel", "b", CANCEL)
        assert r["state"] == "cancelled"
        time.sleep(1.15)
        assert d.cmd("status", "b")[0]["state"] == "cancelled"
        assert d.cmd("start", "b")[0]["state"] == "cancelled"
        results["cancel_no_late_success"] = True
    finally:
        d.close()
    # New interpreter deliberately loses session-only tombstones. No durable replay claim.
    d = Driver(candidate)
    try:
        assert d.cmd("status", "b")[0]["state"] == "unknown"
        results["restart_loses_state_observed"] = True
        assert d.cmd("start", "python-crash-flight")[0]["state"] == "running"
        started = time.perf_counter()
        d.p.stdin.write(frame(b'{"v":1,"id":1,"op":"crash","job":null}'))
        d.p.stdin.flush()
        response = d.recv(TIMEOUT)
        if candidate == "worker":
            assert response["kind"] == "error" and response["state"] == "worker_lost"
            assert d.p.poll() is None  # real Rust host survived Python exit
            assert not d.worker_alive()
            assert d.cmd("start", "forbidden-retry")[0]["state"] == "worker_lost"
        else:
            assert response is None
            assert d.p.wait(timeout=TIMEOUT) == 71
        results["python_crash_ms"] = round((time.perf_counter() - started) * 1000, 3)
        results["python_crash_host_survives"] = candidate == "worker"
    finally:
        d.close()
    # Unresponsive call: worker's 2s deadline must kill+wait; embedding has no such isolation.
    d = Driver(candidate)
    try:
        started = time.perf_counter()
        d.p.stdin.write(frame(b'{"v":1,"id":1,"op":"hang","job":null}'))
        d.p.stdin.flush()
        if candidate == "worker":
            r = d.recv(TIMEOUT)
            assert r["state"] == "worker_timeout"
            assert not d.worker_alive()
            results["timeout_ms"] = round((time.perf_counter() - started) * 1000, 3)
            assert d.cmd("start", "forbidden-retry")[0]["state"] == "worker_lost"
        else:
            try:
                d.recv(0.25)
                raise AssertionError("hang unexpectedly returned")
            except queue.Empty:
                d.p.kill()
                d.p.wait(timeout=TIMEOUT)
            results["embedding_hang_requires_external_kill"] = True
    finally:
        d.close()
    if candidate == "worker":
        d = Driver(candidate)
        try:
            assert d.cmd("start", "crash-flight")[0]["state"] == "running"
            d.p.stdin.write(frame(b'{"v":1,"id":2,"op":"rust_crash","job":null}'))
            d.p.stdin.flush()
            assert d.p.wait(timeout=TIMEOUT) == 72
            started = time.perf_counter()
            while d.worker_alive() and time.perf_counter() - started < TIMEOUT:
                time.sleep(0.01)
            assert not d.worker_alive(), "worker orphaned"
            results["rust_hard_exit_worker_cleanup_ms"] = round((time.perf_counter() - started) * 1000, 3)
        finally:
            d.close()
        # Preserve the first-spike exact hang/host-kill case, now requiring no orphan.
        if os.name == "nt":
            d = Driver(candidate)
            identity = d.worker_process
            captured_handle = identity.handle
            try:
                d.p.stdin.write(frame(b'{"v":1,"id":1,"op":"hang","job":null}'))
                d.p.stdin.flush()
                time.sleep(0.2)
                started = time.perf_counter()
                d.p.kill()
                d.p.wait(timeout=2)
                while identity.alive() and time.perf_counter() - started < 2:
                    time.sleep(0.001)
                assert identity.handle == captured_handle
                assert not identity.alive(), "original hung-call worker orphaned"
                assert time.perf_counter() - started <= 2, "original hung-call cleanup exceeded bound"
                results["original_hang_host_death_cleanup_ms"] = round((time.perf_counter() - started) * 1000, 3)
            finally:
                identity.terminate_and_wait()
                d.close()
            assert identity.handle is None
    # Oversized and truncated framing fail closed in Rust before dispatch.
    for payload in [struct.pack(">I", 4097), struct.pack(">I", 10) + b"{}"]:
        d = Driver(candidate)
        try:
            d.p.stdin.write(payload)
            d.p.stdin.close()
            assert d.p.wait(timeout=TIMEOUT) != 0
        finally:
            d.close()
    results["framing_negatives"] = 2
    return results


def containment(repetitions=10, expect_orphan=False):
    """Kill only this owned Rust process; observe original identities, never PID-reopen."""
    assert os.name == "nt", "containment lane is Windows-only"
    observations = []
    for repetition in range(repetitions):
        fixture = "fixture-hang" if repetition % 2 == 0 else "fixture-busy"
        d = Driver("worker", fixture)
        descendant = None
        identities = [d.worker_process]
        handles = []
        try:
            descendant = OwnedWindowsProcess(d.ready["fixture_descendant_pid"])
            identities.append(descendant)
            handles = [identity.handle for identity in identities]
            # Reply is flushed before this explicit fixture stops reading forever.
            assert d.cmd("start", "death-flight")[0]["state"] == "running"
            time.sleep(0.05)  # Fixture settling only; containment never relies on a timer.
            assert all(identity.alive() for identity in identities)
            started = time.perf_counter()
            d.p.kill()  # Popen retains Rust's original Windows process handle.
            d.p.wait(timeout=2)
            deadline = started + 2
            while any(identity.alive() for identity in identities) and time.perf_counter() < deadline:
                time.sleep(0.001)
            alive = [identity.alive() for identity in identities]
            observation = dict(repetition=repetition + 1, fixture=fixture,
                               host_returncode=d.p.returncode,
                               cleanup_ms=round((time.perf_counter() - started) * 1000, 3),
                               original_worker_alive=alive[0], original_descendant_alive=alive[1])
            observations.append(observation)
            print(json.dumps(observation), flush=True)
            assert [identity.handle for identity in identities] == handles
            if expect_orphan:
                assert all(alive), "RED baseline did not reproduce both orphans"
            else:
                assert not any(alive), "OS containment failed: owned original identities survived 2s"
                assert time.perf_counter() - started <= 2, "OS containment cleanup exceeded bound"
        finally:
            # Emergency RED/failure cleanup is exact-handle only; measured before cleanup.
            for identity in identities:
                identity.terminate_and_wait()
            d.close()
            if descendant is not None:
                descendant.close()
            assert all(identity.handle is None for identity in identities)
        observation["identity_handles_closed"] = True
    return observations


def setup_rejection():
    results = []
    for failure in ("before-create", "before-resume", "invalid-job"):
        env = os.environ.copy()
        env["SYNAPSE_SPIKE_CONTAINMENT_FAILURE"] = failure
        p = subprocess.Popen([str(EXE), "worker"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        stdout, stderr = p.communicate(timeout=START)
        assert p.returncode == 1 and not stdout, (failure, p.returncode, stdout)
        expected = (b"containment CreateProcessW/JOB_LIST:" if failure == "invalid-job"
                    else f"containment injected {failure} rejection".encode())
        assert expected in stderr, (failure, stderr)
        if failure == "invalid-job":
            assert b"os error 6" in stderr, stderr
        results.append(dict(failure=failure, returncode=p.returncode,
                            stdout_bytes=len(stdout), stderr=stderr.decode().strip()))
    # The owner can also die after creation, with the initial thread still suspended.
    env = os.environ.copy()
    env["SYNAPSE_SPIKE_CONTAINMENT_FAILURE"] = "hold-before-resume"
    p = subprocess.Popen([str(EXE), "worker"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    messages = queue.Queue()
    threading.Thread(target=lambda: messages.put(p.stderr.readline()), daemon=True).start()
    identity = None
    try:
        line = messages.get(timeout=START)
        assert line.startswith(b"containment suspended pid="), line
        identity = OwnedWindowsProcess(int(line.split(b"=")[1]))
        started = time.perf_counter()
        p.kill()
        stdout, stderr = p.communicate(timeout=2)
        while identity.alive() and time.perf_counter() - started < 2:
            time.sleep(0.001)
        assert not identity.alive() and not stdout, (stdout, stderr)
        assert time.perf_counter() - started <= 2, "suspended child cleanup exceeded bound"
        results.append(dict(failure="owner-death-before-resume", stdout_bytes=len(stdout),
                            cleanup_ms=round((time.perf_counter() - started) * 1000, 3)))
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=2)
        if identity is not None:
            identity.terminate_and_wait()
            identity.close()
    return results


def tree_shutdown():
    results = []
    for path in ("drop", "timeout"):
        d = Driver("worker", "fixture-hang")
        descendant = None
        try:
            descendant = OwnedWindowsProcess(d.ready["fixture_descendant_pid"])
            assert d.cmd("start", "shutdown-flight")[0]["state"] == "running"
            started = time.perf_counter()
            if path == "drop":
                d.p.stdin.close()
                assert d.p.wait(timeout=TIMEOUT) == 0
            else:
                assert d.cmd("status", "shutdown-flight", TIMEOUT)[0]["state"] == "worker_timeout"
            deadline = time.perf_counter() + 2
            while (d.worker_alive() or descendant.alive()) and time.perf_counter() < deadline:
                time.sleep(0.001)
            assert not d.worker_alive() and not descendant.alive()
            results.append(dict(path=path, cleanup_ms=round((time.perf_counter() - started) * 1000, 3)))
        finally:
            if descendant is not None:
                descendant.terminate_and_wait()
                descendant.close()
            d.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--containment-only", action="store_true")
    parser.add_argument("--expect-orphan", action="store_true")
    parser.add_argument("--repetitions", type=int, default=10)
    args = parser.parse_args()
    assert EXE.is_file(), "FAIL BEFORE: real Rust executable has not been built"
    receipt = dict(budgets_seconds=dict(start=START, healthy=HEALTHY, cancel=CANCEL, timeout=TIMEOUT),
                   working_set_ceiling_bytes=RSS_CEILING,
                   platform=sys.platform, executable_sha256=hashlib.sha256(EXE.read_bytes()).hexdigest(),
                   lock_sha256=hashlib.sha256((ROOT / "Cargo.lock").read_bytes()).hexdigest(),
                   source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in [ROOT / "src" / "main.rs", ROOT / "src" / "containment.rs",
                                               ROOT / "Cargo.toml", ROOT / "engine.py", ROOT / "probe.py"]},
                   results=[] if args.containment_only else [run(mode) for mode in ("worker", "embedded")])
    receipt["containment"] = containment(args.repetitions, args.expect_orphan)
    if not args.expect_orphan:
        receipt["setup_rejection"] = setup_rejection()
        receipt["tree_shutdown"] = tree_shutdown()
    (ROOT / "receipt.local.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
