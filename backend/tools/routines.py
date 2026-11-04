# FILE: backend/tools/routines.py
# Custom workflows and named routines stored in backend/data/routines.json.

import os
import json
import asyncio

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ROUTINES_FILE = os.path.join(DATA_DIR, "routines.json")

_pipeline_ref = None

def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline

def _load_routines() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ROUTINES_FILE):
        # Seed with a default morning routine
        defaults = {
            "morning": {
                "name": "morning routine",
                "steps": [
                    "set brightness to 70",
                    "set volume to 40",
                    "open brave",
                    "what is the weather today"
                ]
            }
        }
        _save_routines(defaults)
        return defaults
    try:
        with open(ROUTINES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_routines(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ROUTINES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def routines_tool(params: dict) -> str:
    action = params.get("action", "list").lower().strip()
    name = str(params.get("name", "morning")).lower().strip()
    steps = params.get("steps", [])

    routines = _load_routines()

    if action in ("run", "execute", "start"):
        # Match routine name
        matched_key = None
        for k in routines:
            if k in name or name in k:
                matched_key = k
                break

        if not matched_key:
            return f"I could not find a routine named '{name}', boss."

        routine = routines[matched_key]
        step_list = routine.get("steps", [])

        async def _run_async():
            if _pipeline_ref:
                for step in step_list:
                    print(f"[Routine] Executing step: {step}")
                    await _pipeline_ref.process_command(step, source="routine")
                    await asyncio.sleep(2.0)

        if _pipeline_ref:
            asyncio.create_task(_run_async())
            return f"Running your {routine.get('name', matched_key)}, boss."
        return f"Executing {matched_key} routine, boss."

    elif action in ("create", "add", "save"):
        if not steps:
            return "Please provide the steps for the routine, boss."
        routines[name] = {"name": name, "steps": steps}
        _save_routines(routines)
        return f"Created routine '{name}' with {len(steps)} steps, boss."

    elif action in ("list", "show"):
        if not routines:
            return "No routines saved yet, boss."
        names = [f"'{r.get('name', k)}' ({len(r.get('steps', []))} steps)" for k, r in routines.items()]
        return "Saved routines: " + ", ".join(names) + ", boss."

    return "Routine action not recognized, boss."
