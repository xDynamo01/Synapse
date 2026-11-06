import asyncio
from contextlib import aclosing
import json
from aiohttp import web, WSMsgType
from server.lifecycle import MAX_FRAME_BYTES, OPEN_TIMEOUT, VERSION, failure


async def start(lifecycle):
    def authorization(request):
        values = request.headers.getall("Authorization", [])
        return values[0] if len(values) == 1 else ""

    async def unary(request):
        # Authentication is checked before parsing untrusted HTTP JSON.
        auth = authorization(request)
        auth_error = lifecycle.check({"contract_version": VERSION}, auth)
        if auth_error:
            return web.json_response(auth_error)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("object required")
        except ValueError:
            return web.json_response(failure("INVALID_ARGUMENT", "JSON object required"))
        return web.json_response(lifecycle.call(request.match_info["method"], body, auth))

    async def subscribe(request):
        ws = web.WebSocketResponse(max_msg_size=MAX_FRAME_BYTES)
        await ws.prepare(request)

        async def receive():
            message = await ws.receive()
            if message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                return None
            if message.type != WSMsgType.TEXT:
                return {}
            try:
                body = json.loads(message.data)
                return body if isinstance(body, dict) else {}
            except ValueError:
                return {}

        try:
            try:
                first = await asyncio.wait_for(receive(), OPEN_TIMEOUT)
            except TimeoutError:
                await asyncio.wait_for(ws.send_json(
                    failure("INVALID_ARGUMENT", "Opening frame deadline exceeded")), 1)
                return ws
            if first is not None:
                async with aclosing(lifecycle.events(first, authorization(request), receive)) as events:
                    async for event in events:
                        await asyncio.wait_for(ws.send_json(event), 1)
        except (TimeoutError, ConnectionError):
            pass
        finally:
            await ws.close()
        return ws

    app = web.Application(client_max_size=MAX_FRAME_BYTES)
    app.router.add_post("/v1/{method:GetStatus|SubmitCommand|CancelCommand}", unary)
    app.router.add_get("/v1/SubscribeEvents", subscribe)
    runner = web.AppRunner(app, access_log=None, handler_cancellation=True, shutdown_timeout=1)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return port, runner.cleanup
