# FILE: backend/tools/clipboard_history.py
# Background clipboard monitor keeping a rolling history of the last 20 entries.

import time
import threading
import pyperclip

_clipboard_buffer = []
_monitor_thread = None
_running = False

def _monitor_loop():
    global _running
    last_text = ""
    while _running:
        try:
            current = pyperclip.paste()
            if current and current != last_text:
                last_text = current
                entry = {
                    "text": current,
                    "timestamp": time.strftime("%H:%M:%S")
                }
                _clipboard_buffer.append(entry)
                if len(_clipboard_buffer) > 20:
                    _clipboard_buffer.pop(0)
        except Exception:
            pass
        time.sleep(1.5)

def start_clipboard_monitor():
    global _monitor_thread, _running
    if not _running:
        _running = True
        _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        _monitor_thread.start()

def clipboard_history(params: dict) -> str:
    start_clipboard_monitor()
    action = params.get("action", "list").lower().strip()
    idx = params.get("index", 1)

    if action in ("list", "show", "recent"):
        if not _clipboard_buffer:
            return "Your clipboard history is currently empty, boss."
        items = [f"[{e['timestamp']}] {e['text'][:40]}..." for e in reversed(_clipboard_buffer[-5:])]
        return "Recent clipboard items: " + " | ".join(items)

    elif action in ("get", "paste", "copy"):
        try:
            num = int(idx)
            if 1 <= num <= len(_clipboard_buffer):
                target = _clipboard_buffer[-num]
                pyperclip.copy(target["text"])
                return f"Copied clipboard item #{num} back to your active clipboard, boss."
        except Exception:
            pass
        return "Invalid clipboard index, boss."

    return "Clipboard action not recognized, boss."
