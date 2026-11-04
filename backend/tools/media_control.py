# FILE: media_control.py
# Controls system-wide media playback (play, pause, next, previous, stop).
import pyautogui

def media_control(params: dict) -> str:
    action = str(params.get("action", "")).lower().strip()
    try:
        if action in ("play", "pause", "playpause", "toggle", "resume"):
            pyautogui.press("playpause")
            return "Toggled media playback, boss."
        elif action in ("next", "skip", "forward"):
            pyautogui.press("nexttrack")
            return "Skipped to next track, boss."
        elif action in ("previous", "prev", "back", "rewind"):
            pyautogui.press("prevtrack")
            return "Skipped to previous track, boss."
        elif action in ("stop",):
            pyautogui.press("stop")
            return "Stopped media playback, boss."
        else:
            return "An error occurred, boss."
    except Exception as e:
        print(f"[MediaControl] Error: {e}")
        return "An error occurred, boss."
