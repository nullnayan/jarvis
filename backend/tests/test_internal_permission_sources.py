import asyncio
from unittest.mock import AsyncMock, MagicMock

from llm.planner import Planner
from security.permissions import PermissionResult, check_permission


def test_plan_source_cannot_call_user_initiated_tools():
    assert check_permission("run_shell_command", source="plan").result == PermissionResult.DENY


def test_planner_skips_user_initiated_tool_steps():
    async def run():
        planner = Planner(MagicMock())
        pipeline = MagicMock()
        pipeline._run_tool = AsyncMock()
        pipeline.send = MagicMock()
        pipeline.stop_event = MagicMock()
        pipeline.stop_event.is_set.return_value = False
        result = await planner.execute_steps([
            {"step": 1, "tool": "run_shell_command", "params": {"command": "whoami"}},
        ], pipeline)
        assert result == "Plan complete, boss."
        pipeline._run_tool.assert_not_called()

    asyncio.run(run())
