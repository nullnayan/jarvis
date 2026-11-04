# FILE: backend/scrapers/base.py
# Core data models and utilities for the Jarvis Deal Hunter system.

import re
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


# ─── Chipset → AnTuTu Score Lookup (approximations for 2025-2026 flagships/mid-range) ───
ANTUTU_SCORES: Dict[str, int] = {
    # MediaTek Dimensity
    "dimensity 9400": 2400000,
    "dimensity 9300": 2100000,
    "dimensity 9200": 1700000,
    "dimensity 8400": 1300000,
    "dimensity 8300": 1200000,
    "dimensity 8200": 1100000,
    "dimensity 7400": 1000000,
    "dimensity 7300": 900000,
    "dimensity 7200": 850000,
    "dimensity 7050": 750000,
    "dimensity 7025": 650000,
    "dimensity 6300": 550000,
    "dimensity 6100": 450000,
    # Qualcomm Snapdragon
    "snapdragon 8 elite": 2700000,
    "snapdragon 8 gen 4": 2700000,
    "snapdragon 8 gen 3": 2200000,
    "snapdragon 8 gen 2": 1500000,
    "snapdragon 8 gen 1": 1050000,
    "snapdragon 8s gen 4": 2200000,
    "snapdragon 8s gen 3": 1500000,
    "snapdragon 7s gen 3": 900000,
    "snapdragon 7s gen 2": 700000,
    "snapdragon 7 gen 3": 1050000,
    "snapdragon 7 gen 1": 800000,
    "snapdragon 6 gen 4": 900000,
    "snapdragon 6 gen 3": 750000,
    "snapdragon 6 gen 1": 650000,
    "snapdragon 695": 400000,
    "snapdragon 4 gen 2": 550000,
    "snapdragon 4 gen 1": 450000,
    # Samsung Exynos
    "exynos 2500": 2300000,
    "exynos 2400": 2000000,
    "exynos 2200": 1000000,
    "exynos 1580": 1100000,
    "exynos 1480": 900000,
    "exynos 1380": 650000,
    # Apple (for reference)
    "a18 pro": 2800000,
    "a18": 2500000,
    "a17 pro": 2200000,
    # Google Tensor
    "tensor g5": 1800000,
    "tensor g4": 1400000,
    "tensor g3": 1200000,
}


@dataclass
class CardOffer:
    """Represents a bank/card discount offer on a product."""
    bank: str               # "SBI", "HDFC", "ICICI", etc.
    offer_type: str         # "percentage" or "flat"
    value: float            # 10 (for 10%) or 3000 (for flat ₹3000)
    max_discount: int       # max cap in rupees
    min_order: int          # minimum order value
    description: str        # "10% instant discount on SBI Credit Card"
    is_emi: bool = False    # True if this is an EMI offer (we exclude these)

    @property
    def effective_discount(self) -> int:
        """Calculate the actual discount amount for a given context."""
        return self.max_discount if self.offer_type == "percentage" else int(self.value)

    def calculate_discount(self, price: int) -> int:
        """Calculate actual discount for a given price."""
        if self.is_emi:
            return 0
        if self.offer_type == "percentage":
            discount = int(price * self.value / 100)
            return min(discount, self.max_discount) if self.max_discount > 0 else discount
        elif self.offer_type == "flat":
            if price >= self.min_order:
                return int(self.value)
        return 0


