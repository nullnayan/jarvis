# FILE: backend/cloud/cloud_bridge.py
# Real-time WebSocket bridge between Jarvis.bat (main.py) and Azure Cloud Gateway.
# Allows the phone app to control the PC directly via Jarvis.bat without needing a separate background agent.

import asyncio
import json
import os
import platform
import socket
import sys
import time
import websockets
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import get_logger
from security.transport import gateway_websocket_url
from pc_agent.dispatcher import execute_local_task
from llm.tools import TOOL_HANDLERS

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass

CLOUD_HOST = os.environ.get("CLOUD_HOST", "127.0.0.1")
CLOUD_PORT = int(os.environ.get("CLOUD_PORT", "8765"))
JARVIS_AUTH_TOKEN = os.environ.get("JARVIS_AUTH_TOKEN", "")
CLOUD_WS_URL = os.environ.get(
    "CLOUD_WS_URL",
    gateway_websocket_url(CLOUD_HOST, CLOUD_PORT, JARVIS_AUTH_TOKEN)
)

_log = get_logger(__name__)
print = _log.info

# Lazy-loaded Brain instance for processing complex commands
_brain = None

def _get_brain():
    global _brain
    if _brain is None:
        from llm.brain import Brain
        _brain = Brain()
        print("[CloudBridge] Initialized local Jarvis Brain for phone command processing")
    return _brain


