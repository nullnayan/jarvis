# FILE: system_power.py
# System power actions: shutdown, restart, lock, sleep, screen off.
import subprocess
import ctypes
from pathlib import Path

def _turn_screen_off():
    # Windows monitor power: WM_SYSCOMMAND (0x0112) + SC_MONITORPOWER (0xF170), 2 = off
    HWND_BROADCAST = 0xFFFF
    ctypes.windll.user32.SendMessageW(HWND_BROADCAST, 0x0112, 0xF170, 2)

def system_power(params: dict) -> str:
    action = params.get("action", "").lower().strip()
    try:
        if action == "lock":
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], shell=False)
            return "Locking the computer, boss."
        elif action == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=False)
            return "Putting the computer to sleep, boss."
        elif action in ("screen_off", "screen off", "monitor_off"):
            _turn_screen_off()
            return "Turning off the screen, boss."
        elif action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "60"], shell=False)
            return "Shutting down in 60 seconds, boss. Say 'cancel shutdown' to abort."
        elif action == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "60"], shell=False)
            return "Restarting in 60 seconds, boss. Say 'cancel shutdown' to abort."
        elif action in ("cancel_shutdown", "cancel"):
            subprocess.Popen(["shutdown", "/a"], shell=False)
            return "Shutdown cancelled, boss."
        elif action == "restart_jarvis":
            (Path(__file__).resolve().parents[1] / "data" / "restart_requested").touch()
            return "Restarting Jarvis now, boss."
        elif action in ("exit_jarvis", "close_jarvis", "close_terminal", "exit", "quit"):
            return "Shutting down Jarvis and closing terminal, boss."
        else:
            return "An error occurred, boss."
    except Exception as e:
        print(f"[SystemPower] Error: {e}")
        return "An error occurred, boss."

def close_current_terminal():
    """Closes the console/terminal window hosting Jarvis and terminates its parent terminal process."""
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            print(f"[SystemPower] Posting WM_CLOSE to console window (HWND {hwnd})")
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    except Exception as e:
        print(f"[SystemPower] Error posting WM_CLOSE to console: {e}")

    try:
        import os
        import psutil
        current_proc = psutil.Process(os.getpid())
        allowed_terminals = {"cmd.exe", "powershell.exe", "pwsh.exe", "wt.exe", "windowsterminal.exe", "conhost.exe"}
        for parent in current_proc.parents():
            pname = parent.name().lower()
            if pname in allowed_terminals:
                print(f"[SystemPower] Terminating parent terminal process: {pname} (PID {parent.pid})")
                try:
                    parent.terminate()
                except Exception:
                    pass
                break
            elif pname in ("explorer.exe", "code.exe", "antigravity.exe"):
                break
    except Exception as e:
        print(f"[SystemPower] Error terminating terminal process: {e}")
