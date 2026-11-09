"""Disposable integration probes. Budgets are engineering calls, not owner SLAs."""
import ctypes
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


class Driver:
    def __init__(self, candidate):
        self.started = time.perf_counter()
        self.p = subprocess.Popen([str(EXE), candidate], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
        if self.p.poll() is None:
            self.p.stdin.close()
            try:
                self.p.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait(timeout=TIMEOUT)
                raise


def alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = ctypes.c_ulong()
    kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
    kernel.CloseHandle(ctypes.c_void_p(handle))
    return code.value == 259


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


def terminate_owned_windows_child(pid):
    """External probe cleanup for the specific PID reported by our owned worker."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x100001, False, pid)
    assert handle
    try:
        assert kernel.TerminateProcess(ctypes.c_void_p(handle), 73)
        assert kernel.WaitForSingleObject(ctypes.c_void_p(handle), int(TIMEOUT * 1000)) == 0
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
        for raw in [b"{", b'{"v":2,"id":1,"op":"status","job":null}',
                    b'{"v":1,"id":1,"op":"status","job":null,"extra":1}',
                    b'{"v":1,"id":1,"op":"unknown","job":null}',
                    b'{"v":1,"id":1,"op":"status"}',
                    b'{"v":1,"id":1,"id":2,"op":"status","job":null}']:
            response, _ = d.raw(raw)
            assert response["kind"] == "error", response
        results["strict_negative_count"] = 6
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
            assert not alive(d.ready["pid"])
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
            assert not alive(d.ready["pid"])
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
            while alive(d.ready["pid"]) and time.perf_counter() - started < TIMEOUT:
                time.sleep(0.01)
            assert not alive(d.ready["pid"]), "worker orphaned"
            results["rust_crash_worker_eof_exit_ms"] = round((time.perf_counter() - started) * 1000, 3)
        finally:
            d.close()
        if os.name == "nt":
            d = Driver(candidate)
            child_pid = d.ready["pid"]
            try:
                d.p.stdin.write(frame(b'{"v":1,"id":1,"op":"hang","job":null}'))
                d.p.stdin.flush()
                time.sleep(0.2)
                d.p.kill()  # abrupt host death while its worker deadline cannot execute
                d.p.wait(timeout=TIMEOUT)
                time.sleep(0.1)
                results["rust_death_during_hang_orphans_worker"] = alive(child_pid)
                assert results["rust_death_during_hang_orphans_worker"]
            finally:
                if alive(child_pid):
                    terminate_owned_windows_child(child_pid)
                d.close()
            assert not alive(child_pid)
            results["orphan_cleaned_by_external_probe"] = True
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


if __name__ == "__main__":
    assert EXE.is_file(), "FAIL BEFORE: real Rust executable has not been built"
    receipt = dict(budgets_seconds=dict(start=START, healthy=HEALTHY, cancel=CANCEL, timeout=TIMEOUT),
                   working_set_ceiling_bytes=RSS_CEILING,
                   platform=sys.platform, executable_sha256=hashlib.sha256(EXE.read_bytes()).hexdigest(),
                   lock_sha256=hashlib.sha256((ROOT / "Cargo.lock").read_bytes()).hexdigest(),
                   results=[run(mode) for mode in ("worker", "embedded")])
    (ROOT / "receipt.local.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
