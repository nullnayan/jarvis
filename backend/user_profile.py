"""Small persistent user profile with safe defaults."""

import json
import os
import tempfile

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")

DEFAULTS = {
    "name": "User",
    "city": "London",
    "language": "en",
    "voice_rate": "+0%",
    "voice_pitch": "+0Hz",
    "idle_gate_enabled": True,
    "conversation_timeout": 10,
    "pyautogui_failsafe": True,
}


def _write(profile: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="profile-", suffix=".json", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(profile, handle, indent=2, ensure_ascii=False)
        os.replace(temp_path, PROFILE_PATH)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _load() -> dict:
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {**DEFAULTS, **data} if isinstance(data, dict) else dict(DEFAULTS)
    except FileNotFoundError:
        profile = dict(DEFAULTS)
        try:
            _write(profile)
        except OSError:
            pass
        return profile
    except (OSError, ValueError, TypeError):
        return dict(DEFAULTS)


def all() -> dict:
    return _load()


def get(key: str, default=None):
    return _load().get(key, DEFAULTS.get(key, default))


def set(key: str, value) -> dict:
    profile = _load()
    if key not in DEFAULTS:
        raise KeyError(f"Unknown profile field: {key}")
    profile[key] = value
    _write(profile)
    return profile