@dataclass
class ProductResult:
    """Represents a single product from Amazon or Flipkart."""
    name: str
    price: int                          # Current sale price in rupees
    mrp: int = 0                        # Original MRP (0 if unknown)
    effective_price: int = 0            # Price after best card discount
    discount_percent: int = 0           # Discount percentage from MRP
    url: str = ""                       # Full product link
    image_url: str = ""                 # Product thumbnail
    platform: str = ""                  # "amazon" or "flipkart"
    rating: float = 0.0                 # Star rating (0-5)
    num_reviews: int = 0                # Number of reviews/ratings
    specs: Dict[str, str] = field(default_factory=dict)  # Extracted specs
    card_offers: List[CardOffer] = field(default_factory=list)  # Bank offers
    in_stock: bool = True               # Availability
    seller: str = ""                    # Seller name
    product_id: str = ""               # ASIN or Flipkart product ID
    category: str = ""                  # "phone", "laptop", "earbuds", etc.
    raw_description: str = ""           # Full product description text

    def __post_init__(self):
        if self.effective_price == 0:
            self.effective_price = self.price
        if self.mrp > 0 and self.discount_percent == 0:
            self.discount_percent = int(((self.mrp - self.price) / self.mrp) * 100)

    @property
    def best_card_discount(self) -> int:
        """Returns the maximum non-EMI card discount available."""
        discounts = [
            offer.calculate_discount(self.price)
            for offer in self.card_offers
            if not offer.is_emi
        ]
        return max(discounts) if discounts else 0

    @property
    def best_card_offer(self) -> Optional[CardOffer]:
        """Returns the best non-EMI card offer."""
        best = None
        best_discount = 0
        for offer in self.card_offers:
            if offer.is_emi:
                continue
            d = offer.calculate_discount(self.price)
            if d > best_discount:
                best_discount = d
                best = offer
        return best

    def calculate_effective_price(self) -> int:
        """Calculate and set effective price after best card discount."""
        self.effective_price = self.price - self.best_card_discount
        return self.effective_price

    @property
    def unique_id(self) -> str:
        """Generate a unique identifier for deduplication."""
        key = f"{self.platform}:{self.name}:{self.product_id}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["best_card_discount"] = self.best_card_discount
        offer = self.best_card_offer
        d["best_card_offer_text"] = offer.description if offer else ""
        return d

    def format_for_notification(self) -> str:
        """Format product info for a notification message."""
        lines = [f"🔥 {self.name}"]
        if self.mrp > 0 and self.mrp != self.price:
            lines.append(f"💰 MRP: ₹{self.mrp:,} → Sale: ₹{self.price:,} ({self.discount_percent}% off)")
        else:
            lines.append(f"💰 Price: ₹{self.price:,}")

        offer = self.best_card_offer
        if offer and not offer.is_emi:
            discount = offer.calculate_discount(self.price)
            lines.append(f"💳 {offer.description}: -₹{discount:,}")
            lines.append(f"✅ Effective: ₹{self.effective_price:,}")

        if self.rating > 0:
            lines.append(f"⭐ {self.rating}/5 ({self.num_reviews:,} reviews)")

        specs_str = " | ".join(f"{v}" for v in list(self.specs.values())[:5])
        if specs_str:
            lines.append(f"📋 {specs_str}")

        lines.append(f"🛒 {self.platform.capitalize()}: {self.url}")
        return "\n".join(lines)

    def format_for_speech(self) -> str:
        """Format product for Jarvis TTS (concise)."""
        offer = self.best_card_offer
        if offer and not offer.is_emi:
            return (
                f"{self.name} is available at {self.price} rupees on {self.platform}. "
                f"With {offer.bank} card discount, effective price is {self.effective_price} rupees."
            )
        return f"{self.name} is available at {self.price} rupees on {self.platform}."


@dataclass
class SpecCriteria:
    """User-defined specification requirements for product matching."""
    category: str = "phone"             # "phone", "laptop", "earbuds"
    min_price: int = 0                  # Min price floor (e.g. 25000 for phones)
    max_price: int = 35000              # Max price after card discount
    reference_product: str = ""         # e.g. "Motorola Edge 70 Fusion"

    # Phone specs
    min_ram_gb: int = 0                 # Minimum RAM in GB
    min_storage_gb: int = 0             # Minimum storage in GB
    min_battery_mah: int = 0            # Minimum battery mAh
    min_antutu: int = 0                 # Minimum AnTuTu score
    display_type: str = ""              # "AMOLED", "IPS", etc.
    min_refresh_rate: int = 0           # Minimum Hz

    # Laptop specs
    min_ram_gb_laptop: int = 0
    min_storage_gb_laptop: int = 0
    processor_keywords: List[str] = field(default_factory=list)  # ["i5", "Ryzen 5"]
    min_screen_size: float = 0          # Minimum inches
    gpu_keywords: List[str] = field(default_factory=list)

    # General
    brand_preference: List[str] = field(default_factory=list)
    must_have_keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Spec Extraction from Product Titles / Descriptions ───

def extract_ram(text: str) -> Optional[int]:
    """Extract RAM in GB from text like '8GB RAM', '(8 GB/128 GB)', '8/128'."""
    text = text.lower()
    # Pattern: 8GB RAM, 8 GB RAM, 8GB
    m = re.search(r'(\d+)\s*gb\s*(?:ram|ddr|lpddr)', text)
    if m:
        return int(m.group(1))
    # Pattern: (8GB/128GB) or 8/128
    m = re.search(r'[\(,]\s*(\d+)\s*gb\s*/\s*\d+\s*gb', text)
    if m:
        return int(m.group(1))
    # Pattern: just "8GB" before storage mention
    m = re.search(r'(\d+)\s*gb\s*[/+]', text)
    if m:
        val = int(m.group(1))
        if val <= 24:  # Likely RAM, not storage
            return val
    return None


def extract_storage(text: str) -> Optional[int]:
    """Extract storage in GB from text."""
    text = text.lower()
    # 1TB, 1 TB
    m = re.search(r'(\d+)\s*tb', text)
    if m:
        return int(m.group(1)) * 1024
    # Pattern: 8GB/128GB or 8 GB / 256 GB
    m = re.search(r'\d+\s*gb\s*[/+]\s*(\d+)\s*gb', text)
    if m:
        return int(m.group(1))
    # Pattern: 128GB storage, 256GB ROM
    m = re.search(r'(\d+)\s*gb\s*(?:storage|rom|ssd|internal|nvme|emmc)', text)
    if m:
        return int(m.group(1))
    return None


def extract_battery(text: str) -> Optional[int]:
    """Extract battery capacity in mAh from text."""
    text = text.lower()
    m = re.search(r'(\d{4,5})\s*mah', text)
    if m:
        return int(m.group(1))
    return None


def extract_display_type(text: str) -> Optional[str]:
    """Extract display type from text."""
    text = text.lower()
    for dtype in ["super amoled", "amoled", "oled", "ips", "ltpo", "lcd", "retina"]:
        if dtype in text:
            return dtype.upper()
    return None


def extract_refresh_rate(text: str) -> Optional[int]:
    """Extract display refresh rate in Hz."""
    m = re.search(r'(\d+)\s*hz', text.lower())
    if m:
        val = int(m.group(1))
        if val in (60, 90, 120, 144, 165, 240):
            return val
    return None


def estimate_antutu(text: str) -> Optional[int]:
    """Estimate AnTuTu score based on chipset mentioned in text."""
    text = text.lower()
    for chipset, score in sorted(ANTUTU_SCORES.items(), key=lambda x: len(x[0]), reverse=True):
        if chipset in text:
            return score
    return None


def extract_specs_from_text(text: str, category: str = "phone") -> Dict[str, str]:
    """Extract all detectable specs from product title/description."""
    specs = {}

    ram = extract_ram(text)
    if ram:
        specs["ram"] = f"{ram}GB"

    storage = extract_storage(text)
    if storage:
        specs["storage"] = f"{storage}GB" if storage < 1024 else f"{storage // 1024}TB"

    battery = extract_battery(text)
    if battery:
        specs["battery"] = f"{battery}mAh"

    display = extract_display_type(text)
    if display:
        specs["display"] = display

    refresh = extract_refresh_rate(text)
    if refresh:
        specs["refresh_rate"] = f"{refresh}Hz"

    antutu = estimate_antutu(text)
    if antutu:
        specs["antutu_estimate"] = str(antutu)

    return specs


# ─── Processor & AnTuTu Detection & Scoring ───

