import unittest
from unittest.mock import patch

from security import credentials


class PasswordHashTests(unittest.TestCase):
    def setUp(self):
        # Credential tests exercise PBKDF2 behavior, not Windows DPAPI. Keeping an
        # in-memory vault makes them deterministic and avoids touching user secrets.
        self.secrets = {}
        self.get_secret = patch.object(
            credentials, "get_secret", side_effect=lambda key, default="": self.secrets.get(key, default)
        )
        self.set_secret = patch.object(
            credentials, "set_secret", side_effect=lambda key, value: self.secrets.__setitem__(key, value) is None
        )
        self.get_secret.start()
        self.set_secret.start()

    def tearDown(self):
        self.set_secret.stop()
        self.get_secret.stop()

    def test_round_trip_verify(self):
        ok, msg = credentials.set_shutdown_password("4829")
        self.assertTrue(ok)
        self.assertTrue(credentials.verify_shutdown_password("4829"))
        self.assertFalse(credentials.verify_shutdown_password("1111"))

    def test_weak_values_rejected(self):
        for weak in ("1111", "1234", "0000", "9999", "2222", "0011"):
            ok, reason = credentials.validate_new_password(weak)
            self.assertFalse(ok, f"{weak} should be rejected")
            self.assertTrue(reason)

    def test_length_and_numeric_validation(self):
        self.assertFalse(credentials.validate_new_password("12")[0])       # too short
        self.assertFalse(credentials.validate_new_password("123456789")[0])  # too long
        self.assertFalse(credentials.validate_new_password("12a4")[0])      # non-numeric
        self.assertTrue(credentials.validate_new_password("4829")[0])      # valid

    def test_legacy_migration(self):
        self.secrets["SHUTDOWN_PASSWORD"] = "4829"
        with patch.object(credentials, "_get_stored_hash", return_value=None):
            with patch.object(credentials, "set_shutdown_password", return_value=(True, "ok")) as mock_set:
                migrated = credentials.migrate_legacy_password()
                self.assertTrue(migrated)
                mock_set.assert_called_once_with("4829")

    def test_first_boot_without_password_does_not_seed_vault(self):
        self.assertFalse(credentials.migrate_legacy_password())
        self.assertEqual(self.secrets, {})

    def test_insecure_legacy_default_cannot_initialize_vault(self):
        self.secrets["SHUTDOWN_PASSWORD"] = "0011"
        self.assertFalse(credentials.migrate_legacy_password())
        self.assertNotIn("SHUTDOWN_PASSWORD_HASH", self.secrets)

    def test_migration_idempotent(self):
        with patch.object(credentials, "_get_stored_hash", return_value="pbkdf2_sha256$200000$aa$bb"):
            self.assertFalse(credentials.migrate_legacy_password())

    def test_plaintext_never_in_vault(self):
        # The stored value must be a pbkdf2 hash, never the plaintext digits.
        ok, _ = credentials.set_shutdown_password("4829")
        self.assertTrue(ok)
        stored = credentials._get_stored_hash()
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertNotIn("4829", stored)


if __name__ == "__main__":
    unittest.main()
