"""Exercise the built Core without inheriting the development state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from package import verify


def smoke(target):
    executable = target / ("synapse-backend.exe" if os.name == "nt" else "synapse-backend")
    commands = [
        {"type": "capabilities_list"},
        {"type": "events_read", "after": 0, "limit": 5},
    ]
    requests = [
        {"version": 1, "request_id": f"release-{index}", "command": command}
        for index, command in enumerate(commands)
    ]
    with tempfile.TemporaryDirectory(prefix="synapse-package-smoke-") as directory:
        workspace = Path(directory) / "workspace"
        workspace.mkdir()
        reply = subprocess.run(
            [executable, "--state-dir", Path(directory) / "state", "--workspace", workspace],
            input="".join(json.dumps(request) + "\n" for request in requests),
            cwd=directory,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
    rows = [json.loads(line) for line in reply.stdout.splitlines()]
    if len(rows) != len(requests) or any(
        response["request_id"] != request["request_id"] or response["ok"] is not True
        for request, response in zip(requests, rows)
    ):
        raise RuntimeError("Core package smoke failed")
    print("Core opened clean state and completed the JSON protocol checks.")


if __name__ == "__main__":
    if sys.argv[1] == "--archive":
        (archive,) = Path(sys.argv[2]).glob("*.zip")
        verify(archive)
        with tempfile.TemporaryDirectory(prefix="synapse-extracted-") as directory:
            target = Path(directory)
            with zipfile.ZipFile(archive) as package:
                package.extractall(target)
                if os.name != "nt":
                    (target / "synapse-backend").chmod(0o755)
            smoke(target)
    else:
        smoke(Path(sys.argv[1]).resolve(strict=True))
