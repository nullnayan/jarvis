import httpx
import asyncio
import logging
from typing import List, Optional
from scrapers.base import ProductResult, extract_specs_from_text
try:
    from security.vault import get_secret
except ImportError:
    def get_secret(key): return None

logger = logging.getLogger(__name__)

class QuickCommerceClient:
    def __init__(self):
        self.keys = []
        for i in range(1, 4):
            key = get_secret(f"QUICKCOMMERCE_KEY_{i}")
            if key:
                self.keys.append(key)

        # Fallback to hardcoded keys from spec
        if not self.keys:
            self.keys = [
                "f0fe1406-2bd7-40f4-b3fb-fd814be93cb1",
                "a098de97-626e-4e9f-a2cb-aa2020649d93",
                "d16042c6-f9bd-4691-b138-9f2a7d7ec850"
            ]

        self.current_key_idx = 0
        self.base_url = "https://api.quickcommerceapi.com"
        self.semaphore = asyncio.Semaphore(1)  # Rate limiting

    def _get_key(self) -> str:
        if not self.keys: return ""
        return self.keys[self.current_key_idx]

    def _rotate_key(self):
        if self.keys:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.keys)
            logger.info(f"Rotated QuickCommerce key to index {self.current_key_idx}")

    async def search_products(self, query: str, lat: float, lon: float) -> List[ProductResult]:
        results = []
        attempts = 0

        while attempts < len(self.keys):
            async with self.semaphore:
                api_key = self._get_key()
                if not api_key: break

                headers = {"X-API-Key": api_key}
                params = {
                    "q": query,
                    "platform": "Flipkart",
                    "lat": lat,
                    "lon": lon
                }

                try:
                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.get(f"{self.base_url}/v1/search", headers=headers, params=params)

                    if resp.status_code in [401, 402, 429]:
                        logger.warning(f"QuickCommerce error {resp.status_code}")
                        self._rotate_key()
                        attempts += 1
                        await asyncio.sleep(1)
                        continue

                    data = resp.json()
                    if data.get("status") != "success":
                        self._rotate_key()
                        attempts += 1
                        continue

                    for item in data.get("data", {}).get("products", []):
                        price = item.get("offer_price")
                        if not price:
                            continue

                        name = item.get("name", "")
                        url = item.get("deeplink") or item.get("url") or (f"https://www.flipkart.com/-/p/-?pid={item.get('id')}" if item.get('id') else "")
                        # Try to extract ID from URL or use name
                        product_id = url.split("?")[0].split("/")[-1] if url else name

                        product = ProductResult(
                            product_id=product_id,
                            name=name,
                            price=int(price),
                            platform="flipkart",
                            url=url,
                            image_url=item.get("image", ""),
                            rating=float(item.get("rating", 0.0)),
                            specs=extract_specs_from_text(name)
                        )
                        results.append(product)
                    return results

                except Exception as e:
                    logger.error(f"Error in QuickCommerce search: {e}")
                    self._rotate_key()
                    attempts += 1
                    await asyncio.sleep(1)

        return results

    async def get_item(self, product_id: str) -> Optional[ProductResult]:
        pass
