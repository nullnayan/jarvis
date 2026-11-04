# FILE: backend/tools/code_reviewer.py
# Reviews code files or the currently active VS Code file using Gemini Flash.

import os
from llm.gemini_client import gemini_client
from tools.context import get_vscode_active_file

def _is_restricted_file(file_path: str) -> bool:
    norm = os.path.normpath(file_path).lower()
    base = os.path.basename(norm)
    if any(k in norm for k in (".secrets", ".env", "vault", "credential", "id_rsa", "token")):
        return True
    if base in ("config.py", ".secrets.enc", ".env", ".env.local", "vault.py"):
        return True
    return False

def code_reviewer(params: dict) -> str:
    path = str(params.get("path", "")).strip()

    if path and _is_restricted_file(path):
        print(f"[CodeReviewer] BLOCKED review of restricted file: {path}")
        return "Reviewing security-critical configuration files is restricted, boss."

    if not path or not os.path.exists(path):
        active = get_vscode_active_file()
        if active:
            # Check if active is already a full path or in Desktop/current workspace
            user_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if os.path.exists(active):
                path = active
            else:
                # Search Desktop for matching file name
                for root, _, files in os.walk(user_desktop):
                    if active in files:
                        path = os.path.join(root, active)
                        break

    if not path or not os.path.exists(path):
        return "Please open a file in VS Code or provide the file path to review, boss."

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read(15000)

        if not code.strip():
            return f"The file {os.path.basename(path)} is empty, boss."

        fname = os.path.basename(path)
        print(f"[CodeReviewer] Reviewing file: {fname}")
        review = gemini_client.review_code(code, filename=fname)
        return review
    except Exception as e:
        print(f"[CodeReviewer] Error: {e}")
        return "An error occurred while reviewing the code, boss."
