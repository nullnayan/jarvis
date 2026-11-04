import json
import unittest
from pathlib import Path

from pipeline import OPEN_INTENT_VERBS, is_open_action


class OpenIntentTests(unittest.TestCase):
    def test_open_intent_detection(self):
        self.assertTrue(is_open_action("open chrome"))
        self.assertFalse(is_open_action("what time is it"))

    def test_shared_verb_list_is_used(self):
        path = Path(__file__).resolve().parents[2] / "shared" / "open_intent.json"
        self.assertEqual(tuple(json.loads(path.read_text(encoding="utf-8"))), OPEN_INTENT_VERBS)


if __name__ == "__main__":
    unittest.main()
