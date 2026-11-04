# FILE: backend/cloud/hub.py
# Real-time WebSocket connection manager and device dispatcher.
# Coordinates between Phone Companion App, PC Agent, and Cloud Brain.

import asyncio
import json
import time
import uuid
import hmac
from typing import Dict, Optional, Set
from fastapi import WebSocket

from cloud.config import JARVIS_AUTH_TOKEN


class DeviceHub:
    """Manages connected devices (PC, Phone, Thin Clients) and dispatches commands."""

    def __init__(self):
        self.pc_socket: Optional[WebSocket] = None
        self.pc_info: dict = {}
        self.phone_sockets: Set[WebSocket] = set()
        self.voice_sockets: Set[WebSocket] = set()
        self.pending_tasks: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def authenticate(self, token: str) -> bool:
        """Validates incoming client authentication token."""
        return bool(JARVIS_AUTH_TOKEN and isinstance(token, str) and token and
                    hmac.compare_digest(token.strip().encode(), JARVIS_AUTH_TOKEN.encode()))

    async def register(self, websocket: WebSocket, role: str, device_meta: Optional[dict] = None):
        """Registers an authenticated client based on its role."""
        async with self._lock:
            if role == "pc":
                # If a previous PC was connected, unregister it
                if self.pc_socket and self.pc_socket != websocket:
                    try:
                        await self.pc_socket.close(code=1000, reason="New PC connected")
                    except Exception:
                        pass
                self.pc_socket = websocket
                self.pc_info = device_meta or {"name": "Windows PC", "connected_at": time.time()}
                print(f"[Hub] PC Agent connected: {self.pc_info.get('name', 'PC')}")
                # Notify phones that PC is now online
                await self.broadcast_to_phones({
                    "type": "device_status",
                    "device": "pc",
                    "status": "online",
                    "info": self.pc_info,
                })
            elif role == "phone":
                self.phone_sockets.add(websocket)
                print(f"[Hub] Phone client connected ({len(self.phone_sockets)} active)")
            elif role in ("voice_client", "web"):
                self.voice_sockets.add(websocket)
                print(f"[Hub] Voice client connected ({len(self.voice_sockets)} active)")

    async def unregister(self, websocket: WebSocket):
        """Removes a disconnected client and cleans up pending state."""
        async with self._lock:
            if self.pc_socket == websocket:
                self.pc_socket = None
                self.pc_info = {}
                print("[Hub] PC Agent disconnected")
                # Fail any pending PC tasks
                for task_id, future in list(self.pending_tasks.items()):
                    if not future.done():
                        future.set_result({
                            "success": False,
                            "error": "PC disconnected while task was executing",
                        })
                self.pending_tasks.clear()
                # Notify phones that PC went offline
                await self.broadcast_to_phones({
                    "type": "device_status",
                    "device": "pc",
                    "status": "offline",
                })
            elif websocket in self.phone_sockets:
                self.phone_sockets.discard(websocket)
                print(f"[Hub] Phone client disconnected ({len(self.phone_sockets)} active)")
            elif websocket in self.voice_sockets:
                self.voice_sockets.discard(websocket)
                print(f"[Hub] Voice client disconnected ({len(self.voice_sockets)} active)")

    def is_pc_online(self) -> bool:
        """Returns True if a PC agent is actively connected."""
        return self.pc_socket is not None

    async def dispatch_to_pc(self, action: str, params: dict, timeout: float = 30.0) -> dict:
        """Dispatches an action to the PC Agent and waits for completion."""
        if not self.pc_socket:
            return {
                "success": False,
                "error": "pc_offline",
                "message": "Your PC is currently offline, boss. Please make sure Jarvis PC Agent is running.",
            }

        task_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending_tasks[task_id] = future

        payload = {
            "type": "execute_task",
            "task_id": task_id,
            "action": action,
            "params": params,
            "created_at": time.time(),
        }

        try:
            await self.pc_socket.send_text(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self.pending_tasks.pop(task_id, None)
            return {
                "success": False,
                "error": "timeout",
                "message": f"Task '{action}' on PC timed out after {timeout} seconds, boss.",
            }
        except Exception as e:
            self.pending_tasks.pop(task_id, None)
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to execute task on PC: {e}",
            }

    def handle_task_result(self, task_id: str, result: dict):
        """Called when PC Agent sends back the result of a dispatched task."""
        future = self.pending_tasks.pop(task_id, None)
        if future and not future.done():
            future.set_result(result)

    async def broadcast_to_phones(self, data: dict):
        """Sends a message to all connected phone companion apps."""
        raw = json.dumps(data)
        stale = set()
        for ws in self.phone_sockets:
            try:
                await ws.send_text(raw)
            except Exception:
                stale.add(ws)
        self.phone_sockets.difference_update(stale)

    async def send_call_notification(self, caller_name: str, caller_number: str, message: str = "", recording_url: str = "") -> None:
        """Sends a call notification to all connected phone companion apps."""
        await self.broadcast_to_phones({
            "type": "call_notification",
            "caller_name": caller_name,
            "caller_number": caller_number,
            "message": message,
            "recording_url": recording_url,
            "timestamp": __import__("time").time(),
        })

    async def send_urgent_alert(self, caller_name: str, caller_number: str, urgent_message: str) -> None:
        """Sends an urgent alert to all connected phones — removes DND and disables forwarding."""
        await self.broadcast_to_phones({
            "type": "urgent_alert",
            "caller_name": caller_name,
            "caller_number": caller_number,
            "urgent_message": urgent_message,
            "timestamp": __import__("time").time(),
        })
        # Also send commands to remove DND and disable call forwarding
        await self.broadcast_to_phones({
            "type": "execute_task",
            "action": "phone_dnd",
            "params": {"enabled": False},
        })
        await self.broadcast_to_phones({
            "type": "execute_task",
            "action": "disable_call_forwarding",
            "params": {},
        })

    def update_contact_whitelist(self, contacts: dict) -> None:
        """Stores the contact whitelist received from the phone app and pushes to Twilio handler."""
        try:
            from cloud.twilio_handler import update_contact_whitelist
            update_contact_whitelist(contacts)
        except Exception as e:
            print(f"[Hub] Error updating contact whitelist: {e}")

    async def send(self, websocket: WebSocket, data: dict):
        """Sends a JSON message to a specific websocket."""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            print(f"[Hub] Error sending to client: {e}")

    async def send_deal_alert(self, product_name, price, effective_price,
                              platform, url, specs, card_offer="",
                              match_score=0, category="",
                              other_platform_price=0, alert_id=0):
        await self.broadcast_to_phones({
            "type": "deal_alert",
            "alert_id": alert_id,
            "product_name": product_name, "price": price,
            "effective_price": effective_price, "platform": platform,
            "url": url, "specs": specs, "card_offer": card_offer,
            "match_score": match_score, "category": category,
            "other_platform_price": other_platform_price,
            "timestamp": __import__("time").time(),
        })

    async def send_deal_status_alert(self, message: str, alert_id: int = 0):
        await self.broadcast_to_phones({
            "type": "deal_status_alert",
            "alert_id": alert_id,
            "message": message,
            "timestamp": __import__("time").time(),
        })

    async def send_deal_toggle_state(self, is_on: bool):
        await self.broadcast_to_phones({
            "type": "deal_toggle_state", "is_on": is_on,
            "timestamp": __import__("time").time(),
        })

    def get_status(self) -> dict:
        """Returns snapshot of connected devices."""
        return {
            "pc_connected": self.is_pc_online(),
            "pc_info": self.pc_info if self.is_pc_online() else None,
            "phone_clients_count": len(self.phone_sockets),
            "voice_clients_count": len(self.voice_sockets),
            "pending_pc_tasks": len(self.pending_tasks),
        }


hub = DeviceHub()
