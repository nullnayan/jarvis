# FILE: backend/llm/prompt_enhancer.py
# Stage 1: Expands brief user prompts into detailed flagship specifications
# using Groq openai/gpt-oss-120b. Supports deterministic platform templates and
# capped 1-round web search (max 3 queries) only when time-sensitive/uncertain information is needed.

import re
from logger import get_logger
from tools.web_search import web_search
from config import SEARCH_MODEL

_log = get_logger(__name__)
print = _log.info

# ---------------------------------------------------------------------------
# 1. Deterministic Hardcoded Feature Templates (Zero-search cost baseline)
# ---------------------------------------------------------------------------
PLATFORM_TEMPLATES = {
    "food-delivery": {
        "keywords": ("zomato", "swiggy", "ubereats", "doordash", "food delivery", "restaurant app", "food app"),
        "features": (
            "User authentication (login/signup), geo-location address picker, restaurant discovery & categorization, "
            "multi-factor dish search & dietary filters (Veg/Non-veg/Vegan), dish customizations & add-ons, "
            "interactive cart drawer with bill breakdown (item total, delivery fee, taxes, tips), simulated checkout "
            "with Razorpay/Stripe mock, animated real-time order tracking with multi-stage progress (Placed -> Preparing -> "
            "Out for Delivery -> Delivered), delivery partner tracking simulation, ratings & photo review modal, "
            "push toast notifications, responsive mobile-first UI with dark/light mode, and merchant menu management."
        ),
        "entities": "User, Restaurant, MenuCategory, MenuItem, CustomizationOption, CartItem, Order, DeliveryPartner, Review",
        "views": "Navbar with address selector, Hero search, Cuisine carousel, Restaurant grid, Menu drawer/modal, Cart drawer, Order tracking screen, Checkout modal"
    },
    "ecommerce": {
        "keywords": ("ecommerce", "e-commerce", "amazon", "flipkart", "shopify", "online store", "online shop", "shopping app"),
        "features": (
            "Product catalog browsing with infinite scroll/pagination, live autocomplete search, multi-faceted filtering "
            "(price slider, category, brand, rating), product details modal/page with image gallery & zoom, size/color variant "
            "selection, persistent shopping cart drawer with quantity counters, coupon code discount validator, multi-step checkout "
            "simulation, order history with tracking status, wishlist toggle, customer reviews and rating breakdown."
        ),
        "entities": "Product, Category, Variant, Cart, CartItem, Order, Customer, DiscountCode, Review",
        "views": "Hero banner carousel, Product showcase grid, Filter sidebar, Cart slide-out drawer, Product quick-view modal, Checkout summary stepper"
    },
    "chat": {
        "keywords": ("chat", "whatsapp", "slack", "discord", "messaging", "telegram", "chat app"),
        "features": (
            "Direct 1-on-1 messaging and group channels, real-time message stream with auto-scroll and delivery receipts (sent, delivered, read), "
            "typing indicator simulation, rich message formatting (markdown, emojis), message reactions with emoji counters, media/file "
            "attachment preview, active online/offline status indicators, channel creation modal, and message search."
        ),
        "entities": "User, Channel, Message, Attachment, Reaction, Membership",
        "views": "Sidebar channel/chat list with unread counters, Main chat thread header with active status, Message stream, Message composer with emoji picker"
    },
    "dashboard": {
        "keywords": ("dashboard", "admin", "analytics", "metrics", "crm", "saas", "portal"),
        "features": (
            "KPI statistical summary cards (revenue, users, conversions, growth percentage with trend arrows), interactive data charts "
            "(time-series revenue line chart, category distribution doughnut chart, bar chart), sortable data table with pagination, "
            "column filtering, and CSV/JSON export, user management modal (add/edit/delete), system activity audit log, and theme switcher."
        ),
        "entities": "Metric, User, ActivityLog, Transaction, Report",
        "views": "Collapsible sidebar navigation, Top metric KPI bar, Analytics chart grid, Data table with controls, Activity stream drawer"
    },
    "blog": {
        "keywords": ("blog", "cms", "medium", "news", "articles", "portfolio", "publishing"),
        "features": (
            "Featured hero article, categorized article feed with tag filters, estimated reading time, rich typography with code syntax "
            "highlighting, author bio card with social links, social sharing buttons, interactive comment section with nested replies, "
            "reading progress indicator bar, and newsletter subscription form with validation."
        ),
        "entities": "Article, Author, Category, Tag, Comment, Subscriber",
        "views": "Header with navigation and dark toggle, Hero featured story, Category pill filter, Article card feed, Full article reader view, Comments block"
    }
}


