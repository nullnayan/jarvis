# FILE: backend/tools/context.py
# Detects foreground application, active VS Code file, browser title, and screen context.

import ctypes
import psutil
import os
import re

def get_active_window() -> dict:
    """Returns the title and process name of the current foreground window."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"title": "", "process": "", "app": ""}

        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pname = psutil.Process(pid.value).name().lower() if pid.value else ""

        return {"title": title, "process": pname, "app": os.path.splitext(pname)[0]}
    except Exception as e:
        return {"title": "", "process": "", "app": "", "error": str(e)}

def get_vscode_active_file() -> str:
    """Extracts the currently active file from a VS Code window title."""
    try:
        info = get_active_window()
        title = info.get("title", "")
        if "visual studio code" in title.lower() or "code" in info.get("process", "").lower():
            # Format in VS Code is usually "filename.ext - folder - Visual Studio Code"
            parts = title.split(" - ")
            if parts and len(parts) >= 2:
                candidate = parts[0].strip().lstrip("● ")
                return candidate
    except Exception:
        pass
    return ""

def get_context_summary() -> str:
    """Provides a brief context string for LLM prompt injection."""
    w = get_active_window()
    if not w.get("title"):
        return ""
    active_file = get_vscode_active_file()
    file_info = f", active file: '{active_file}'" if active_file else ""
    return f"Active window: '{w['title']}' (app: {w.get('app', 'unknown')}{file_info})"
