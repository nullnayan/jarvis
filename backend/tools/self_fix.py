"""Tool interface for preparing a self-fix; application is owned by pipeline approval."""

import json
from pathlib import Path
from self_dev.patcher import prepare_patch, revert_last_self_fix


def self_fix(params: dict):
    action = str(params.get("action", "fix")).strip().lower()
    if action == "revert":
        return revert_last_self_fix()[1]
    if action != "fix":
        return "Self-fix action not recognized, boss."
    path = str(params.get("path", "")).strip()
    instruction = str(params.get("instruction", "")).strip()
    finding_id = str(params.get("finding_id", "")).strip()
    if finding_id and not path:
        report = Path(__file__).resolve().parents[1] / "data" / "self_audit.json"
        try:
            findings = json.loads(report.read_text(encoding="utf-8")).get("findings", [])
            finding = next((item for item in findings if item.get("finding_id") == finding_id), None)
            if finding:
                path = str(finding.get("file", ""))
                instruction = instruction or str(finding.get("fix_hint") or finding.get("detail") or "Repair this finding.")
        except (OSError, json.JSONDecodeError):
            pass
    if not path or not instruction:
        return "Tell me which file and issue to fix, boss."
    return prepare_patch(path, instruction)
