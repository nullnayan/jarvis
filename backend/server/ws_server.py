# FILE: ws_server.py
# Hosts the local WebSocket bridge and broadcasts messages to connected Electron clients.
import asyncio
import inspect
import hmac
import ipaddress
import websockets
from config import WS_AUTH_TOKEN, WS_HOST, WS_PORT
from logger import get_logger
from server.messages import parse_message

_log = get_logger(__name__)
print = _log.info

class WebSocketServer:
    def __init__(self):
        self.clients = set()
        self.message_handler = None
        self.server = None
        # Holds in-flight dispatch tasks: asyncio keeps only weak refs to bare
        # tasks, so an unheld one can be garbage-collected mid-run.
        self._dispatch_tasks = set()

    def on_message(self, callback):
        self.message_handler = callback

    async def _dispatch(self, awaitable):
        # Holder so fire-and-forget commands survive GC and surface failures.
        task = asyncio.ensure_future(awaitable)
        self._dispatch_tasks.add(task)

        def _finished(done_task):
            self._dispatch_tasks.discard(task)
            if not done_task.cancelled() and done_task.exception():
                print(f"[WS] Command handler failed: {done_task.exception()}")

        task.add_done_callback(_finished)

    async def _handle(self, websocket):
        request = getattr(websocket, "request", None)
        headers = request.headers if request is not None else getattr(websocket, "request_headers", {})
        authorization = headers.get("Authorization", "")
        if not WS_AUTH_TOKEN or not hmac.compare_digest(authorization.encode(), f"Bearer {WS_AUTH_TOKEN}".encode()):
            await websocket.close(code=1008, reason="Authentication required")
            return
        self.clients.add(websocket)
        print("Electron connected")
        try:
            async for raw in websocket:
                if self.message_handler:
                    result = self.message_handler(parse_message(raw))
                    if inspect.isawaitable(result):
                        # Dispatch concurrently so long-running commands (chains,
                        # coding projects) never block the socket loop — otherwise
                        # cancel/mute/typed commands queue up and get lost.
                        await self._dispatch(result)
        finally:
            self.clients.discard(websocket)
            print("Electron disconnected")

    async def start(self):
        if WS_HOST != "localhost" and not ipaddress.ip_address(WS_HOST).is_loopback:
            raise ValueError("The desktop WebSocket must bind to loopback.")
        if len(WS_AUTH_TOKEN) < 32:
            raise RuntimeError("Launch through Electron or configure JARVIS_LOCAL_AUTH_TOKEN (32+ characters).")
        self.server = await websockets.serve(self._handle, WS_HOST, WS_PORT, origins=[None], max_size=1024 * 1024)
        print(f"WebSocket server listening on ws://{WS_HOST}:{WS_PORT}")

    async def send(self, message):
        stale = []
        for client in list(self.clients):
            try:
                await client.send(message)
            except websockets.ConnectionClosed:
                stale.append(client)
        self.clients.difference_update(stale)

    async def stop(self):
        pending = list(self._dispatch_tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._dispatch_tasks.clear()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
