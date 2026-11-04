import unittest
from unittest.mock import patch

from pipeline import shutdown_password_matches


class PasswordTests(unittest.TestCase):
    def test_partial_values_do_not_match(self):
        with patch("security.credentials.verify_shutdown_password", return_value=False):
            self.assertFalse(shutdown_password_matches("51111"))
            self.assertFalse(shutdown_password_matches("11110"))

    def test_correct_password_matches(self):
        with patch("security.credentials.verify_shutdown_password", return_value=True):
            self.assertTrue(shutdown_password_matches("0011"))


if __name__ == "__main__":
    unittest.main()
