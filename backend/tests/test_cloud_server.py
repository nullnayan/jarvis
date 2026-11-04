# FILE: backend/tests/test_cloud_server.py
# Unit tests for Cloud Jarvis Gateway (Phase 1).

import pytest
import pytest_asyncio
import json
from fastapi.testclient import TestClient

from cloud.server import app
from cloud.hub import hub
from cloud.config import JARVIS_AUTH_TOKEN


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Verifies that /health responds with 200 OK and online status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert data["service"] == "jarvis-cloud"


def test_status_auth_protection(client):
    """Verifies that /status requires valid auth token."""
    # Invalid token -> 401
    resp = client.get("/status?token=wrong_token")
    assert resp.status_code == 401

    # Valid token -> 200 with device counts
    resp = client.get(f"/status?token={JARVIS_AUTH_TOKEN}")
    assert resp.status_code == 200
    data = resp.json()
    assert "devices" in data
    assert data["devices"]["pc_connected"] is False


@pytest.mark.asyncio
async def test_pc_offline_rejection():
    """Verifies that dispatching a PC task fails cleanly when PC is offline."""
    res = await hub.dispatch_to_pc("open_app", {"app": "youtube"}, timeout=1.0)
    assert res["success"] is False
    assert res["error"] == "pc_offline"
    assert "offline" in res["message"].lower()
