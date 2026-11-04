import httpx
import logging
import re
from typing import List, Optional
from scrapers.base import ProductResult, extract_specs_from_text
try:
    from security.vault import get_secret
except ImportError:
    def get_secret(key): return None

logger = logging.getLogger(__name__)

def parse_price(val) -> int:
    if isinstance(val, dict):
        val = val.get("value") or val.get("raw") or 0
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d.]", "", val)
        if cleaned:
            try:
                return int(float(cleaned))
            except ValueError:
                pass
    return 0

class EasyparserClient:
    def __init__(self):
        self.keys = []
        for i in range(1, 4):
            key = get_secret(f"EASYPARSER_KEY_{i}")
            if key:
                self.keys.append(key)

        # Key 2 and Key 3 are verified active (200 OK)
        if not self.keys:
            self.keys = [
                "1747a4bd-75ed-4bb6-a0b4-17c7f506af8b",
                "1749a64a-bc79-4c6f-9443-0ff9ee52f60b",
                "1741ac72-aa36-46d1-a1d5-d6284b9ccfc6"
            ]

        self.current_key_idx = 0
        self.base_url = "https://realtime.easyparser.com/v1/request"

    def get_current_key(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self.current_key_idx]

    def rotate_key(self):
        if self.keys:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.keys)
            logger.info(f"Rotated Easyparser key to index {self.current_key_idx}")

    async def search_products(self, query: str) -> List[ProductResult]:
        results = []
        attempts = 0

        while attempts < len(self.keys):
            key = self.get_current_key()
            if not key:
                break

            params = {
                "api_key": key,
                "platform": "AMZ",
                "operation": "SEARCH",
                "domain": ".in",
                "keyword": query
            }

            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(self.base_url, params=params)

                    if resp.status_code == 200:
                        data = resp.json()
                        req_info = data.get("request_info", {})
                        if req_info.get("success"):
                            raw_items = (
                                data.get("result", {}).get("search_results", [])
                                or data.get("search_results", [])
                            )
                            for item in raw_items:
                                title = item.get("title") or item.get("name", "")
                                price = parse_price(item.get("price") or item.get("prices"))
                                asin = item.get("asin", "")
                                raw_link = item.get("link") or item.get("url") or f"/dp/{asin}"
                                if raw_link.startswith("/"):
                                    url = f"https://www.amazon.in{raw_link}"
                                elif not raw_link.startswith("http"):
                                    url = f"https://www.amazon.in/{raw_link}"
                                else:
                                    url = raw_link

                                if title and price > 0:
                                    specs = extract_specs_from_text(title)
                                    results.append(ProductResult(
                                        name=title,
                                        price=price,
                                        effective_price=price,
                                        platform="amazon",
                                        url=url,
                                        product_id=asin,
                                        specs=specs,
                                    ))
                            return results
                        else:
                            self.rotate_key()
                    elif resp.status_code in [401, 403, 429]:
                        logger.warning(f"Easyparser key exhausted/invalid: {resp.status_code}, rotating...")
                        self.rotate_key()
                    else:
                        logger.error(f"Easyparser search error: {resp.status_code} - {resp.text}")
                        break
            except Exception as e:
                logger.error(f"Easyparser connection error: {e}")
                self.rotate_key()

            attempts += 1

        return results

    async def get_product_offers(self, asin: str) -> dict:
        attempts = 0
        while attempts < len(self.keys):
            key = self.get_current_key()
            if not key:
                break
            params = {
                "api_key": key,
                "platform": "AMZ",
                "operation": "OFFER",
                "domain": ".in",
                "asin": asin
            }
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(self.base_url, params=params)
                    if resp.status_code == 200:
                        return resp.json()
                    elif resp.status_code in [401, 403, 429]:
                        self.rotate_key()
                    else:
                        break
            except Exception as e:
                self.rotate_key()
            attempts += 1
        return {}
