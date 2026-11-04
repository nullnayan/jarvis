"""Static and optional model-assisted audit support for Jarvis source files."""

from __future__ import annotations

import ast
import builtins
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from logger import get_logger
from self_dev.repo_map import PROJECT_ROOT, list_source_files, read_source

_log = get_logger(__name__)
AUDIT_FILE = Path(__file__).resolve().parents[1] / "data" / "self_audit.json"


def parse_audit_findings(content: str) -> list[dict]:
    """Tolerantly parse the JSON array returned by the model."""
    if not content:
        return []
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL | re.I)
    if fenced:
        content = fenced.group(1)
    start, end = content.find("["), content.rfind("]")
    if start < 0 or end <= start:
        return []
    candidate = re.sub(r",\s*([}\]])", r"\1", content[start : end + 1])
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _finding(path: str, line: int, severity: str, title: str, detail: str, fix_hint: str) -> dict:
    return {"severity": severity, "file": path, "line": line, "title": title,
            "detail": detail, "fix_hint": fix_hint, "finding_id": uuid4().hex[:8]}


def _relative(path: str) -> str:
    return os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")


def static_audit(files: list[str]) -> list[dict]:
    """Run conservative AST checks without executing any project code."""
    findings: list[dict] = []
    for file_name in files:
        abs_path = file_name if os.path.isabs(file_name) else os.path.join(PROJECT_ROOT, file_name)
        rel_path = _relative(abs_path)
        try:
            source = Path(abs_path).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError as exc:
            findings.append(_finding(rel_path, exc.lineno or 1, "high", "Syntax error", str(exc), "Correct the invalid syntax."))
            continue
        except OSError as exc:
            _log.warning("Could not audit %s: %s", rel_path, exc)
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(_finding(rel_path, node.lineno, "medium", "Bare except", "A bare except hides unexpected failures.", "Catch a specific exception type."))

        # Check only function-local plain names. This deliberately avoids trying to
        # emulate Python's full scope rules, which would create noisy false positives.
        module_bound = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        module_bound.update(alias.asname or alias.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names)
        module_bound.update(alias.asname or alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for alias in n.names)
        builtin_names = set(dir(builtins))
        for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            local_bound = {arg.arg for arg in fn.args.args + fn.args.kwonlyargs}
            if fn.args.vararg:
                local_bound.add(fn.args.vararg.arg)
            if fn.args.kwarg:
                local_bound.add(fn.args.kwarg.arg)
            local_bound.update(n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)))
            for name in (n for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)):
                if name.id not in local_bound | module_bound | builtin_names:
                    findings.append(_finding(rel_path, name.lineno, "high", "Possible unbound name", f"{name.id!r} is used without a visible binding.", "Import it or bind it before use."))

    unique = {(f["file"], f["line"], f["title"]): f for f in findings}
    return list(unique.values())


def llm_audit(files: list[str]) -> list[dict]:
    """Ask Gemini for additional findings, safely skipping when it is unavailable."""
    try:
        from config import GEMINI_MODEL
        from llm.coding_prompts import SELF_AUDIT_PROMPT
        from llm.gemini_client import gemini_client
    except Exception as exc:
        _log.info("LLM audit unavailable: %s", exc)
        return []
    batches, current, size = [], [], 0
    for file_name in files:
        text = read_source(file_name)
        block = f"\n\nFILE: {file_name}\n{text}"
        if current and size + len(block) > 20_000:
            batches.append("".join(current)); current, size = [], 0
        current.append(block); size += len(block)
    if current:
        batches.append("".join(current))
    findings = []
    for batch in batches:
        try:
            for item in parse_audit_findings(gemini_client.generate_content_with_failover(SELF_AUDIT_PROMPT + batch, model=GEMINI_MODEL)):
                item.setdefault("finding_id", uuid4().hex[:8])
                findings.append(item)
        except Exception as exc:
            _log.warning("LLM audit batch failed: %s", exc)
    return findings


def _scope_files(scope: str) -> list[str]:
    if scope.startswith("file:"):
        return [scope[5:].strip()]
    if scope == "changed":
        try:
            result = subprocess.run(["git", "diff", "--name-only"], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)
            changed = [line for line in result.stdout.splitlines() if line.endswith(".py")]
            if changed:
                return changed
        except Exception as exc:
            _log.info("Could not get changed files: %s", exc)
    return [path for path in list_source_files() if path.endswith(".py")][:30]


def run_audit(scope: str = "changed") -> list[dict]:
    files = _scope_files(scope)
    findings = static_audit(files) + llm_audit(files)
    deduped = {(f.get("file"), f.get("line"), f.get("title")): f for f in findings}
    result = list(deduped.values())
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_FILE.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "findings": result}, indent=2), encoding="utf-8")
    return result
