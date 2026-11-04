# FILE: timer.py
# Sets a countdown timer that triggers a TTS alert when complete.
import asyncio

_pipeline_ref = None

def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline

def _to_num(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0

def set_timer(params: dict) -> str:
    minutes = _to_num(params.get("minutes", 0))
    seconds = _to_num(params.get("seconds", 0))
    total = int(minutes * 60 + seconds)
    if total <= 0:
        return "Please specify a valid duration, boss."
    if total > 7200:
        return "The maximum timer duration is two hours, boss."

    async def _fire():
        await asyncio.sleep(total)
        if _pipeline_ref:
            await _pipeline_ref.respond_and_idle(f"Your {_format_duration(total)} timer is up, boss.")

    if _pipeline_ref:
        asyncio.create_task(_fire())

    return f"Timer set for {_format_duration(total)}, boss."

def _format_duration(secs: int) -> str:
    if secs >= 3600:
        h, r = divmod(secs, 3600)
        m = r // 60
        return f"{h} hour{'s' if h > 1 else ''}" + (f" {m} minute{'s' if m > 1 else ''}" if m else "")
    elif secs >= 60:
        m, s = divmod(secs, 60)
        return f"{m} minute{'s' if m > 1 else ''}" + (f" {s} second{'s' if s > 1 else ''}" if s else "")
    return f"{secs} second{'s' if secs > 1 else ''}"
