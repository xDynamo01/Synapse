"""Fresh-process readiness and post-import RSS; never loads model weights."""

import argparse
import datetime
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time

PYTHON_PROBE = r'''
import importlib, json, os, socket, sys, time
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
def deny_network(event, args):
    if event == "socket.connect":
        raise RuntimeError("Network is forbidden during import measurement")
sys.addaudithook(deny_network)
for name in ("anyio", "pydantic", "ctranslate2", "faster_whisper", "piper", "onnxruntime", "aiosqlite"):
    importlib.import_module(name)
import psutil
print("ready", flush=True)
time.sleep(0.1)
rss = psutil.Process().memory_info().rss
print(json.dumps({"idle_rss_bytes": rss, "version": sys.version.split()[0]}))
'''

NODE_PROBE = r'''
import { spawn } from 'node:child_process';
import { once } from 'node:events';
await Promise.resolve();
console.log('ready');
await new Promise(resolve => setTimeout(resolve, 100));
console.log(JSON.stringify({idle_rss_bytes:process.memoryUsage().rss, version:process.versions.node}));
'''


def sample(command):
    start = time.perf_counter_ns()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
        deadline = threading.Timer(30, child.kill)
        deadline.start()
        try:
            ready = child.stdout.readline().strip()
            startup = (time.perf_counter_ns() - start) / 1_000_000
            output, diagnostics = child.communicate(timeout=30)
            if child.returncode != 0 or ready != "ready" or diagnostics.strip():
                raise RuntimeError("Probe failed readiness or emitted unexpected diagnostics")
        finally:
            deadline.cancel()
            if child.poll() is None:
                child.kill()
                child.wait()
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    payload = json.loads(output)
    return {"version": payload["version"], "startup_ms": round(startup, 3),
            "idle_rss_bytes": payload["idle_rss_bytes"], "process_total_ms": round(elapsed, 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": {"os": platform.system(), "architecture": platform.machine()},
        "method": {
            "runs": 5, "idle_delay_ms": 100, "models_loaded": False,
            "startup": "parent launch to ready line received, measured with parent perf_counter",
            "rss": "one post-import process working-set snapshot per run, not peak",
            "cache": "fresh processes; warm OS/package caches; not reboot/disk-cold",
        },
        "python": [sample([sys.executable, "-I", "-c", PYTHON_PROBE]) for _ in range(5)],
        "node": [sample([args.node, "--input-type=module", "-e", NODE_PROBE]) for _ in range(5)],
    }
    for kind in ("python", "node"):
        data[kind + "_summary"] = {
            "median_startup_ms": statistics.median(row["startup_ms"] for row in data[kind]),
            "median_idle_rss_bytes": statistics.median(row["idle_rss_bytes"] for row in data[kind]),
            "max_idle_rss_bytes": max(row["idle_rss_bytes"] for row in data[kind]),
        }
    args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in data.items() if key.endswith("_summary")}))


if __name__ == "__main__":
    main()
