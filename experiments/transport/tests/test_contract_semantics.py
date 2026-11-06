"""The exact same lifecycle expectations are sent over each real candidate."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CANDIDATES = [os.environ["TRANSPORT"]] if "TRANSPORT" in os.environ else ["grpc", "http"]


@pytest.mark.parametrize("candidate", CANDIDATES)
def test_lifecycle_restart_and_faults(candidate, tmp_path):
    from client.python_client import Client
    from tests.process_harness import Server

    async def check():
        async with Server(candidate, tmp_path / "journal.sqlite") as process:
            import psutil
            assert psutil.Process(process.runtime_pid).is_running()
            listening = psutil.Process(process.runtime_pid).net_connections(kind="inet")
            assert {(socket.laddr.ip, socket.laddr.port) for socket in listening
                    if socket.status == psutil.CONN_LISTEN} == {("127.0.0.1", process.port)}
            async with Client(candidate, process.port) as client:
                status = await client.call("GetStatus")
                assert status == {"healthy": True, "contract_version": "1.0", "last_event_id": "0", "command_count": 0}
                for method, payload in [
                    ("GetStatus", {}),
                    ("SubmitCommand", {"command_id": "unauthorized", "causation_id": "owner", "action": "hold"}),
                    ("CancelCommand", {"command_id": "one", "causation_id": "owner"}),
                ]:
                    assert (await client.call(method, payload, token="wrong"))["error"]["code"] == "UNAUTHENTICATED"
                    assert (await client.call(method, payload, version="2.0"))["error"]["code"] == "INCOMPATIBLE_VERSION"
                assert (await client.call("GetStatus", version="1.9"))["healthy"] is True
                assert (await client.call("GetStatus", version="garbage"))["error"]["code"] == "INVALID_ARGUMENT"
                request = {"command_id": "one", "causation_id": "owner", "action": "hold"}
                first = await client.call("SubmitCommand", request)
                assert first == {"state": "ACKNOWLEDGED", "event_id": "1", "command_id": "one",
                                 "causation_id": "owner", "contract_version": "1.0", "duplicate": False}
                duplicate = await client.call("SubmitCommand", request)
                assert duplicate["duplicate"] is True and duplicate["event_id"] == "1"
                conflict = await client.call("SubmitCommand", {**request, "action": "other"})
                assert conflict["error"]["code"] == "COMMAND_CONFLICT"
                assert (await client.call("SubmitCommand", {**request, "command_id": "bad", "action": "shell"}))["error"]["code"] == "INVALID_ARGUMENT"
                async with client.events("0") as stream:
                    event = await stream.next()
                    assert event == first
                    second_request = {**request, "command_id": "two"}
                    second = await client.call("SubmitCommand", second_request)
                    assert second["event_id"] == "2"
                    # Kill with a live subscription after commit, before the client consumes event 2.
                    runtime_pid = process.runtime_pid
                    await process.kill()
                    assert not psutil.pid_exists(runtime_pid)
            await process.start()
            async with Client(candidate, process.port) as client:
                duplicate = await client.call("SubmitCommand", request)
                assert duplicate["duplicate"] is True and duplicate["event_id"] == "1"
                assert (await client.call("SubmitCommand", second_request)) == {**second, "duplicate": True}
                status = await client.call("GetStatus")
                assert status["command_count"] == 2 and status["last_event_id"] == "2"
                cancelled = await client.call("CancelCommand", {"command_id": "one", "causation_id": "cancel-owner"})
                assert cancelled["state"] == "CANCELLED" and cancelled["event_id"] == "3"
                repeated = await client.call("CancelCommand", {"command_id": "one", "causation_id": "cancel-owner"})
                assert repeated["duplicate"] and repeated["event_id"] == "3"
                async with client.events("1") as stream:
                    events = [await stream.next(), await stream.next()]
                    assert events == [second, cancelled]
                assert (await client.call("CancelCommand", {"command_id": "missing", "causation_id": "owner"}))["error"]["code"] == "NOT_FOUND"
                for kwargs, code in [({"token": "wrong"}, "UNAUTHENTICATED"), ({"version": "2.0"}, "INCOMPATIBLE_VERSION")]:
                    async with client.events("0", **kwargs) as stream:
                        assert (await stream.next())["error"]["code"] == code
                async with client.events("999") as stream:
                    assert (await stream.next())["error"]["code"] == "INVALID_CURSOR"
                async with client.events("0", acknowledge=False) as stream:
                    assert (await stream.next())["event_id"] == "1"
                    blocked = await stream.next()
                    assert blocked == {"contract_version": "1.0", "error": {
                        "code": "BACKPRESSURE", "message": "Event acknowledgement deadline exceeded",
                        "retryable": True, "last_event_id": "0",
                    }}
                # Stalled consumer does not prevent unary work or lose the journal.
                assert (await client.call("GetStatus"))["last_event_id"] == "3"
                async with client.events("0") as stream:
                    assert [(await stream.next())["event_id"] for _ in range(3)] == ["1", "2", "3"]

    assert sys.version_info[:3] == (3, 14, 10)
    assert sys._is_gil_enabled()
    asyncio.run(check())


@pytest.mark.parametrize("candidate", CANDIDATES)
def test_active_subscription_remains_open_past_ten_seconds(candidate, tmp_path):
    from client.python_client import Client
    from tests.process_harness import Server

    async def check():
        async with Server(candidate, tmp_path / "journal.sqlite") as process:
            async with Client(candidate, process.port) as client:
                async with client.events("0") as stream:
                    started = asyncio.get_running_loop().time()
                    for sequence in range(1, 13):
                        if sequence > 1:
                            await asyncio.sleep(1)
                        event = await client.call("SubmitCommand", {
                            "command_id": f"active-{sequence}", "causation_id": "owner", "action": "hold",
                        })
                        assert event["event_id"] == str(sequence)
                        assert await stream.next() == event
                    assert asyncio.get_running_loop().time() - started > 10

    asyncio.run(check())


@pytest.mark.parametrize("candidate", CANDIDATES)
def test_admission_bound_concurrent_duplicates_and_bad_ack(candidate, tmp_path):
    from client.python_client import Client
    from tests.process_harness import Server

    async def check():
        async with Server(candidate, tmp_path / "journal.sqlite") as process:
            async with Client(candidate, process.port) as client:
                payload = {"command_id": "racing", "causation_id": "owner", "action": "hold"}
                replies = await asyncio.gather(*[client.call("SubmitCommand", payload) for _ in range(8)])
                assert sum(not reply.get("duplicate", False) for reply in replies) == 1
                assert {reply["event_id"] for reply in replies} == {"1"}
                for cursor in ("-1", "01", "nonsense"):
                    async with client.events(cursor) as stream:
                        assert (await stream.next())["error"]["code"] == "INVALID_CURSOR"
                async with client.events("0", acknowledge=False) as stream:
                    assert (await stream.next())["event_id"] == "1"
                    await stream.send({"contract_version": "1.0", "ack_event_id": "99"})
                    assert (await stream.next())["error"]["code"] == "INVALID_ACK"
                async with client.events("0", acknowledge=False) as stream:
                    assert (await stream.next())["event_id"] == "1"
                    await stream.send({"contract_version": "1.0", "ack_event_id": "1", "after_event_id": "0"})
                    assert (await stream.next())["error"]["code"] == "INVALID_ACK"
                for index in range(127):
                    reply = await client.call("SubmitCommand", {**payload, "command_id": f"limit-{index}"})
                    assert reply["state"] == "ACKNOWLEDGED"
                rejected = await client.call("SubmitCommand", {**payload, "command_id": "overflow"})
                assert rejected["error"]["code"] == "RESOURCE_EXHAUSTED"
                assert (await client.call("GetStatus"))["command_count"] == 128
                # Read/cancel/retry remain available at capacity; rejection has no event.
                assert (await client.call("SubmitCommand", payload))["duplicate"]
                assert (await client.call("CancelCommand", {"command_id": "racing", "causation_id": "owner"}))["event_id"] == "129"
                assert (await client.call("GetStatus"))["last_event_id"] == "129"
    asyncio.run(check())
