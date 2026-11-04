# FILE: backend/tools/phone_link.py
# Opt-in Android phone connectivity via ADB and screen mirroring via scrcpy.
# Security rule: connection is strictly opt-in (never on boot) and disconnect is
# authoritative (kills ADB daemon, terminates scrcpy, and clears pairing state).

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Optional, Tuple

from config import (
    ADB_PATH,
    PHONE_MIRROR_IDLE_TIMEOUT,
    SCRCPY_AUDIO,
    SCRCPY_BIT_RATE,
    SCRCPY_MAX_SIZE,
    SCRCPY_PATH,
)
from logger import get_logger

_log = get_logger(__name__)
print = _log.info

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PHONE_LINK_FILE = os.path.join(DATA_DIR, "phone_link.json")
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")

ANDROID_APP_PACKAGES = {
    "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome",
    "browser": "com.android.chrome",
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "spotify": "com.spotify.music",
    "settings": "com.android.settings",
    "camera": "android.media.action.IMAGE_CAPTURE",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm",
    "calculator": "com.google.android.calculator",
    "photos": "com.google.android.apps.photos",
    "gallery": "com.google.android.apps.photos",
    "play store": "com.android.vending",
    "telegram": "org.telegram.messenger",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
}



class PhoneLink:
    """Manages ADB pairing/connection and scrcpy screen mirroring lifecycle."""

    def __init__(self):
        self.state = "disconnected"  # "disconnected", "pairing", "connected"
        self.device_serial: Optional[str] = None
        self.device_model: Optional[str] = None
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self.last_connected_time: Optional[float] = None

    def _adb_binary(self) -> Optional[str]:
        """Locates the adb executable across environment and standard Windows paths."""
        if ADB_PATH and os.path.isfile(ADB_PATH):
            return ADB_PATH
        which_adb = shutil.which("adb")
        if which_adb:
            return which_adb

        common_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
            r"C:\platform-tools\adb.exe",
            r"C:\Program Files\platform-tools\adb.exe",
            os.path.expanduser(r"~\platform-tools\adb.exe"),
            os.path.expanduser(r"~\Downloads\platform-tools\adb.exe"),
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path

        winget_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.isdir(winget_dir):
            for root, _, files in os.walk(winget_dir):
                for f in files:
                    if f.lower() == "adb.exe":
                        return os.path.join(root, f)
        return None

    def _scrcpy_binary(self) -> Optional[str]:
        """Locates the scrcpy executable across environment and standard Windows paths."""
        if SCRCPY_PATH and os.path.isfile(SCRCPY_PATH):
            return SCRCPY_PATH
        which_scrcpy = shutil.which("scrcpy")
        if which_scrcpy:
            return which_scrcpy

        common_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\scrcpy\scrcpy.exe"),
            r"C:\scrcpy\scrcpy.exe",
            os.path.expanduser(r"~\scrcpy\scrcpy.exe"),
            r"C:\Program Files\scrcpy\scrcpy.exe",
            os.path.expanduser(r"~\Downloads\scrcpy\scrcpy.exe"),
        ]
        for path in common_paths:
            if os.path.isfile(path):
                return path

        winget_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.isdir(winget_dir):
            for root, _, files in os.walk(winget_dir):
                for f in files:
                    if f.lower() == "scrcpy.exe":
                        return os.path.join(root, f)
        return None

    def _adb(self, args: list[str], timeout: int = 20) -> Tuple[bool, str, str]:
        """Executes an adb command with safety timeouts. Never raises uncaught exceptions."""
        adb_bin = self._adb_binary()
        if not adb_bin:
            return False, "", "adb executable not found"
        try:
            res = subprocess.run(
                [adb_bin, *args],
                capture_output=True,
                timeout=timeout,
            )
            stdout = res.stdout.decode("utf-8", errors="replace").strip() if isinstance(res.stdout, bytes) else str(res.stdout or "").strip()
            stderr = res.stderr.decode("utf-8", errors="replace").strip() if isinstance(res.stderr, bytes) else str(res.stderr or "").strip()
            return res.returncode == 0, stdout, stderr
        except subprocess.TimeoutExpired:
            return False, "", "adb command timed out"
        except Exception as exc:
            return False, "", str(exc)

    def _get_last_known_target(self) -> Optional[Tuple[str, str]]:
        """Reads persisted host/port for convenience hint only — never auto-connects."""
        try:
            if os.path.isfile(PHONE_LINK_FILE):
                with open(PHONE_LINK_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("host"), str(data.get("port", "5555"))
        except Exception:
            pass
        return None

    def _save_target(self, host: str, port: str):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(PHONE_LINK_FILE, "w", encoding="utf-8") as f:
                json.dump({"host": host, "port": port}, f)
        except Exception as exc:
            print(f"[PhoneLink] Failed to persist target: {exc}")

    def _clear_persisted_target(self):
        try:
            if os.path.isfile(PHONE_LINK_FILE):
                os.remove(PHONE_LINK_FILE)
        except Exception:
            pass

    def _fetch_device_model(self, target: Optional[str] = None) -> str:
        args = ["-s", target, "shell", "getprop", "ro.product.model"] if target else ["shell", "getprop", "ro.product.model"]
        ok, out, _ = self._adb(args, timeout=8)
        if ok and out:
            return out.strip()
        return "Android Phone"

    def pair(self, host: str, port: str, code: str) -> Tuple[bool, str]:
        """Pairs with an Android 11+ device using wireless debugging pairing code."""
        if not self._adb_binary():
            return False, "I need Android platform-tools, boss. Please install adb and add it to PATH, then try connecting again."
        target = f"{host}:{port}"
        print(f"[PhoneLink] Pairing with {target}...")
        ok, out, err = self._adb(["pair", target, str(code)], timeout=25)
        combined = f"{out} {err}".lower()
        if "successfully paired" in combined or ok:
            self.state = "pairing"
            return True, f"Successfully paired with {host}, boss."
        return False, f"Failed to pair with your phone: {err or out or 'unknown error'}"

    def _discover_mdns_target(self) -> Optional[Tuple[str, str]]:
        """Queries adb mdns services to auto-discover active wireless debugging connection port."""
        ok, out, _ = self._adb(["mdns", "services"], timeout=8)
        if not ok or not out:
            return None
        for line in out.splitlines():
            if "_adb-tls-connect._tcp" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    target = parts[-1]
                    if ":" in target:
                        host, port = target.split(":", 1)
                        return host, port
        return None

    def connect(self, host: Optional[str] = None, port: Optional[str] = None) -> Tuple[bool, str]:
        """Connects to the phone over wireless ADB or USB fallback."""
        if not self._adb_binary():
            return False, "I need Android platform-tools, boss. Please install adb and add it to PATH, then try connecting again."

        # 1. Fast path: check if an online device is already attached (USB or wireless)
        ok_dev, out_dev, _ = self._adb(["devices"], timeout=8)
        if ok_dev and out_dev:
            for line in out_dev.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "device":
                    if host and not parts[0].startswith(host) and not parts[0].startswith("adb-"):
                        continue
                    serial = parts[0]
                    self.device_serial = serial
                    self.device_model = self._fetch_device_model(serial)
                    self.state = "connected"
                    self.last_connected_time = time.time()
                    return True, f"Connected to {self.device_model}, boss."

        # If no host specified, check mDNS discovery or last-known target
        if not host:
            mdns = self._discover_mdns_target()
            if mdns:
                host, port = mdns
            else:
                last = self._get_last_known_target()
                if last and last[0]:
                    host, port = last[0], port or last[1]

        if host:
            port = port or "5555"
            target = f"{host}:{port}"
            print(f"[PhoneLink] Connecting to wireless target {target}...")
            ok, out, err = self._adb(["connect", target], timeout=20)
            combined = f"{out} {err}".lower()
            if "connected to" in combined or "already connected" in combined:
                self.device_serial = target
                self.device_model = self._fetch_device_model(target)
                self.state = "connected"
                self.last_connected_time = time.time()
                self._save_target(host, port)
                return True, f"Connected to {self.device_model}, boss."

            # If connecting to the given port failed (e.g. was pairing port), try mDNS auto-discovery
            mdns = self._discover_mdns_target()
            if mdns and mdns[0] == host and mdns[1] != port:
                mdns_target = f"{mdns[0]}:{mdns[1]}"
                print(f"[PhoneLink] Discovered active mDNS connection port {mdns_target}, connecting...")
                ok_m, out_m, _ = self._adb(["connect", mdns_target], timeout=15)
                comb_m = out_m.lower()
                if "connected to" in comb_m or "already connected" in comb_m or ok_m:
                    self.device_serial = mdns_target
                    self.device_model = self._fetch_device_model(mdns_target)
                    self.state = "connected"
                    self.last_connected_time = time.time()
                    self._save_target(mdns[0], mdns[1])
                    return True, f"Connected to {self.device_model}, boss."

            return False, f"Could not connect to {target}, boss: {err or out or 'device unreachable'}"

        # USB fallback check
        return self.connect_usb()

    def connect_usb(self) -> Tuple[bool, str]:
        """Detects USB-connected devices and establishes connection."""
        ok, out, err = self._adb(["devices"], timeout=10)
        if not ok:
            return False, f"Could not list adb devices, boss: {err}"

        lines = [line.strip() for line in out.splitlines() if line.strip() and not line.startswith("List of devices")]
        for line in lines:
            parts = re.split(r"\s+", line)
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                self.device_serial = serial
                self.device_model = self._fetch_device_model(serial)
                self.state = "connected"
                self.last_connected_time = time.time()
                return True, f"Connected to {self.device_model} over USB, boss."
            elif len(parts) >= 2 and parts[1] == "unauthorized":
                return False, "Your phone is connected but unauthorized, boss. Please tap 'Allow USB debugging' on your phone screen."

        return False, "No phone detected over WiFi or USB, boss. Please provide the host address or connect via USB with debugging enabled."

    def disconnect(self) -> str:
        """Authoritative sever: terminates scrcpy, disconnects all devices, kills ADB server, and clears state."""
        self.stop_scrcpy()
        self._adb(["disconnect"], timeout=10)
        self._adb(["kill-server"], timeout=10)
        self.state = "disconnected"
        self.device_serial = None
        self.device_model = None
        self.last_connected_time = None
        self._clear_persisted_target()
        print("[PhoneLink] Authoritative disconnect executed (adb kill-server).")
        return "Disconnected from your phone, boss."

    def status(self) -> str:
        """Returns readable connection status and device model."""
        if self.state != "connected":
            return "Your phone is not connected, boss."
        model = self.device_model or "Android device"
        target = self.device_serial or "unknown"
        return f"Your phone ({model}) is connected at {target}, boss."

    def screencap_png(self) -> Tuple[bool, bytes, str]:
        """Captures a one-shot screenshot from the phone returning raw PNG bytes."""
        if self.state != "connected":
            return False, b"", "Phone is not connected, boss."
        adb_bin = self._adb_binary()
        if not adb_bin:
            return False, b"", "adb executable not found"

        args = [adb_bin]
        if self.device_serial:
            args.extend(["-s", self.device_serial])
        args.extend(["exec-out", "screencap", "-p"])

        try:
            res = subprocess.run(args, capture_output=True, timeout=15)
            if res.returncode == 0 and res.stdout and len(res.stdout) > 100:
                return True, res.stdout, ""
            return False, b"", res.stderr.decode("utf-8", errors="replace") or "Empty screenshot returned"
        except subprocess.TimeoutExpired:
            return False, b"", "Screencap command timed out"
        except Exception as exc:
            return False, b"", str(exc)

    def launch_scrcpy(self, serial: Optional[str] = None, audio: Optional[bool] = None) -> Tuple[bool, str]:
        """Launches the scrcpy window streaming at 30-60 fps."""
        if self.state != "connected":
            return False, "Please connect to your phone first, boss."

        if self._scrcpy_proc and self._scrcpy_proc.poll() is None:
            if self.last_connected_time and (time.time() - self.last_connected_time > PHONE_MIRROR_IDLE_TIMEOUT):
                print(f"[PhoneLink] Mirroring idle timeout ({PHONE_MIRROR_IDLE_TIMEOUT}s) reached; restarting session.")
                self.stop_scrcpy()
            else:
                return True, "Screen mirroring is already running, boss."

        scrcpy_bin = self._scrcpy_binary()
        if not scrcpy_bin:
            return False, "I need scrcpy for screen mirroring, boss. Please download scrcpy and add it to your PATH."

        target_serial = serial or self.device_serial
        cmd = [scrcpy_bin]
        if target_serial:
            cmd.extend(["-s", target_serial])
        cmd.extend(["--window-title", "Jarvis Phone"])

        include_audio = SCRCPY_AUDIO if audio is None else audio
        if not include_audio:
            cmd.append("--no-audio")

        cmd.extend(["--max-size", str(SCRCPY_MAX_SIZE)])
        cmd.extend(["--video-bit-rate", str(SCRCPY_BIT_RATE)])

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            self._scrcpy_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            print(f"[PhoneLink] scrcpy launched (PID: {self._scrcpy_proc.pid})")
            return True, "Mirroring your phone screen, boss."
        except Exception as exc:
            print(f"[PhoneLink] Failed to launch scrcpy: {exc}")
            return False, f"Failed to start screen mirroring, boss: {exc}"

    def stop_scrcpy(self) -> str:
        """Terminates the scrcpy process tree."""
        if not self._scrcpy_proc:
            return "Screen mirroring is not active, boss."
        try:
            pid = self._scrcpy_proc.pid
            if self._scrcpy_proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5)
                else:
                    self._scrcpy_proc.kill()
            self._scrcpy_proc = None
            print(f"[PhoneLink] scrcpy terminated (PID {pid}).")
            return "Stopped mirroring your phone screen, boss."
        except Exception as exc:
            return f"Failed to stop screen mirroring, boss: {exc}"

    def open_app(self, app_name: str, query: Optional[str] = None) -> Tuple[bool, str]:
        """Launches an Android application or intent via ADB."""
        if self.state != "connected":
            ok_conn, _ = self.connect()
            if not ok_conn:
                return False, "Please connect to your phone first, boss."

        app_clean = app_name.lower().strip()
        serial_args = ["-s", self.device_serial] if self.device_serial else []

        if "youtube" in app_clean:
            if query:
                import urllib.parse
                video_id = None
                try:
                    import httpx
                    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
                    resp = httpx.get(search_url, timeout=5, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    m = re.search(r'/watch\?v=([a-zA-Z0-9_-]{11})', resp.text)
                    if m:
                        video_id = m.group(1)
                except Exception as exc:
                    print(f"[PhoneLink] Could not resolve YouTube video ID: {exc}")

                if video_id:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    ok, _, _ = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
                    if ok:
                        return True, f"Playing {query} on YouTube on your phone, boss."

                # Fallback: open the search URL. Do not auto-tap a fixed screen
                # coordinate: device layouts vary and the tap can activate the
                # wrong result or another control.
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
                ok, _, _ = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
                if ok:
                    return True, f"Searching for {query} on YouTube on your phone, boss."

            ok, _, err = self._adb([*serial_args, "shell", "monkey", "-p", "com.google.android.youtube", "-c", "android.intent.category.LAUNCHER", "1"])
            if ok:
                return True, "Opening YouTube on your phone, boss."

        if "instagram" in app_clean or "insta" in app_clean:
            if query:
                import urllib.parse
                clean_user = query.strip().lstrip("@")
                url = f"https://instagram.com/_u/{urllib.parse.quote_plus(clean_user)}"
                ok, _, _ = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
                if ok:
                    return True, f"Opening {clean_user}'s Instagram profile on your phone, boss."
            ok, _, _ = self._adb([*serial_args, "shell", "monkey", "-p", "com.instagram.android", "-c", "android.intent.category.LAUNCHER", "1"])
            if ok:
                return True, "Opening Instagram on your phone, boss."

        if "spotify" in app_clean:
            if query:
                import urllib.parse
                url = f"spotify:search:{urllib.parse.quote_plus(query)}"
                ok, _, _ = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
                if ok:
                    return True, f"Searching {query} on Spotify on your phone, boss."
            ok, _, _ = self._adb([*serial_args, "shell", "monkey", "-p", "com.spotify.music", "-c", "android.intent.category.LAUNCHER", "1"])
            if ok:
                return True, "Opening Spotify on your phone, boss."

        if "chrome" in app_clean or "browser" in app_clean:
            if query and ("http" in query or "." in query):
                import urllib.parse
                target_url = query if query.startswith("http") else f"https://{query}"
                ok, _, _ = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", target_url])
                if ok:
                    return True, f"Opening {target_url} in Chrome on your phone, boss."

        if "camera" in app_clean:
            ok, _, err = self._adb([*serial_args, "shell", "am", "start", "-a", "android.media.action.IMAGE_CAPTURE"])
            if ok:
                return True, "Opening Camera on your phone, boss."

        pkg = ANDROID_APP_PACKAGES.get(app_clean)
        if not pkg:
            # Dynamic package search on the phone
            ok, out, _ = self._adb([*serial_args, "shell", "pm", "list", "packages", app_clean])
            if ok and out:
                for line in out.splitlines():
                    if line.startswith("package:"):
                        pkg = line.replace("package:", "").strip()
                        break

        if pkg:
            ok, out, err = self._adb([*serial_args, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
            if ok:
                return True, f"Opening {app_name.title()} on your phone, boss."
            return False, f"Could not open {app_name} on your phone, boss: {err or out}"

        return False, f"I couldn't find an app named {app_name} on your phone, boss."

    def _get_screen_size(self) -> Tuple[int, int]:
        """Returns (width, height) of connected phone display."""
        serial_args = ["-s", self.device_serial] if self.device_serial else []
        ok, out, _ = self._adb([*serial_args, "shell", "wm", "size"])
        if ok and out:
            m = re.search(r"(\d+)x(\d+)", out)
            if m:
                return int(m.group(1)), int(m.group(2))
        return (1080, 2400)

    def input_action(self, action: str, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
        """Performs touch or navigation actions (like, scroll, back, home, tap)."""
        if self.state != "connected":
            ok_conn, _ = self.connect()
            if not ok_conn:
                return False, "Please connect to your phone first, boss."

        serial_args = ["-s", self.device_serial] if self.device_serial else []
        act = action.lower().strip()
        w, h = self._get_screen_size()
        cx, cy = w // 2, h // 2

        if act in ("like", "double_tap", "like_post"):
            # Double tap center of screen (likes post in Instagram / Reels / Shorts / TikTok)
            tap_x = x if x is not None else cx
            tap_y = y if y is not None else cy
            self._adb([*serial_args, "shell", "input", "tap", str(tap_x), str(tap_y)])
            time.sleep(0.08)
            self._adb([*serial_args, "shell", "input", "tap", str(tap_x), str(tap_y)])
            return True, "Liked the post on your phone, boss."

        if act in ("scroll_down", "down", "next"):
            y_start = int(h * 0.75)
            y_end = int(h * 0.25)
            self._adb([*serial_args, "shell", "input", "swipe", str(cx), str(y_start), str(cx), str(y_end), "300"])
            return True, "Scrolled down on your phone, boss."

        if act in ("scroll_up", "up", "previous"):
            y_start = int(h * 0.25)
            y_end = int(h * 0.75)
            self._adb([*serial_args, "shell", "input", "swipe", str(cx), str(y_start), str(cx), str(y_end), "300"])
            return True, "Scrolled up on your phone, boss."

        if act in ("back", "go_back"):
            self._adb([*serial_args, "shell", "input", "keyevent", "4"])
            return True, "Navigated back on your phone, boss."

        if act in ("home", "home_screen"):
            self._adb([*serial_args, "shell", "input", "keyevent", "3"])
            return True, "Returned to home screen on your phone, boss."

        if act in ("tap", "click"):
            tap_x = x if x is not None else cx
            tap_y = y if y is not None else cy
            self._adb([*serial_args, "shell", "input", "tap", str(tap_x), str(tap_y)])
            return True, f"Tapped screen on your phone, boss."

        return False, f"Unknown phone action: {action}"

    def _lookup_contact_number(self, name: str) -> Tuple[Optional[str], Optional[str]]:
        """Looks up phone number and display name from local contacts cache or Android contacts provider."""
        serial_args = ["-s", self.device_serial] if self.device_serial else []
        q = name.lower().strip()
        aliases = {"mom": ["mother", "mummy", "maa"], "dad": ["father", "papa"]}
        search_terms = [q] + aliases.get(q, [])

        # 1. Local contacts.json cache in data/
        contacts_file = os.path.join(DATA_DIR, "contacts.json")
        if os.path.exists(contacts_file):
            try:
                with open(contacts_file, "r", encoding="utf-8") as f:
                    contacts = json.load(f)
                    for c_name, c_num in contacts.items():
                        c_clean = c_name.lower().strip()
                        for term in search_terms:
                            if term in c_clean or c_clean in term:
                                return str(c_num), c_name
            except Exception:
                pass

        # 2. Query Android Contacts Provider via adb content query
        ok, out, _ = self._adb([
            *serial_args, "shell", "content", "query",
            "--uri", "content://com.android.contacts/data/phones",
            "--projection", "display_name:data1",
        ])
        if ok and out:
            import difflib
            best_match = None
            best_ratio = 0.0

            for line in out.splitlines():
                if "display_name=" in line and "data1=" in line:
                    m = re.search(r"display_name=([^,]+).*?data1=(.*?)(?:,\s*[a-zA-Z0-9_]+=|$|\r|\n)", line)
                    if m:
                        disp_name = m.group(1).strip()
                        raw_num = m.group(2).strip()
                        num = re.sub(r"[^\+0-9]", "", raw_num)
                        if len(num) < 7:
                            continue
                        c_clean = re.sub(r"\s*\d+$", "", disp_name).lower()
                        for term in search_terms:
                            if term in c_clean or c_clean in term:
                                return num, disp_name
                            ratio = difflib.SequenceMatcher(None, term, c_clean).ratio()
                            if ratio > best_ratio and ratio >= 0.72:
                                best_ratio = ratio
                                best_match = (num, disp_name)

            if best_match:
                return best_match

        return None, None

    def make_call(self, recipient: str) -> Tuple[bool, str]:
        """Places a phone call to a phone number or contact name via ADB."""
        if self.state != "connected":
            ok_conn, _ = self.connect()
            if not ok_conn:
                return False, "Please connect to your phone first, boss."

        serial_args = ["-s", self.device_serial] if self.device_serial else []
        clean_rec = recipient.strip()

        # Check if recipient is a phone number (e.g. "+91...", "9876543210")
        is_number = bool(re.match(r"^[\+0-9\-\s\(\)]+$", clean_rec) and len(re.sub(r"\D", "", clean_rec)) >= 3)
        phone_number = re.sub(r"[^\+0-9]", "", clean_rec) if is_number else None
        disp_name = None

        # If not a raw number, try looking up contact name
        if not phone_number:
            phone_number, disp_name = self._lookup_contact_number(clean_rec)

        if phone_number:
            # 1. Try direct CALL intent
            ok, out, err = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{phone_number}"])
            combined = f"{out} {err}".lower()
            if not ok or "securityexception" in combined or "error" in combined:
                # 2. Fallback to DIAL intent
                self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{phone_number}"])

            # Send KEYCODE_CALL (5) after 0.5s to trigger dialing / confirm SIM choice
            time.sleep(0.5)
            self._adb([*serial_args, "shell", "input", "keyevent", "5"])
            name_label = disp_name or recipient
            return True, f"Calling {name_label} on your phone, boss."

        # If contact couldn't be resolved, open phone dialer/contacts with name
        ok_view, _, _ = self._adb([*serial_args, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"tel:{clean_rec}"])
        if ok_view:
            return True, f"Opened phone dialer for {recipient}, boss."

        return False, f"Could not find a phone number for {recipient}, boss."


# Singleton instance
phone_link = PhoneLink()


# --- Tool Handlers ---

def phone_connect(params: dict) -> str:
    """Handler for phone_connect tool."""
    host = params.get("host")
    port = params.get("port")
    code = params.get("code")

    # 1. Fast check: if an active device is already attached, connect immediately
    ok_dev, out_dev, _ = phone_link._adb(["devices"], timeout=6)
    if ok_dev and out_dev:
        for line in out_dev.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                phone_link.device_serial = serial
                phone_link.device_model = phone_link._fetch_device_model(serial)
                phone_link.state = "connected"
                phone_link.last_connected_time = time.time()
                return f"Connected to {phone_link.device_model}, boss."

    # 2. If code was provided, attempt pairing
    if code and host and port:
        ok, msg = phone_link.pair(host, str(port), str(code))
        # Even if pairing reported an error (e.g. protocol fault because already paired), try connecting!
        ok_conn, conn_msg = phone_link.connect(host)
        if ok_conn:
            return conn_msg
        if not ok:
            return msg
        return f"{msg} You can now say 'connect to my phone', boss."

    ok, msg = phone_link.connect(host, str(port) if port else None)
    return msg


def phone_disconnect(params: dict = None) -> str:
    """Handler for phone_disconnect tool."""
    return phone_link.disconnect()


def phone_status(params: dict = None) -> str:
    """Handler for phone_status tool."""
    return phone_link.status()


def phone_mirror(params: dict) -> str:
    """Handler for phone_mirror tool (start/stop)."""
    action = str(params.get("action", "start")).lower().strip()
    if action in ("stop", "close", "end"):
        return phone_link.stop_scrcpy()
    audio = params.get("audio", None)
    ok, msg = phone_link.launch_scrcpy(audio=audio)
    return msg


def phone_screencap(params: dict) -> str:
    """Handler for phone_screencap tool with optional vision analysis."""
    ok, png_bytes, err = phone_link.screencap_png()
    if not ok:
        return f"Could not capture phone screen, boss: {err}"

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = f"phone_{int(time.time())}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(png_bytes)
    except Exception as exc:
        print(f"[PhoneLink] Failed to save screenshot: {exc}")

    analyze = params.get("analyze", True)  # Default True if user asks "what's on my phone"
    question = params.get("question", "Describe what is visible on this phone screen in 2-3 concise sentences.")
    if analyze:
        try:
            from tools.screenshot import _analyze_image
            return _analyze_image(filepath, question)
        except Exception as exc:
            print(f"[PhoneLink] Vision analysis error: {exc}")
            return "Captured your phone screen, but vision analysis encountered an error, boss."

    return "Captured your phone screen, boss."


def phone_open_app(params: dict) -> str:
    """Handler for phone_open_app tool: launches apps and plays media on the phone."""
    app = params.get("app") or params.get("app_name") or "youtube"
    query = params.get("query")
    ok, msg = phone_link.open_app(app, query=query)
    return msg


def phone_action(params: dict) -> str:
    """Handler for phone_action tool: touch and navigation (like, scroll, back, home)."""
    action = params.get("action", "like")
    x = params.get("x")
    y = params.get("y")
    ok, msg = phone_link.input_action(action, x=x, y=y)
    return msg


def phone_call(params: dict) -> str:
    """Handler for phone_call tool: places phone calls via ADB."""
    recipient = params.get("recipient") or params.get("contact") or params.get("phone") or ""
    if not recipient:
        return "Who should I call on your phone, boss?"
    ok, msg = phone_link.make_call(recipient)
    return msg
