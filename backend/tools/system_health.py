# FILE: backend/tools/system_health.py
# System health monitoring: CPU, RAM, disk, battery, and top resource consumers.

import psutil
import shutil

def system_health(params: dict = None) -> str:
    try:
        cpu_pct = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        mem_used_gb = round(mem.used / (1024**3), 1)
        mem_total_gb = round(mem.total / (1024**3), 1)

        # Disk usage for C:
        disk = shutil.disk_usage("C:\\")
        disk_free_gb = round(disk.free / (1024**3), 1)
        disk_total_gb = round(disk.total / (1024**3), 1)

        # Battery
        battery = psutil.sensors_battery()
        bat_str = ""
        if battery:
            status = "charging" if battery.power_plugged else "on battery"
            bat_str = f", battery is at {battery.percent}% ({status})"

        summary = (
            f"CPU is running at {cpu_pct}%, "
            f"RAM usage is {mem_used_gb} of {mem_total_gb} gigabytes ({mem.percent}%), "
            f"drive C has {disk_free_gb} gigabytes free of {disk_total_gb} gigabytes{bat_str}, boss."
        )
        return summary
    except Exception as e:
        print(f"[SystemHealth] Error: {e}")
        return "An error occurred while checking system health, boss."
