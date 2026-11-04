"""Append-only, redacted tool execution audit records."""
import json
from datetime import datetime
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parents[1] / "data" / "audit"
SENSITIVE = ("password", "token", "key", "secret")


def _redact(value):
    if isinstance(value, dict):
        return {key: "[redacted]" if any(word in key.lower() for word in SENSITIVE) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def log_action(entry: dict) -> None:
    payload = {"timestamp": datetime.now().astimezone().isoformat(), **_redact(entry)}
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        path = AUDIT_DIR / f"jarvis-audit-{datetime.now():%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent(n: int = 5) -> list[dict]:
    rows = []
    for path in sorted(AUDIT_DIR.glob("jarvis-audit-*.jsonl")) if AUDIT_DIR.exists() else []:
        try:
            rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except (OSError, json.JSONDecodeError):
            continue
    return rows[-n:]


def read_today() -> list[dict]:
    path = AUDIT_DIR / f"jarvis-audit-{datetime.now():%Y-%m-%d}.jsonl"
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []
