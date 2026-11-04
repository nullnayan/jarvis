# FILE: backend/security/vault.py
# Cryptographically secured credentials vault using Windows DPAPI (Data Protection API).
# Encrypts all API keys and tokens at rest tied to the Windows user account.
# Unreadable by other users, other machines, or plain text scanners.

import os
import sys
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger

_log = get_logger(__name__)
print = _log.info

try:
    import win32crypt
    HAS_WIN32CRYPT = True
except ImportError:
    HAS_WIN32CRYPT = False

VAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
VAULT_PATH = os.path.join(VAULT_DIR, ".secrets.enc")
_CACHE = None
ALLOW_INSECURE_VAULT = os.environ.get("JARVIS_ALLOW_INSECURE_VAULT", "").strip() == "1"

def _encrypt_bytes(data: bytes) -> bytes:
    """Encrypts bytes using Windows DPAPI tied to current user account."""
    if HAS_WIN32CRYPT:
        # CryptProtectData(data, description, optional_entropy, reserved, prompt_struct, flags)
        return win32crypt.CryptProtectData(data, "JarvisEncryptedVault", None, None, None, 0)
    if not ALLOW_INSECURE_VAULT:
        raise RuntimeError(
            "Windows DPAPI is unavailable; refusing insecure vault write. "
            "Install pywin32 or explicitly set JARVIS_ALLOW_INSECURE_VAULT=1."
        )
    print("[Vault] WARNING: storing secrets with insecure XOR compatibility mode")
    key = 0xAA
    return bytes([b ^ key for b in data])

def _decrypt_bytes(ciphertext: bytes) -> bytes:
    """Decrypts bytes using Windows DPAPI tied to current user account."""
    if HAS_WIN32CRYPT:
        _, plaintext = win32crypt.CryptUnprotectData(ciphertext, None, None, None, 0)
        return plaintext
    if not ALLOW_INSECURE_VAULT:
        raise RuntimeError("Windows DPAPI is unavailable; refusing legacy insecure vault decryption.")
    print("[Vault] WARNING: reading a legacy XOR-obfuscated vault; secrets are not securely encrypted")
    key = 0xAA
    return bytes([b ^ key for b in ciphertext])

def save_secrets(secrets: dict) -> bool:
    """Encrypts and persists the given dictionary of secrets to disk."""
    global _CACHE
    try:
        os.makedirs(VAULT_DIR, exist_ok=True)
        raw_json = json.dumps(secrets).encode("utf-8")
        encrypted = _encrypt_bytes(raw_json)
        with open(VAULT_PATH, "wb") as f:
            f.write(encrypted)
        _CACHE = dict(secrets)
        return True
    except Exception as e:
        print(f"[Vault] Failed to save secrets: {e}")
        return False

def load_secrets() -> dict:
    """Loads and decrypts all secrets from the vault into memory."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    if not os.path.exists(VAULT_PATH):
        _CACHE = {}
        return _CACHE

    try:
        with open(VAULT_PATH, "rb") as f:
            encrypted = f.read()
        plaintext = _decrypt_bytes(encrypted)
        _CACHE = json.loads(plaintext.decode("utf-8"))
        return _CACHE
    except Exception as e:
        print(f"[Vault] Failed to decrypt secrets vault: {e}")
        _CACHE = {}
        return _CACHE

def get_secret(key: str, default: str = "") -> str:
    """Retrieves a secret by key:
    1. Checks active process environment (os.environ)
    2. Checks encrypted vault
    3. Returns default if not found
    """
    env_val = os.environ.get(key)
    if env_val and env_val.strip():
        return env_val.strip()

    secrets = load_secrets()
    val = secrets.get(key)
    if val and str(val).strip():
        return str(val).strip()

    return default

def set_secret(key: str, value: str) -> bool:
    """Sets or updates a single secret in the encrypted vault."""
    secrets = load_secrets()
    secrets[key] = value.strip()
    return save_secrets(secrets)

def mask_secret(value: str) -> str:
    """Returns a masked version of a sensitive value for safe display."""
    if not value:
        return "<not set>"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"

def list_keys_status() -> dict:
    """Returns a dictionary of all known keys and their masked status."""
    secrets = load_secrets()
    return {k: mask_secret(v) for k, v in secrets.items()}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "status":
            print("=== JARVIS ENCRYPTED VAULT STATUS ===")
            keys = list_keys_status()
            if not keys:
                print("Vault is empty or not yet initialized.")
            else:
                for k, v in keys.items():
                    print(f"  {k}: {v}")
            print(f"Vault location: {VAULT_PATH}")
        elif cmd == "set" and len(sys.argv) >= 4:
            k = sys.argv[2]
            v = sys.argv[3]
            if set_secret(k, v):
                print(f"✓ Successfully stored encrypted key '{k}'.")
            else:
                print(f"✗ Failed to store key '{k}'.")
        elif cmd == "get" and len(sys.argv) >= 3:
            k = sys.argv[2]
            print(f"{k}: {mask_secret(get_secret(k))}")
        else:
            print("Usage: python vault.py [status | set KEY VALUE | get KEY]")
    else:
        print("Jarvis Vault module loaded.")
