"""Bounded, binary-safe stdout/stderr capture for the concrete Windows driver."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO


class WindowsOutputStream(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


class WindowsOutputState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CAPTURING = "capturing"
    EOF = "eof"
    TRUNCATED = "truncated"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    FINALIZED = "finalized"


class WindowsOutputDecodingStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    VALID_UTF8 = "valid_utf8"
    INVALID_UTF8 = "invalid_utf8"


@dataclass(frozen=True, slots=True)
class WindowsOutputLimits:
    stdout_bytes: int = 1_048_576
    stderr_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if self.stdout_bytes < 0 or self.stderr_bytes < 0:
            raise ValueError("output_limit_invalid")


@dataclass(frozen=True, slots=True)
class WindowsCapturedOutputV1:
    stream: WindowsOutputStream
    retained_bytes: bytes
    bytes_retained: int
    bytes_observed: int
    configured_limit: int
    truncated: bool
    retained_checksum: str
    capture_fingerprint: str
    decoding_status: WindowsOutputDecodingStatus
    state: WindowsOutputState
    diagnostics: tuple[str, ...] = ()

    def decode_utf8(self) -> str | None:
        if self.decoding_status is WindowsOutputDecodingStatus.INVALID_UTF8:
            return None
        return self.retained_bytes.decode("utf-8")


class WindowsOutputReader:
    """Drain one byte stream fully while retaining at most its configured limit."""

    def __init__(self, stream: WindowsOutputStream, source: BinaryIO, limit: int) -> None:
        if limit < 0:
            raise ValueError("output_limit_invalid")
        self._stream = stream
        self._source = source
        self._limit = limit
        self._retained = bytearray()
        self._observed = 0
        self._state = WindowsOutputState.NOT_CONFIGURED
        self._diagnostics: tuple[str, ...] = ()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._lock = threading.Lock()

    def start(self) -> bool:
        if self._thread is not None:
            return True
        self._state = WindowsOutputState.CAPTURING
        try:
            self._thread = threading.Thread(
                target=self._drain,
                name=f"sandbox-{self._stream.value}-reader",
                daemon=True,
            )
            self._thread.start()
        except RuntimeError:
            self._state = WindowsOutputState.FAILED
            self._diagnostics = ("reader_startup_failed",)
            return False
        return True

    def _drain(self) -> None:
        try:
            while True:
                chunk = self._source.read(65_536)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise OSError("non_binary_pipe")
                with self._lock:
                    self._observed += len(chunk)
                    remaining = self._limit - len(self._retained)
                    if remaining > 0:
                        self._retained.extend(chunk[:remaining])
            self._state = (
                WindowsOutputState.TRUNCATED
                if self._observed > self._limit
                else WindowsOutputState.EOF
            )
        except OSError:
            self._state = WindowsOutputState.FAILED
            self._diagnostics = ("read_failed",)

    def finalize(self, timeout_seconds: float | None = None) -> WindowsCapturedOutputV1:
        thread = self._thread
        if thread is None:
            return self._snapshot(WindowsOutputState.FAILED, ("reader_not_started",))
        thread.join(timeout_seconds)
        if thread.is_alive():
            return self._snapshot(WindowsOutputState.INCOMPLETE, ("output_incomplete",))
        state = self._state
        if state in {WindowsOutputState.EOF, WindowsOutputState.TRUNCATED}:
            state = WindowsOutputState.FINALIZED
        return self._snapshot(state, self._diagnostics)

    def close(self) -> bool:
        if self._closed:
            return True
        try:
            self._source.close()
        except OSError:
            return False
        self._closed = True
        return True

    def _snapshot(
        self, state: WindowsOutputState, diagnostics: tuple[str, ...]
    ) -> WindowsCapturedOutputV1:
        with self._lock:
            retained = bytes(self._retained)
            observed = self._observed
        try:
            retained.decode("utf-8")
            decoding = WindowsOutputDecodingStatus.VALID_UTF8
        except UnicodeDecodeError:
            decoding = WindowsOutputDecodingStatus.INVALID_UTF8
        retained_checksum = hashlib.sha256(retained).hexdigest()
        fingerprint_payload = json.dumps(
            {
                "bytes_observed": observed,
                "bytes_retained": len(retained),
                "configured_limit": self._limit,
                "decoding_status": decoding.value,
                "diagnostics": diagnostics,
                "retained_checksum": retained_checksum,
                "state": state.value,
                "stream": self._stream.value,
                "truncated": observed > self._limit,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return WindowsCapturedOutputV1(
            self._stream,
            retained,
            len(retained),
            observed,
            self._limit,
            observed > self._limit,
            retained_checksum,
            hashlib.sha256(fingerprint_payload).hexdigest(),
            decoding,
            state,
            diagnostics,
        )


@dataclass(slots=True)
class WindowsOutputCapture:
    stdout: WindowsOutputReader | None = None
    stderr: WindowsOutputReader | None = None
    drains: tuple[WindowsOutputReader, ...] = ()
    _finalized: bool = False

    def start(self) -> bool:
        readers = tuple(item for item in (self.stdout, self.stderr) if item is not None) + self.drains
        started = tuple(reader.start() for reader in readers)
        return bool(readers) and all(started)

    def finalize(
        self, timeout_seconds: float | None = None
    ) -> tuple[WindowsCapturedOutputV1, ...]:
        results = tuple(
            reader.finalize(timeout_seconds)
            for reader in (self.stdout, self.stderr)
            if reader is not None
        )
        self._finalized = all(
            item.state not in {WindowsOutputState.CAPTURING, WindowsOutputState.INCOMPLETE}
            for item in results
        )
        return results

    def close(self) -> bool:
        return all(
            reader.close()
            for reader in (self.stdout, self.stderr, *self.drains)
            if reader is not None
        )

    @property
    def finalized(self) -> bool:
        return self._finalized
