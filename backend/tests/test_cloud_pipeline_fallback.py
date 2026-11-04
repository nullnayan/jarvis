# FILE: backend/tests/test_cloud_pipeline_fallback.py
# Unit tests for Cloud-first thinking and local fallback in pipeline.py.

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline import AudioPipeline


@pytest.fixture
def mock_pipeline():
    server = MagicMock()
    loop = MagicMock()
    pipe = AudioPipeline(server, loop)
    # Silence threads and I/O
    pipe.tts = MagicMock()
    pipe.tts.speak = AsyncMock()
    pipe.send = MagicMock()
    return pipe


@pytest.mark.asyncio
async def test_cloud_think_success(mock_pipeline, monkeypatch):
    """Verifies that _think returns cloud response when cloud responds 200."""
    import httpx

    class MockResp:
        status_code = 200
        def json(self):
            return {
                "type": "chat",
                "action": "none",
                "response": "Hello from Cloud Azure, boss.",
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    res = await mock_pipeline._think("hello jarvis")

    assert res["source"] == "cloud"
    assert res["response"] == "Hello from Cloud Azure, boss."
    assert res["tool"] is None


@pytest.mark.asyncio
async def test_cloud_think_fallback_on_network_error(mock_pipeline, monkeypatch):
    """Verifies that _think seamlessly falls back to local Brain on cloud network failure."""
    import httpx

    class FailingAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", FailingAsyncClient)
    mock_pipeline.brain.think = AsyncMock(return_value={
        "tool": None,
        "response": "Hello from local Brain fallback, boss."
    })

    res = await mock_pipeline._think("hello jarvis")

    # Verify local brain was invoked
    assert res["response"] == "Hello from local Brain fallback, boss."
    mock_pipeline.brain.think.assert_awaited_once()


@pytest.mark.asyncio
async def test_dev_mode_bypasses_cloud_for_local_power(mock_pipeline):
    """Verifies that Dev Mode immediately uses local Brain for full sandbox tools."""
    mock_pipeline.dev_mode = True
    mock_pipeline.brain.think = AsyncMock(return_value={
        "tool": "coding_agent",
        "response": "Starting local coding agent, boss."
    })

    res = await mock_pipeline._think("make a react calculator app")
    assert res["tool"] == "coding_agent"
    mock_pipeline.brain.think.assert_awaited_once()
