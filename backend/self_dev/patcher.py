"""Guarded, approval-only source patch preparation and file-level rollback."""

from __future__ import annotations

import ast
import difflib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from security import file_guard

PROJECT_ROOT = file_guard.PROJECT_ROOT


def _data_dir() -> Path:
    return Path(PROJECT_ROOT) / "backend" / "data"


def _clean_model_source(source: str) -> str:
    source = source.strip()
    if source.startswith("```"):
        source = source.split("\n", 1)[1] if "\n" in source else ""
        if source.rstrip().endswith("```"):
            source = source.rstrip()[:-3]
    return source.strip() + "\n"


def prepare_patch(target_rel: str, instruction: str) -> dict:
    """Create and validate a proposed replacement without writing any file."""
    if not target_rel or os.path.isabs(target_rel):
        return {"error": "The target path must be a project-relative source file."}
    abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, target_rel))
    if not file_guard.is_writable_source(abs_path) or os.path.islink(abs_path):
        return {"error": "That file is not safe for self-modification."}
    try:
        original = Path(abs_path).read_text(encoding="utf-8")
        mtime = os.path.getmtime(abs_path)
    except OSError as exc:
        return {"error": f"I could not read that file: {exc}"}
    try:
        from llm.coding_prompts import SELF_PATCH_PROMPT
        from llm.gemini_client import gemini_client
        from config import GEMINI_MODEL
        new_source = _clean_model_source(gemini_client.generate_content_with_failover(
            SELF_PATCH_PROMPT.format(instruction=instruction, path=target_rel, source=original), model=GEMINI_MODEL))
    except Exception as exc:
        return {"error": f"I could not prepare a patch: {exc}"}
    if not new_source:
        return {"error": "The repair model returned no replacement source."}
    if target_rel.lower().endswith(".py"):
        try:
            ast.parse(new_source)
        except SyntaxError as exc:
            return {"error": f"The proposed Python has invalid syntax: {exc.msg}"}
    old_lines, new_lines = original.splitlines(), new_source.splitlines()
    if abs(len(new_lines) - len(old_lines)) > 400:
        return {"error": "The proposed change is too large."}
    if old_lines and len(new_lines) < len(old_lines) * 0.5:
        return {"error": "The proposed change removes too much of the file."}
    if os.path.getmtime(abs_path) != mtime:
        return {"error": "The file changed while I was preparing the patch; please try again."}
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=target_rel, tofile=target_rel, lineterm=""))
    return {"id": uuid4().hex[:8], "path": target_rel.replace("\\", "/"), "diff": "\n".join(diff_lines),
            "added": sum(line.startswith("+") and not line.startswith("+++") for line in diff_lines),
            "removed": sum(line.startswith("-") and not line.startswith("---") for line in diff_lines),
            "new_source": new_source, "summary": instruction}


def apply_patch(patch: dict) -> tuple[bool, str]:
    """Back up then write an already-approved patch; never call this while proposing."""
    target = str(patch.get("path", ""))
    abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, target))
    if not patch.get("new_source") or not file_guard.is_writable_source(abs_path) or os.path.islink(abs_path):
        return False, "That patch is not safe to apply."
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_root = _data_dir() / "self_fix_backups" / stamp
    try:
        backup_path = backup_root / target
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, backup_path)
        Path(abs_path).write_text(str(patch["new_source"]), encoding="utf-8")
        state = {"last_applied_at": datetime.now(timezone.utc).isoformat(), "backup": str(backup_root), "path": target}
        (_data_dir() / "self_fix_state.json").write_text(json.dumps(state), encoding="utf-8")
        return True, ""
    except OSError as exc:
        return False, f"I could not apply the patch: {exc}"


def revert_last_self_fix() -> tuple[bool, str]:
    root = _data_dir() / "self_fix_backups"
    backups = sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if root.exists() else []
    if not backups:
        return False, "There is no self-fix backup to restore."
    try:
        for saved in backups[0].rglob("*"):
            if saved.is_file():
                target = Path(PROJECT_ROOT) / saved.relative_to(backups[0])
                if not file_guard.is_writable_source(str(target)):
                    return False, "The backup contains an unsafe target."
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, target)
        return True, "The last self-fix was restored, boss."
    except OSError as exc:
        return False, f"I could not restore the backup: {exc}"


def run_tests_and_revert_if_broken(patch: dict) -> tuple[bool, str]:
    try:
        result = subprocess.run([str(Path(PROJECT_ROOT) / "backend" / ".venv" / "Scripts" / "python.exe"), "-m", "pytest", "tests", "-q"], cwd=Path(PROJECT_ROOT) / "backend", capture_output=True, text=True, timeout=60)
    except Exception as exc:
        revert_last_self_fix()
        return False, f"Tests could not run, reverted: {exc}"
    if result.returncode:
        revert_last_self_fix()
        return False, "Tests failed, reverted."
    return True, "The fix was applied and tests passed, boss."
