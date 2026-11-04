import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from llm.prompt_enhancer import enhance_prompt
from llm.project_context import (
    get_sanitized_package_inventory,
    _clean_json_plan,
)
from server.messages import enhanced_prompt_msg, parse_message


class PromptEnhancerTests(unittest.TestCase):
    def test_enhance_prompt_success(self):
        async def run():
            brain = MagicMock()
            brain._coder_clients = MagicMock(return_value=[])
            brain._chat_with_failover = AsyncMock(
                return_value="<think>analysis</think># Flagship Specification\n1. Core Auth\n2. Order System"
            )
            result = await enhance_prompt("build zomato clone", brain)
            self.assertIn("# Flagship Specification", result)
            self.assertNotIn("<think>", result)
            brain._chat_with_failover.assert_called_once()

        asyncio.run(run())

    def test_enhance_prompt_empty_returns_empty(self):
        async def run():
            brain = MagicMock()
            result = await enhance_prompt("", brain)
            self.assertEqual(result, "")

        asyncio.run(run())

    def test_sanitized_inventory_no_paths_or_secrets(self):
        inv = get_sanitized_package_inventory()
        self.assertIsInstance(inv, list)
        self.assertTrue(len(inv) > 0)
        for pkg in inv:
            self.assertIsInstance(pkg, str)
            # Ensure no absolute paths or secret substrings are leaked
            self.assertNotIn("\\", pkg)
            self.assertNotIn("/", pkg)
            # A leaked API key would look like sk-<20+ random chars>; package
            # names like 'flask-cors' / 'python-socketio' legitimately contain
            # 'sk-' so only flag a realistic full key length.
            import re
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{20,}", pkg))
            self.assertNotIn("key", pkg)

    def test_clean_json_plan_with_required_installs(self):
        sample = """
        ```json
        {
          "steps": [
            {"step": 1, "description": "init project", "target_file": "index.html", "narration": "done"}
          ],
          "required_installs": ["stripe", "flask-cors"]
        }
        ```
        """
        plan = _clean_json_plan(sample)
        self.assertEqual(len(plan["steps"]), 1)
        self.assertEqual(plan["steps"][0]["step"], 1)
        self.assertEqual(plan["required_installs"], ["stripe", "flask-cors"])



    def test_enhanced_prompt_message(self):
        msg = enhanced_prompt_msg("Full spec details")
        parsed = parse_message(msg)
        self.assertEqual(parsed.get("type"), "enhanced_prompt")
        self.assertEqual(parsed.get("value"), "Full spec details")

    def test_stable_request_uses_template_and_does_not_search(self):
        """A stable request ('make a zomato clone') must use the deterministic template
        and NOT trigger any web search (0 search calls)."""
        from llm.prompt_enhancer import get_matching_template, detect_search_queries

        task = "make a zomato clone"
        template = get_matching_template(task)
        self.assertIn("FOOD-DELIVERY", template)
        self.assertIn("restaurant discovery", template.lower())

        queries = detect_search_queries(task, "Standard initial spec")
        self.assertEqual(queries, [])

        async def run():
            brain = MagicMock()
            brain._coder_clients = MagicMock(return_value=[])
            brain._chat_with_failover = AsyncMock(return_value="Detailed Food Delivery Spec")

            with patch("llm.prompt_enhancer.web_search") as mock_search:
                result = await enhance_prompt(task, brain)
                self.assertEqual(result, "Detailed Food Delivery Spec")
                mock_search.assert_not_called()
                # Only 1 model call (initial pass), no refinement call
                self.assertEqual(brain._chat_with_failover.call_count, 1)

        asyncio.run(run())

    def test_time_sensitive_request_triggers_capped_search(self):
        """A time-sensitive request ('build ecommerce with latest stripe api 2026')
        triggers ONE capped search round (max 3 queries) and refines the spec."""
        from llm.prompt_enhancer import detect_search_queries

        task = "build ecommerce with latest stripe api 2026"
        queries = detect_search_queries(task, "Initial spec mentioning current version")
        self.assertTrue(len(queries) > 0)
        self.assertTrue(len(queries) <= 3)
        self.assertTrue(any("stripe" in q.lower() for q in queries))

        async def run():
            brain = MagicMock()
            brain._coder_clients = MagicMock(return_value=[])
            # First call returns initial spec, second call returns refined spec
            brain._chat_with_failover = AsyncMock(side_effect=[
                "Initial Spec: Need to verify latest Stripe 2026 endpoints",
                "Refined Flagship Spec with Verified Stripe 2026 APIs"
            ])

            with patch("llm.prompt_enhancer.web_search", return_value="1. Stripe API 2026\nUpgraded endpoints") as mock_search:
                result = await enhance_prompt(task, brain)
                self.assertEqual(result, "Refined Flagship Spec with Verified Stripe 2026 APIs")
                self.assertTrue(mock_search.called)
                self.assertLessEqual(mock_search.call_count, 3)
                # Exactly 2 LLM passes: initial + refinement
                self.assertEqual(brain._chat_with_failover.call_count, 2)

        asyncio.run(run())

    def test_uncertainty_marker_in_spec_triggers_capped_search(self):
        """When task is stable but initial spec flags uncertainty, capped search is triggered."""
        from llm.prompt_enhancer import detect_search_queries

        task = "build internal analytics app"
        initial_spec = (
            "# System Architecture\n"
            "- Database: SQLite\n"
            "- Auth: UNCERTAIN: verify current oauth2 pkce flow\n"
            "- Metrics: Active users\n"
        )
        queries = detect_search_queries(task, initial_spec)
        self.assertTrue(len(queries) >= 1)
        self.assertTrue(len(queries) <= 3)
        self.assertTrue(any("oauth2 pkce flow" in q.lower() for q in queries))
        self.assertFalse(any("uncertain:" in q.lower() for q in queries))

        async def run():
            brain = MagicMock()
            brain._coder_clients = MagicMock(return_value=[])
            brain._chat_with_failover = AsyncMock(side_effect=[
                initial_spec,
                "# System Architecture\n- Auth: Verified PKCE Flow 2026"
            ])

            with patch("llm.prompt_enhancer.web_search", return_value="1. PKCE Best Practices 2026") as mock_search:
                result = await enhance_prompt(task, brain)
                self.assertIn("Verified PKCE Flow 2026", result)
                self.assertTrue(mock_search.called)
                self.assertLessEqual(mock_search.call_count, 3)
                self.assertEqual(brain._chat_with_failover.call_count, 2)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
