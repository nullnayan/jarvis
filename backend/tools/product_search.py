import asyncio
import re
from typing import List
from scrapers.easyparser import EasyparserClient
from scrapers.quickcommerce import QuickCommerceClient
from cloud.deal_db import DealDB
from scrapers.card_offers import get_latlon, apply_phone_discount, apply_laptop_flat_discount
from scrapers.base import ProductResult

TABLET_KEYWORDS = ["pad", "tablet", "tab", "ipad", "kindle", "case", "cover", "protector", "tempered"]
ACCESSORY_KEYWORDS = ["bag", "sleeve", "backpack", "mouse", "keyboard", "stand", "charger", "adapter", "cable", "skin", "cover", "screen protector"]

def extract_platform_and_clean_query(raw_text: str) -> tuple[str, str]:
    text = raw_text.lower().strip()
    platform = "both"

    if "flipkart" in text or " on fk" in text:
        platform = "flipkart"
    elif "amazon" in text or " on amz" in text:
        platform = "amazon"

    # Clean filler words
    cleaned = re.sub(r"\b(price of|price for|search for|find|check price of|show me|on flipkart|on amazon|from flipkart|from amazon|flipkart|amazon)\b", "", text, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split()).strip()
    return platform, cleaned

def is_valid_phone(name: str) -> bool:
    lower = name.lower()
    for bad in TABLET_KEYWORDS:
        if re.search(rf"\b{re.escape(bad)}\b", lower):
            return False
    return True

def is_valid_laptop(name: str) -> bool:
    lower = name.lower()
    for bad in ACCESSORY_KEYWORDS:
        if re.search(rf"\b{re.escape(bad)}\b", lower):
            return False
    return True

async def product_search(query: str = "", max_price: int = 0, platform: str = "both", **kwargs) -> str:
    """Search products on Amazon India and/or Flipkart with strict filtering and relevance."""
    raw_query = query or kwargs.get("product") or kwargs.get("product_name") or kwargs.get("name") or kwargs.get("q") or ""
    if not raw_query:
        return "Please specify a product name to search for."

    detected_platform, clean_query = extract_platform_and_clean_query(raw_query)
    if platform == "both" and detected_platform != "both":
        platform = detected_platform
    elif "platform" in kwargs and kwargs["platform"]:
        platform = kwargs["platform"]

    search_term = clean_query if clean_query else raw_query

    db = DealDB()
    pincodes = await db.get_pincodes()
    if not pincodes:
        return "Configure your delivery pincode before searching local products."
    lat, lon = get_latlon(pincodes[0])

    easyparser = EasyparserClient()
    quickcommerce = QuickCommerceClient()

    amazon_task = None
    flipkart_task = None

    plat_lower = platform.lower()
    if plat_lower in ["amazon", "amz", "both"]:
        amazon_task = easyparser.search_products(search_term)
    if plat_lower in ["flipkart", "fk", "both"]:
        flipkart_task = quickcommerce.search_products(search_term, lat, lon)

    results: List[ProductResult] = []

    if amazon_task and flipkart_task:
        amz_res, fk_res = await asyncio.gather(amazon_task, flipkart_task, return_exceptions=True)
        if isinstance(amz_res, list): results.extend(amz_res)
        if isinstance(fk_res, list): results.extend(fk_res)
    elif amazon_task:
        amz_res = await amazon_task
        if isinstance(amz_res, list): results.extend(amz_res)
    elif flipkart_task:
        fk_res = await flipkart_task
        if isinstance(fk_res, list): results.extend(fk_res)

    if not results:
        return f"I couldn't find any products matching '{search_term}' on {platform.title()}."

    is_phone_query = any(k in search_term.lower() for k in ["phone", "mobile", "smartphone", "motorola", "edge", "fusion", "redmi", "realme", "samsung", "oneplus", "iqoo"])
    is_laptop_query = "laptop" in search_term.lower()

    # Query tokens for relevance matching (ignore tiny words)
    query_tokens = [w for w in re.findall(r"\w+", search_term.lower()) if len(w) > 2]

    filtered: List[tuple[ProductResult, int]] = []
    for p in results:
        name_lower = p.name.lower()

        # Category rejection
        if is_phone_query and not is_valid_phone(name_lower):
            continue
        if is_laptop_query and not is_valid_laptop(name_lower):
            continue

        # Relevance scoring: count how many query words appear in product name
        match_count = sum(1 for token in query_tokens if token in name_lower)
        if query_tokens and match_count == 0:
            continue

        # Apply card discounts
        if is_phone_query or "phone" in name_lower:
            apply_phone_discount(p)
        elif is_laptop_query or "laptop" in name_lower:
            apply_laptop_flat_discount(p)
        else:
            p.effective_price = p.price

        if max_price > 0 and p.effective_price > max_price:
            continue

        filtered.append((p, match_count))

    if not filtered:
        # Fallback if strict filter rejected everything
        for p in results:
            if is_phone_query and not is_valid_phone(p.name.lower()):
                continue
            p.effective_price = p.price
            filtered.append((p, 1))

    if not filtered:
        return f"No matching {search_term} found within budget."

    # Sort primarily by relevance (highest match_count), secondarily by effective price
    filtered.sort(key=lambda x: (-x[1], x[0].effective_price))
    top_matches = [item[0] for item in filtered[:5]]

    # Highlight top match directly
    best = top_matches[0]
    out = f"The {best.name} is available on {best.platform.title()} for Rs. {best.effective_price:,}"
    if best.effective_price < best.price:
        out += f" (down from Rs. {best.price:,} with Rs. {best.price - best.effective_price:,} card discount)"
    out += ".\n"

    if len(top_matches) > 1:
        out += "\nOther options found:\n"
        for i, p in enumerate(top_matches[1:], 2):
            out += f"{i}. {p.name} - Rs. {p.effective_price:,} on {p.platform.title()}"
            if p.effective_price < p.price:
                out += f" (MRP/Listed: Rs. {p.price:,})"
            out += "\n"

    return out.strip()
