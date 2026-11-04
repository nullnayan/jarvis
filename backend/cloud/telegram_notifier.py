import httpx
import logging
import os

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")

async def send_telegram_deal_alert(
    product_name: str,
    price: int,
    effective_price: int,
    platform: str,
    url: str,
    specs: str = "",
    card_offer: str = "",
    category: str = "product",
    match_score: int = 0,
    processor: str = "",
    antutu_score: str = "",
    rank: int = 0,
    total_ranks: int = 3
) -> bool:
    """Send rich formatted deal card to user's Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    icon = "💻" if "laptop" in category.lower() else "📱"
    cat_title = category.upper()

    header = f"🔥 <b>DEAL HUNTER ALERT: {cat_title}</b>"
    if rank > 0:
        header += f" <b>(#{rank} of {total_ranks})</b>"

    lines = [
        header,
        "",
        f"{icon} <b>Product:</b> {product_name}",
        f"🏪 <b>Platform:</b> {platform.title()}",
        f"💰 <b>Listed Price:</b> ₹{price:,}",
        f"🏷️ <b>Effective Price:</b> <b>₹{effective_price:,}</b>" + (f" ({card_offer})" if card_offer else "")
    ]

    # Processor & Benchmark Display (Strict user requirement)
    if processor:
        lines.append(f"\n⚡ <b>Processor:</b> {processor}")
    if antutu_score:
        lines.append(f"📊 <b>AnTuTu Benchmark:</b> {antutu_score}")

    if specs:
        # Format pipe-separated specs cleanly, skipping processor/antutu if already displayed above
        spec_lines = [
            s.strip() for s in specs.split("|")
            if s.strip() and not s.strip().startswith("processor:") and not s.strip().startswith("antutu:")
        ]
        if spec_lines:
            lines.append("\n⚙️ <b>Specifications:</b>")
            for s in spec_lines:
                lines.append(f"• {s}")

    if match_score > 0:
        lines.append(f"\n🎯 <b>Match Score:</b> {match_score}%")

    if url:
        lines.append(f"\n🔗 <b>Open Product in App:</b>\n{url}")
    else:
        lines.append("\n(Direct link not available)")

    text = "\n".join(lines)

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"[Telegram] Deal alert sent for {product_name}")
                return True
            else:
                logger.error("[Telegram] API error %s", resp.status_code)
    except Exception as e:
        # HTTP exception strings may contain the bot token in the request URL.
        logger.error("[Telegram] Failed to send alert (%s)", type(e).__name__)
    return False

async def send_telegram_status_update(message: str) -> bool:
    """Send informational status / heartbeat / no-deal update to user's Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, json=payload)
            if resp.status_code == 200:
                logger.info("[Telegram] Status update delivered.")
                return True
            else:
                logger.error("[Telegram] Status update API error %s", resp.status_code)
    except Exception as e:
        logger.error("[Telegram] Failed to send status update (%s)", type(e).__name__)
    return False
