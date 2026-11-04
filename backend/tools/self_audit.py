"""Tool interface for background self-audits."""

import json
from pathlib import Path

AUDIT_FILE = Path(__file__).resolve().parents[1] / "data" / "self_audit.json"


def self_audit(params: dict) -> str:
    action = str(params.get("action", "run")).strip().lower()
    if action == "run":
        return "AUDIT_REQUESTED"
    if action == "report":
        try:
            findings = json.loads(AUDIT_FILE.read_text(encoding="utf-8")).get("findings", [])
        except (OSError, json.JSONDecodeError):
            return "I do not have an audit report yet, boss."
        if not findings:
            return "My latest audit found no issues, boss."
        counts = {level: sum(f.get("severity") == level for f in findings) for level in ("high", "medium", "low")}
        titles = ", ".join(str(f.get("title", "issue")) for f in findings[:3])
        return f"My latest audit found {len(findings)} issues: {counts['high']} high, {counts['medium']} medium, {counts['low']} low. Top findings: {titles}, boss."
    return "Audit action not recognized, boss."
