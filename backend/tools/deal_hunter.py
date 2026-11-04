import json
from cloud.deal_db import DealDB
from scrapers.base import SpecCriteria

async def deal_hunter(action: str = "status", category: str = "", query: str = "", max_price: int = 0, specs: str = "", interval_hours: float = 2, target: str = "", pincodes: str = "", **kwargs) -> str:
    db = DealDB()
    await db.init_db()

    if "action" not in kwargs and not action:
        action = kwargs.get("cmd", "status")

    action = action.lower()
    if action in ["start", "toggle_on", "enable"]:
        await db.set_global_toggle(True)
        return "Deal Hunter is active. Add your own product watches and delivery location to start monitoring."

    elif action in ["stop", "toggle_off", "disable"]:
        await db.set_global_toggle(False)
        return "Deal Hunter stopped. Background monitoring and notifications are paused."

    elif action == "pause":
        await db.pause_watch(target or category)
        return f"Notifications for {target or category} paused."

    elif action == "resume":
        await db.resume_watch(target or category)
        return f"Notifications for {target or category} resumed."

    elif action == "watch":
        spec_obj = SpecCriteria(category=category, max_price=max_price)
        await db.add_watch(
            category=category, query=query, max_price=max_price,
            specs_json=json.dumps(spec_obj.to_dict()),
            interval_minutes=int(interval_hours * 60), deep_interval_minutes=int(interval_hours * 60)
        )
        return f"Added new watch for {category}: '{query}' under ₹{max_price}."

    elif action == "status":
        toggle = await db.get_global_toggle()
        watches = await db.get_active_watches()
        status = "ON" if toggle else "OFF"
        res = f"Deal Hunter is currently {status}.\n"
        if watches:
            res += f"Active watches: {len(watches)}\n"
            for w in watches:
                res += f"- {w['category'].title()}: '{w['query']}' (Max: ₹{w['max_price']})\n"
        return res

    elif action == "set_pincodes":
        if pincodes:
            pins = [p.strip() for p in pincodes.split(',')]
            await db.set_pincodes(pins)
            return f"Pincodes updated to: {', '.join(pins)}"
        return "No pincodes provided."

    return f"Unknown action: {action}. Valid actions: start, stop, pause, resume, watch, status, set_pincodes."
