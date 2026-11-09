"""Fresh synthetic fixture shared verbatim by child and embedded candidates."""
import json
import os
import struct
import subprocess
import sys
import threading
import time

LIMIT = 4096


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}

    def hello(self):
        return json.dumps(dict(kind="ready", v=1, runtime=sys.version.split()[0], pid=os.getpid()))

    def dispatch(self, raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate")
                result[key] = value
            return result
        try:
            c = json.loads(raw, object_pairs_hook=unique)
            assert type(c) is dict and set(c) == {"v", "id", "op", "job"}
            assert type(c["v"]) is int and c["v"] == 1
            assert type(c["id"]) is int and 0 <= c["id"] <= 2**32 - 1
            assert c["op"] in ("start", "status", "cancel", "crash", "hang", "rust_crash")
            assert c["job"] is None or (type(c["job"]) is str and 1 <= len(c["job"]) <= 64)
            assert (c["op"] in ("start", "status", "cancel")) == (c["job"] is not None)
        except (AssertionError, ValueError, TypeError, KeyError):
            return json.dumps(dict(v=1, id=0, kind="error", state="invalid_schema", value=None))
        if c["op"] == "crash":
            os._exit(71)
        if c["op"] == "hang":
            time.sleep(60)
        with self.lock:
            job = c["job"]
            state = self.jobs.get(job, "unknown")
            kind = "event"
            if c["op"] == "start" and state == "unknown":
                if "running" in self.jobs.values() or len(self.jobs) >= 8:
                    kind, state = "error", "capacity"
                else:
                    self.jobs[job] = state = "running"
                    threading.Thread(target=self.complete, args=(job,), daemon=True).start()
            elif c["op"] == "cancel" and state == "running":
                self.jobs[job] = state = "cancelled"
            return json.dumps(dict(v=1, id=c["id"], kind=kind, state=state,
                                   value=42 if state == "succeeded" else None))

    def complete(self, job):
        for _ in range(100):
            time.sleep(0.01)
            with self.lock:
                if self.jobs[job] != "running":
                    return
        with self.lock:
            if self.jobs[job] == "running":
                self.jobs[job] = "succeeded"


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise EOFError
        data.extend(part)
    return bytes(data)


def write_frame(raw):
    body = raw.encode("utf-8")
    assert len(body) <= LIMIT
    sys.stdout.buffer.write(struct.pack(">I", len(body)) + body)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    engine = Engine()
    # Explicit synthetic lifetime fixture, absent from the compared protocol.
    fixture = sys.argv[1] if len(sys.argv) == 2 else None
    descendant = None
    hello = json.loads(engine.hello())
    if fixture in ("fixture-hang", "fixture-busy"):
        descendant = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True)
        hello["fixture_descendant_pid"] = descendant.pid
    write_frame(json.dumps(hello))
    try:
        while True:
            size = struct.unpack(">I", read_exact(sys.stdin.buffer, 4))[0]
            if not 1 <= size <= LIMIT:
                sys.exit(65)
            write_frame(engine.dispatch(read_exact(sys.stdin.buffer, size).decode("utf-8")))
            if fixture == "fixture-hang":
                time.sleep(60)
            elif fixture == "fixture-busy":
                end = time.monotonic() + 60
                while time.monotonic() < end:
                    pass
    except EOFError:
        pass  # Cooperative exit only; Windows Job Object owns abrupt-death cleanup.
