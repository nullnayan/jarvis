# FILE: messages.py
# Creates and parses the compact JSON messages exchanged with the Electron interface.
import json
import math

def _message(kind, value=None):
    payload = {"type": kind}
    if value is not None:
        payload["value"] = value
    return json.dumps(payload)


def settings_values_msg(values: dict):
    """Pushes the current user-profile settings to the UI (for the settings panel)."""
    return _message("settings_values", values)

def state_msg(state):
    return _message("state", state)

def caption_msg(text):
    return _message("caption", text)

def amplitude_msg(value):
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            val = 0.0
    except (ValueError, TypeError):
        val = 0.0
    return _message("amplitude", round(val, 4))

def persona_msg(persona):
    return _message("persona", persona)

def user_speech_msg(text):
    return _message("user_speech", text)

def jarvis_speech_msg(text):
    return _message("jarvis_speech", text)

def dodge_msg(position="top-left"):
    return _message("dodge", position)

def undodge_msg():
    return _message("undodge")

def minimize_msg():
    return _message("minimize")

def restore_msg():
    return _message("restore")

def shrink_to_dot_msg():
    return _message("shrink_to_dot")

def restore_orb_msg():
    return _message("restore_orb")

def hand_gesture_msg(data):
    return _message("hand_gesture", data)

def fullscreen_toggle_msg(enable=True):
    return _message("fullscreen_toggle", bool(enable))

def app_exit_msg():
    return _message("app_exit")

def approval_request_msg(approval_id, files):
    return _message("approval_request", {"id": approval_id, "files": files})

def approval_result_msg(approval_id, approved):
    return _message("approval_result", {"id": approval_id, "approved": bool(approved)})

def self_audit_msg(findings):
    return _message("self_audit", findings)

def self_code_msg(payload):
    return _message("self_code", payload)

def plan_progress_msg(step, total, status):
    return _message("plan_progress", {"step": step, "total": total, "status": status})

def permission_request_msg(tool, reason):
    return _message("permission_request", {"tool": tool, "reason": reason})

def enhanced_prompt_msg(text):
    return _message("enhanced_prompt", text)

def phone_status_msg(state, device=""):
    return _message("phone_status", {"state": state, "device": device})


def parse_message(raw):
    try:
        message = json.loads(raw)
        return message if isinstance(message, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}
