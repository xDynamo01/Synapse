"""Test adapter only; reconnection is explicit and never resubmits commands."""
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generated/python"))
from server.lifecycle import TEST_TOKEN


class Client:
    def __init__(self, candidate, port):
        self.candidate, self.port = candidate, port

    async def __aenter__(self):
        if self.candidate == "grpc":
            import grpc
            from synapse.foundation.v1 import lifecycle_pb2_grpc as rpc
            self.connection = grpc.aio.insecure_channel(f"127.0.0.1:{self.port}", options=(
                ("grpc.enable_http_proxy", 0), ("grpc.enable_retries", 0),
            ))
            self.stub = rpc.LifecycleStub(self.connection)
        else:
            from aiohttp import ClientSession, ClientTimeout
            self.connection = ClientSession(timeout=ClientTimeout(total=3))
        return self

    async def __aexit__(self, *args):
        await self.connection.close()

    async def call(self, method, payload=None, token=TEST_TOKEN, version="1.0"):
        request = {"contract_version": version, **(payload or {})}
        if self.candidate == "grpc":
            from google.protobuf.json_format import ParseDict
            from synapse.foundation.v1 import lifecycle_pb2 as pb
            from server.grpc_server import as_dict
            cls = {"GetStatus": pb.StatusRequest, "SubmitCommand": pb.CommandRequest, "CancelCommand": pb.CancelRequest}[method]
            reply = await getattr(self.stub, method)(ParseDict(request, cls()),
                       metadata=(("authorization", f"Bearer {token}"),), timeout=3)
            return as_dict(reply)
        async with self.connection.post(f"http://127.0.0.1:{self.port}/v1/{method}", json=request,
                                        headers={"Authorization": f"Bearer {token}"}) as response:
            return await response.json()

    @asynccontextmanager
    async def events(self, cursor, acknowledge=True, token=TEST_TOKEN, version="1.0"):
        stream = Stream(self, acknowledge, version)
        try:
            await stream.open(cursor, token)
            yield stream
        finally:
            await stream.close()


class Stream:
    def __init__(self, client, acknowledge, version):
        self.client, self.acknowledge, self.version = client, acknowledge, version
        self.wire = None

    async def open(self, cursor, token):
        if self.client.candidate == "grpc":
            self.wire = self.client.stub.SubscribeEvents(metadata=(("authorization", f"Bearer {token}"),), timeout=10)
        else:
            self.wire = await self.client.connection.ws_connect(f"http://127.0.0.1:{self.client.port}/v1/SubscribeEvents",
                                                               headers={"Authorization": f"Bearer {token}"})
        await self.send({"contract_version": self.version, "after_event_id": cursor})

    async def send(self, frame):
        if self.client.candidate == "grpc":
            from synapse.foundation.v1 import lifecycle_pb2 as pb
            await self.wire.write(pb.SubscribeFrame(**frame))
        else:
            await self.wire.send_json(frame)

    async def next(self):
        if self.client.candidate == "grpc":
            import grpc
            from server.grpc_server import as_dict
            reply = await asyncio.wait_for(self.wire.read(), 3)
            if reply is grpc.aio.EOF:
                raise EOFError("Event stream ended")
            result = as_dict(reply)
        else:
            result = await asyncio.wait_for(self.wire.receive_json(), 3)
        if result.get("event_id") and self.acknowledge:
            await self.send({"contract_version": self.version, "ack_event_id": result["event_id"]})
        return result

    async def close(self):
        if self.wire is None:
            return
        if self.client.candidate == "grpc":
            self.wire.cancel()
        else:
            await self.wire.close()
