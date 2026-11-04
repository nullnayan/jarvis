# FILE: window_manager.py
# Finds, activates, and maximizes application windows (like WhatsApp Desktop / Chrome).
import time
import ctypes
import pygetwindow as gw

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def force_foreground_window(hwnd) -> bool:
    """Bypasses Windows focus-stealing prevention to bring any window to the front."""
    try:
        # 1. Restore if minimized
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        # 2. Simulate pressing ALT key (0x12) to reset Windows focus lock
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)

        # 3. Attach thread input for guarantee
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_thread = kernel32.GetCurrentThreadId()

        if fg_thread and cur_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        return True
    except Exception as e:
        print(f"[WindowManager] force_foreground_window error: {e}")
        return False

def focus_and_maximize_window(keyword="whatsapp", max_wait=3.0) -> bool:
    """Finds a window matching keyword, brings it to foreground, and maximizes it."""
    keyword = keyword.lower()
    start = time.time()

    while time.time() - start <= max_wait:
        windows = gw.getAllWindows()
        target_window = None

        for w in windows:
            title = (w.title or "").lower()
            if keyword in title:
                target_window = w
                break

        if target_window:
            print(f"[WindowManager] Found window: '{target_window.title}' (HWND: {target_window._hWnd})")
            success = force_foreground_window(target_window._hWnd)
            time.sleep(0.5)
            return success

        time.sleep(0.5)

    print(f"[WindowManager] Window matching '{keyword}' not found after {max_wait}s.")
    return False

_pipeline_ref = None

def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline

def minimize_jarvis_orb() -> bool:
    """Minimizes or hides the Jarvis window so it does not block the screen during UI automation.
    Uses Electron WebSocket message (shrink_to_dot) as the primary method.
    Falls back to Win32 SW_MINIMIZE only if WebSocket is unavailable."""
    ws_sent = False
    try:
        if _pipeline_ref and _pipeline_ref.server and _pipeline_ref.loop:
            from server.messages import shrink_to_dot_msg
            import asyncio
            asyncio.run_coroutine_threadsafe(_pipeline_ref.server.send(shrink_to_dot_msg()), _pipeline_ref.loop)
            ws_sent = True
            print("[WindowManager] Sent shrink_to_dot message to Electron UI")
            time.sleep(0.3)  # Let Electron process the message
            return True
    except Exception as e:
        print(f"[WindowManager] WebSocket shrink_to_dot error: {e}")

    # Only use Win32 minimize as fallback if WebSocket didn't work
    if not ws_sent:
        try:
            hwnd = user32.FindWindowW(None, "Jarvis")
            if hwnd:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                print(f"[WindowManager] Minimized Jarvis window via Win32 (HWND: {hwnd})")
                return True
            windows = gw.getAllWindows()
            for w in windows:
                if "jarvis" in (w.title or "").lower():
                    user32.ShowWindow(w._hWnd, 6)
                    print(f"[WindowManager] Minimized Jarvis window via gw (HWND: {w._hWnd})")
                    return True
        except Exception as e:
            print(f"[WindowManager] Error minimizing Jarvis: {e}")
    return False

def restore_jarvis_orb() -> bool:
    """Restores the Jarvis window after UI automation finishes.
    Uses Electron WebSocket message (restore_orb) as the primary method.
    Falls back to Win32 SW_RESTORE only if WebSocket is unavailable."""
    ws_sent = False
    try:
        if _pipeline_ref and _pipeline_ref.server and _pipeline_ref.loop:
            from server.messages import restore_orb_msg
            import asyncio
            asyncio.run_coroutine_threadsafe(_pipeline_ref.server.send(restore_orb_msg()), _pipeline_ref.loop)
            ws_sent = True
            print("[WindowManager] Sent restore_orb message to Electron UI")
            time.sleep(0.3)  # Let Electron process the message
            return True
    except Exception as e:
        print(f"[WindowManager] WebSocket restore_orb error: {e}")

    # Only use Win32 restore as fallback if WebSocket didn't work
    if not ws_sent:
        try:
            hwnd = user32.FindWindowW(None, "Jarvis")
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                print(f"[WindowManager] Restored Jarvis window via Win32 (HWND: {hwnd})")
                return True
            windows = gw.getAllWindows()
            for w in windows:
                if "jarvis" in (w.title or "").lower():
                    user32.ShowWindow(w._hWnd, 9)
                    print(f"[WindowManager] Restored Jarvis window via gw (HWND: {w._hWnd})")
                    return True
        except Exception as e:
            print(f"[WindowManager] Error restoring Jarvis: {e}")
    return False