def detect_phone_processor_and_antutu(name: str, desc: str = "") -> tuple:
    """
    Detects phone processor name and estimated AnTuTu score.
    Motorola Edge 70 Fusion baseline is calibrated at 1,000,000+ (1M+) AnTuTu.
    """
    text = f"{name} {desc}".lower()

    mapping = [
        # Flagship / Top-tier SoCs (1.3M - 1.6M)
        (['poco f6', 'gt 6', 'snapdragon 8s gen 3', '8s gen 3', '8 gen 3'], 'Snapdragon 8s Gen 3', 1520000),
        (['nord 4', 'snapdragon 7+ gen 3', '7+ gen 3'], 'Snapdragon 7+ Gen 3', 1400000),
        (['poco x6 pro', 'dimensity 8300'], 'Dimensity 8300 Ultra', 1380000),

        # 1M+ Tier: Edge 70 Fusion & Direct Competitors (Realme P4 Pro, Note 14 Pro+)
        (['edge 70 fusion', 'edge 70'], 'Snapdragon 7s Gen 3 (1M+ Benchmark)', 1050000),
        (['p4 pro', 'realme p4 pro'], 'Snapdragon 7 Gen 3 (1M+ Benchmark)', 1020000),
        (['edge 50 pro'], 'Snapdragon 7 Gen 3', 1000000),
        (['note 14 pro+', 'note-14 pro+'], 'Snapdragon 7s Gen 3', 1010000),
        (['nord ce4', 'snapdragon 7 gen 3', '7 gen 3'], 'Snapdragon 7 Gen 3', 950000),
        (['nord ce6'], 'Snapdragon 7s Gen 3', 980000),
        (['oppo k14 plus'], 'Snapdragon 7 Gen 3', 950000),

        # Upper Mid-range (700k - 800k)
        (['note 14 pro', 'note-14 pro', 'dimensity 7300'], 'Dimensity 7300 Ultra', 750000),
        (['nothing phone (4b)', 'nothing phone (2a)', 'dimensity 7200', 'iqoo z9', 'z11x'], 'Dimensity 7200 Pro', 730000),
        (['galaxy a36', 'galaxy f36', 'galaxy f70 pro', 'exynos 1480'], 'Exynos 1480 5G', 720000),
        (['edge 50 fusion', 'p2 pro', 'p1 pro', 'snapdragon 7s gen 2', '7s gen 2'], 'Snapdragon 7s Gen 2', 680000),

        # Lower Mid-range (550k - 650k)
        (['narzo 80 pro', 'narzo 70 pro', 'dimensity 7050'], 'Dimensity 7050', 600000),

        # Budget SoCs (< 500k) - Inferior to Edge 70 Fusion
        (['realme 4t', '12x', '13x', 'dimensity 6300', '6300'], 'Dimensity 6300 (Budget)', 420000),
        (['snapdragon 4 gen 2', '4 gen 2'], 'Snapdragon 4 Gen 2 (Budget)', 430000),
        (['g99', 'g85', 'unisoc', 'p35'], 'Entry-Level Processor', 250000),
    ]

    for keys, proc, score in mapping:
        if any(k in text for k in keys):
            return proc, score

    if 'snapdragon' in text:
        return 'Snapdragon 5G Processor', 800000
    if 'dimensity' in text:
        return 'MediaTek Dimensity 5G', 750000
    return '5G Octa-Core Processor', 700000


def detect_laptop_processor(name: str, desc: str = "") -> tuple:
    """
    Detects laptop processor name and ranking tier score (0 to 50).
    Returns -1 for low-end / disqualified processors (Celeron, Pentium, Athlon).
    """
    text = f"{name} {desc}".lower()

    if any(k in text for k in ['celeron', 'pentium', 'athlon']):
        return 'Low-End Processor (Disqualified)', -1

    # Tier 1 (High Performance i7 / Ryzen 7 / Ultra 7)
    if any(k in text for k in ['core i7', 'i7-', 'ryzen 7', 'r7-', 'ultra 7', '12700h', '13700h', '13620h', '12650h', '7730u', '7735hs', '5800h', '8845hs']):
        return 'Intel Core i7 / AMD Ryzen 7 (Top Tier)', 50

    # Tier 2 (Performance H-Series i5 / Ryzen 5 H)
    if any(k in text for k in ['12450h', '13420h', '12500h', '13500h', '7535hs', '5600h', '6600h', '7640hs', '12450hx', '13450hx']):
        return 'Intel Core i5 H-Series / AMD Ryzen 5 H (High Performance)', 45

    # Tier 3 (Mainstream Modern i5 / Ryzen 5 Hexa-Core)
    if any(k in text for k in ['core i5', 'i5-', 'ryzen 5', 'r5-', '7430u', '7530u', '7535u', '5500u', '1235u', '1335u', '120u', 'ultra 5']):
        return 'Intel Core i5 / AMD Ryzen 5 (Mainstream)', 38

    # Tier 4 (Core i3 / Ryzen 3)
    if any(k in text for k in ['core i3', 'i3-', 'ryzen 3', 'r3-', '7320u', '1215u', '1315u']):
        return 'Intel Core i3 / AMD Ryzen 3', 20

    return 'Standard Processor', 25


