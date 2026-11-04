import unittest

from llm.brain import detect_complex_project


class DetectComplexProjectTests(unittest.TestCase):
    def test_open_youtube_not_a_project(self):
        # Regression: router rephrased 'open youtube' as 'Open the YouTube website...',
        # and the old bare-substring keyword match on 'website' routed it to CodingAgent.
        is_complex, _ = detect_complex_project(
            "Open the YouTube website in the default web browser", "open youtube"
        )
        self.assertFalse(is_complex)

    def test_open_notepad_not_a_project(self):
        is_complex, _ = detect_complex_project(
            "Open Notepad application on Windows", "open notepad"
        )
        self.assertFalse(is_complex)

    def test_play_song_not_a_project(self):
        is_complex, _ = detect_complex_project(
            "Play a song on YouTube", "play mai hir bhi tumko chahunga song"
        )
        self.assertFalse(is_complex)

    def test_restore_is_not_store_substring(self):
        # Word-boundary matching: 'restore' must not match the noun 'store'.
        is_complex, _ = detect_complex_project(
            "Restore the file from backup", "restore file from backup"
        )
        self.assertFalse(is_complex)

    def test_build_website_is_project(self):
        is_complex, is_repair = detect_complex_project(
            "Build a modern responsive e-commerce website for shoes",
            "make an e-commerce website for shoes",
        )
        self.assertTrue(is_complex)
        self.assertFalse(is_repair)

    def test_portfolio_is_project(self):
        is_complex, _ = detect_complex_project(
            "Build a personal portfolio website with projects and contact section",
            "build a portfolio website",
        )
        self.assertTrue(is_complex)

    def test_fix_error_is_repair(self):
        is_complex, is_repair = detect_complex_project(
            "Fix the error in my project", "solve that error"
        )
        self.assertTrue(is_complex)
        self.assertTrue(is_repair)

    def test_restart_server_is_repair(self):
        is_complex, is_repair = detect_complex_project(
            "Restart the server", "restart the server"
        )
        self.assertTrue(is_complex)
        self.assertTrue(is_repair)

    def test_app_open_not_project(self):
        # 'Open the app' has the noun 'app' but no build verb — not a project.
        is_complex, _ = detect_complex_project(
            "Open the settings app", "open settings app"
        )
        self.assertFalse(is_complex)

    def test_simple_calculator_stays_fast(self):
        # 'make a calculator app in python' matches noun+verb but is a small
        # single-file script — must stay in fast execute_code, not CodingAgent.
        is_complex, _ = detect_complex_project(
            "Write a Python script for a simple calculator app",
            "jarvis write a code for a simple calculator",
        )
        self.assertFalse(is_complex)

    def test_write_code_for_question_is_not_project(self):
        # 'write a code for <question>' is a quick single answer, never a project.
        is_complex, _ = detect_complex_project(
            "Write a Python function for the two-sum problem",
            "write a code for two sum question",
        )
        self.assertFalse(is_complex)

    def test_quick_script_not_project(self):
        is_complex, _ = detect_complex_project(
            "Create a quick script to convert CSV to JSON",
            "make a quick script to convert csv to json",
        )
        self.assertFalse(is_complex)


if __name__ == "__main__":
    unittest.main()
