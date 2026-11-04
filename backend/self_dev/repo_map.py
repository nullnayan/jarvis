# FILE: backend/self_dev/repo_map.py
# Read-only access to the Jarvis codebase: list, read, search source files.

import os
import re
import subprocess
from security.file_guard import is_restricted_file, is_inside_project, PROJECT_ROOT

SOURCE_EXTENSIONS = {".py", ".js", ".json", ".css", ".html", ".md"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "data", ".venv"}


def list_source_files() -> list[str]:
    """Returns project source file paths (git-tracked + untracked), excluding noise."""
    files = []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            candidates = result.stdout.splitlines()
        else:
            candidates = []
    except Exception:
        candidates = []
    for rel in candidates:
        if not rel:
            continue
        parts = rel.split(os.sep)
        if any(p in SKIP_DIRS for p in parts):
            continue
        if os.path.splitext(rel)[1].lower() in SOURCE_EXTENSIONS:
            files.append(rel)
    return sorted(files)


def read_source(rel_path: str, max_chars: int = 20000) -> str:
    """Reads a source file relative to the project root, guarded."""
    abs_path = os.path.join(PROJECT_ROOT, rel_path)
    if not is_inside_project(abs_path):
        return "Blocked: path is outside the project."
    if is_restricted_file(abs_path):
        return "Blocked: that file is security-sensitive."
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def search_source(pattern: str, max_hits: int = 40) -> list[str]:
    """Regex search over source file contents. Returns 'path:line' hits."""
    hits = []
    try:
        regex = re.compile(pattern)
    except re.error:
        return ["Invalid regex pattern."]
    for rel in list_source_files():
        abs_path = os.path.join(PROJECT_ROOT, rel)
        if is_restricted_file(abs_path):
            continue
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if regex.search(line):
                        hits.append(f"{rel}:{lineno}: {line.rstrip()[:120]}")
                        if len(hits) >= max_hits:
                            return hits
        except Exception:
            continue
    return hits


def project_summary() -> str:
    """Returns a concise summary of the codebase."""
    files = list_source_files()
    loc_by_dir = {}
    module_list = []
    for rel in files:
        parts = rel.split(os.sep)
        top = parts[0] if len(parts) > 1 else "root"
        loc_by_dir[top] = loc_by_dir.get(top, 0)
        if rel.endswith(".py"):
            module_list.append(rel)
    return f"{len(files)} source files; Python modules: {len(module_list)}."
