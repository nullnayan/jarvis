import unittest

from utils.digits import spoken_to_digits


class DigitsTests(unittest.TestCase):
    def test_spoken_words_to_digits(self):
        self.assertEqual(spoken_to_digits("one one one one"), "1111")
        self.assertEqual(spoken_to_digits("zero zero one one"), "0011")

    def test_plain_digits_pass_through(self):
        self.assertEqual(spoken_to_digits("0011"), "0011")

    def test_non_digit_words_dropped(self):
        self.assertEqual(spoken_to_digits("password is four eight two nine"), "4829")

    def test_double_repetition(self):
        self.assertEqual(spoken_to_digits("double zero one one"), "0011")

    def test_whisper_phonetic_variants(self):
        self.assertEqual(spoken_to_digits("won too"), "12")
        self.assertEqual(spoken_to_digits("for ate"), "48")


if __name__ == "__main__":
    unittest.main()
