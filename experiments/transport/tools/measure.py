"""Five process-cold samples per candidate; never a product performance claim."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from client.python_client import Client
from tests.process_harness import Server


async def measure(candidate, journal):
    async with Server(candidate, journal) as process:
        startup = process.startup_ms
        await asyncio.sleep(0.1)
        rss = psutil.Process(process.runtime_pid).memory_info().rss
        async with Client(candidate, process.port) as client:
            request = {"command_id": "measurement", "causation_id": "owner", "action": "hold"}
            await client.call("SubmitCommand", request)
            async with client.events("0") as stream:
                assert (await stream.next())["event_id"] == "1"
            await client.call("CancelCommand", {"command_id": "measurement", "causation_id": "owner-cancel"})
        started = time.perf_counter()
        async with Client(candidate, process.port) as client:
            async with client.events("1") as stream:
                assert (await stream.next())["event_id"] == "2"
                reconnect = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        await process.kill()
        await process.start()
        async with Client(candidate, process.port) as client:
            async with client.events("1") as stream:
                assert (await stream.next())["event_id"] == "2"
                restart = (time.perf_counter() - started) * 1000
            assert (await client.call("SubmitCommand", request))["duplicate"]
            assert (await client.call("GetStatus"))["command_count"] == 1
        return {"startup_ms": round(startup, 3), "idle_rss_bytes": rss,
                "reconnect_to_replay_ms": round(reconnect, 3), "kill_restart_to_replay_ms": round(restart, 3)}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", choices=["grpc", "http"])
    args = parser.parse_args()
    result = {"status": "TESTED", "result": "PASS", "platform": platform.platform(),
              "python": platform.python_version(), "samples_per_candidate": 5,
              "method": "fresh process; warm OS cache; actual server PID RSS at 100ms idle, excludes Windows venv launcher; reconnect includes new client and replay; restart includes actual server PID forced kill, new ephemeral bind and replay",
              "candidates": {}}
    scratch = ROOT / ".local"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="measure-", dir=scratch) as directory:
        for candidate in [args.candidate] if args.candidate else ["grpc", "http"]:
            samples = []
            for index in range(5):
                samples.append(await measure(candidate, Path(directory) / f"{candidate}-{index}.sqlite"))
                print(json.dumps({"candidate": candidate, "sample": index + 1, **samples[-1]}), flush=True)
            result["candidates"][candidate] = {"samples": samples, "medians": {
                field: statistics.median(sample[field] for sample in samples) for field in samples[0]
            }}
    inputs = [ROOT / name for name in (
        ".gitattributes", ".gitignore", ".node-version", ".python-version", "package.json",
        "pnpm-lock.yaml", "pnpm-workspace.yaml", "pyproject.toml", "tsconfig.json", "uv.lock",
    )]
    for folder in ("client", "proto", "server", "tests", "tools"):
        inputs.extend(path for path in (ROOT / folder).rglob("*") if path.suffix in {".py", ".proto", ".ts", ".mjs"})
    result["inputs_sha256"] = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in sorted(inputs)}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
