# FILE: performance_control.py
# Controls monitor refresh rate (Hz), Windows power plans, and battery saver.
import ctypes
import re
import subprocess
import os
from ctypes import wintypes

user32 = ctypes.windll.user32

class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmOrientation", ctypes.c_short),
        ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short),
        ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short),
        ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short),
        ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]

POWER_PLANS = {
    "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "power_saving": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "eco": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "ultimate": "e9a42b02-d5df-448d-aa00-03f14749eb61",
}

def _get_current_display_frequency() -> int:
    devmode = DEVMODEW()
    devmode.dmSize = ctypes.sizeof(DEVMODEW)
    ENUM_CURRENT_SETTINGS = -1
    if user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
        return devmode.dmDisplayFrequency
    return 60

def _set_display_frequency(target_hz: int) -> tuple[bool, str]:
    ENUM_CURRENT_SETTINGS = -1
    devmode = DEVMODEW()
    devmode.dmSize = ctypes.sizeof(DEVMODEW)
    if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
        return False, "Could not query current display settings, boss."

    devmode.dmDisplayFrequency = target_hz
    devmode.dmFields = 0x00400000  # DM_DISPLAYFREQUENCY
    CDS_UPDATEREGISTRY = 0x00000001
    DISP_CHANGE_SUCCESSFUL = 0

    res = user32.ChangeDisplaySettingsExW(None, ctypes.byref(devmode), None, CDS_UPDATEREGISTRY, None)
    if res == DISP_CHANGE_SUCCESSFUL:
        return True, f"Display refresh rate adjusted to {target_hz}Hz, boss."
    elif res == -2:
        return False, f"The refresh rate {target_hz}Hz is not supported by your display, boss."
    else:
        return False, f"Unable to change refresh rate to {target_hz}Hz (error code {res}), boss."

def performance_control(params: dict) -> str:
    """Controls display refresh rate, power plans, and battery saver."""
    action = str(params.get("action", "")).lower().strip()
    value = str(params.get("value", "")).lower().strip()

    try:
        # Refresh rate commands
        if "refresh" in action or "hz" in action or "hertz" in action or ("rate" in action and any(char.isdigit() for char in action + value)):
            # Extract number
            match = re.search(r"(\d+)", value or action)
            if match:
                hz = int(match.group(1))
                success, msg = _set_display_frequency(hz)
                return msg
            current = _get_current_display_frequency()
            return f"Current display refresh rate is {current}Hz, boss."

        elif action in ("get_refresh_rate", "check_refresh_rate", "refresh_rate_status"):
            current = _get_current_display_frequency()
            return f"Your monitor is currently running at {current}Hz, boss."

        # Power plan commands
        elif "power" in action or "plan" in action or "scheme" in action or "saver" in action:
            # Check for specific plan requests
            matched_guid = None
            plan_name = "balanced"
            for key, guid in POWER_PLANS.items():
                if key in action or key in value:
                    matched_guid = guid
                    plan_name = key.replace("_", " ")
                    break

            if matched_guid:
                subprocess.run(["powercfg", "/setactive", matched_guid], capture_output=True, timeout=5)
                return f"Switched power scheme to {plan_name}, boss."

            # Query current plan
            res = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=5)
            out = res.stdout.strip()
            match = re.search(r"\((.*?)\)", out)
            current_name = match.group(1) if match else "Balanced"
            return f"Current active power plan is {current_name}, boss."

        elif action in ("battery_saver", "power_saving_mode"):
            if value in ("on", "enable", "start"):
                # Open settings or trigger power saver
                subprocess.run(["powercfg", "/setactive", POWER_PLANS["power_saver"]], capture_output=True, timeout=5)
                return "Power saver mode activated, boss."
            elif value in ("off", "disable", "stop"):
                subprocess.run(["powercfg", "/setactive", POWER_PLANS["balanced"]], capture_output=True, timeout=5)
                return "Restored balanced power plan, boss."
            else:
                os.startfile("ms-settings:batterysaver")
                return "Opening battery saver settings, boss."

        elif action in ("settings", "open"):
            os.startfile("ms-settings:powersleep")
            return "Opening power and sleep settings, boss."

        return f"Performance setting action '{action}' completed, boss."
    except Exception as e:
        print(f"[PerformanceControl] Error: {e}")
        return "An error occurred while modifying performance settings, boss."
