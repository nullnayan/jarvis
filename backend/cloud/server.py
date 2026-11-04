# FILE: backend/cloud/server.py
# FastAPI WebSocket & REST Server for Cloud Jarvis.
# Runs on Cloud Gateway VM.

import asyncio
import json
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cloud.config import CLOUD_HOST, CLOUD_PORT, JARVIS_AUTH_TOKEN, CLOUD_ALLOWED_ORIGINS
from cloud.hub import hub
from cloud.deal_monitor import DealMonitor
from cloud.deal_db import DealDB
deal_db = DealDB()
deal_monitor = DealMonitor(deal_db, hub)

from cloud.cloud_brain import cloud_brain
from cloud.twilio_handler import router as twilio_router, get_call_log, clear_call_log

app = FastAPI(
    title="Cloud Jarvis Gateway",
    description="Central coordination brain for Jarvis Phone App and PC Agent",
    version="2.0.0",
)

# Enable CORS for web and mobile dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=CLOUD_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Twilio voice webhook router
app.include_router(twilio_router, prefix="/twilio", tags=["twilio"])


@app.on_event("startup")
async def on_startup():
    if len(JARVIS_AUTH_TOKEN) < 32:
        raise RuntimeError("Configure a random JARVIS_AUTH_TOKEN of at least 32 characters before starting the gateway.")
    print("[CloudServer] Starting DealMonitor background task...")
    asyncio.create_task(deal_monitor.run_forever())


@app.on_event("shutdown")
async def on_shutdown():
    print("[CloudServer] Stopping DealMonitor...")
    deal_monitor.stop()



class ChatRequest(BaseModel):
    message: str
    token: str
    role: Optional[str] = "web"


@app.get("/health")
async def health():
    """Liveness probe for cloud monitor and uptime checks."""
    return {
        "status": "online",
        "service": "jarvis-cloud",
        "timestamp": time.time(),
    }


