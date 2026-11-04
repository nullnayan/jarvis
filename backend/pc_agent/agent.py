# FILE: backend/pc_agent/agent.py
# Lightweight Windows PC Agent for Jarvis.
# Connects to Cloud Jarvis on Azure VM and executes desktop tasks.

import asyncio
import json
import os
import platform
import socket
import sys
import time
import websockets

# Ensure backend path is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import get_logger
from security.transport import gateway_websocket_url
from pc_agent.dispatcher import execute_local_task

from pathlib import Path
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass

# Read environment configuration or use cloud defaults
CLOUD_HOST = os.environ.get("CLOUD_HOST", "127.0.0.1")
CLOUD_PORT = int(os.environ.get("CLOUD_PORT", "8765"))
JARVIS_AUTH_TOKEN = os.environ.get("JARVIS_AUTH_TOKEN", "")
CLOUD_WS_URL = os.environ.get(
    "CLOUD_WS_URL",
    gateway_websocket_url(CLOUD_HOST, CLOUD_PORT, JARVIS_AUTH_TOKEN)
)

_log = get_logger(__name__)
print = _log.info


class PCAgent:
    """Persistent agent running on Windows that listens for cloud commands."""

    def __init__(self, ws_url: str = CLOUD_WS_URL):
        self.ws_url = ws_url
        self.is_running = True
        self.reconnect_delay = 2.0  # seconds

    def _get_device_meta(self) -> dict:
        return {
            "hostname": socket.gethostname(),
            "os": f"Windows {platform.version()}",
            "machine": platform.machine(),
            "connected_at": time.time(),
        }

    async def start(self):
        """Runs the main agent loop with automatic reconnect.
        Stands by automatically if jarvis.bat is running.
        """
        from security.transport import require_secure_gateway
        if os.environ.get("CLOUD_ENABLED", "false").lower() not in {"true", "1", "yes"}:
            print("[PCAgent] Disabled until secure cloud configuration is enabled.")
            return
        if len(JARVIS_AUTH_TOKEN) < 32:
            raise RuntimeError("Configure JARVIS_AUTH_TOKEN before enabling the PC agent.")
        require_secure_gateway(self.ws_url)
        from pc_agent.voice import is_jarvis_bat_running

        print(f"[PCAgent] Starting Jarvis Windows Agent...")
        print(f"[PCAgent] Target Cloud Gateway: {self.ws_url.split('?')[0]}")

        while self.is_running:
            # If jarvis.bat is active, it handles cloud tasks directly via CloudBridge
            if is_jarvis_bat_running():
                print("[PCAgent] jarvis.bat is running. PC Agent standing by (jarvis.bat is active)...")
                while is_jarvis_bat_running() and self.is_running:
                    await asyncio.sleep(4.0)
                if not self.is_running:
                    break
                print("[PCAgent] jarvis.bat closed. PC Agent resuming cloud connection...")

            try:
                print("[PCAgent] Connecting to Cloud Jarvis...")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    print("[PCAgent] ✓ Connected to Cloud Jarvis successfully!")
                    self.reconnect_delay = 2.0  # Reset delay on successful connection

                    # Send handshake device metadata
                    meta_payload = {
                        "type": "device_info",
                        "device": "pc",
                        "meta": self._get_device_meta(),
                    }
                    await ws.send(json.dumps(meta_payload))

                    # Start periodic ping task
                    ping_task = asyncio.create_task(self._keepalive_ping(ws))

                    try:
                        # Main message receiver loop
                        async for raw_message in ws:
                            # If jarvis.bat started up, yield connection to it
                            if is_jarvis_bat_running():
                                print("[PCAgent] jarvis.bat detected! Yielding cloud connection to jarvis.bat...")
                                break
                            await self._handle_message(ws, raw_message)
                    finally:
                        ping_task.cancel()

            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK):
                print(f"[PCAgent] Connection closed. Reconnecting in {self.reconnect_delay:.1f}s...")
            except Exception as e:
                print(f"[PCAgent] Connection error: {e}. Reconnecting in {self.reconnect_delay:.1f}s...")

            await asyncio.sleep(self.reconnect_delay)
            self.reconnect_delay = min(self.reconnect_delay * 1.5, 30.0)

    async def _keepalive_ping(self, ws):
        """Sends periodic heartbeats to maintain cloud connection."""
        while True:
            await asyncio.sleep(15.0)
            try:
                await ws.send(json.dumps({"type": "ping"}))
            except Exception:
                break

    async def _handle_message(self, ws, raw_message: str):
        """Processes incoming messages from Cloud Jarvis."""
        try:
            msg = json.loads(raw_message)
        except Exception:
            return

        msg_type = msg.get("type")

        # Connection Ack
        if msg_type == "connected":
            print(f"[PCAgent] Cloud confirmed registration (role={msg.get('role')})")
            return

        # Pong Ack
        if msg_type == "pong":
            return

        # Execute Task Requested by Cloud Brain
        if msg_type == "execute_task":
            task_id = msg.get("task_id", "")
            action = msg.get("action", "")
            params = msg.get("params", {})

            print(f"[PCAgent] ➜ Received cloud task [{task_id[:8]}]: {action} (params={params})")

            # Run task in thread pool so async loop is never blocked
            loop = asyncio.get_running_loop()
            success, message = await loop.run_in_executor(
                None, execute_local_task, action, params
            )

            # NOTE: Reply routing rule:
            # Commands from phone must reply on phone. PC Agent executes silently without speaking.
            spoken_on_pc = False

            print(f"[PCAgent] ✓ Task completed [{task_id[:8]}]: success={success}, msg='{message}'")

            # Send result back to Cloud Jarvis
            result_payload = {
                "type": "task_result",
                "task_id": task_id,
                "action": action,
                "success": success,
                "message": message,
                "spoken_on_pc": spoken_on_pc,
                "completed_at": time.time(),
            }
            await ws.send(json.dumps(result_payload))


def main():
    agent = PCAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\n[PCAgent] Stopped by user.")


if __name__ == "__main__":
    main()