def score_phone_processor(name: str, desc: str = "") -> int:
    """
    Scores phone processor based on AnTuTu benchmark vs Edge 70 Fusion (1,000,000+).
    Returns -1 if processor is below acceptable 700k threshold.
    """
    proc, antutu = detect_phone_processor_and_antutu(name, desc)
    if antutu < 700000:
        return -1
    if antutu >= 1300000:
        return 40
    if antutu >= 1000000:
        return 35  # Edge 70 Fusion (1M+) / Realme P4 Pro
    if antutu >= 850000:
        return 28
    return 20


def score_laptop_processor(name: str, desc: str = "") -> int:
    """
    Scores laptop processor tier (0 to 50).
    Returns -1 if processor is low-end (Celeron/Pentium/Athlon).
    """
    proc, score = detect_laptop_processor(name, desc)
    return score


def score_product(product: ProductResult, criteria: SpecCriteria) -> int:
    """
    Score a product against user criteria. Higher = better match.
    Max score = 100.
    Returns -1 if product is disqualified.
    """
    # Check price bounds (strict floor & ceiling)
    if criteria.min_price > 0 and product.effective_price < criteria.min_price:
        return -1
    if criteria.max_price > 0 and product.effective_price > criteria.max_price:
        return -1

    name_lower = product.name.lower()
    desc_lower = product.raw_description.lower()
    full_text = f"{name_lower} {desc_lower}"

    for kw in criteria.exclude_keywords:
        if kw.lower() in full_text:
            return -1

    # Category-specific disqualifiers
    if criteria.category == "phone":
        phone_disqualifiers = ['case', 'cover', 'tempered', 'glass', 'screen guard', 'cable', 'adapter', 'tablet', 'pad', 'watch', 'strap']
        if any(d in name_lower for d in phone_disqualifiers):
            return -1
    elif criteria.category == "laptop":
        laptop_disqualifiers = ['bag', 'backpack', 'sleeve', 'mouse', 'keyboard', 'stand', 'cooler', 'charger', 'adapter', 'skin', 'cable']
        if any(d in name_lower for d in laptop_disqualifiers):
            return -1

    score = 0
    max_possible = 0

    # ─── Phone scoring ───
    if criteria.category == "phone":
        # 1. Processor & AnTuTu (40 points) - Baseline calibrated to Edge 70 Fusion 1M+
        proc_name, antutu = detect_phone_processor_and_antutu(product.name, product.raw_description)
        if antutu < 700000:
            return -1  # Disqualify inferior/budget processors (<700k AnTuTu)

        product.specs["processor"] = proc_name
        product.specs["antutu"] = f"~{antutu:,} (vs Edge 70 Fusion ~1M+ baseline)"

        max_possible += 40
        if antutu >= 1300000:
            score += 40
        elif antutu >= 1000000:
            score += 35
        elif antutu >= 850000:
            score += 28
        else:
            score += 20

        # 2. RAM check (20 points)
        max_possible += 20
        ram = extract_ram(full_text)
        if ram and ram >= 12:
            score += 20
        elif ram and ram >= 8:
            score += 16
        elif ram and ram >= 6:
            score += 8
        elif ram and ram < 6:
            return -1  # Reject phones with <6GB RAM in this budget

        # 3. Storage check (15 points)
        max_possible += 15
        storage = extract_storage(full_text)
        if storage and storage >= 256:
            score += 15
        elif storage and storage >= 128:
            score += 11
        else:
            score += 5

        # 4. Display check (15 points)
        max_possible += 15
        display = extract_display_type(full_text)
        if display and any(d in display.upper() for d in ["AMOLED", "POLED", "OLED"]):
            score += 10
        refresh = extract_refresh_rate(full_text)
        if refresh and refresh >= 120:
            score += 5

        # 5. Battery check (10 points)
        max_possible += 10
        battery = extract_battery(full_text)
        if battery and battery >= 5000:
            score += 10
        elif battery and battery >= 4500:
            score += 6

    # ─── Laptop scoring ───
    elif criteria.category == "laptop":
        # 1. Processor (50 points!) - Crucial for "best processor laptop"
        proc_name, cpu_score = detect_laptop_processor(product.name, product.raw_description)
        if cpu_score == -1:
            return -1  # Disqualified low-end Celeron/Pentium/Athlon

        product.specs["processor"] = proc_name

        max_possible += 50
        score += cpu_score

        # 2. RAM (25 points) - 16GB preferred
        max_possible += 25
        ram = extract_ram(full_text)
        if ram and ram >= 16:
            score += 25
        elif ram and ram >= 8:
            score += 14
        else:
            score += 5

        # 3. Storage (15 points)
        max_possible += 15
        storage = extract_storage(full_text)
        if storage and storage >= 512:
            score += 15
        elif storage and storage >= 256:
            score += 8

        # 4. Display (10 points)
        max_possible += 10
        if any(d in full_text for d in ['fhd', 'ips', '1920x1080', 'anti-glare', 'oled']):
            score += 10
        else:
            score += 5

    # Brand preference (up to 5 bonus points)
    if criteria.brand_preference:
        for brand in criteria.brand_preference:
            if brand.lower() in name_lower:
                score += 5
                break

    # Normalize to 0-100
    if max_possible > 0:
        return min(100, int((score / max_possible) * 100))
    return 50