class CloudBridge:
    """Connects Jarvis.bat (main.py) directly to Cloud Gateway as the PC agent."""

    def __init__(self, ws_url: str = CLOUD_WS_URL, source_name: str = "Jarvis.bat"):
        self.ws_url = ws_url
        self.source_name = source_name
        self.is_running = True
        self.reconnect_delay = 2.0
        self.ws = None

    def _get_device_meta(self) -> dict:
        return {
            "name": f"Windows PC ({self.source_name})",
            "hostname": socket.gethostname(),
            "os": f"Windows {platform.version()}",
            "machine": platform.machine(),
            "connected_at": time.time(),
        }

    async def start(self):
        """Persistent connection loop to the Cloud Gateway."""
        from security.transport import require_secure_gateway
        if os.environ.get("CLOUD_ENABLED", "false").lower() not in {"true", "1", "yes"}:
            print("[CloudBridge] Disabled until secure cloud configuration is enabled.")
            return
        if len(JARVIS_AUTH_TOKEN) < 32:
            raise RuntimeError("Configure JARVIS_AUTH_TOKEN before enabling the cloud bridge.")
        require_secure_gateway(self.ws_url)
        print(f"[CloudBridge] Starting cloud link for {self.source_name}...")
        print(f"[CloudBridge] Target Cloud Gateway: {self.ws_url.split('?')[0]}")

        while self.is_running:
            try:
                print(f"[CloudBridge] Connecting to Cloud Jarvis at {CLOUD_HOST}:{CLOUD_PORT}...")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    self.ws = ws
                    print(f"[CloudBridge] ✓ Connected to Cloud Jarvis! ({self.source_name} is now active PC handler)")
                    self.reconnect_delay = 2.0

                    # Send device registration
                    meta_payload = {
                        "type": "device_info",
                        "device": "pc",
                        "meta": self._get_device_meta(),
                    }
                    await ws.send(json.dumps(meta_payload))

                    # Start periodic keepalive
                    ping_task = asyncio.create_task(self._keepalive_ping(ws))

                    try:
                        async for raw_message in ws:
                            await self._handle_message(ws, raw_message)
                    finally:
                        ping_task.cancel()
                        self.ws = None

            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK):
                print(f"[CloudBridge] Cloud link disconnected. Reconnecting in {self.reconnect_delay:.1f}s...")
            except Exception as e:
                print(f"[CloudBridge] Cloud connection error: {e}. Reconnecting in {self.reconnect_delay:.1f}s...")

            await asyncio.sleep(self.reconnect_delay)
            self.reconnect_delay = min(self.reconnect_delay * 1.5, 30.0)

    async def _keepalive_ping(self, ws):
        while True:
            await asyncio.sleep(15.0)
            try:
                await ws.send(json.dumps({"type": "ping"}))
            except Exception:
                break

    async def _handle_message(self, ws, raw_message: str):
        try:
            msg = json.loads(raw_message)
        except Exception:
            return

        msg_type = msg.get("type")

        if msg_type == "connected":
            print(f"[CloudBridge] Cloud confirmed PC registration (role={msg.get('role')})")
            return

        if msg_type == "pong":
            return

        if msg_type == "execute_task":
            task_id = msg.get("task_id", "")
            action = msg.get("action", "")
            params = msg.get("params", {})
            original_text = params.get("_original_text", "")

            # Prominently print in the Jarvis.bat console
            print("=" * 60)
            print(f"  [PHONE ➜ PC] Command: {original_text or action}")
            print("=" * 60)

            # PRIMARY: Use the full Jarvis Brain for ALL commands
            # This gives the phone the EXACT same capabilities as speaking to Jarvis on PC
            if original_text:
                try:
                    success, message = await self._process_with_brain(original_text)
                except Exception as e:
                    print(f"  [PHONE ➜ PC] Brain error: {e}. Falling back to dispatcher...")
                    # Fallback to dispatcher only if brain fails
                    loop = asyncio.get_running_loop()
                    success, message = await loop.run_in_executor(
                        None, execute_local_task, action, params
                    )
            else:
                # No original text (shouldn't happen, but handle gracefully)
                loop = asyncio.get_running_loop()
                success, message = await loop.run_in_executor(
                    None, execute_local_task, action, params
                )

            print(f"  [PHONE ➜ PC] Result: {'✓' if success else '✗'} {message[:200]}")
            print("=" * 60)
            print("=" * 60)

            # Reply back to phone (PC does NOT speak — phone handles output)
            result_payload = {
                "type": "task_result",
                "task_id": task_id,
                "action": action,
                "success": success,
                "message": message,
                "spoken_on_pc": False,
                "completed_at": time.time(),
            }
            await ws.send(json.dumps(result_payload))

    async def _process_with_brain(self, text: str) -> tuple:
        """Use the full Jarvis Brain to process any command — same as speaking to Jarvis on PC."""
        brain = _get_brain()
        result = await brain.think(text)

        tool_name = result.get("tool")
        params = result.get("params", {})
        response = result.get("response", "")

        # If no tool needed (chat/search response), return the brain's response directly
        if not tool_name or tool_name == "none":
            return True, response or "I processed that, boss."

        # Execute the tool using the same TOOL_HANDLERS as the pipeline
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return True, response or f"I understood the command, but the tool '{tool_name}' is not available."

        # Security gate: Block Level 4 destructive actions via remote bridge
        if tool_name == "system_power" and params.get("action") in ("shutdown", "restart"):
            return False, "Shutdown and restart require the Jarvis desktop application for password verification, boss."

        print(f"  [PHONE ➜ PC] Brain selected tool: {tool_name} with params: {params}")

        try:
            loop = asyncio.get_running_loop()
            tool_result = await loop.run_in_executor(None, handler, params)
            tool_result_str = str(tool_result) if tool_result else ""

            # For some tools, the tool result IS the response (doc_reader, web_search, etc.)
            # For others, the brain's response is better (open_app, volume, etc.)
            final_msg = tool_result_str if (tool_result_str and len(tool_result_str) > len(response)) else (response or tool_result_str or "Done, boss.")
            try:
                from security.audit_log import log_action
                log_action({
                    "source": "phone_remote",
                    "tool": tool_name,
                    "params": params,
                    "permission_result": "EXECUTED",
                    "result_summary": final_msg[:200],
                })
            except Exception:
                pass
            return True, final_msg
        except Exception as e:
            print(f"  [PHONE ➜ PC] Tool execution error ({tool_name}): {e}")
            return False, f"Failed to execute {tool_name}: {str(e)}"

    def stop(self):
        self.is_running = False
