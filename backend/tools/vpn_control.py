# FILE: vpn_control.py
# Launches and manages Proton VPN connections on Windows.
import os
import glob
import subprocess
from tools.app_readiness import wait_for_app
from tools.window_manager import focus_and_maximize_window

COUNTRY_CODES = {
    "us": "US", "usa": "US", "united states": "US", "america": "US",
    "netherlands": "NL", "holland": "NL", "nl": "NL",
    "japan": "JP", "jp": "JP", "tokyo": "JP",
    "india": "IN", "in": "IN",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "england": "GB",
    "germany": "DE", "de": "DE",
    "singapore": "SG", "sg": "SG",
    "switzerland": "CH", "swiss": "CH", "ch": "CH",
    "canada": "CA", "ca": "CA",
    "france": "FR", "fr": "FR",
    "australia": "AU", "au": "AU",
    "fastest": "fastest", "quickest": "fastest",
}

def _find_proton_vpn_exe() -> str | None:
    """Searches common installation locations for ProtonVPN.exe."""
    candidates = [
        r"C:\Program Files\Proton\VPN\ProtonVPN.exe",
        r"C:\Program Files (x86)\Proton\VPN\ProtonVPN.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Proton\VPN\ProtonVPN.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\ProtonVPN\ProtonVPN.exe"),
    ]
    # Check glob for versioned subfolders
    for base in [r"C:\Program Files\Proton\VPN", os.path.expandvars(r"%LOCALAPPDATA%\Programs\Proton\VPN")]:
        if os.path.isdir(base):
            matches = glob.glob(os.path.join(base, "v*", "ProtonVPN.exe"))
            candidates.extend(matches)

    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def vpn_control(params: dict) -> str:
    """Manages Proton VPN application and server connections."""
    action = str(params.get("action", "open")).lower().strip()
    country = str(params.get("country", "")).lower().strip()
    vpn_exe = _find_proton_vpn_exe()

    try:
        if action in ("connect", "start"):
            if not vpn_exe:
                # Try launching via start command
                os.startfile("protonvpn:")
                wait_for_app("ProtonVPN", "proton", max_wait=10.0)
                return "Proton VPN started. Please select your desired server, boss."

            if country:
                cc = COUNTRY_CODES.get(country, country.upper()[:2])
                if cc == "fastest":
                    subprocess.Popen([vpn_exe, "/connect"])
                    return "Connecting to the fastest Proton VPN server, boss."
                subprocess.Popen([vpn_exe, "/connect", "/country", cc])
                return f"Connecting Proton VPN to {country.title()}, boss."
            else:
                subprocess.Popen([vpn_exe, "/connect"])
                return "Connecting Proton VPN to the fastest server, boss."

        elif action in ("disconnect", "stop", "kill"):
            if vpn_exe:
                subprocess.Popen([vpn_exe, "/disconnect"])
                return "Disconnecting Proton VPN, boss."
            return "Disconnect command sent to VPN, boss."

        elif action in ("open", "launch", "show"):
            if vpn_exe:
                subprocess.Popen([vpn_exe])
            else:
                os.startfile("protonvpn:")
            wait_for_app("ProtonVPN", "proton", max_wait=10.0)
            focus_and_maximize_window("proton", max_wait=5.0)
            return "Proton VPN opened, boss."

        elif action in ("status", "check"):
            res = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=5)
            if "protonvpn" in res.stdout.lower():
                return "Proton VPN is currently running, boss."
            return "Proton VPN is not currently running, boss."

        return f"VPN action '{action}' completed, boss."
    except Exception as e:
        print(f"[VPNControl] Error: {e}")
        return "An error occurred while managing Proton VPN, boss."