# ─── Card Offer Parsing from Text ───

EMI_KEYWORDS = {"emi", "no cost emi", "no-cost emi", "bajaj finserv", "emi starting", "per month", "/month"}

def parse_card_offers_from_text(text: str) -> List[CardOffer]:
    """Parse card/bank offers from offer description text. Excludes EMI offers."""
    offers = []
    if not text:
        return offers

    text_lower = text.lower()

    # Skip EMI offers
    for emi_kw in EMI_KEYWORDS:
        if emi_kw in text_lower:
            return []

    # Pattern: "10% instant discount on SBI Credit Card, up to ₹3000"
    pct_match = re.search(
        r'(\d+)%\s*(?:instant\s+)?(?:discount|off|cashback).*?(?:on|with)\s+([\w\s]+?)(?:credit|debit|card)',
        text_lower
    )
    if pct_match:
        value = float(pct_match.group(1))
        bank = pct_match.group(2).strip().upper()
        # Extract max cap
        cap_match = re.search(r'(?:up\s*to|max|maximum)\s*(?:₹|rs\.?|inr)\s*([\d,]+)', text_lower)
        max_discount = int(cap_match.group(1).replace(",", "")) if cap_match else 0
        offers.append(CardOffer(
            bank=bank,
            offer_type="percentage",
            value=value,
            max_discount=max_discount,
            min_order=0,
            description=text.strip(),
        ))
        return offers

    # Pattern: "Flat ₹3000 off on HDFC Bank Credit Card"
    flat_match = re.search(
        r'(?:flat\s+)?(?:₹|rs\.?|inr)\s*([\d,]+)\s*(?:instant\s+)?(?:discount|off|cashback).*?(?:on|with)\s+([\w\s]+?)(?:credit|debit|card)',
        text_lower
    )
    if flat_match:
        value = float(flat_match.group(1).replace(",", ""))
        bank = flat_match.group(2).strip().upper()
        offers.append(CardOffer(
            bank=bank,
            offer_type="flat",
            value=value,
            max_discount=int(value),
            min_order=0,
            description=text.strip(),
        ))
        return offers

    return offers


# ─── Cross-Platform Price Comparison ───

def get_best_deal(products: List[ProductResult]) -> Optional[ProductResult]:
    """Given products from multiple platforms, return the one with the lowest effective price."""
    if not products:
        return None
    # Filter in-stock only
    in_stock = [p for p in products if p.in_stock]
    if not in_stock:
        return None
    return min(in_stock, key=lambda p: p.effective_price)


def find_same_product_cross_platform(
    product: ProductResult,
    other_products: List[ProductResult]
) -> Optional[ProductResult]:
    """Find the same product on the other platform by fuzzy name matching."""
    name_lower = product.name.lower()
    # Extract key identifiers (brand + model)
    name_words = set(re.findall(r'\b[a-z0-9]+\b', name_lower))

    best_match = None
    best_overlap = 0

    for other in other_products:
        if other.platform == product.platform:
            continue
        other_words = set(re.findall(r'\b[a-z0-9]+\b', other.name.lower()))
        overlap = len(name_words & other_words)
        similarity = overlap / max(len(name_words), 1)
        if similarity > 0.6 and overlap > best_overlap:
            best_overlap = overlap
            best_match = other

    return best_match
