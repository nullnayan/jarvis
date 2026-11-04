import unittest

from llm.tools import TOOL_DEFINITIONS, TOOL_HANDLERS
from security.permissions import USER_INITIATED_ONLY, TOOL_PERMISSION_LEVELS


class ToolRegistryTests(unittest.TestCase):
    def test_definitions_handlers_bijection(self):
        names_def = {d["name"] for d in TOOL_DEFINITIONS}
        names_hand = set(TOOL_HANDLERS.keys())
        self.assertEqual(names_def, names_hand)

    def test_user_initiated_names_exist_in_registry(self):
        names_def = {d["name"] for d in TOOL_DEFINITIONS}
        # self_audit / self_code_write / self_fix are added in Phase 4/5.
        for name in USER_INITIATED_ONLY:
            if name in ("self_audit", "self_code_write", "self_fix"):
                continue
            self.assertIn(name, names_def)

    def test_every_handler_has_permission_level(self):
        for name in TOOL_HANDLERS:
            self.assertIn(name, TOOL_PERMISSION_LEVELS)


if __name__ == "__main__":
    unittest.main()
