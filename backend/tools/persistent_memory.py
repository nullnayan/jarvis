# FILE: backend/tools/persistent_memory.py
# Persistent key-value memory stored in backend/data/memory.json across restarts.

import os
import json
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")

def _load_memory() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_memory(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def recall_relevant(query: str, top_n: int = 5) -> list[str]:
    """Returns up to top_n stored facts whose key/value overlap the query's tokens."""
    if not query:
        return []
    mem = _load_memory()
    if not mem:
        return []
    q_tokens = {w for w in query.lower().split() if len(w) > 3}
    scored = []
    for item in mem.values():
        key = str(item.get("key", "")).lower()
        value = str(item.get("value", "")).lower()
        score = 0
        if q_tokens:
            score += sum(1 for w in q_tokens if w in key or w in value)
        if any(w in key for w in query.lower().split()):
            score += 1
        if score > 0:
            scored.append((score, f"{item.get('key')}: {item.get('value')}"))
    scored.sort(key=lambda x: -x[0])
    return [text for _, text in scored[:top_n]]

def persistent_memory(params: dict) -> str:
    action = params.get("action", "recall").lower().strip()
    key = str(params.get("key", "")).strip()
    value = str(params.get("value", "")).strip()
    query = str(params.get("query", "") or key).strip()

    mem = _load_memory()

    if action in ("remember", "save", "store"):
        if not key or not value:
            return "Please provide both what to remember and its detail, boss."
        mem[key.lower()] = {
            "key": key,
            "value": value,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        _save_memory(mem)
        return f"I have remembered that {key} is {value}, boss."

    elif action in ("recall", "get", "find", "search"):
        if not query:
            return "What would you like me to recall, boss?"
        q_lower = query.lower()
        # Exact match
        if q_lower in mem:
            return f"You told me that {mem[q_lower]['key']} is {mem[q_lower]['value']}, boss."
        # Fuzzy / substring match
        for k, item in mem.items():
            if q_lower in k or k in q_lower or any(word in k for word in q_lower.split() if len(word) > 3):
                return f"You told me that {item['key']} is {item['value']}, boss."
        return f"I don't have anything saved about {query}, boss."

    elif action in ("forget", "delete", "remove"):
        if not key:
            return "What would you like me to forget, boss?"
        q_lower = key.lower()
        if q_lower in mem:
            del mem[q_lower]
            _save_memory(mem)
            return f"I have forgotten about {key}, boss."
        for k in list(mem.keys()):
            if q_lower in k:
                del mem[k]
                _save_memory(mem)
                return f"I have forgotten about {key}, boss."
        return f"I didn't have anything saved about {key} anyway, boss."

    elif action in ("list", "all", "show"):
        if not mem:
            return "I don't have any notes or memories saved right now, boss."
        items = [f"{item['key']}: {item['value']}" for item in mem.values()]
        return "Here is what I have remembered: " + "; ".join(items[:10]) + ", boss."

    return "Memory action not recognized, boss."
