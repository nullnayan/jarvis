# FILE: brightness_control.py
# Controls screen brightness using screen_brightness_control.
import screen_brightness_control as sbc

def brightness_control(params: dict) -> str:
    action = str(params.get("action", "")).lower().strip()
    try:
        current_list = sbc.get_brightness()
        current = current_list[0] if isinstance(current_list, list) and current_list else 50

        if action in ("up", "increase", "brighter"):
            new_val = min(100, current + 15)
            sbc.set_brightness(new_val)
            return f"Brightness increased to {new_val}%, boss."
        elif action in ("down", "decrease", "dim", "lower"):
            new_val = max(10, current - 15)
            sbc.set_brightness(new_val)
            return f"Brightness decreased to {new_val}%, boss."
        elif action in ("max", "maximum", "full"):
            sbc.set_brightness(100)
            return "Brightness set to maximum, boss."
        elif action in ("min", "minimum", "lowest"):
            sbc.set_brightness(10)
            return "Brightness set to minimum, boss."
        elif action in ("get", "status", "current", "what"):
            return f"Current screen brightness is at {current}%, boss."
        elif action.isdigit():
            level = max(0, min(100, int(action)))
            sbc.set_brightness(level)
            return f"Brightness set to {level}%, boss."
        else:
            # Fallback: try parsing number from action string (e.g. "50%", "75")
            digits = "".join([c for c in action if c.isdigit()])
            if digits:
                level = max(0, min(100, int(digits)))
                sbc.set_brightness(level)
                return f"Brightness set to {level}%, boss."
            return "An error occurred, boss."
    except Exception as e:
        print(f"[Brightness] Error: {e}")
        return "An error occurred, boss."
