import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from config import BRAIN_MODEL, CODER_MODEL, CODING_AGENT_MODEL
from llm.planner import Planner
from llm.project_paths import validate_project_paths
from llm.coding_prompts import render_coding_prompt
from tools.coding_agent import CodingAgent

MODEL = "openai/gpt-oss-120b"


class GroqArchitectureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.brain = MagicMock()
        self.brain._coder_clients.return_value = [('groq-client', 'Groq key')]
        self.brain._chat_with_failover = AsyncMock()
        self.brain._clean_code.side_effect = lambda value: value
        self.agent = CodingAgent.__new__(CodingAgent)
        self.agent.brain = self.brain
        self.agent.project_dir = tempfile.gettempdir()
        self.agent.current_step = 1
        self.agent.current_task = 'build a website'
        self.agent.completed_steps = []
        self.agent.created_files = []

    async def test_project_planning_uses_groq_and_preserves_installs(self):
        self.brain._chat_with_failover.return_value = '{"steps":[{"step":1,"description":"setup"}],"required_installs":["flask"]}'
        result = await self.agent._generate_plan('build a website', 'reviewed spec')
        self.assertEqual(result['required_installs'], ['flask'])
        self.assertEqual(len(result['steps']), 1)
        self.assertEqual(self.brain._chat_with_failover.call_args.args[0], MODEL)
        self.brain._chat_with_failover.assert_awaited_once()

    async def test_step_code_and_recovery_use_groq_without_provider_fallback(self):
        self.brain._chat_with_failover.return_value = "print('ready')"
        self.assertEqual(await self.agent._generate_step_code({'description':'setup'}), "print('ready')")
        self.assertEqual(await self.agent._recover_step_code({'description':'setup'}, 'bad source', 'error'), "print('ready')")
        self.assertEqual([call.args[0] for call in self.brain._chat_with_failover.call_args_list], [MODEL, MODEL])

    async def test_empty_generation_does_not_call_another_provider(self):
        self.brain._chat_with_failover.return_value = ''
        self.assertEqual(await self.agent._generate_step_code({'description':'setup'}), '')
        self.brain._chat_with_failover.assert_awaited_once()

    async def test_general_task_planning_uses_same_groq_model(self):
        self.brain._chat_with_failover.return_value = '[{"step":1,"tool":"web_search","params":{},"description":"search"}]'
        plan = await Planner(self.brain).create_plan('research a topic', '', 'web_search')
        self.assertEqual(len(plan), 1)
        self.assertEqual(self.brain._chat_with_failover.call_args.args[0], MODEL)

    async def test_local_runner_dispatch_and_project_boundary(self):
        self.agent._run_local_script = AsyncMock(return_value={'success':True,'stdout':'done','stderr':''})
        self.assertTrue((await self.agent._run_script("print('ready')"))['success'])
        self.assertFalse((await self.agent._run_script("open('../private.txt','w')"))['success'])
        self.agent._run_local_script.assert_awaited_once()

    async def test_local_code_runs_in_project_without_provider_credentials(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as project:
            self.agent.project_dir = project
            source = "from pathlib import Path\nimport os\nPath('created.txt').write_text('ready')\nprint(bool(os.getenv('SAMPLE_API_KEY')))"
            with patch.dict(os.environ, {'SAMPLE_API_KEY':'private-test-value'}):
                result = await self.agent._run_script(source)
            self.assertTrue(result['success'], result['stderr'])
            self.assertEqual(result['stdout'], 'False')
            self.assertEqual((Path(project)/'created.txt').read_text(), 'ready')

    def test_text_model_configuration(self):
        self.assertEqual((BRAIN_MODEL, CODER_MODEL, CODING_AGENT_MODEL), (MODEL, MODEL, MODEL))


class ProjectPathTests(unittest.TestCase):
    def test_prompt_json_and_inserted_source_are_preserved(self):
        template = "Task: {task}; response: {'error': 'Unauthorized'}; source: {code}; literal: {{name}}"
        rendered = render_coding_prompt(template, task='build', code="f'{{value}}'")
        self.assertEqual(rendered, "Task: build; response: {'error': 'Unauthorized'}; source: f'{{value}}'; literal: {name}")

    def test_obvious_file_escape_is_blocked(self):
        with tempfile.TemporaryDirectory() as project:
            for source in ["open('../private.txt','w')", "Path('/etc/passwd')"]:
                self.assertFalse(validate_project_paths(source, project)[0])

    def test_relative_project_files_and_web_routes_are_allowed(self):
        with tempfile.TemporaryDirectory() as project:
            self.assertTrue(validate_project_paths("open('index.html','w')", project)[0])
            self.assertTrue(validate_project_paths("@app.route('/api/login')\ndef login():\n    return 'ok'", project)[0])


if __name__ == '__main__':unittest.main()
