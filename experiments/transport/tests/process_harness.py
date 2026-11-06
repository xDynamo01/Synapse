import asyncio
import json
from pathlib import Path
import sys
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]


class Server:
    def __init__(self, candidate, journal):
        self.candidate, self.journal = candidate, journal
        self.process = None
        self.port = None
        self.startup_ms = None
        self.runtime_pid = None
        self.runtime = None

    async def start(self):
        assert self.process is None
        started = time.perf_counter()
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "server/main.py"), "--candidate", self.candidate,
            "--journal", str(self.journal), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), 10)
            self.startup_ms = (time.perf_counter() - started) * 1000
            if not line:
                raise RuntimeError((await asyncio.wait_for(self.process.stderr.read(), 2)).decode())
            ready = json.loads(line)
            assert ready["host"] == "127.0.0.1" and 0 < ready["port"] < 65536
            assert ready["candidate"] == self.candidate
            launcher = psutil.Process(self.process.pid)
            owned = {child.pid: child for child in launcher.children(recursive=True)}
            owned[launcher.pid] = launcher
            self.runtime = owned[ready["pid"]]
            self.port = ready["port"]
            self.runtime_pid = ready["pid"]
        except BaseException:
            await self.kill()
            raise

    async def kill(self):
        if self.process:
            if self.runtime and self.runtime.is_running():
                self.runtime.kill()
            elif self.runtime is None and self.process.returncode is None:
                # A failed startup may have spawned the Windows venv interpreter
                # without publishing readiness. Only terminate owned descendants.
                try:
                    children = psutil.Process(self.process.pid).children(recursive=True)
                except psutil.NoSuchProcess:
                    children = []
                for child in reversed(children):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                self.process.stdin.close()
            if self.process.returncode is None:
                try:
                    await asyncio.wait_for(self.process.wait(), 2)
                except TimeoutError:
                    self.process.kill()
            await asyncio.wait_for(self.process.communicate(), 5)
            assert self.process.returncode is not None
            self.process = None
            if self.runtime:
                assert not self.runtime.is_running()
            self.runtime = None
            self.runtime_pid = None

    async def stop(self):
        if self.process:
            self.process.stdin.close()
            try:
                _, stderr = await asyncio.wait_for(self.process.communicate(), 5)
                assert self.process.returncode == 0, stderr.decode()
                assert not stderr, stderr.decode()
            finally:
                await self.kill()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()
