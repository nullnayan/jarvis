import unittest

from security.permissions import (
    PermissionResult,
    USER_INITIATED_ONLY,
    check_permission,
    permission_level,
)


class PhonePermissionsTests(unittest.TestCase):
    PHONE_TOOLS = (
        "phone_connect",
        "phone_disconnect",
        "phone_status",
        "phone_mirror",
        "phone_screencap",
        "phone_open_app",
        "phone_action",
        "phone_call",
    )

    def test_all_five_in_user_initiated_only(self):
        """Prompt-injection defense: every phone tool must refuse non-direct sources."""
        for tool in self.PHONE_TOOLS:
            self.assertIn(tool, USER_INITIATED_ONLY)

    def test_phone_connect_denied_from_chain(self):
        decision = check_permission("phone_connect", {}, source="chain")
        self.assertEqual(decision.result, PermissionResult.DENY)

    def test_phone_disconnect_denied_from_runtime(self):
        decision = check_permission("phone_disconnect", {}, source="runtime")
        self.assertEqual(decision.result, PermissionResult.DENY)

    def test_phone_mirror_denied_from_chain(self):
        decision = check_permission("phone_mirror", {"action": "start"}, source="chain")
        self.assertEqual(decision.result, PermissionResult.DENY)

    def test_phone_screencap_denied_from_chain(self):
        decision = check_permission("phone_screencap", {}, source="chain")
        self.assertEqual(decision.result, PermissionResult.DENY)

    def test_phone_status_denied_from_chain(self):
        decision = check_permission("phone_status", {}, source="chain")
        self.assertEqual(decision.result, PermissionResult.DENY)

    def test_phone_status_level_0_safe_from_voice(self):
        decision = check_permission("phone_status", {}, source="voice")
        self.assertEqual(decision.result, PermissionResult.ALLOW)
        self.assertEqual(permission_level("phone_status"), 0)

    def test_phone_mirror_screencap_level_2_from_voice(self):
        self.assertEqual(permission_level("phone_mirror"), 2)
        self.assertEqual(permission_level("phone_screencap"), 2)
        decision = check_permission("phone_mirror", {"action": "start"}, source="voice")
        self.assertEqual(decision.result, PermissionResult.CONFIRM_REQUIRED)

    def test_phone_connect_disconnect_level_0_from_voice(self):
        self.assertEqual(permission_level("phone_connect"), 0)
        self.assertEqual(permission_level("phone_disconnect"), 0)
        decision = check_permission("phone_connect", {}, source="voice")
        self.assertEqual(decision.result, PermissionResult.ALLOW)


if __name__ == "__main__":
    unittest.main()
