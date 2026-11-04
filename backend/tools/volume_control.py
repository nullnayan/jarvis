# FILE: volume_control.py
# Controls Windows system volume using pycaw.
from pycaw.pycaw import AudioUtilities

def volume_control(params: dict) -> str:
    action = str(params.get("action", "")).lower().strip()
    try:
        device = AudioUtilities.GetSpeakers()
        if not device:
            return "No audio output device found"
        volume = device.EndpointVolume

        if action in ("status", "get", "check", "level", "current", ""):
            current = int(volume.GetMasterVolumeLevelScalar() * 100)
            is_muted = bool(volume.GetMute())
            status_str = f"Volume is at {current}%, boss."
            if is_muted:
                status_str += " Note that system audio is currently muted."
            return status_str
        elif action == "mute":
            volume.SetMute(1, None)
            return "Muted system volume, boss."
        elif action == "unmute":
            volume.SetMute(0, None)
            return "Unmuted system volume, boss."
        elif action in ("up", "increase"):
            current = volume.GetMasterVolumeLevelScalar()
            new_vol = min(current + 0.1, 1.0)
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"Volume increased to {int(new_vol * 100)}%, boss."
        elif action in ("down", "decrease", "lower"):
            current = volume.GetMasterVolumeLevelScalar()
            new_vol = max(current - 0.1, 0.0)
            volume.SetMasterVolumeLevelScalar(new_vol, None)
            return f"Volume decreased to {int(new_vol * 100)}%, boss."

        # Check for numeric or percentage values (e.g. "50", "50%", "75 %")
        digits = "".join([c for c in action if c.isdigit()])
        if digits:
            level = max(0, min(100, int(digits)))
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"Volume set to {level}%, boss."

        # Fallback to current status
        current = int(volume.GetMasterVolumeLevelScalar() * 100)
        return f"Volume is currently at {current}%, boss."
    except Exception as e:
        print(f"[VolumeControl] Error: {e}")
        return "An error occurred, boss."
