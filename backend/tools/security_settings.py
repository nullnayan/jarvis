# FILE: backend/tools/security_settings.py
# Voice/UI tool for managing the shutdown password and security state.
# Never speaks, logs, or returns the plaintext password or its hash.

from security.credentials import password_is_set


def security_settings(params: dict) -> str:
    action = str(params.get("action", "")).strip().lower()

    if action == "status":
        if password_is_set():
            return "A shutdown password is set, boss."
        return "No shutdown password is set, boss."
    if action == "change_shutdown_password":
        # The actual change flows through the pipeline's pending_password state
        # machine (verify -> new -> confirm). This tool just arms that flow.
        return "PASSWORD_CHANGE_REQUESTED"
    if action == "revoke_all":
        return "REVOKE_ALL_GRANTS"
    return "Security action not recognized, boss."
