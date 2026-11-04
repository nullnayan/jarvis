import unittest
from unittest.mock import patch

from llm.brain import Brain


class ContextBlockTests(unittest.TestCase):
    def test_context_block_includes_profile(self):
        brain = Brain.__new__(Brain)
        brain.memory = type("M", (), {"get_recent": lambda self, n: []})()
        with patch("user_profile.all", return_value={"name": "User", "city": "London"}):
            with patch("tools.context.get_context_summary", return_value="Active window: 'VS Code'"):
                with patch("tools.persistent_memory.recall_relevant", return_value=["prefers dark mode"]):
                    block = brain._build_context_block("hello")
        self.assertIn("User: User", block)
        self.assertIn("City: London", block)
        self.assertIn("Active window: 'VS Code'", block)
        self.assertIn("prefers dark mode", block)

    def test_context_block_empty_on_error(self):
        brain = Brain.__new__(Brain)
        brain.memory = type("M", (), {"get_recent": lambda self, n: []})()
        with patch("user_profile.all", side_effect=Exception("boom")):
            with patch("tools.context.get_context_summary", side_effect=Exception("boom")):
                with patch("tools.persistent_memory.recall_relevant", side_effect=Exception("boom")):
                    block = brain._build_context_block("hello")
        self.assertIn("[CONTEXT]", block)


if __name__ == "__main__":
    unittest.main()
