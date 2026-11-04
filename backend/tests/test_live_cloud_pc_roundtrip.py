# FILE: backend/tests/test_live_cloud_pc_roundtrip.py
# Tests the live WebSocket handshake and task execution between PC Agent and Azure Cloud VM.

import asyncio
import json
import pytest
import websockets
import httpx

import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

TOKEN = os.environ.get("JARVIS_AUTH_TOKEN", "")
CLOUD_HOST = os.environ.get("CLOUD_HOST", "127.0.0.1")
CLOUD_PORT = int(os.environ.get("CLOUD_PORT", "8765"))
CLOUD_WS = f"ws://{CLOUD_HOST}:{CLOUD_PORT}/ws/pc?token={TOKEN}"
CLOUD_STATUS = f"http://{CLOUD_HOST}:{CLOUD_PORT}/status?token={TOKEN}"
CLOUD_CHAT = f"http://{CLOUD_HOST}:{CLOUD_PORT}/api/chat"


@pytest.mark.asyncio
async def test_pc_connect_and_task_execution():
    """Connects mock PC agent to Azure cloud, sends cloud command, and executes task."""
    received_tasks = []

    async with websockets.connect(CLOUD_WS, open_timeout=10) as ws:
        # 1. Verify connection ack
        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        conn_msg = json.loads(raw)
        assert conn_msg.get("type") == "connected"
        assert conn_msg.get("role") == "pc"

        # 2. Check cloud status shows PC is online
        async with httpx.AsyncClient() as client:
            resp = await client.get(CLOUD_STATUS)
            assert resp.status_code == 200
            data = resp.json()
            assert data["devices"]["pc_connected"] is True

        # 3. Trigger a PC task via Cloud REST API from a simulated phone/test client
        async def trigger_cloud_command():
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    CLOUD_CHAT,
                    json={
                        "message": "Open notepad on my PC",
                        "token": TOKEN,
                        "role": "phone"
                    },
                    timeout=15.0
                )
                return res.json()

        cmd_task = asyncio.create_task(trigger_cloud_command())

        # 4. PC Agent receives the task over WebSocket!
        task_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        task_msg = json.loads(task_raw)
        assert task_msg.get("type") == "execute_task"
        assert task_msg.get("action") == "open_app"

        # 5. PC Agent sends back task_result
        task_id = task_msg.get("task_id")
        await ws.send(json.dumps({
            "type": "task_result",
            "task_id": task_id,
            "action": "open_app",
            "success": True,
            "message": "Notepad opened successfully on PC, boss."
        }))

        # 6. Verify cloud API receives the result and responds to the phone!
        cmd_result = await cmd_task
        assert cmd_result.get("type") == "pc_task"
        assert cmd_result.get("success") is True
        assert "notepad" in cmd_result.get("response").lower()

    # 7. After disconnect, verify cloud detects PC offline
    await asyncio.sleep(0.5)
    async with httpx.AsyncClient() as client:
        resp = await client.get(CLOUD_STATUS)
        data = resp.json()
        assert data["devices"]["pc_connected"] is False
