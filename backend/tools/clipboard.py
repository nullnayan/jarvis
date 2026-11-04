# FILE: clipboard.py
# Reads and writes system clipboard.
import pyperclip

def clipboard(params: dict) -> str:
    action = params.get("action", "read").lower().strip()
    try:
        if action == "read":
            text = pyperclip.paste()
            if not text:
                return "The clipboard is empty, boss."
            return f"Clipboard contents: {text[:300]}, boss."
        elif action == "write":
            text = params.get("text", "")
            pyperclip.copy(text)
            return "Copied to clipboard, boss."
        else:
            return "An error occurred, boss."
    except Exception as e:
        print(f"[Clipboard] Error: {e}")
        return "An error occurred, boss."