@app.get("/status")
async def status_check(token: Optional[str] = Query(None)):
    """Returns connected device status."""
    if not await hub.authenticate(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {
        "status": "online",
        "devices": hub.get_status(),
        "sleep_mode": cloud_brain.call_state.active,
        "call_mode": cloud_brain.call_state.mode,
    }


@app.get("/api/call-log")
async def get_call_log_endpoint(token: Optional[str] = Query(None)):
    """Returns the call log from the current call handling session."""
    if not await hub.authenticate(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"calls": get_call_log()}


@app.delete("/api/call-log")
async def clear_call_log_endpoint(token: Optional[str] = Query(None)):
    """Clears the call log (called when User wakes up and reviews calls)."""
    if not await hub.authenticate(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    clear_call_log()
    return {"status": "cleared"}


class UrgentAlertRequest(BaseModel):
    caller_name: str
    caller_number: str = ""
    message: str
    token: str


class UrgentDecisionRequest(BaseModel):
    decision: str
    token: str


_latest_decision = {"decision": None, "timestamp": 0}


@app.post("/api/urgent-alert")
async def trigger_urgent_alert(req: UrgentAlertRequest):
    if not await hub.authenticate(req.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    _latest_decision["decision"] = None
    await hub.send_urgent_alert(req.caller_name, req.caller_number, req.message)
    return {"status": "alert_broadcasted"}


@app.post("/api/urgent-decision")
async def submit_urgent_decision(req: UrgentDecisionRequest):
    if not await hub.authenticate(req.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    _latest_decision["decision"] = req.decision
    _latest_decision["timestamp"] = time.time()
    return {"status": "decision_recorded"}


@app.get("/api/urgent-decision")
async def get_urgent_decision_status(token: Optional[str] = Query(None)):
    if not await hub.authenticate(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return _latest_decision


@app.post("/api/chat")
async def http_chat(req: ChatRequest):
    """REST endpoint for sending a text command to Jarvis."""
    if not await hub.authenticate(req.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await cloud_brain.process_command(req.message, client_role=req.role or "web")
    return result


from pydantic import BaseModel
class DealToggleRequest(BaseModel):
    enabled: bool
    token: str

@app.post("/api/deal-toggle")
async def toggle_deal_monitoring(req: DealToggleRequest):
    if not await hub.authenticate(req.token):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")
    await deal_db.set_global_toggle(req.enabled)
    await hub.send_deal_toggle_state(req.enabled)
    if req.enabled:
        deal_monitor.trigger_immediate_run()
    return {"status": "on" if req.enabled else "off"}

@app.get("/api/deal-status")
async def get_deal_status(token: str = None):
    if not await hub.authenticate(token):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")
    toggle = await deal_db.get_global_toggle()
    watches = await deal_db.get_active_watches()
    return {"toggle": toggle, "watches": watches}


@app.post("/api/test-deal-alert")
@app.get("/api/test-deal-alert")
async def trigger_test_deal_alert(token: Optional[str] = Query(None)):
    if not await hub.authenticate(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    await hub.send_deal_alert(
        product_name="Example phone",
        price=24999,
        effective_price=23499,
        platform="flipkart",
        url="https://www.flipkart.com",
        specs="8GB RAM - 128GB - 6000mAh - AMOLED 120Hz",
        card_offer="Flat 1500 Bank Discount",
        match_score=95,
        category="phone"
    )
    return {"status": "sent", "message": "Deal alert broadcasted to connected phones!"}

@app.websocket("/ws/{role}")
async def websocket_endpoint(
    websocket: WebSocket,
    role: str,
    token: Optional[str] = Query(None),
):
    """Real-time bidirectional WebSocket gateway.
    Roles: 'pc' (Windows PC Agent), 'phone' (Mobile Companion App), 'voice_client' (PC jarvis.bat)
    """
    if role not in {"pc", "phone", "voice_client", "web"}:
        await websocket.close(code=1008, reason="Unknown device role")
        return
    await websocket.accept()

    # Authenticate via query param or initial auth message
    is_authenticated = False
    if token and await hub.authenticate(token):
        is_authenticated = True

    try:
        if not is_authenticated:
            # Wait up to 5s for an auth handshake message: {"type": "auth", "token": "..."}
            try:
                raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                auth_data = json.loads(raw_auth)
                if auth_data.get("type") == "auth" and await hub.authenticate(auth_data.get("token", "")):
                    is_authenticated = True
                    await websocket.send_text(json.dumps({"type": "auth_ok", "role": role}))
                else:
                    await websocket.send_text(json.dumps({"type": "auth_failed", "error": "Invalid auth token"}))
                    await websocket.close(code=4001, reason="Authentication failed")
                    return
            except (asyncio.TimeoutError, json.JSONDecodeError):
                await websocket.close(code=4001, reason="Authentication timeout")
                return

        # Register client in Hub
        await hub.register(websocket, role)
        await websocket.send_text(json.dumps({
            "type": "connected",
            "role": role,
            "pc_online": hub.is_pc_online(),
            "sleep_mode": cloud_brain.call_state.active,
            "call_mode": cloud_brain.call_state.mode,
        }))

        # If phone connected, inform it of current cloud toggle state & push any offline pending alerts
        if role == "phone":
            try:
                server_toggle = await deal_db.get_global_toggle()
                await websocket.send_text(json.dumps({
                    "type": "deal_toggle_state",
                    "is_on": server_toggle,
                }))
                pending_alerts = await deal_db.get_pending_alerts()
                for alert in pending_alerts:
                    payload = json.loads(alert["payload_json"])
                    payload["alert_id"] = alert["id"]
                    await websocket.send_text(json.dumps(payload))
            except Exception as e:
                print(f"[Hub] Error sending initial deal state/alerts on phone connect: {e}")

        # Main message loop
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            # 1. Ping / Pong Heartbeat
            if msg_type == "deal_toggle":
                enabled = msg.get("enabled", False)
                await deal_db.set_global_toggle(enabled)
                await hub.send_deal_toggle_state(enabled)
                if enabled:
                    deal_monitor.trigger_immediate_run()
                continue

            if msg_type == "deal_sync":
                server_enabled = await deal_db.get_global_toggle()
                await websocket.send_text(json.dumps({
                    "type": "deal_toggle_state",
                    "is_on": server_enabled,
                }))
                try:
                    pending_alerts = await deal_db.get_pending_alerts()
                    for alert in pending_alerts:
                        payload = json.loads(alert["payload_json"])
                        payload["alert_id"] = alert["id"]
                        await websocket.send_text(json.dumps(payload))
                except Exception as e:
                    print(f"[Hub] Error sending pending alerts on deal_sync: {e}")
                continue

            if msg_type == "ack_alert":
                alert_id = msg.get("alert_id")
                if alert_id:
                    await deal_db.mark_alert_delivered(alert_id)
                continue

            if msg_type == "deal_set_pincodes":
                pincodes = msg.get("pincodes", [])
                await deal_db.set_pincodes(pincodes)
                continue

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "time": time.time()}))
                continue

            # 2. Task Result from PC Agent
            if msg_type == "task_result" and role == "pc":
                task_id = msg.get("task_id", "")
                hub.handle_task_result(task_id, msg)
                continue

            # 2b. Urgent Call Decision from Phone
            if msg_type == "urgent_decision":
                decision = msg.get("decision", "decline")
                _latest_decision["decision"] = decision
                _latest_decision["timestamp"] = time.time()
                print(f"[Hub] Urgent decision received: {decision}")
                continue

            # 3. Contact Whitelist Sync from Phone App
            if msg_type == "contacts_sync" and role == "phone":
                contacts = msg.get("contacts", {})
                hub.update_contact_whitelist(contacts)
                await websocket.send_text(json.dumps({
                    "type": "contacts_sync_ack",
                    "count": len(contacts),
                }))
                continue

            # 4. Call Log Request from Phone App (wake-up summary)
            if msg_type == "call_log_request" and role == "phone":
                calls = get_call_log()
                await websocket.send_text(json.dumps({
                    "type": "call_log_response",
                    "calls": calls,
                }))
                clear_call_log()
                continue

            # 5. User Speech or Text Command
            if msg_type == "command":
                text = msg.get("text", "")
                reply = await cloud_brain.process_command(text, client_role=role)
                payload = dict(reply)
                payload["cmd_type"] = reply.get("type", "chat")
                payload["type"] = "command_response"
                await websocket.send_text(json.dumps(payload))

                continue

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[CloudServer] WebSocket error ({role}): {e}")
    finally:
        await hub.unregister(websocket)


def start():
    """Launches the cloud server."""
    print(f"[CloudServer] Starting Cloud Jarvis Gateway on {CLOUD_HOST}:{CLOUD_PORT}...")
    uvicorn.run("cloud.server:app", host=CLOUD_HOST, port=CLOUD_PORT, reload=False)


if __name__ == "__main__":
    start()
