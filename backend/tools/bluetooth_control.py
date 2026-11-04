# FILE: bluetooth_control.py
# Toggles and checks Windows Bluetooth radio using Windows Runtime (WinRT) PowerShell APIs.
import subprocess
import os

PS_BLUETOOTH_SCRIPT = """
param ([string]$Action = 'Status')
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}[0]

Function Await-WinRt($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
$radios = Await-WinRt ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bluetooth = $radios | Where-Object { $_.Kind -eq 'Bluetooth' }

if (-not $bluetooth) {
    Write-Output "NO_BLUETOOTH"
    exit
}

if ($Action -eq 'Status') {
    Write-Output $bluetooth.State
} elseif ($Action -eq 'On') {
    $op = $bluetooth.SetStateAsync([Windows.Devices.Radios.RadioState]::On)
    Await-WinRt $op ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
    Write-Output "ON"
} elseif ($Action -eq 'Off') {
    $op = $bluetooth.SetStateAsync([Windows.Devices.Radios.RadioState]::Off)
    Await-WinRt $op ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
    Write-Output "OFF"
}
"""

def bluetooth_control(params: dict) -> str:
    action = str(params.get("action", "")).lower().strip()
    try:
        if action in ("settings", "open", "configure"):
            os.startfile("ms-settings:bluetooth")
            return "Opening Bluetooth settings, boss."

        ps_action = "Status"
        if action in ("on", "enable", "start", "turn on"):
            ps_action = "On"
        elif action in ("off", "disable", "stop", "turn off"):
            ps_action = "Off"
        elif action in ("status", "check", "state", "what"):
            ps_action = "Status"
        elif action in ("toggle", "switch"):
            # Check status first to toggle
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", PS_BLUETOOTH_SCRIPT, "-Action", "Status"],
                capture_output=True, text=True, timeout=8
            )
            current = res.stdout.strip().lower()
            ps_action = "Off" if "on" in current else "On"

        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", PS_BLUETOOTH_SCRIPT, "-Action", ps_action],
            capture_output=True, text=True, timeout=8
        )
        out = res.stdout.strip().lower()

        if "no_bluetooth" in out:
            return "No Bluetooth radio found on this system, boss."
        elif "on" in out:
            return "Bluetooth is now enabled, boss." if ps_action == "On" else "Bluetooth is currently on, boss."
        elif "off" in out:
            return "Bluetooth is now disabled, boss." if ps_action == "Off" else "Bluetooth is currently off, boss."
        else:
            return "Bluetooth is currently off, boss."
    except Exception as e:
        print(f"[Bluetooth] Error: {e}")
        return "An error occurred, boss."
