import asyncio
from contextlib import aclosing
import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
from synapse.foundation.v1 import lifecycle_pb2 as pb, lifecycle_pb2_grpc as rpc
from server.lifecycle import MAX_FRAME_BYTES, OPEN_TIMEOUT, failure


def as_dict(message):
    return MessageToDict(message, preserving_proto_field_name=True)


class Service(rpc.LifecycleServicer):
    def __init__(self, lifecycle):
        self.lifecycle = lifecycle

    def auth(self, context):
        values = [value for key, value in context.invocation_metadata() if key == "authorization"]
        return values[0] if len(values) == 1 else ""

    async def GetStatus(self, request, context):
        return self.unary("GetStatus", request, context)

    async def SubmitCommand(self, request, context):
        return self.unary("SubmitCommand", request, context)

    async def CancelCommand(self, request, context):
        return self.unary("CancelCommand", request, context)

    def unary(self, method, request, context):
        return ParseDict(self.lifecycle.call(method, as_dict(request), self.auth(context)), pb.Envelope())

    async def SubscribeEvents(self, requests, context):
        async def receive():
            try:
                return as_dict(await anext(requests))
            except StopAsyncIteration:
                return None
        try:
            first = await asyncio.wait_for(receive(), OPEN_TIMEOUT)
        except TimeoutError:
            yield ParseDict(failure("INVALID_ARGUMENT", "Opening frame deadline exceeded"), pb.Envelope())
            return
        if first is not None:
            async with aclosing(self.lifecycle.events(first, self.auth(context), receive)) as events:
                async for event in events:
                    yield ParseDict(event, pb.Envelope())


async def start(lifecycle):
    server = grpc.aio.server(options=[("grpc.max_receive_message_length", MAX_FRAME_BYTES),
                                      ("grpc.max_send_message_length", MAX_FRAME_BYTES)])
    rpc.add_LifecycleServicer_to_server(Service(lifecycle), server)
    port = server.add_insecure_port("127.0.0.1:0")
    if not port:
        raise RuntimeError("Loopback bind failed")
    await server.start()
    return port, lambda: server.stop(0)
