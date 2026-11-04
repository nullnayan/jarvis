import logging
import json
from pathlib import Path

PRIVATE_LOCATIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "delivery_locations.json"

PHONE_FLAT_DISCOUNT = 1500
LAPTOP_FLAT_DISCOUNT = 1500

DEFAULT_SALE_OFFERS = {
    "flipkart": [
        {"bank": "SBI", "type": "percentage", "value": 10, "max_discount": 3000,
         "description": "10% instant discount on SBI Credit Card, up to ₹3,000"},
    ],
    "amazon": [
        {"bank": "SBI", "type": "percentage", "value": 10, "max_discount": 3000,
         "description": "10% instant discount on SBI Credit Card, up to ₹3,000"},
    ],
}

PINCODE_MAP = {
    "110001": (28.6139, 77.2090),   # Delhi
    "201301": (28.5355, 77.3910),   # Noida
    "122001": (28.4595, 77.0266),   # Gurgaon
    "400001": (18.9388, 72.8354),   # Mumbai
    "560001": (12.9716, 77.5946),   # Bangalore
    "500001": (17.3850, 78.4867),   # Hyderabad
    "411001": (18.5204, 73.8567),   # Pune
    "302001": (26.9124, 75.7873),   # Jaipur
    "226001": (26.8467, 80.9462),   # Lucknow
    "700001": (22.5726, 88.3639),   # Kolkata
    "600001": (13.0827, 80.2707),   # Chennai
}

def get_latlon(pincode: str) -> tuple:
    value = str(pincode).strip()
    private_locations = {}
    if PRIVATE_LOCATIONS_PATH.exists():
        private_locations = json.loads(PRIVATE_LOCATIONS_PATH.read_text(encoding="utf-8"))
    coordinates = private_locations.get(value) or PINCODE_MAP.get(value)
    if coordinates is None:
        raise ValueError("Configure coordinates for your delivery pincode; there is no personal-location fallback.")
    return tuple(coordinates)

def apply_phone_discount(product) -> int:
    product.effective_price = max(0, product.price - PHONE_FLAT_DISCOUNT)
    return product.effective_price

def apply_laptop_flat_discount(product) -> int:
    product.effective_price = max(0, product.price - LAPTOP_FLAT_DISCOUNT)
    return product.effective_price

def apply_laptop_offer_discount(product, offer_coupons: list) -> int:
    total_coupon_discount = 0
    for offer in offer_coupons:
        # Simplistic parsing of coupon discounts
        discount = offer.get("discount_amount", 0)
        total_coupon_discount += discount

    platform = product.platform.lower()
    sale_offers = DEFAULT_SALE_OFFERS.get(platform, [])
    best_sale_discount = 0
    for sale in sale_offers:
        if sale.get("type") == "percentage":
            discount = (product.price * sale.get("value", 0)) / 100
            discount = min(discount, sale.get("max_discount", float('inf')))
            best_sale_discount = max(best_sale_discount, discount)

    total_discount = total_coupon_discount + best_sale_discount
    product.effective_price = max(0, int(product.price - total_discount))
    return product.effective_price
