import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from llm.planner import parse_plan, resolve_results, MAX_STEPS, Planner


class PlannerTests(unittest.TestCase):
    def test_parse_plain_json(self):
        content = '[{"step": 1, "tool": "run_shell_command", "params": {"command": "dir"}, "description": "list files"}]'
        steps = parse_plan(content)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["tool"], "run_shell_command")

    def test_parse_fenced_json(self):
        content = '```json\n[{"step": 1, "tool": "get_datetime", "params": {}, "description": "time"}]\n```'
        steps = parse_plan(content)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["tool"], "get_datetime")

    def test_parse_prose_wrapped(self):
        content = 'Here is the plan:\n[{"step": 1, "tool": "clipboard", "params": {"action": "read"}, "description": "read"}]'
        steps = parse_plan(content)
        self.assertEqual(len(steps), 1)

    def test_parse_invalid_returns_empty(self):
        self.assertEqual(parse_plan("no json here"), [])

    def test_result_references_resolved(self):
        steps = [{"step": 2, "tool": "run_shell_command", "params": {"command": "$result_1"}, "description": "x"}]
        resolved = resolve_results(steps, {1: "echo hi"})
        self.assertEqual(resolved[0]["params"]["command"], "echo hi")

    def test_execute_asks_then_stores_plan_no_execution(self):
        """Regression: execute() must NOT run steps optimistically. It speaks the
        plan review and stores a pending_action; nothing executes until confirmed."""
        async def run():
            brain = MagicMock()
            brain._build_context_block = MagicMock(return_value="ctx")
            brain._chat_with_failover = AsyncMock(return_value='[{"step": 1, "tool": "get_datetime", "params": {}, "description": "get time"}]')
            planner = Planner(brain)
            pipeline = MagicMock()
            pipeline.respond = AsyncMock()
            pipeline.pending_action = None
            result = await planner.execute("what time is it", pipeline, lang="en")
            self.assertEqual(result, "")
            # Plan stored, not executed.
            self.assertIsNotNone(pipeline.pending_action)
            self.assertEqual(pipeline.pending_action["kind"], "plan")
            # No tool ran (no _run_tool call).
            pipeline._run_tool.assert_not_called()
            # The review question was spoken.
            pipeline.respond.assert_called_once()
            self.assertIn("Go ahead, boss?", pipeline.respond.call_args[0][0])
        asyncio.run(run())

    def test_execute_steps_runs_tools_with_progress(self):
        """Confirmed plans execute each step and emit progress messages."""
        async def run():
            brain = MagicMock()
            planner = Planner(brain)
            pipeline = MagicMock()
            pipeline._run_tool = AsyncMock(side_effect=["out1", "out2"])
            pipeline.send = MagicMock()
            pipeline.stop_event = MagicMock()
            pipeline.stop_event.is_set = MagicMock(return_value=False)
            steps = [
                {"step": 1, "tool": "get_datetime", "params": {}, "description": "time"},
                {"step": 2, "tool": "clipboard", "params": {"action": "read"}, "description": "read"},
            ]
            result = await planner.execute_steps(steps, pipeline, lang="en")
            self.assertEqual(result, "Plan complete, boss.")
            self.assertEqual(pipeline._run_tool.call_count, 2)
            # Progress emitted for each step + a final complete.
            progress = [c.args[0] for c in pipeline.send.call_args_list]
            self.assertTrue(any('"type": "plan_progress"' in m for m in progress))
        asyncio.run(run())

    def test_execute_steps_cancelled_when_stop_event_set(self):
        async def run():
            brain = MagicMock()
            planner = Planner(brain)
            pipeline = MagicMock()
            pipeline._run_tool = AsyncMock()
            pipeline.respond_and_idle = AsyncMock()
            pipeline.stop_event = MagicMock()
            pipeline.stop_event.is_set = MagicMock(return_value=True)
            steps = [{"step": 1, "tool": "get_datetime", "params": {}, "description": "time"}]
            result = await planner.execute_steps(steps, pipeline, lang="en")
            self.assertEqual(result, "Plan cancelled, boss.")
            pipeline._run_tool.assert_not_called()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
