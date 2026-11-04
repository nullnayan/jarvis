import unittest

from security.permissions import (
    check_permission,
    permission_level,
    PermissionResult,
    USER_INITIATED_ONLY,
    TOOL_PERMISSION_LEVELS,
)


class PermissionTests(unittest.TestCase):
    def test_level_0_allow(self):
        decision = check_permission("get_datetime", {}, source="voice")
        self.assertEqual(decision.result, PermissionResult.ALLOW)

    def test_level_4_confirm(self):
        decision = check_permission("system_power", {"action": "shutdown"}, source="voice")
        self.assertEqual(decision.result, PermissionResult.CONFIRM_REQUIRED)

    def test_unregistered_defaults_to_level_2(self):
        self.assertEqual(permission_level("some_unknown_tool"), 2)

    def test_user_initiated_only_refused_from_chain(self):
        decision = check_permission("run_shell_command", {"command": "git status"}, source="chain")
        self.assertEqual(decision.result, PermissionResult.DENY)

    def test_user_initiated_allowed_from_voice(self):
        decision = check_permission("run_shell_command", {"command": "git status"}, source="voice")
        self.assertNotEqual(decision.result, PermissionResult.DENY)

    def test_all_user_initiated_names_registered(self):
        for name in USER_INITIATED_ONLY:
            self.assertIn(name, TOOL_PERMISSION_LEVELS)


if __name__ == "__main__":
    unittest.main()
