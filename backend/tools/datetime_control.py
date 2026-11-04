# FILE: datetime_control.py
# Modifies and manages Windows Date & Time settings: automatic sync (NTP), manual date/time setting, and random time.
import random
import re
import subprocess
from datetime import datetime, timedelta

def datetime_control(params: dict) -> str:
    """Controls Windows date and time settings."""
    action = str(params.get("action", "get")).lower().strip()
    value = str(params.get("value", "")).strip()

    try:
        if action in ("auto", "automatic", "sync", "set_automatic"):
            ps_cmd = (
                "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\W32Time\\Parameters' -Name 'Type' -Value 'NTP'; "
                "Start-Service w32time -ErrorAction SilentlyContinue; "
                "w32tm /resync /force"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10
            )
            out = (res.stdout + res.stderr).lower()
            if "access is denied" in out or "privilege" in out:
                return "Setting time to automatic requires administrator privileges, boss. Please run the backend as administrator."
            return "Date and time have been synchronized to automatic network time, boss."

        elif action in ("random", "randomly", "change_randomly"):
            # Shift time by a random offset (-5 to +5 hours)
            now = datetime.now()
            hours_shift = random.choice([-4, -3, -2, -1, 1, 2, 3, 4])
            mins_shift = random.randint(1, 59)
            new_time = now + timedelta(hours=hours_shift, minutes=mins_shift)
            time_str = new_time.strftime("%H:%M:%S")
            ps_cmd = f"Set-Date -Date (Get-Date '{time_str}')"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=8
            )
            out = (res.stdout + res.stderr).lower()
            if "access is denied" in out or "privilege" in out:
                return "Modifying system time requires administrator privileges, boss."
            return f"System time randomly changed to {time_str}, boss."

        elif action in ("set", "set_date", "set_time", "manual"):
            if not value:
                return "Please specify the date or time you would like me to set, boss."
            ps_cmd = f"Set-Date -Date (Get-Date '{value}')"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=8
            )
            out = (res.stdout + res.stderr).lower()
            if "access is denied" in out or "privilege" in out:
                return "Modifying the system date and time requires administrator privileges, boss."
            return f"System date and time updated to {value}, boss."

        elif action in ("get", "status", "info"):
            now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
            return f"Currently it is {now_str}, boss."

        return f"Completed date and time action: {action}, boss."
    except Exception as e:
        print(f"[DateTimeControl] Error: {e}")
        return "An error occurred while managing date and time, boss."
