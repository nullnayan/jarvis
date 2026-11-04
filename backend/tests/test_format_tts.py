import unittest

from pipeline import format_tts_response


class FormatTtsTests(unittest.TestCase):
    def test_false_positive_error_word_is_preserved(self):
        text = "The log shows zero errors, boss."
        self.assertEqual(format_tts_response(text), text)

    def test_error_prefixes_are_normalized(self):
        for text in ("error: failed", "failed to open", "could not find the file"):
            with self.subTest(text=text):
                self.assertEqual(format_tts_response(text), "An error occurred, boss.")

    def test_normal_response_is_preserved(self):
        text = "The operation completed successfully, boss."
        self.assertEqual(format_tts_response(text), text)


if __name__ == "__main__":
    unittest.main()
