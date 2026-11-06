"""Compatibility evidence only: no model, audio, device, or product state."""

import importlib
import socket
import sys
import sysconfig

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original_connect = socket.socket.connect

    def connect_local(sock, address):
        # Windows asyncio creates its wakeup socketpair over numeric loopback.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        reject()

    def reject(*args, **kwargs):
        raise AssertionError("Network is forbidden in the compatibility probe")

    monkeypatch.setattr(socket.socket, "connect", connect_local)
    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")


@pytest.mark.parametrize(
    "module", ["anyio", "pydantic", "ctranslate2", "faster_whisper", "piper", "onnxruntime", "aiosqlite"]
)
def test_candidate_imports(module):
    assert importlib.import_module(module) is not None


def test_async_schema_sqlite_composition():
    import aiosqlite
    import anyio
    from pydantic import BaseModel, ConfigDict

    class Record(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        sequence: int
        text: str

    async def exercise():
        record = Record.model_validate_json('{"sequence":1,"text":"fixture"}')
        async with aiosqlite.connect(":memory:") as db:
            await db.execute("CREATE TABLE events (sequence INTEGER PRIMARY KEY, text TEXT NOT NULL)")
            await db.execute("INSERT INTO events VALUES (?, ?)", (record.sequence, record.text))
            await db.commit()
            async with db.execute("SELECT sequence, text FROM events") as cursor:
                assert await cursor.fetchall() == [(1, "fixture")]
        with anyio.move_on_after(0) as scope:
            await anyio.sleep_forever()
        assert scope.cancel_called

    anyio.run(exercise)


def test_schema_rejects_invalid_type_and_extra_fields():
    from pydantic import BaseModel, ConfigDict, ValidationError

    class Record(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        sequence: int

    for payload in ({"sequence": "1"}, {"sequence": 1, "authority": True}):
        with pytest.raises(ValidationError):
            Record.model_validate(payload)


def test_native_cpu_surfaces_without_loading_weights():
    import ctranslate2
    import onnxruntime
    from faster_whisper import WhisperModel
    from piper import PiperVoice

    assert "float32" in ctranslate2.get_supported_compute_types("cpu")
    assert "CPUExecutionProvider" in onnxruntime.get_available_providers()
    assert callable(WhisperModel)
    assert callable(PiperVoice.load)


def test_network_guard_is_active():
    with pytest.raises(AssertionError, match="Network is forbidden"):
        socket.create_connection(("192.0.2.1", 1))
    with socket.socket() as sock:
        with pytest.raises(AssertionError, match="Network is forbidden"):
            sock.connect(("192.0.2.1", 1))


def test_pinned_cpython_matrix():
    assert sys.version_info[:3] in {(3, 13, 18), (3, 14, 10)}
    assert sys.implementation.name == "cpython"
    assert not sysconfig.get_config_var("Py_GIL_DISABLED")
