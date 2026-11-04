import asyncio
import json
import logging
import re
import time
from scrapers.easyparser import EasyparserClient
from scrapers.quickcommerce import QuickCommerceClient
from cloud.deal_db import DealDB
from scrapers.card_offers import get_latlon, apply_phone_discount, apply_laptop_flat_discount, apply_laptop_offer_discount
from scrapers.base import (
    SpecCriteria, score_product,
    detect_phone_processor_and_antutu, detect_laptop_processor
)

logger = logging.getLogger(__name__)

VALID_SPEC_KEYS = {
    "category", "min_price", "max_price", "reference_product",
    "min_ram_gb", "min_storage_gb", "min_battery_mah", "min_antutu",
    "display_type", "min_refresh_rate", "min_ram_gb_laptop",
    "min_storage_gb_laptop", "processor_keywords", "min_screen_size",
    "gpu_keywords", "brand_preference", "must_have_keywords", "exclude_keywords"
}

def get_base_model_key(name: str) -> str:
    """Extract a canonical base model key to avoid notifying the same model in different colors."""
    text = name.lower()
    if "|" in text:
        text = text.split("|")[0]
    text = re.sub(r'\(.*?\)', '', text)
    for w in [
        '5g', '4g', 'with', 'intel', 'amd', 'laptop', 'thin', 'and', 'light',
        'notebook', 'prime', 'edition', 'processor', 'oneplus', 'xiaomi', 'redmi',
        'realme', 'motorola', 'moto', 'samsung', 'oppo', 'vivo', 'iqoo', 'poco',
        'acer', 'asus', 'hp', 'lenovo', 'dell', 'msi'
    ]:
        text = re.sub(rf'\b{w}\b', '', text)
    tokens = [t for t in re.findall(r'\b[a-z0-9\+\-]+\b', text) if len(t) > 1]
    return " ".join(tokens[:2]) if tokens else name.lower()[:15]


