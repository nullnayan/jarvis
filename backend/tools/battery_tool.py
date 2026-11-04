# FILE: battery_tool.py
# Queries battery status and power source using psutil.
import psutil

def get_battery_status(params: dict) -> str:
    try:
        battery = psutil.sensors_battery()
        if not battery:
            return "This computer is running on direct AC power with no battery detected, boss."

        pct = int(battery.percent)
        plugged = battery.power_plugged
        charging_str = "plugged in and charging" if plugged else "running on battery"

        # Estimate remaining time if discharging
        if not plugged and battery.secsleft > 0 and battery.secsleft != psutil.POWER_TIME_UNLIMITED:
            hrs = battery.secsleft // 3600
            mins = (battery.secsleft % 3600) // 60
            time_str = f" with approximately {hrs} hours and {mins} minutes remaining"
        else:
            time_str = ""

        return f"Battery is at {pct}%, {charging_str}{time_str}, boss."
    except Exception as e:
        print(f"[BatteryTool] Error: {e}")
        return "An error occurred, boss."
