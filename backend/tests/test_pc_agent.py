# FILE: backend/tests/test_pc_agent.py
# Unit tests for Jarvis PC Agent Dispatcher.

import pytest
from pc_agent.dispatcher import execute_local_task


def test_dispatcher_unknown_action():
    """Verifies that an unknown action returns success=False and an informative message."""
    ok, msg = execute_local_task("nonexistent_action_xyz", {})
    assert ok is False
    assert "unknown" in msg.lower()


def test_dispatcher_open_app_missing_name():
    """Verifies that open_app requires an app name parameter."""
    ok, msg = execute_local_task("open_app", {})
    assert ok is False
    assert "no app name" in msg.lower()


def test_dispatcher_volume_call(monkeypatch):
    """Verifies that volume actions route to volume_control."""
    called = []

    def mock_vol(params):
        called.append(params)
        return "Volume adjusted"

    from llm.tools import TOOL_HANDLERS
    monkeypatch.setitem(TOOL_HANDLERS, "volume_control", mock_vol)

    ok, msg = execute_local_task("volume_set", {"level": 50})
    assert ok is True
    assert msg == "Volume adjusted"
    assert len(called) == 1
    assert called[0] == {"action": "set", "level": 50}
