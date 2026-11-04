# FILE: app_readiness.py
# Intelligent app window polling and learning timing database.
# Replaces fragile hardcoded time.sleep() calls with responsiveness checks and learned launch timing.
import os
import time
import json
import ctypes
from datetime import datetime
import pygetwindow as gw

TIMINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_timings.json")

user32 = ctypes.windll.user32

def _is_window_responsive(hwnd) -> bool:
    """Checks if a window is actively pumping messages and not hung/loading."""
    if not hwnd:
        return False
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_ulong()
    # Send WM_NULL (0x0000) with a 800ms timeout
    ret = user32.SendMessageTimeoutW(
        hwnd, 0x0000, 0, 0, SMTO_ABORTIFHUNG, 800, ctypes.byref(result)
    )
    return ret != 0

def _load_timings() -> dict:
    if os.path.exists(TIMINGS_FILE):
        try:
            with open(TIMINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[AppReadiness] Error loading timings: {e}")
    return {}

def _save_timings(timings: dict) -> None:
    try:
        with open(TIMINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(timings, f, indent=2)
    except Exception as e:
        print(f"[AppReadiness] Error saving timings: {e}")

def is_process_running(pattern: str) -> bool:
    """Checks if any currently running process matches the given pattern."""
    try:
        import psutil
        pat = pattern.lower()
        for p in psutil.process_iter(['name']):
            try:
                name = (p.info.get('name') or '').lower()
                if pat in name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return False

def record_launch_timing(app_name: str, duration_sec: float, is_cold: bool = False) -> None:
    """Records an app's launch duration and updates rolling metrics separated by cold/warm."""
    try:
        timings = _load_timings()
        duration_ms = int(duration_sec * 1000)
        app_data = timings.get(app_name, {
            "samples": [],
            "cold_samples": [],
            "warm_samples": [],
            "avg_launch_ms": duration_ms,
            "avg_cold_ms": duration_ms if is_cold else 0,
            "avg_warm_ms": 0 if is_cold else duration_ms,
            "min_launch_ms": duration_ms,
            "max_launch_ms": duration_ms,
            "total_launches": 0,
        })

        samples = app_data.setdefault("samples", [])
        samples.append(duration_ms)
        if len(samples) > 20:
            samples.pop(0)

        bucket_key = "cold_samples" if is_cold else "warm_samples"
        bucket = app_data.setdefault(bucket_key, [])
        bucket.append(duration_ms)
        if len(bucket) > 15:
            bucket.pop(0)

        if app_data.get("cold_samples"):
            app_data["avg_cold_ms"] = int(sum(app_data["cold_samples"]) / len(app_data["cold_samples"]))
        if app_data.get("warm_samples"):
            app_data["avg_warm_ms"] = int(sum(app_data["warm_samples"]) / len(app_data["warm_samples"]))

        app_data["samples"] = samples
        app_data["avg_launch_ms"] = int(sum(samples) / len(samples))
        app_data["min_launch_ms"] = min(samples)
        app_data["max_launch_ms"] = max(samples)
        app_data["total_launches"] = app_data.get("total_launches", 0) + 1
        app_data["last_updated"] = datetime.now().isoformat()

        timings[app_name] = app_data
        _save_timings(timings)
        mode = "Cold" if is_cold else "Warm"
        print(f"[AppReadiness] Learned {app_name} ({mode}) launch time: {duration_ms}ms (Avg: {app_data['avg_launch_ms']}ms)")
    except Exception as e:
        print(f"[AppReadiness] Failed to record timing for {app_name}: {e}")

def get_recommended_wait(app_name: str, default_wait: float = 15.0, is_cold: bool = False) -> float:
    """Gets recommended max timeout based on historical launch times and cold/warm state."""
    from config import APP_COLD_START_MIN_WAIT
    timings = _load_timings()
    if app_name in timings:
        if is_cold and timings[app_name].get("avg_cold_ms", 0) > 0:
            avg_cold_s = timings[app_name]["avg_cold_ms"] / 1000.0
            return max(APP_COLD_START_MIN_WAIT, avg_cold_s * 1.8)
        avg_s = timings[app_name].get("avg_launch_ms", 0) / 1000.0
        if avg_s > 0:
            floor = APP_COLD_START_MIN_WAIT if is_cold else 2.0
            return max(floor, avg_s * 1.8)
    return max(default_wait, APP_COLD_START_MIN_WAIT if is_cold else 5.0)

def wait_for_app(app_name: str, window_keyword: str, max_wait: float = None, poll_interval: float = 0.25, is_cold: bool = False) -> bool:
    """
    Polls for an application window to exist, be visible, and responsive.
    Learns launch timing automatically with cold-start awareness.
    """
    if max_wait is None:
        max_wait = get_recommended_wait(app_name, default_wait=15.0, is_cold=is_cold)

    keyword = window_keyword.lower()
    start = time.time()
    print(f"[AppReadiness] Waiting for '{app_name}' ({'cold' if is_cold else 'warm'}) matching '{keyword}' max {max_wait:.1f}s...")

    while time.time() - start <= max_wait:
        try:
            windows = gw.getAllWindows()
            for w in windows:
                title = (w.title or "").strip().lower()
                if keyword in title and w._hWnd and user32.IsWindowVisible(w._hWnd):
                    # Found matching window; verify it's responsive
                    if _is_window_responsive(w._hWnd):
                        elapsed = time.time() - start
                        record_launch_timing(app_name, elapsed, is_cold=is_cold)
                        return True
        except Exception as e:
            print(f"[AppReadiness] Polling error: {e}")
        time.sleep(poll_interval)

    print(f"[AppReadiness] Timeout waiting for '{app_name}' after {max_wait:.1f}s")
    return False

def wait_for_app_interactive(app_name: str, window_keyword: str, max_wait: float = 4.0, poll_interval: float = 0.2) -> bool:
    """
    Waits until the window not only exists and responds to WM_NULL,
    but has fully initialized its client area (non-zero width/height).
    """
    keyword = window_keyword.lower()
    start = time.time()
    rect = ctypes.wintypes.RECT()

    while time.time() - start <= max_wait:
        try:
            windows = gw.getAllWindows()
            for w in windows:
                title = (w.title or "").strip().lower()
                if keyword in title and w._hWnd and user32.IsWindowVisible(w._hWnd):
                    if user32.GetClientRect(w._hWnd, ctypes.byref(rect)):
                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        if width > 100 and height > 100 and _is_window_responsive(w._hWnd):
                            return True
        except Exception:
            pass
        time.sleep(poll_interval)
    return False
