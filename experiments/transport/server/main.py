"""Loopback-only entrypoint. No host/port/token override and no product effects."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "generated/python")]
from server.lifecycle import Lifecycle


async def main():
    assert sys.version_info[:3] == (3, 14, 10) and sys._is_gil_enabled()
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=["grpc", "http"], required=True)
    parser.add_argument("--journal", required=True)
    args = parser.parse_args()
    if args.candidate == "grpc":
        from server.grpc_server import start
    else:
        from server.http_server import start
    lifecycle = Lifecycle(args.journal)
    try:
        port, stop = await start(lifecycle)
        try:
            print(json.dumps({"host": "127.0.0.1", "port": port, "candidate": args.candidate,
                              "pid": os.getpid(), "parent_pid": os.getppid()}), flush=True)
            # Test harness closes stdin to request graceful cleanup; kill tests bypass it.
            await asyncio.to_thread(sys.stdin.buffer.read, 1)
        finally:
            await stop()
    finally:
        lifecycle.close()


if __name__ == "__main__":
    asyncio.run(main())