class DealMonitor:
    def __init__(self, db: DealDB, hub):
        self.db = db
        self.hub = hub
        self.easyparser = EasyparserClient()
        self.quickcommerce = QuickCommerceClient()
        self._running = True
        self._cycle_count = 0
        self._wake_event = asyncio.Event()
        self._force_notify_on_wake = False

    def trigger_immediate_run(self):
        """Immediately wakes up monitor and forces notification of current best deals."""
        logger.info("[DealMonitor] Immediate run triggered via toggle.")
        self._force_notify_on_wake = True
        self._wake_event.set()

    async def run_forever(self):
        logger.info("[DealMonitor] Background monitor loop active.")
        while self._running:
            try:
                toggle = await self.db.get_global_toggle()
                if not toggle:
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=30.0)
                        self._wake_event.clear()
                    except asyncio.TimeoutError:
                        continue

                    toggle = await self.db.get_global_toggle()
                    if not toggle:
                        continue

                force_notify = self._force_notify_on_wake
                self._force_notify_on_wake = False
                self._wake_event.clear()

                self._cycle_count += 1
                # Every 3rd cycle (3 * 4h = 12 hours) does deep card discount search for top 3 laptops
                is_12hr_deep_search = (self._cycle_count % 3 == 0)

                watches = await self.db.get_active_watches()
                if not watches:
                    await self.db.seed_default_watches()
                    watches = await self.db.get_active_watches()

                logger.info(f"[DealMonitor] Cycle #{self._cycle_count} running (12hr_deep={is_12hr_deep_search}, force_notify={force_notify})")
                total_deals_notified = 0
                for watch in watches:
                    count = await self.process_watch(watch, is_12hr_deep=is_12hr_deep_search, force_notify=force_notify)
                    total_deals_notified += (count or 0)

                if total_deals_notified == 0:
                    logger.info("[DealMonitor] Cycle complete: No new deals found. Sending status notification.")
                    try:
                        from cloud.telegram_notifier import send_telegram_status_update
                        status_text = "🔍 Deal Hunter: Scanned Amazon & Flipkart. No new price drops or qualifying deals found under your budget. Next scan in 4 hours."
                        tg_msg = (
                            "🔍 <b>DEAL HUNTER SCAN COMPLETE</b>\n\n"
                            "Scanned Amazon & Flipkart.\n"
                            "No new price drops or qualifying deals below budget in this cycle.\n\n"
                            "⏰ <i>Next scan scheduled in 4 hours.</i>"
                        )
                        await send_telegram_status_update(tg_msg)

                        status_payload = {
                            "type": "deal_status_alert",
                            "message": status_text,
                            "timestamp": time.time(),
                        }
                        alert_id = await self.db.save_pending_alert("deal_status", status_payload)
                        await self.hub.send_deal_status_alert(status_text, alert_id=alert_id)
                    except Exception as status_err:
                        logger.error(f"[DealMonitor] Failed to send no-deal status: {status_err}")

                # Continuous interval: every 4 hours (14,400 seconds)
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=14400.0)
                    self._wake_event.clear()
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error(f"[DealMonitor] Loop Error: {e}", exc_info=True)
                await asyncio.sleep(15)

    async def process_watch(self, watch, is_12hr_deep=False, force_notify=False):
        category = watch["category"]
        pincodes_str = watch.get("pincodes", "")
        if not pincodes_str:
            pincodes_str = ",".join(await self.db.get_pincodes())
        if not pincodes_str:
            logger.info("Configure delivery pincodes before running location-based watches.")
            return
        pincodes = pincodes_str.split(",")
        lat, lon = get_latlon(pincodes[0])

        # Search BOTH Amazon & Flipkart every 4 hours
        amz_task = self.search_amazon(watch, is_deep_laptop=(is_12hr_deep and category == "laptop"))
        fk_task = self.search_flipkart(watch, lat, lon)

        amz_res, fk_res = await asyncio.gather(amz_task, fk_task, return_exceptions=True)
        products = []
        if isinstance(amz_res, list): products.extend(amz_res)
        if isinstance(fk_res, list): products.extend(fk_res)

        return await self.filter_and_notify(watch, products, force_notify=force_notify)

    async def search_amazon(self, watch, is_deep_laptop=False):
        results = await self.easyparser.search_products(watch["query"])
        for product in results:
            if watch["category"] == "phone":
                apply_phone_discount(product)
            elif watch["category"] == "laptop":
                apply_laptop_flat_discount(product)
        return results


    async def search_flipkart(self, watch, lat, lon):
        results = await self.quickcommerce.search_products(watch["query"], lat, lon)
        for product in results:
            if watch["category"] == "phone":
                apply_phone_discount(product)
            elif watch["category"] == "laptop":
                apply_laptop_flat_discount(product)
            else:
                product.effective_price = product.price
        return results


    async def pick_top3_with_groq(self, products, watch):
        return sorted(products, key=lambda product: product.effective_price)[:3]


    async def filter_and_notify(self, watch, products, force_notify=False):
        if not products:
            return 0

        category = watch.get("category", "phone")
        specs_dict = json.loads(watch.get("specs_json") or "{}")
        max_price = watch.get("max_price", 0)

        if isinstance(specs_dict, dict) and specs_dict:
            clean_specs = {k: v for k, v in specs_dict.items() if k in VALID_SPEC_KEYS}
            clean_specs["max_price"] = max_price
            criteria = SpecCriteria(**clean_specs)
        else:
            criteria = SpecCriteria(category=category, max_price=max_price)

        matches = []
        for p in products:
            if criteria.min_price > 0 and p.effective_price < criteria.min_price:
                continue
            if criteria.max_price > 0 and p.effective_price > criteria.max_price:
                continue

            score = score_product(p, criteria)
            if score == -1 or score < 40:
                continue

            if not force_notify and await self.db.was_already_notified(p.name, p.effective_price):
                continue
            matches.append((p, score))

        if not matches and force_notify:
            in_range = [p for p in products if criteria.min_price <= p.effective_price and (not criteria.max_price or p.effective_price <= criteria.max_price)]
            for p in in_range:
                s = score_product(p, criteria)
                if s != -1:
                    matches.append((p, max(s, 70)))

        # Sort matches: highest score first, then best price
        matches.sort(key=lambda x: (-x[1], x[0].effective_price))

        # Smart deduplication by base product model
        deduped = []
        seen_keys = set()
        for p, score in matches:
            base_key = get_base_model_key(p.name)
            if base_key not in seen_keys:
                seen_keys.add(base_key)
                deduped.append((p, score))

        # Select Top 3 prioritized deals
        to_notify = deduped[:3]

        notified_count = 0
        for idx, (product, score) in enumerate(to_notify):
            rank = idx + 1
            offer_str = f"Rs. {product.price - product.effective_price:,} card discount" if product.effective_price < product.price else ""
            spec_str = " | ".join(product.specs.values()) if product.specs else ""

            # Extract processor and AnTuTu benchmark
            processor = product.specs.get("processor", "")
            antutu = product.specs.get("antutu", "")
            if category == "phone" and not processor:
                p_name, a_score = detect_phone_processor_and_antutu(product.name, product.raw_description)
                processor = p_name
                antutu = f"~{a_score:,}"
            elif category == "laptop" and not processor:
                p_name, _ = detect_laptop_processor(product.name, product.raw_description)
                processor = p_name

            # 1. Send rich card to Telegram
            try:
                from cloud.telegram_notifier import send_telegram_deal_alert
                await send_telegram_deal_alert(
                    product_name=product.name,
                    price=product.price,
                    effective_price=product.effective_price,
                    platform=product.platform,
                    url=product.url,
                    specs=spec_str,
                    card_offer=offer_str,
                    category=category,
                    match_score=score,
                    processor=processor,
                    antutu_score=antutu,
                    rank=rank,
                    total_ranks=len(to_notify)
                )
            except Exception as tg_err:
                logger.error(f"[DealMonitor] Telegram alert error: {tg_err}")

            # 2. Save in pending alerts for companion app
            alert_payload = {
                "type": "deal_alert",
                "product_name": product.name,
                "price": product.price,
                "effective_price": product.effective_price,
                "platform": product.platform,
                "url": product.url,
                "specs": spec_str,
                "card_offer": offer_str,
                "match_score": score,
                "category": category,
                "processor": processor,
                "antutu_score": antutu,
                "rank": rank,
                "timestamp": time.time(),
            }
            alert_id = await self.db.save_pending_alert("deal_alert", alert_payload)

            # 3. Send notification to Phone Companion App
            await self.hub.send_deal_alert(
                product_name=product.name,
                price=product.price,
                effective_price=product.effective_price,
                platform=product.platform,
                url=product.url,
                specs=spec_str,
                card_offer=offer_str,
                match_score=score,
                category=category,
                alert_id=alert_id
            )
            await self.db.log_notification(product.name, product.product_id,
                                          product.platform, product.price,
                                          product.effective_price)
            notified_count += 1

        return notified_count

    def stop(self):
        self._running = False
        self._wake_event.set()
