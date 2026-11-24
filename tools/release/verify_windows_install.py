"""Validate a clean Windows install, update, migration and rollback."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import zipfile

from package import verify
from smoke import smoke
from worker_smoke import worker_smoke


def install(script, root, archive=None, state=None):
    command = ["pwsh", "-NoProfile", "-File", script, "-InstallRoot", root]
    if state:
        command.extend(("-StateRoot", state))
    if archive is None:
        command.append("-Rollback")
    else:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        command.extend(("-Package", archive, "-TrustedSha256", digest))
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

        first = install(installer, program, previous, state)
        old = program / "versions" / first
        smoke(old)
        call(old / "synapse-backend.exe", state, workspace,
             {"type": "memory_put", "scope": "project:release", "key": "release-check",
              "kind": "fact", "content": "preserve", "expected_revision": 0,
              "provenance": {"source_type": "human", "source_id": "release-test",
                             "evidence": "Disposable migration fixture"}, "status": "active"})
        db = state / "core.sqlite3"
        old_schema = 15 if "format" not in verify(previous) else verify(previous)["compatibility"]["storage_max"]
        with closing(sqlite3.connect(db)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (old_schema,)

        maintenance = root / "synapse-maintenance.exe"
        with zipfile.ZipFile(candidate) as package:
            maintenance.write_bytes(package.read("synapse-maintenance.exe"))
        configuration = root / "configuration"
        configuration.mkdir()
        (configuration / "native-toolchain.json").write_text("{}")
        backup = root / "pre-update.backup"
        subprocess.run([maintenance, "backup", "--state-dir", state, "--output", backup,
                        "--config-root", configuration], check=True, capture_output=True, timeout=30)
        assert backup.is_file()

        second = install(installer, program, candidate, state)
        assert first != second
        upgraded = program / "versions" / second
        smoke(upgraded)
        worker_smoke(upgraded)
        subprocess.run(
            ["pwsh", "-NoProfile", "-File", upgraded / "start-windows.ps1", "-Verify",
             "-InstallRoot", program, "-StateRoot", state, "-Workspace", workspace,
             "-ConfigRoot", configuration],
            check=True, timeout=180,
            env={key:value for key,value in os.environ.items() if not key.startswith("SYNAPSE_") and key not in ("PYTHONPATH","PYTHONHOME")},
        )
        call(upgraded / "synapse-backend.exe", state, workspace, {"type": "capabilities_list"})
        with closing(sqlite3.connect(db)) as connection, connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (verify(candidate)["compatibility"]["storage_max"],)
            assert connection.execute("SELECT content FROM memory WHERE key='release-check'").fetchone() == ("preserve",)
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        new_schema = verify(candidate)["compatibility"]["storage_max"]
        if old_schema < new_schema:
            rejected = subprocess.run(["pwsh", "-NoProfile", "-File", installer, "-InstallRoot", program,
                                       "-StateRoot", state, "-Rollback"], capture_output=True, timeout=30)
            assert rejected.returncode != 0
            assert json.loads((program / "active.json").read_text())["current"] == second
            restored = root / "restored-state"
            restored_config = root / "restored-config"
            subprocess.run([maintenance, "restore", "--archive", backup, "--state-dir", restored,
                            "--config-root", restored_config], check=True, capture_output=True, timeout=30)
            with closing(sqlite3.connect(restored / "core.sqlite3")) as connection:
                assert connection.execute("PRAGMA user_version").fetchone() == (old_schema,)
                assert connection.execute("SELECT content FROM memory WHERE key='release-check'").fetchone() == ("preserve",)
            assert json.loads((restored_config / "native-toolchain.json").read_text()) == {}
            assert install(installer, program, state=restored) == first
            call(old / "synapse-backend.exe", restored, workspace, {"type": "capabilities_list"})
            rollback = "downgrade_rejected_then_backup_restore_rollback"

        else:
            assert install(installer, program, state=state) == first
            call(old / "synapse-backend.exe", state, workspace, {"type": "capabilities_list"})
            rollback = "compatible_program_rollback"
        print(json.dumps({"clean_install": first, "update": second, "migrated_schema": new_schema,
                          "candidate_sha256":hashlib.sha256(candidate.read_bytes()).hexdigest(),
                          "previous_fixture_sha256":hashlib.sha256(previous.read_bytes()).hexdigest(),
                          "installed_core_sha256":hashlib.sha256((upgraded/'synapse-backend.exe').read_bytes()).hexdigest(),
                          "installed_checker_sha256":hashlib.sha256((upgraded/'check-runtime/runtime/python.exe').read_bytes()).hexdigest(),
                          "platform":"windows","bundled_worker":True,"bundled_lpac_json_mission":True,"clean_configuration":True,
                          "data_preserved": True, "program_rollback": rollback, "tamper_rejected": True}))


if __name__ == "__main__":
    main()
