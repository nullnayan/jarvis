# FILE: backend/security/permissions.py
# Permission engine: maps every tool to a permission level and decides whether a
# tool call may run, needs human confirmation, or must be refused.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class PermissionResult:
    ALLOW = "ALLOW"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    DENY = "DENY"


# Level 0 — safe read-only / reversible app launches: no confirmation.
LEVEL_0_SAFE = {
    "get_datetime", "get_weather", "get_battery_status", "clipboard",
    "screenshot", "system_health", "web_search", "persistent_memory",
    "clipboard_history", "self_code",
    "open_app", "open_website", "youtube_play", "phone_status",
    "phone_connect", "phone_disconnect", "phone_open_app", "phone_action",
    "phone_call",
}

# Level 1 — reversible workspace: one confirmation for a grouped plan.
LEVEL_1_REVERSIBLE = {
    "self_fix", "coding_agent", "file_manager", "code_reviewer",
}

# Level 2 — system-impacting: always per-action confirmation.
LEVEL_2_SYSTEM = {
    "run_shell_command", "window_manager", "volume_control", "brightness_control",
    "wifi_control", "bluetooth_control", "vpn_control", "performance_control",
    "datetime_control", "media_control", "music_control", "set_timer",
    "gesture_control", "generate_image", "video_tool", "computer_use",
    "routines_tool", "scheduler_tool", "execute_code", "close_app",
    "phone_mirror", "phone_screencap",
}

# Level 3 — external side effects: preview + confirm.
LEVEL_3_EXTERNAL = {
    "whatsapp_message", "whatsapp_call", "whatsapp_video_call", "whatsapp_open",
    "whatsapp_take_call", "google_calendar", "google_drive", "google_sheets",
    "google_tasks", "youtube_intel", "doc_reader",
}

# Level 4 — irreversible / security: auth + confirm.
LEVEL_4_IRREVERSIBLE = {
    "system_power", "security_settings", "self_audit", "self_code_write",
}

# Default level for any tool not explicitly mapped.
DEFAULT_LEVEL = 2

TOOL_PERMISSION_LEVELS: dict[str, int] = {}
for _name in LEVEL_0_SAFE:
    TOOL_PERMISSION_LEVELS[_name] = 0
for _name in LEVEL_1_REVERSIBLE:
    TOOL_PERMISSION_LEVELS[_name] = 1
for _name in LEVEL_2_SYSTEM:
    TOOL_PERMISSION_LEVELS[_name] = 2
for _name in LEVEL_3_EXTERNAL:
    TOOL_PERMISSION_LEVELS[_name] = 3
for _name in LEVEL_4_IRREVERSIBLE:
    TOOL_PERMISSION_LEVELS[_name] = 4

# Tools that may ONLY be triggered by a direct user utterance (voice or typed text).
# Never callable from chains, routines, scheduler, or web-scraped text.
USER_INITIATED_ONLY: frozenset = frozenset({
    "self_code_write", "self_fix", "self_audit", "security_settings",
    "run_shell_command",
    "phone_connect", "phone_disconnect", "phone_mirror", "phone_screencap", "phone_status",
    "phone_open_app", "phone_action", "phone_call",
})

# Sources that count as "direct user".
DIRECT_USER_SOURCES = frozenset({"voice", "text"})


def permission_level(tool_name: str) -> int:
    return TOOL_PERMISSION_LEVELS.get(tool_name, DEFAULT_LEVEL)


@dataclass
class PermissionGrant:
    capability: str            # tool name or "*"
    path_pattern: str | None = None
    duration: str = "once"     # "once", "session", "persistent"
    granted_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        if self.expires_at and now > self.expires_at:
            return False
        return True


class PermissionDecision:
    __slots__ = ("result", "reason", "level", "grant")

    def __init__(self, result, reason="", level=None, grant: PermissionGrant | None = None):
        self.result = result
        self.reason = reason
        self.level = level
        self.grant = grant

    @property
    def is_allow(self) -> bool:
        return self.result == PermissionResult.ALLOW


def check_permission(
    tool_name: str,
    params: dict | None = None,
    source: str = "voice",
    grants: list[PermissionGrant] | None = None,
) -> PermissionDecision:
    """Decides whether a tool call may proceed.

    - USER_INITIATED_ONLY tools refuse unless source is a direct user utterance.
    - Level 3-4 tools always require confirmation.
    - A matching active grant short-circuits to ALLOW.
    """
    params = params or {}
    grants = grants or []
    level = permission_level(tool_name)

    # 1. User-initiated-only gate (prompt-injection defense).
    if tool_name in USER_INITIATED_ONLY and source not in DIRECT_USER_SOURCES:
        return PermissionDecision(
            PermissionResult.DENY,
            "That action can only be started by you directly, boss.",
            level,
        )

    # 2. Active grant short-circuit.
    for grant in grants:
        if grant.is_active() and (grant.capability == "*" or grant.capability == tool_name):
            return PermissionDecision(PermissionResult.ALLOW, "granted", level, grant)

    # 3. Level-based decision.
    if level <= 0:
        return PermissionDecision(PermissionResult.ALLOW, "", level)
    if level <= 1:
        # Level 1 tools run with a single grouped confirmation (handled by caller).
        return PermissionDecision(PermissionResult.ALLOW, "", level)
    if level <= 2:
        return PermissionDecision(PermissionResult.CONFIRM_REQUIRED, "confirm", level)
    if level <= 3:
        return PermissionDecision(PermissionResult.CONFIRM_REQUIRED, "confirm", level)
    # Level 4
    return PermissionDecision(PermissionResult.CONFIRM_REQUIRED, "confirm", level)


def revoke_all_grants(grants: list[PermissionGrant]) -> list[PermissionGrant]:
    """Clears any session-level grants, returning an empty list."""
    return []
