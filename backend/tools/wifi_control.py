# FILE: wifi_control.py
# Controls Wi-Fi interface, connections, saved profiles, and scanning using native Windows netsh CLI.
import os
import re
import subprocess
import tempfile

def _get_wifi_interface_name() -> str:
    """Finds the active Wi-Fi interface name (defaults to 'Wi-Fi')."""
    try:
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=5
        )
        for line in res.stdout.splitlines():
            line_s = line.strip()
            if line_s.lower().startswith("name"):
                parts = line_s.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()
    except Exception:
        pass
    return "Wi-Fi"

def wifi_control(params: dict) -> str:
    """Direct tool for Wi-Fi management on Windows."""
    action = str(params.get("action", "status")).lower().strip()
    network = str(params.get("network", "")).strip()
    password = str(params.get("password", "")).strip()
    iface = _get_wifi_interface_name()

    try:
        if action in ("on", "enable", "turn on", "start"):
            res = subprocess.run(
                ["netsh", "interface", "set", "interface", iface, "enabled"],
                capture_output=True, text=True, timeout=8
            )
            out = (res.stdout + res.stderr).lower()
            if "elevation" in out or "administrator" in out or "access is denied" in out:
                return "Enabling the Wi-Fi adapter requires administrator permissions, boss. Please run the backend as administrator."
            return "Wi-Fi is now enabled, boss."

        elif action in ("off", "disable", "turn off", "stop"):
            res = subprocess.run(
                ["netsh", "interface", "set", "interface", iface, "disabled"],
                capture_output=True, text=True, timeout=8
            )
            out = (res.stdout + res.stderr).lower()
            if "elevation" in out or "administrator" in out or "access is denied" in out:
                return "Disabling the Wi-Fi adapter requires administrator permissions, boss. Please run the backend as administrator."
            return "Wi-Fi is now turned off, boss."

        elif action in ("status", "check", "state", "info"):
            res = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=8
            )
            out = res.stdout
            state_match = re.search(r"State\s*:\s*(\w+)", out, re.I)
            ssid_match = re.search(r"SSID\s*:\s*([^\r\n]+)", out, re.I)
            signal_match = re.search(r"Signal\s*:\s*(\d+%)", out, re.I)

            state = state_match.group(1).lower() if state_match else "disconnected"
            if state == "connected" and ssid_match:
                ssid = ssid_match.group(1).strip()
                signal = signal_match.group(1) if signal_match else "strong"
                return f"You are connected to {ssid} with {signal} signal strength, boss."
            elif state == "connected":
                return "Wi-Fi is connected, boss."
            else:
                return "Wi-Fi is currently disconnected, boss."

        elif action in ("disconnect", "drop"):
            res = subprocess.run(
                ["netsh", "wlan", "disconnect"],
                capture_output=True, text=True, timeout=6
            )
            return "Disconnected from Wi-Fi, boss."

        elif action in ("list", "scan", "available", "networks"):
            res = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, timeout=10
            )
            out = res.stdout
            ssids = []
            for match in re.finditer(r"SSID\s+\d+\s+:\s*([^\r\n]+)", out):
                name = match.group(1).strip()
                if name and name not in ssids:
                    ssids.append(name)
            if ssids:
                preview = ", ".join(ssids[:5])
                extra = f" and {len(ssids) - 5} more" if len(ssids) > 5 else ""
                return f"Available Wi-Fi networks are: {preview}{extra}, boss."
            return "No Wi-Fi networks found in range, boss."

        elif action in ("connect", "join", "switch"):
            if not network:
                return "Please specify the Wi-Fi network name you want to connect to, boss."

            # Case A: Password provided -> create/update profile
            if password:
                xml_content = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{network}</name>
    <SSIDConfig>
        <SSID>
            <name>{network}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
                temp_xml = os.path.join(tempfile.gettempdir(), f"wifi_{os.getpid()}.xml")
                try:
                    with open(temp_xml, "w", encoding="utf-8") as f:
                        f.write(xml_content)
                    subprocess.run(
                        ["netsh", "wlan", "add", "profile", f"filename={temp_xml}", f"interface={iface}"],
                        capture_output=True, text=True, timeout=8
                    )
                finally:
                    if os.path.exists(temp_xml):
                        try:
                            os.remove(temp_xml)
                        except Exception:
                            pass

            # Case B: Connect by profile name
            res = subprocess.run(
                ["netsh", "wlan", "connect", f"name={network}", f"interface={iface}"],
                capture_output=True, text=True, timeout=10
            )
            out = (res.stdout + res.stderr).lower()
            if "completed successfully" in out or "success" in out:
                return f"Connecting to {network}, boss."
            elif "profile" in out and "not found" in out:
                return f"Network {network} was not found in your saved profiles. Please provide the password so I can configure it, boss."
            return f"Requested connection to {network}, boss."

        elif action in ("settings", "open"):
            os.startfile("ms-settings:network-wifi")
            return "Opening Wi-Fi settings, boss."

        return f"Unknown Wi-Fi action: {action}, boss."
    except Exception as e:
        print(f"[WiFiControl] Error: {e}")
        return "An error occurred while managing Wi-Fi, boss."
