"""Transport-neutral, effect-free admission/cancellation journal for this spike.

There is no mission execution or authority implementation. A token authenticates
only the synthetic test owner; the only accepted action is a held test command.
"""
import asyncio
from contextlib import suppress
import hmac
import re
import sqlite3

VERSION = "1.0"
TEST_TOKEN = "synapse-transport-spike-test-only"
ACK_TIMEOUT = 0.5
OPEN_TIMEOUT = 2
MAX_COMMANDS = 128
MAX_FRAME_BYTES = 4096


def failure(code, message, retryable=False, cursor="0"):
    return {"contract_version": VERSION, "error": {
        "code": code, "message": message, "retryable": retryable, "last_event_id": cursor,
    }}


class Lifecycle:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS commands (
            command_id TEXT PRIMARY KEY, causation_id TEXT, action TEXT,
            state TEXT, event_id INTEGER, ack_id INTEGER);
          CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, command_id TEXT,
            causation_id TEXT, state TEXT);
        """)

    def close(self):
        self.db.close()

    def last_id(self):
        return self.db.execute("SELECT COALESCE(MAX(event_id), 0) FROM events").fetchone()[0]

    def check(self, request, authorization):
        if not hmac.compare_digest(authorization.encode("utf-8", errors="surrogatepass"),
                                   f"Bearer {TEST_TOKEN}".encode("ascii")):
            return failure("UNAUTHENTICATED", "Test-owner authentication required")
        version = request.get("contract_version", "")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}", version):
            return failure("INVALID_ARGUMENT", "contract_version must be major.minor")
        if int(version.split(".")[0]) != 1:
            return failure("INCOMPATIBLE_VERSION", "Supported major contract version is 1")
        return None

    def envelope(self, row, duplicate=False):
        return {"contract_version": VERSION, "event_id": str(row["event_id"]),
                "command_id": row["command_id"], "causation_id": row["causation_id"],
                "state": row["state"], "duplicate": duplicate}

    def call(self, method, request, authorization):
        error = self.check(request, authorization)
        if error:
            return error
        if method == "GetStatus":
            return {"contract_version": VERSION, "healthy": True,
                    "last_event_id": str(self.last_id()),
                    "command_count": self.db.execute("SELECT COUNT(*) FROM commands").fetchone()[0]}
        for field in ("command_id", "causation_id"):
            if not isinstance(request.get(field), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request[field]):
                return failure("INVALID_ARGUMENT", f"Invalid {field}")
        command_id = request["command_id"]
        # No awaits inside a transaction: commands and events commit before ACK.
        with self.db:
            row = self.db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
            if method == "SubmitCommand":
                if row:
                    if row["action"] != request.get("action") or row["causation_id"] != request["causation_id"]:
                        return failure("COMMAND_CONFLICT", "command_id already has different immutable input")
                    original = self.db.execute("SELECT * FROM events WHERE event_id=?", (row["ack_id"],)).fetchone()
                    return self.envelope(original, True)
                if request.get("action") != "hold":
                    return failure("INVALID_ARGUMENT", "Only the effect-free hold action exists in this spike")
                count = self.db.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
                if count >= MAX_COMMANDS:
                    return failure("RESOURCE_EXHAUSTED", "Experiment journal command limit reached")
                event_id = self.db.execute(
                    "INSERT INTO events(command_id,causation_id,state) VALUES(?,?,'ACKNOWLEDGED')",
                    (command_id, request["causation_id"])).lastrowid
                self.db.execute("INSERT INTO commands VALUES(?,?,?,'ACKNOWLEDGED',?,?)",
                                (command_id, request["causation_id"], "hold", event_id, event_id))
            elif method == "CancelCommand":
                if not row:
                    return failure("NOT_FOUND", "Unknown command_id")
                if row["state"] == "CANCELLED":
                    event = self.db.execute("SELECT * FROM events WHERE event_id=?", (row["event_id"],)).fetchone()
                    return self.envelope(event, True)
                event_id = self.db.execute(
                    "INSERT INTO events(command_id,causation_id,state) VALUES(?,?,'CANCELLED')",
                    (command_id, request["causation_id"])).lastrowid
                self.db.execute("UPDATE commands SET state='CANCELLED',event_id=? WHERE command_id=?", (event_id, command_id))
            else:
                return failure("INVALID_ARGUMENT", "Unknown method")
            result = self.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return self.envelope(result)

    async def events(self, first, authorization, receive):
        error = self.check(first, authorization)
        if error:
            yield error
            return
        if first.get("ack_event_id", "") != "":
            yield failure("INVALID_ACK", "The opening frame cannot acknowledge an event")
            return
        cursor = first.get("after_event_id", "")
        if not isinstance(cursor, str) or not re.fullmatch(r"0|[1-9][0-9]{0,17}", cursor) or int(cursor) > self.last_id():
            yield failure("INVALID_CURSOR", "Cursor is outside this journal")
            return
        cursor = int(cursor)
        reader = asyncio.create_task(receive())
        try:
            while True:
                if reader.done():
                    frame = reader.result()
                    if frame is not None:
                        yield failure("INVALID_ACK", "No event awaits acknowledgement", cursor=str(cursor))
                    return
                row = self.db.execute("SELECT * FROM events WHERE event_id>? ORDER BY event_id LIMIT 1", (cursor,)).fetchone()
                if row is None:
                    await asyncio.wait({reader}, timeout=0.02)
                    continue
                yield self.envelope(row)
                try:
                    frame = await asyncio.wait_for(asyncio.shield(reader), ACK_TIMEOUT)
                except TimeoutError:
                    yield failure("BACKPRESSURE", "Event acknowledgement deadline exceeded", True, str(cursor))
                    return
                if frame is None:
                    return
                error = self.check(frame, authorization)
                if error:
                    yield error
                    return
                if frame.get("ack_event_id") != str(row["event_id"]) or frame.get("after_event_id", "") != "":
                    yield failure("INVALID_ACK", "Acknowledge exactly the outstanding event", cursor=str(cursor))
                    return
                cursor = row["event_id"]
                reader = asyncio.create_task(receive())
        finally:
            reader.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration, ConnectionError):
                await reader
