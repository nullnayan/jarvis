import unittest
import os
import json
import tempfile
from unittest.mock import patch

from llm.brain import Brain
from llm.tools import TOOL_DEFINITIONS_CORE, TOOL_DEFINITIONS_DEV, TOOL_DEFINITIONS
from tools.app_readiness import record_launch_timing, get_recommended_wait, _load_timings
from tools.whatsapp import _load_contact_cache, _save_contact_cache, _generate_name_variations


class DevModeOverhaulTests(unittest.TestCase):
    def test_tool_definitions_core_and_dev_partition(self):
        core_names = {t["name"] for t in TOOL_DEFINITIONS_CORE}
        dev_names = {t["name"] for t in TOOL_DEFINITIONS_DEV}
        all_names = {t["name"] for t in TOOL_DEFINITIONS}

        self.assertEqual(core_names.union(dev_names), all_names)
        self.assertEqual(len(core_names.intersection(dev_names)), 0)

        self.assertIn("open_app", core_names)
        self.assertIn("whatsapp_message", core_names)
        self.assertIn("doc_reader", core_names)
        self.assertIn("volume_control", core_names)

        self.assertIn("execute_code", dev_names)
        self.assertIn("self_audit", dev_names)
        self.assertIn("self_fix", dev_names)

    def test_brain_dev_mode_toggle_updates_system_prompt(self):
        brain = Brain()
        brain.set_dev_mode(False)
        self.assertFalse(brain.dev_mode)
        prompt_normal = brain.system_prompt
        self.assertIn("open_app", prompt_normal)
        self.assertNotIn('"name":"self_audit"', prompt_normal)
        self.assertNotIn('"name":"self_fix"', prompt_normal)

        brain.set_dev_mode(True)
        self.assertTrue(brain.dev_mode)
        prompt_dev = brain.system_prompt
        self.assertIn('"name":"self_audit"', prompt_dev)
        self.assertIn('"name":"self_fix"', prompt_dev)
        self.assertIn('"name":"execute_code"', prompt_dev)

    def test_chat_depth_heuristics(self):
        brain = Brain()
        self.assertFalse(brain._needs_deep_conversation("hello"))
        self.assertFalse(brain._needs_deep_conversation("kya hal hai"))
        self.assertFalse(brain._needs_deep_conversation("good morning jarvis"))

        self.assertTrue(brain._needs_deep_conversation("why is the sky blue?"))
        self.assertTrue(brain._needs_deep_conversation("explain quantum computing in detail"))
        self.assertTrue(brain._needs_deep_conversation("tell me about the history of artificial intelligence"))
        self.assertTrue(brain._needs_deep_conversation("what is the difference between synchronous and asynchronous python?"))

    def test_whatsapp_contact_cache_and_variation_priority(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "test_contacts.json")
            with patch("tools.whatsapp.WHATSAPP_CONTACT_CACHE_FILE", cache_file):
                _save_contact_cache("Mata Shri", "matashree")
                self.assertTrue(os.path.exists(cache_file))
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.assertEqual(data.get("mata shri"), "matashree")

                variations = _generate_name_variations("Mata Shri")
                self.assertEqual(variations[0], "matashree")

    def test_app_readiness_cold_vs_warm_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timing_file = os.path.join(tmpdir, "test_timings.json")
            with patch("tools.app_readiness.TIMINGS_FILE", timing_file):
                record_launch_timing("TestApp", 4.0, is_cold=True)
                record_launch_timing("TestApp", 0.1, is_cold=False)

                timings = _load_timings()
                app_info = timings.get("TestApp", {})
                self.assertEqual(len(app_info.get("cold_samples", [])), 1)
                self.assertEqual(len(app_info.get("warm_samples", [])), 1)
                self.assertEqual(app_info.get("avg_cold_ms"), 4000)
                self.assertEqual(app_info.get("avg_warm_ms"), 100)

                cold_wait = get_recommended_wait("TestApp", is_cold=True)
                self.assertGreaterEqual(cold_wait, 3.0)


if __name__ == "__main__":
    unittest.main()
