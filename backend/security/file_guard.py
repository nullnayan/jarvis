# FILE: backend/security/file_guard.py
# Shared guard for review, audit, and patching. Prevents Jarvis from reading or
# editing files outside the project, or editing its own guard rails.

import os

# Project root derived from this file's location: backend/security/file_guard.py -> project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_inside_project(path: str) -> bool:
    """True if path is inside the project root (rejects .. traversal and symlinks)."""
    try:
        real = os.path.realpath(path)
        root = os.path.realpath(PROJECT_ROOT)
        return os.path.commonpath([real, root]) == root
    except (ValueError, OSError):
        return False


# Files that may be read for review but never edited.
RESTRICTED_NAMES = {
    "vault.py", "credentials.py", "permissions.py", "file_guard.py",
    "config.py", ".env", ".env.example", ".secrets.enc",
}


def is_restricted_file(path: str) -> bool:
    """True if the file is security-sensitive and should not be read/edited freely."""
    name = os.path.basename(path).lower()
    if name in RESTRICTED_NAMES:
        return True
    if name.endswith(".enc"):
        return True
    return False


# Files that can never be written by Jarvis (its own guard rails).
WRITE_BLOCKED_DIRS = ("security", "data")
WRITE_BLOCKED_NAMES = {
    "config.py", "requirements.txt", "requirements-dev.txt",
}


def is_writable_source(path: str) -> bool:
    """Stricter subset of is_restricted_file: additionally denies guard-rail files."""
    if not is_inside_project(path):
        return False
    name = os.path.basename(path).lower()
    if name in WRITE_BLOCKED_NAMES:
        return False
    if name.startswith(".env") or name.endswith(".enc"):
        return False
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(PROJECT_ROOT))
    parts = rel.split(os.sep)
    if any(p in WRITE_BLOCKED_DIRS for p in parts):
        return False
    if any(p in (".git", ".venv", "node_modules", "__pycache__") for p in parts):
        return False
    return True