def get_matching_template(task: str) -> str:
    """Finds a matching deterministic platform template if the task represents a known archetype."""
    lower = task.lower()
    for category, tmpl in PLATFORM_TEMPLATES.items():
        if any(k in lower for k in tmpl["keywords"]):
            return (
                f"\nBASELINE DETERMINISTIC ARCHITECTURE ({category.upper()}):\n"
                f"- Core Features: {tmpl['features']}\n"
                f"- Data Model Entities: {tmpl['entities']}\n"
                f"- Primary UI Layouts: {tmpl['views']}\n"
            )
    return ""


# ---------------------------------------------------------------------------
# 2. Heuristic Detection for Time-Sensitive / Version-Sensitive Searches
# ---------------------------------------------------------------------------
TIME_SENSITIVE_KEYWORDS = (
    "latest", "current", "recent", "newest", "trending", "updated",
    "2025", "2026", "modern 2026", "deprecated", "breaking changes",
    "new api", "api v", "stripe latest", "payment gateway 2026",
    "framework version", "latest release", "library version"
)

UNCERTAINTY_MARKERS = (
    "uncertain", "verify current", "current version", "check latest documentation",
    "depends on latest", "version-sensitive", "verify api", "needs verification"
)


def detect_search_queries(task: str, initial_spec: str = "") -> list[str]:
    """Detects whether a web search is genuinely needed and extracts up to 3 targeted queries.
    Returns an empty list for stable requests ('make a zomato clone') with 0 search cost."""
    task_lower = task.lower()
    spec_lower = initial_spec.lower() if initial_spec else ""

    needs_search = any(k in task_lower for k in TIME_SENSITIVE_KEYWORDS) or any(m in spec_lower for m in UNCERTAINTY_MARKERS)
    if not needs_search:
        return []

    # Extract up to 3 focused search queries
    queries = []

    # 1. If user explicitly specified versions or latest tech in task
    for kw in ["payment", "stripe", "razorpay", "auth", "oauth", "tailwind", "fastapi", "react", "vue", "nextjs"]:
        if kw in task_lower:
            queries.append(f"{kw} latest API developer documentation 2026")

    # 2. If task contains explicit time phrase
    clean_task = re.sub(r"[^\w\s-]", "", task).strip()
    words = clean_task.split()
    subject = " ".join(words[:6])
    queries.append(f"{subject} modern best practices 2026")

    # 3. If initial spec specifically flagged an uncertainty line (e.g. 'UNCERTAIN: stripe api 2026')
    if initial_spec:
        for line in initial_spec.splitlines():
            line_low = line.lower()
            if any(m in line_low for m in UNCERTAINTY_MARKERS):
                # Clean prefix if it begins with UNCERTAIN: or similar
                clean_item = re.sub(r"^[^:]*:\s*", "", line).strip()
                clean_item = re.sub(r"[^\w\s-]", "", clean_item)[:50].strip()
                if clean_item and clean_item not in queries:
                    queries.append(f"{clean_item} documentation 2026")
                    if len(queries) >= 3:
                        break

    # Strictly cap to max 3 queries
    deduped = []
    for q in queries:
        if q not in deduped:
            deduped.append(q)
        if len(deduped) >= 3:
            break

    return deduped[:3]


def execute_capped_search(queries: list[str]) -> str:
    """Executes a single search round strictly capped at max 3 queries using existing search tooling (web_search / SEARCH_MODEL)."""
    if not queries:
        return ""

    capped = queries[:3]
    print(f"[PromptEnhancer] Running capped web-search round ({len(capped)} queries)...")
    results = []
    for idx, q in enumerate(capped, 1):
        try:
            print(f"[PromptEnhancer] Search query {idx}/{len(capped)}: '{q}'")
            res = web_search({"query": q})
            if res and not res.startswith("No results") and not res.startswith("An error occurred") and not res.startswith("Search error"):
                # Limit body to prevent token bloat
                snippet = res[:600].strip()
                results.append(f"### Query: {q}\n{snippet}\n")
        except Exception as e:
            print(f"[PromptEnhancer] Search error for '{q}': {e}")

    return "\n".join(results).strip()


