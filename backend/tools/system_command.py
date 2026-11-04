# FILE: system_command.py
# Executes PowerShell system commands with strict safety guardrails and destructive action detection.
import subprocess
import re
import ctypes

# Commands that are permanently forbidden for system safety
HARD_BLOCKED_PATTERNS = [
    r"format\s+[a-zA-Z]:",
    r"diskpart",
    r"remove-item\s+.*c:\\windows",
    r"del\s+.*c:\\windows",
    r"rmdir\s+.*c:\\windows",
    r"system32",
    r"invoke-expression.*downloadstring",
    r"iex\s*\(.*download",
]

# Patterns that indicate a destructive or irreversible action requiring user confirmation
DESTRUCTIVE_PATTERNS = [
    (r"\b(remove-item|del|rmdir|erase|rm)\b", "delete files or directories"),
    (r"\bclear-recyclebin\b", "empty the Recycle Bin"),
    (r"\b(stop-process|taskkill)\b", "terminate a running application or process"),
    (r"\b(clear-content|clear-history)\b", "clear stored data or history"),
    (r"\b(format|initialize-disk)\b", "format disk storage"),
]

def empty_recycle_bin() -> str:
    """Empties the Windows Recycle Bin across all drives instantly using Win32 API."""
    try:
        from tools.file_manager import empty_recycle_bin as fm_empty_recycle_bin
        return fm_empty_recycle_bin()
    except Exception as e:
        print(f"[SystemCommand] Error emptying Recycle Bin: {e}")
        return "An error occurred, boss."

def is_destructive_action(command: str) -> tuple[bool, str]:
    """
    Analyzes a command string to detect if it deletes, clears, or destroys any data.
    Returns (is_destructive: bool, description: str).
    """
    cmd_lower = command.lower().strip()

    # Check for hard blocked commands
    for pattern in HARD_BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True, "BLOCKED: This command is dangerous to the operating system and is permanently forbidden"

    # Check for destructive patterns requiring confirmation
    for pattern, description in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True, description

    return False, ""

def run_shell_command(params: dict) -> str:
    """
    Executes a shell command via PowerShell with timeout and output limits.
    """
    cmd = params.get("command", "").strip()
    if not cmd:
        return "No command provided to execute, boss."

    cmd_lower = cmd.lower()
    for pattern in HARD_BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            print(f"[SystemCommand] Security Alert: Blocked dangerous command: {cmd}")
            return "Execution blocked: This command alters critical system files and cannot be run, boss."

    # Fast Win32 execution for emptying Recycle Bin (avoids PowerShell progress bar timeouts)
    if "clear-recyclebin" in cmd_lower or "empty-recyclebin" in cmd_lower:
        print("[SystemCommand] Executing native Win32 SHEmptyRecycleBinW...")
        return empty_recycle_bin()

    print(f"[SystemCommand] Executing PowerShell: {cmd}")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=15
        )

        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode != 0 or (errors and not output):
            print(f"[SystemCommand] Command failed (exit {result.returncode}): {errors or output}")
            return "An error occurred, boss."

        if not output:
            return "Command executed successfully, boss."

        # Truncate output to 400 characters so speech and UI stay concise
        truncated = output[:400]
        if len(output) > 400:
            truncated += "..."

        return truncated

    except subprocess.TimeoutExpired:
        print("[SystemCommand] Command timed out after 15 seconds")
        return "An error occurred, boss."
    except Exception as e:
        print(f"[SystemCommand] Error: {e}")
        return "An error occurred, boss."
