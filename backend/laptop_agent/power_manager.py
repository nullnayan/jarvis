# FILE: backend/laptop_agent/power_manager.py
"""
Windows Power & Away Mode Manager for Jarvis Laptop Call Secretary.
Keeps the CPU, network, and Bluetooth active at minimal power (<3W)
while the screen is completely black/off and the laptop lid is closed.
"""

import ctypes
import logging
import subprocess

log = logging.getLogger("jarvis.power")

# Windows API constants for SetThreadExecutionState
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


class PowerManager:
    """Manages Windows low-power Away Mode and power scheme settings."""

    def __init__(self):
        self._away_mode_active = False

    def enable_away_mode(self) -> bool:
        """
        Enables Windows Away Mode.
        In Away Mode, Windows dims/shuts off the display and suspends user apps,
        but keeps background audio, network, and Bluetooth services active at minimal power.
        """
        try:
            res = ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
            self._away_mode_active = res != 0
            log.info(f"Windows Away Mode ENABLED: {self._away_mode_active}")
            return self._away_mode_active
        except Exception as e:
            log.error(f"Failed to enable Away Mode: {e}")
            return False

    def disable_away_mode(self) -> None:
        """Restores normal Windows power management."""
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            self._away_mode_active = False
            log.info("Windows Away Mode DISABLED — restored default sleep.")
        except Exception as e:
            log.error(f"Failed to disable Away Mode: {e}")

    def configure_power_plan(self, screen_timeout_minutes: int = 3) -> bool:
        """
        Configures the active Windows power plan:
        - Standby timeout on AC: Never (0)
        - Monitor turn-off on AC: X minutes (pitch black room)
        - Lid close action on AC: Do nothing (allows closing the laptop)
        """
        try:
            # 1. Standby timeout = 0 (never sleep system while on AC)
            subprocess.run(["powercfg", "/change", "standby-timeout-ac", "0"], capture_output=True, check=True)

            # 2. Monitor timeout = screen_timeout_minutes
            subprocess.run(["powercfg", "/change", "monitor-timeout-ac", str(screen_timeout_minutes)], capture_output=True, check=True)

            # 3. Lid close action = 0 (Do nothing)
            # GUID: Balanced scheme, SUB_BUTTONS, LIDACTION = 0
            scheme_res = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True)
            output = scheme_res.stdout
            if "GUID:" in output:
                scheme_guid = output.split("GUID:")[1].split("(")[0].strip()
                cmd = [
                    "powercfg", "/setacvalueindex", scheme_guid,
                    "4f971e89-eebd-4455-a8de-9e59040e7347",
                    "5ca83367-6e45-459f-a27b-476b1d01c936",
                    "0",
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                subprocess.run(["powercfg", "/setactive", scheme_guid], capture_output=True, check=True)

            log.info(f"Power plan configured: Lid=DoNothing, Sleep=Never, Display={screen_timeout_minutes}m")
            return True
        except Exception as e:
            log.error(f"Error configuring power plan: {e}")
            return False


power_manager = PowerManager()