# ---------------------------------------------------------------------------
# 3. Prompts
# ---------------------------------------------------------------------------
ENHANCER_BASE_PROMPT = """You are an elite software requirements analyst and flagship systems architect.
Expand the user's brief request into an exhaustive, flagship implementation specification.

HARD ARCHITECTURAL CONSTRAINT (MANDATORY — do not deviate):
The final product MUST be a SELF-CONTAINED web application built with ONLY:
- Semantic HTML5 (`index.html`)
- Responsive CSS (`styles.css`)
- Vanilla JavaScript with reactive state (`app.js`)
- A single unified Python Flask server (`server.py`) that serves the static files AND API endpoints on ONE port.
- For apps requiring user accounts, authentication, or persistent storage (e.g. social networks, food delivery, e-commerce, blogs, task managers): use SQLite (Python stdlib `sqlite3`, stored as `app.db` in the project root) with real signup/login/logout, session cookies, `werkzeug.security` password hashing, and protected routes.
This is the ONLY stack the build executor supports. DO NOT recommend or plan for React, Next.js, Vue, Node.js, Express, MongoDB, PostgreSQL, Redis, Socket.io, TypeScript, Docker, Kubernetes, Tailwind, or any framework requiring `npm install` or a build step. SQLite is the ONLY database. For a rich UI, describe the equivalent vanilla HTML/CSS/JS structure and interactivity. Do NOT let any web-search results override this constraint.

User request: {task}
{template_section}
Produce a structured, comprehensive specification covering:
- Executive Vision & Core Features (every feature a flagship version of this would have)
- Data Model & Schema (entities, fields, relationships, and mock records)
- Pages, Screens, UI/UX Layouts (semantic HTML structure, responsive CSS aesthetics, components)
- API Endpoints & Routes (REST methods, payload structures, status codes)
- Tech Stack (ALWAYS the mandated vanilla HTML/CSS/JS + unified Flask server above)
- Edge Cases, Error Handling, and Resilience (offline fallback data, empty states, input validations)

If any modern 2026 library conventions, external payment APIs, or time-sensitive integration details are uncertain or require verification, explicitly mark them with 'UNCERTAIN: [topic to verify]'.

Return ONLY the enhanced specification as clear, structured text. Be exhaustive and specific —
this spec will directly guide the multi-step architectural implementation plan."""

ENHANCER_REFINE_PROMPT = """You are a senior software architect incorporating real-time verified web documentation
into an implementation specification.

Update and refine the initial specification using the provided live search results.
Ensure accurate, modern 2026 API patterns, correct library conventions, and current security best practices.
Output the complete, updated flagship specification."""


# ---------------------------------------------------------------------------
# 4. Main Enhancer Workflow (1 Round Capped Search)
# ---------------------------------------------------------------------------
async def enhance_prompt(task: str, brain) -> str:
    """Uses Groq gpt-oss-120b to expand the weak prompt into a rich flagship spec.
    1. Uses deterministic template for known archetypes (food-delivery, ecommerce, etc.) -> 0 search cost.
    2. Runs ONE capped search round (max 3 queries) only when time-sensitive/uncertain items are present.
    3. Merges search findings into final spec."""
    if not task or not task.strip():
        return ""

    template_section = get_matching_template(task)
    if template_section:
        print(f"[PromptEnhancer] Applied deterministic template surface for known archetype")

    prompt_content = ENHANCER_BASE_PROMPT.format(task=task, template_section=template_section)
    messages = [
        {"role": "system", "content": prompt_content},
        {"role": "user", "content": f"Create the comprehensive flagship specification for: {task}"},
    ]

    print(f"[PromptEnhancer] Expanding prompt via gpt-oss-120b: '{task[:60]}...'")
    try:
        raw_spec = await brain._chat_with_failover(
            "openai/gpt-oss-120b",
            messages,
            clients=brain._coder_clients(),
            temperature=0.3,
            max_tokens=2500,
        )
        initial_spec = re.sub(r"<think>.*?</think>", "", raw_spec, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"[PromptEnhancer] Initial expansion error: {e}")
        return task

    # Check if a web search round is genuinely needed
    search_queries = detect_search_queries(task, initial_spec)
    if not search_queries:
        # Fast path: stable request or deterministic template covered it. Zero search cost.
        print(f"[PromptEnhancer] Flagship specification ready ({len(initial_spec)} chars, 0 search cost)")
        return initial_spec

    # Run ONE capped search round (max 3 queries)
    search_context = execute_capped_search(search_queries)
    if not search_context:
        return initial_spec

    # Merge verified search context in a single refinement pass
    print(f"[PromptEnhancer] Refining specification with live search context...")
    refine_messages = [
        {"role": "system", "content": ENHANCER_REFINE_PROMPT},
        {
            "role": "user",
            "content": (
                f"Original Task: {task}\n\n"
                f"Initial Specification:\n{initial_spec}\n\n"
                f"Real-Time Verified Search Findings:\n{search_context}\n\n"
                "Please output the updated, complete flagship specification."
            ),
        },
    ]

    try:
        refined_raw = await brain._chat_with_failover(
            "openai/gpt-oss-120b",
            refine_messages,
            clients=brain._coder_clients(),
            temperature=0.2,
            max_tokens=2500,
        )
        final_spec = re.sub(r"<think>.*?</think>", "", refined_raw, flags=re.DOTALL).strip()
        print(f"[PromptEnhancer] Final refined specification ready ({len(final_spec)} chars)")
        return final_spec
    except Exception as e:
        print(f"[PromptEnhancer] Refinement error, using initial spec: {e}")
        return initial_spec
