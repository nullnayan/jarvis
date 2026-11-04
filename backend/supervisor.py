"""Small stdlib supervisor that restarts the Jarvis backend after a crash."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOCK = DATA / "supervisor.lock"
HEARTBEAT = DATA / "heartbeat"
RESTART = DATA / "restart_requested"
SELF_FIX_STATE = DATA / "self_fix_state.json"
BACKOFF = (2, 5, 15, 60)


def _live_pid(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_lock() -> bool:
    DATA.mkdir(exist_ok=True)
    try:
        if LOCK.exists() and _live_pid(int(LOCK.read_text())):
            return False
    except (OSError, ValueError):
        pass
    LOCK.write_text(str(os.getpid()))
    return True


def _maybe_rollback_self_fix(uptime_seconds: float) -> bool:
    """If the backend crashed quickly after a self-fix was applied, revert it.
    Returns True if a rollback was attempted (caller should restart immediately)."""
    if uptime_seconds >= 10:
        return False
    try:
        if not SELF_FIX_STATE.exists():
            return False
        state = json.loads(SELF_FIX_STATE.read_text())
        applied_at_str = state.get("last_applied_at", "")
        if not applied_at_str:
            return False
        from datetime import datetime, timezone
        applied_at = datetime.fromisoformat(applied_at_str)
        age = (datetime.now(timezone.utc) - applied_at).total_seconds()
        # Only rollback if the fix was applied recently (within 5 minutes)
        if age > 300:
            return False
        print(f"[Supervisor] Crash <10s after self-fix applied {age:.0f}s ago — rolling back.")
        sys.path.insert(0, str(ROOT))
        from self_dev.patcher import revert_last_self_fix
        ok, msg = revert_last_self_fix()
        print(f"[Supervisor] Rollback {'succeeded' if ok else 'failed'}: {msg}")
        # Remove state so we don't rollback again on the next crash
        SELF_FIX_STATE.unlink(missing_ok=True)
        return True
    except Exception as exc:
        print(f"[Supervisor] Rollback error: {exc}")
        return False


def _is_main_running() -> bool:
    try:
        import psutil
        my_pid = os.getpid()
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            if p.info['pid'] != my_pid and p.info['name'] and 'python' in p.info['name'].lower():
                cmdline = p.info.get('cmdline') or []
                if any(arg.endswith('main.py') or 'main.py' in arg for arg in cmdline if not arg.startswith('-c')):
                    return True
    except Exception:
        pass
    return False


def main() -> int:
    if not _acquire_lock():
        print("Jarvis supervisor is already running.")
        return 1
    child = None
    try:
        failures = 0
        while True:
            # If main.py was already started externally (e.g. by Jarvis.bat), stand by
            if _is_main_running():
                print("[Supervisor] Detected main.py already running. Standing by...")
                while _is_main_running():
                    time.sleep(3)
                print("[Supervisor] External main.py exited. Taking over supervisor control...")

            # A heartbeat from a previous process must not make a fresh child
            # look healthy before it has written its first heartbeat.
            HEARTBEAT.unlink(missing_ok=True)
            child = subprocess.Popen(
                [sys.executable, "-u", "main.py"],
                cwd=ROOT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            started = time.monotonic()
            while child.poll() is None:
                time.sleep(2)
                if HEARTBEAT.exists() and time.time() - HEARTBEAT.stat().st_mtime > 15:
                    child.terminate()
                    break
            uptime = time.monotonic() - started
            immediate = RESTART.exists()
            if immediate:
                RESTART.unlink(missing_ok=True)
                failures = 0
                continue
            # Crash-loop self-fix rollback: revert and restart immediately if applicable
            if _maybe_rollback_self_fix(uptime):
                failures = 0
                continue
            failures = failures + 1 if uptime < 10 else 0
            time.sleep(BACKOFF[min(failures, len(BACKOFF) - 1)])
    finally:
        if child and child.poll() is None:
            child.terminate()
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
