# FILE: backend/security/credentials.py
# Vault-backed shutdown password with PBKDF2-SHA256 hashing.
# The plaintext password and its hash are never logged, spoken, or returned.

import hashlib
import hmac
import os

from security.vault import get_secret, set_secret
from config import PASSWORD_MAX_ATTEMPTS

# Vault key under which the PBKDF2 hash string is stored.
_HASH_KEY = "SHUTDOWN_PASSWORD_HASH"

# Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
_ITERATIONS = 200_000
_SALT_BYTES = 16

# Weak values that are never accepted as a new password.
_WEAK_VALUES = {"1111", "1234", "0000", "9999", "0011"}


def _hash_password(digits: str, salt: bytes, iterations: int = _ITERATIONS) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", digits.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def _parse_hash(stored: str):
    """Parses a stored hash string into (iterations, salt_bytes, digest_bytes)."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return None
        return int(iterations), bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return None


def _get_stored_hash() -> str | None:
    value = get_secret(_HASH_KEY, "").strip()
    return value or None


def _validate_new_password(digits: str) -> tuple[bool, str]:
    """Validates a proposed password. Returns (ok, reason)."""
    if not digits or not digits.isdigit():
        return False, "Password must contain only digits, boss."
    if not (4 <= len(digits) <= 8):
        return False, "Password must be 4 to 8 digits, boss."
    if digits in _WEAK_VALUES:
        return False, "That password is too easy to guess, boss. Please choose a different one."
    if len(set(digits)) == 1:
        return False, "That password is too easy to guess, boss. Please choose a different one."
    return True, ""


def verify_shutdown_password(digits: str) -> bool:
    """Verifies a spoken/typed digit sequence against the stored hash."""
    stored = _get_stored_hash()
    if not stored:
        return False
    parsed = _parse_hash(stored)
    if not parsed:
        return False
    iterations, salt, expected = parsed
    candidate = hashlib.pbkdf2_hmac("sha256", digits.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def validate_new_password(digits: str) -> tuple[bool, str]:
    """Public validation of a proposed password. Returns (ok, reason)."""
    return _validate_new_password(digits)


def set_shutdown_password(digits: str) -> tuple[bool, str]:
    """Sets a new shutdown password. Returns (ok, message)."""
    ok, reason = _validate_new_password(digits)
    if not ok:
        return False, reason
    salt = os.urandom(_SALT_BYTES)
    stored = _hash_password(digits, salt)
    if not set_secret(_HASH_KEY, stored):
        return False, "I could not save the new password, boss."
    return True, "Shutdown password updated, boss."


def migrate_legacy_password() -> bool:
    """Initialize only from an explicitly configured password; never seed a default.

    Existing vault hashes remain intact. Set a new password in the application
    to replace a legacy credential; clearing the repository cannot rotate it.
    """
    if _get_stored_hash():
        return False
    password = get_secret("SHUTDOWN_PASSWORD", "").strip()
    if not password:
        return False
    ok, _ = set_shutdown_password(password)
    return ok


def password_is_set() -> bool:
    return _get_stored_hash() is not None
