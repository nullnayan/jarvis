# FILE: backend/tools/scheduler.py
# Persistent scheduled tasks and reminders stored in backend/data/schedules.json.

import os
import json
import time
import asyncio
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SCHEDULE_FILE = os.path.join(DATA_DIR, "schedules.json")

_pipeline_ref = None
_loop_task = None

def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline
    start_scheduler_loop()

def _load_schedules() -> list:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SCHEDULE_FILE):
        return []
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_schedules(data: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def _scheduler_worker():
    while True:
        try:
            now = time.time()
            schedules = _load_schedules()
            remaining = []
            fired = False

            for item in schedules:
                trigger_time = item.get("trigger_time", 0)
                command = item.get("command", "")
                recurring = item.get("recurring", False)
                interval = item.get("interval", 0)

                if now >= trigger_time:
                    fired = True
                    print(f"[Scheduler] Triggering task: '{command}'")
                    if _pipeline_ref:
                        asyncio.create_task(_pipeline_ref.process_command(command, source="scheduler"))

                    if recurring and interval > 0:
                        item["trigger_time"] = now + interval
                        remaining.append(item)
                else:
                    remaining.append(item)

            if fired:
                _save_schedules(remaining)
        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")
        await asyncio.sleep(10)

def start_scheduler_loop():
    global _loop_task
    if _loop_task is None and _pipeline_ref and _pipeline_ref.loop:
        try:
            _loop_task = asyncio.create_task(_scheduler_worker())
        except RuntimeError:
            pass

def scheduler_tool(params: dict) -> str:
    action = params.get("action", "add").lower().strip()
    command = str(params.get("command", "")).strip()
    minutes = float(params.get("minutes", 0) or 0)
    hours = float(params.get("hours", 0) or 0)
    delay_sec = int(hours * 3600 + minutes * 60)

    schedules = _load_schedules()

    if action in ("add", "schedule", "remind"):
        if not command:
            return "Please provide the task or reminder to schedule, boss."
        if delay_sec <= 0:
            delay_sec = 300  # 5 minutes default

        trigger_time = time.time() + delay_sec
        item = {
            "id": uuid.uuid4().hex[:8],
            "command": command,
            "trigger_time": trigger_time,
            "scheduled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "recurring": bool(params.get("recurring", False)),
            "interval": int(params.get("interval_hours", 0)) * 3600
        }
        schedules.append(item)
        _save_schedules(schedules)

        target_time_str = time.strftime("%I:%M %p", time.localtime(trigger_time))
        return f"Scheduled '{command}' for {target_time_str}, boss."

    elif action in ("list", "show"):
        if not schedules:
            return "You have no upcoming scheduled tasks, boss."
        now = time.time()
        lines = []
        for s in schedules:
            mins_left = max(1, int((s["trigger_time"] - now) / 60))
            lines.append(f"'{s['command']}' in {mins_left} minutes")
        return "Upcoming tasks: " + "; ".join(lines) + ", boss."

    elif action in ("clear", "cancel"):
        _save_schedules([])
        return "Cleared all scheduled tasks, boss."

    return "Scheduler action not recognized, boss."
