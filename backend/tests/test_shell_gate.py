import unittest

from tools.system_command import is_destructive_action, run_shell_command


class ShellGateTests(unittest.TestCase):
    def test_destructive_forces_confirm(self):
        destructive, desc = is_destructive_action("Remove-Item C:\\Users\\USER\\file.txt")
        self.assertTrue(destructive)
        self.assertTrue(desc)

    def test_hard_blocked_refused(self):
        destructive, desc = is_destructive_action("format C:")
        self.assertTrue(destructive)
        self.assertIn("BLOCKED", desc)

    def test_safe_command_not_destructive(self):
        destructive, desc = is_destructive_action("git status")
        self.assertFalse(destructive)
        self.assertEqual(desc, "")

    def test_run_shell_command_empty(self):
        result = run_shell_command({"command": ""})
        self.assertIn("No command", result)

    def test_run_shell_command_blocks_dangerous(self):
        result = run_shell_command({"command": "format C:"})
        self.assertIn("blocked", result.lower())


if __name__ == "__main__":
    unittest.main()
