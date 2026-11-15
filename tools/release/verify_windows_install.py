"""Validate a clean Windows install, update, migration and rollback."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import zipfile

from package import verify
from smoke import smoke


def install(script, root, archive=None):
    command = ["pwsh", "-NoProfile", "-File", script, "-InstallRoot", root]
    if archive is None:
        command.append("-Rollback")
    else:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        command.extend(("-Package", archive, "-Sha256", digest))
    return subprocess.check_output(command, text=True).strip()


def call(binary, state, workspace, *commands):
    frames = [
        json.dumps({"version": 1, "request_id": f"migration-{uuid.uuid4().hex}-{index}", "command": command}) + "\n"
        for index, command in enumerate(commands)
    ]
    result = subprocess.run(
        [binary, "--state-dir", state, "--workspace", workspace], input="".join(frames),
        text=True, encoding="utf-8", capture_output=True, timeout=30, check=True,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    if not replies or len(replies) != len(commands) or not all(row["ok"] is True for row in replies):
        raise RuntimeError(f"Packaged Core rejected migration probes: {replies}")
    return replies


def main():
    installer, previous, candidate = (Path(arg).resolve(strict=True) for arg in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="Synapse-distribution-acceptance-") as temporary:
        root = Path(temporary)
        program = root / "distribution"
        state = root / "state"
        workspace = root / "workspace"
        workspace.mkdir()
        tampered = root / "tampered.zip"
        with zipfile.ZipFile(candidate) as incoming, zipfile.ZipFile(tampered, "w") as outgoing:
            for name in incoming.namelist():
                data = incoming.read(name)
                if name == "start-windows.ps1":
                    data += b"changed"
                outgoing.writestr(name, data)
        try:
            verify(tampered)
        except ValueError as error:
            assert "checksum mismatch" in str(error)
        else:
            raise AssertionError("Tampered package passed verification")
        rejected = subprocess.run(
            ["pwsh", "-NoProfile", "-File", installer, "-InstallRoot", program,
             "-Package", tampered, "-Sha256", hashlib.sha256(candidate.read_bytes()).hexdigest()],
            capture_output=True, timeout=30,
        )
        assert rejected.returncode != 0 and not (program / "active.json").exists()

        first = install(installer, program, previous)
        old = program / "versions" / first
        smoke(old)
        call(old / "synapse-backend.exe", state, workspace,
             {"type": "memory_put", "scope": "project:release", "key": "release-check",
              "kind": "fact", "content": "preserve", "expected_revision": 0,
              "provenance": {"source_type": "human", "source_id": "release-test",
                             "evidence": "Disposable migration fixture"}, "status": "active"})
        db = state / "core.sqlite3"
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute("DROP TABLE voice_translation_jobs")
            connection.execute("DROP TABLE voice_translators")
            connection.execute("PRAGMA user_version=14")

        second = install(installer, program, candidate)
        assert first != second
        upgraded = program / "versions" / second
        smoke(upgraded)
        subprocess.run(
            ["pwsh", "-NoProfile", "-File", upgraded / "start-windows.ps1", "-Verify",
             "-InstallRoot", program, "-StateRoot", state, "-Workspace", workspace,
             "-Python", sys.executable],
            check=True, timeout=30,
        )
        call(upgraded / "synapse-backend.exe", state, workspace, {"type": "capabilities_list"})
        with closing(sqlite3.connect(db)) as connection, connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (15,)
            assert connection.execute("SELECT content FROM memory WHERE key='release-check'").fetchone() == ("preserve",)
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert install(installer, program) == first
        call(old / "synapse-backend.exe", state, workspace, {"type": "capabilities_list"})
        print(json.dumps({"clean_install": first, "update": second, "migrated_schema": 15,
                          "data_preserved": True, "program_rollback": True, "tamper_rejected": True}))


if __name__ == "__main__":
    main()
