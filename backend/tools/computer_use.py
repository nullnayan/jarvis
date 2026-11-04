"""Conservative GUI automation with window-relative coordinates and bounded retries."""
import ctypes
from ctypes import wintypes
import re
import time

from logger import get_logger

_log = get_logger(__name__)


def window_rect_to_header_button(rect, button: str = "voice"):
    """Return absolute WhatsApp header coordinates from an absolute window rect."""
    left, top, right, _bottom = rect
    offset = 128 if button == "video" else 174
    return left + max(40, (right - left) - offset), top + 62


def find_window_rect(title_hint: str):
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title_hint.lower() in title.value.lower():
                rect = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append((hwnd, (rect.left, rect.top, rect.right, rect.bottom)))
                return False
        return True
    user32.EnumWindows(callback_type(visit), 0)
    return found[0] if found else (None, None)


def computer_use(params: dict) -> str:
    """Perform a confirmed, bounded click task in a named application window."""
    task, app = str(params.get("task", "")).strip(), str(params.get("app", "")).strip()
    if not task or not app:
        return "Tell me which application and control to use, boss."
    try:
        hwnd, rect = find_window_rect(app)
        if not hwnd or not rect:
            return f"I could not find the {app} window, boss."
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        label = "video" if re.search(r"video|camera", task, re.I) else "voice"
        if "call" not in task.lower():
            return "I could not safely identify that control, boss."
        import pyautogui
        x, y = window_rect_to_header_button(rect, label)
        if not (rect[0] <= x < rect[2] and rect[1] <= y < rect[3]):
            return "The requested control is outside the application window, boss."
        for attempt in range(3):
            try:
                pyautogui.click(x, y)
                _log.info("computer_use rung=win32-window-relative app=%s attempt=%s", app, attempt + 1)
                return f"I used the {app} {label} call control, boss."
            except Exception as click_exc:
                _log.warning("computer_use click attempt %s failed: %s", attempt + 1, click_exc)
                time.sleep(0.5)
        return "I could not complete that GUI action after 3 attempts, boss."
    except Exception as exc:
        _log.warning("computer_use failed: %s", exc)
        return "An error occurred, boss."
