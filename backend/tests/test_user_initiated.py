import pytest

from security.permissions import PermissionResult, check_permission


@pytest.mark.parametrize("tool", ["self_fix", "self_audit", "security_settings", "run_shell_command"])
def test_user_initiated_tools_are_refused_from_chains(tool):
    assert check_permission(tool, source="chain").result == PermissionResult.DENY


@pytest.mark.parametrize("tool", ["self_fix", "self_audit", "security_settings", "run_shell_command"])
def test_user_initiated_tools_are_allowed_to_reach_confirmation_from_voice(tool):
    assert check_permission(tool, source="voice").result != PermissionResult.DENY
