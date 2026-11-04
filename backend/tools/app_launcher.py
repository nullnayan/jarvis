# FILE: app_launcher.py
# Opens and closes desktop apps and websites using normalized Start Menu & Desktop search.
import subprocess
import webbrowser
import os
import re
import psutil

BROWSER_EXECUTABLES = {
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "microsoft edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
}

def clean_str(s: str) -> str:
    """Normalizes a string by stripping punctuation, hyphens, and whitespace."""
    return re.sub(r'[\W_]+', '', (s or "").lower())

def open_url_in_browser(url: str, browser: str = None) -> bool:
    """Opens a URL in a specific browser (brave, chrome, edge) or default browser."""
    if not url.startswith("http"):
        url = "https://" + url

    browser_key = (browser or "").lower().strip()
    if browser_key in BROWSER_EXECUTABLES and os.path.exists(BROWSER_EXECUTABLES[browser_key]):
        exe = BROWSER_EXECUTABLES[browser_key]
        subprocess.Popen([exe, url], shell=False)
        return True

    # An unknown browser name never reaches a shell command — a caller-controlled
    # string interpolated into `start ...` would allow command injection.
    # Fall back to the system default browser instead.
    webbrowser.open(url)
    return True

APP_ALIASES = {
    "edge": "microsoft-edge:",
    "microsoft edge": "microsoft-edge:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "brave": "brave",
    "firefox": "firefox",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "file explorer": "explorer",
    "explorer": "explorer",
    "files": "explorer",
    "spotify": "spotify",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "cmd": "cmd",
    "command prompt": "cmd",
    "terminal": "wt",
    "powershell": "powershell",
    "settings": "ms-settings:",
    "task manager": "taskmgr",
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "whatsapp": "whatsapp:",
    "camera": "microsoft.windows.camera:",
    "store": "ms-windows-store:",
    "snipping tool": "snippingtool",
    "youtube": "https://www.youtube.com",
    "antigravity": os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Antigravity.lnk"),
    "anti-gravity": os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Antigravity.lnk"),
}

CLOSE_ALIASES = {
    "cloud": "onedrive",
    "cloud app": "onedrive",
    "onedrive": "onedrive",
    "chrome": "chrome",
    "google chrome": "chrome",
    "brave": "brave",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "antigravity": "antigravity",
    "anti-gravity": "antigravity",
    "notepad": "notepad",
    "calc": "calc",
    "calculator": "calculator",
    "spotify": "spotify",
    "whatsapp": "whatsapp",
}

def find_start_menu_app(app_name: str) -> str | None:
    """Searches Windows Start Menu and Desktop shortcuts (.lnk) for any installed application."""
    search_dirs = [
        os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.expanduser(r"~\Desktop"),
        r"C:\Users\Public\Desktop",
    ]
    cleaned_query = clean_str(app_name)
    if not cleaned_query:
        return None

    # Priority 1: Exact match on normalized name (e.g. 'antigravity' matches 'Antigravity.lnk')
    for sdir in search_dirs:
        if os.path.exists(sdir):
            for root, dirs, files in os.walk(sdir):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name_clean = clean_str(f[:-4])
                        if cleaned_query == name_clean:
                            return os.path.join(root, f)

    # Priority 2: Substring match on normalized name
    for sdir in search_dirs:
        if os.path.exists(sdir):
            for root, dirs, files in os.walk(sdir):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name_clean = clean_str(f[:-4])
                        if cleaned_query in name_clean:
                            return os.path.join(root, f)

    return None

def open_app(params: dict) -> str:
    app = (params.get("app") or params.get("app_name") or "").strip()
    if not app:
        return "No application name specified."

    app_lower = app.lower()

    # Special handling for YouTube songs / queries
    if app_lower in ("youtube", "yt"):
        query = (params.get("query") or params.get("media") or params.get("search") or "").strip()
        if query and query.lower() not in ("song", "music", "video"):
            try:
                from tools.youtube import youtube_play
                return youtube_play({"query": query})
            except Exception:
                pass
        open_url_in_browser("https://www.youtube.com")
        return "Opening YouTube, boss."

    # 1. Check known aliases & protocol schemes
    if app_lower in APP_ALIASES:
        target = APP_ALIASES[app_lower]
        try:
            if target.startswith("http"):
                open_url_in_browser(target)
                return f"Opening {app}, boss."
            elif target.endswith(":"):
                os.startfile(target)
                return f"Opening {app}, boss."
            elif os.path.exists(target):
                os.startfile(target)
                return f"Opening {app}, boss."
            else:
                subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
                return f"Opening {app}, boss."
        except Exception as e:
            print(f"[AppLauncher] Alias launch error: {e}")

    # 2. Dynamic Start Menu & Desktop normalized search
    shortcut = find_start_menu_app(app)
    if shortcut:
        try:
            print(f"[AppLauncher] Found shortcut: {shortcut}")
            os.startfile(shortcut)
            return f"Opening {app}, boss."
        except Exception as e:
            print(f"[AppLauncher] Shortcut launch error: {e}")

    # 3. Direct Windows execution fallback. List form (no shell=True) so a
    # crafted app name can't be parsed as shell metacharacters.
    try:
        subprocess.Popen(["cmd", "/c", "start", "", app], shell=False)
        return f"Opening {app}, boss."
    except Exception as e:
        print(f"[AppLauncher] Direct launch error: {e}")
        return "An error occurred, boss."

def close_app(params: dict) -> str:
    """Finds and closes running processes matching the requested app name."""
    app = params.get("app", "").strip()
    if not app:
        return "No application specified to close, boss."

    target = CLOSE_ALIASES.get(app.lower(), app)
    clean_target = clean_str(target)

    closed = []
    for p in psutil.process_iter(['pid', 'name']):
        try:
            p_name = p.info['name']
            if clean_target in clean_str(p_name):
                p.terminate()
                closed.append(p_name)
                print(f"[AppLauncher] Closed process: {p_name} (PID: {p.info['pid']})")
        except Exception:
            pass

    if closed:
        return f"Closed {app}, boss."
    return f"I could not find a running process for {app}, boss."

def open_website(params: dict) -> str:
    url = params.get("url", "").strip()
    browser = params.get("browser", "").strip()
    target_browser = f" in {browser.title()}" if browser else ""
    try:
        open_url_in_browser(url, browser=browser)
        return f"Opened {url}{target_browser}, boss."
    except Exception as e:
        print(f"[AppLauncher] Open website error: {e}")
        return "An error occurred, boss."
