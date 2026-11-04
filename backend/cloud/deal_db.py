import aiosqlite
import json
import os
import uuid
import time
from typing import List, Dict, Any

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "deal_hunter.db")

class DealDB:
    def __init__(self):
        os.makedirs(DB_DIR, exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    query TEXT NOT NULL,
                    max_price INTEGER NOT NULL,
                    specs_json TEXT,
                    reference_product TEXT,
                    interval_minutes INTEGER DEFAULT 120,
                    deep_interval_minutes INTEGER DEFAULT 720,
                    notifications_enabled INTEGER DEFAULT 1,
                    pincodes TEXT DEFAULT '',
                    last_checked REAL DEFAULT 0,
                    last_deep_checked REAL DEFAULT 0,
                    created_at REAL NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT, product_id TEXT, platform TEXT,
                    price INTEGER, effective_price INTEGER, url TEXT,
                    timestamp REAL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT, product_id TEXT, platform TEXT,
                    price INTEGER, effective_price INTEGER,
                    notified_at REAL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_prefs (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pending_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    delivered_to_device INTEGER DEFAULT 0
                )
            """)
            await db.commit()

            # Ensure no duplicate watches per category exist
            await db.execute("""
                DELETE FROM watchlist WHERE rowid NOT IN (
                    SELECT MAX(rowid) FROM watchlist GROUP BY category
                )
            """)
            await db.commit()

    async def get_pref(self, key: str, default: str = None) -> str:
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT value FROM user_prefs WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def set_pref(self, key: str, value: str):
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO user_prefs (key, value) VALUES (?, ?)", (key, str(value)))
            await db.commit()

    async def seed_default_watches(self):
        """New installations start empty; watches are created explicitly by their user."""
        return




    async def get_global_toggle(self) -> bool:
        val = await self.get_pref("global_toggle", "0")
        return val == "1"

    async def set_global_toggle(self, enabled: bool):
        await self.set_pref("global_toggle", "1" if enabled else "0")
        if enabled:
            watches = await self.get_active_watches()
            if not watches:
                await self.seed_default_watches()

    async def get_active_watches(self) -> List[Dict[str, Any]]:
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM watchlist WHERE notifications_enabled = 1") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def add_watch(self, category, query, max_price, specs_json, reference_product="", interval_minutes=120, deep_interval_minutes=720):
        await self.init_db()
        watch_id = str(uuid.uuid4())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO watchlist
                (id, category, query, max_price, specs_json, reference_product, interval_minutes, deep_interval_minutes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (watch_id, category, query, max_price, specs_json, reference_product, interval_minutes, deep_interval_minutes, time.time()))
            await db.commit()
        return watch_id

    async def pause_watch(self, category: str):
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            if category.lower() == "all":
                await db.execute("UPDATE watchlist SET notifications_enabled = 0")
            else:
                await db.execute("UPDATE watchlist SET notifications_enabled = 0 WHERE category = ?", (category,))
            await db.commit()

    async def resume_watch(self, category: str):
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            if category.lower() == "all":
                await db.execute("UPDATE watchlist SET notifications_enabled = 1")
            else:
                await db.execute("UPDATE watchlist SET notifications_enabled = 1 WHERE category = ?", (category,))
            await db.commit()

    async def was_already_notified(self, product_name: str, effective_price: int) -> bool:
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM notification_log WHERE product_name = ? AND effective_price <= ?", (product_name, effective_price)) as cursor:
                return await cursor.fetchone() is not None

    async def log_notification(self, product_name, product_id, platform, price, effective_price):
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO notification_log
                (product_name, product_id, platform, price, effective_price, notified_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (product_name, product_id, platform, price, effective_price, time.time()))
            await db.commit()

    async def set_pincodes(self, pincodes: List[str]):
        await self.set_pref("pincodes", ",".join(pincodes))

    async def get_pincodes(self) -> List[str]:
        val = await self.get_pref("pincodes", "")
        return [p.strip() for p in val.split(",") if p.strip()]

    async def save_pending_alert(self, alert_type: str, payload: dict) -> int:
        """Saves an alert into pending_alerts so offline devices receive it on reconnect."""
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            # Prune alerts older than 24 hours (86,400s)
            cutoff = time.time() - 86400
            await db.execute("DELETE FROM pending_alerts WHERE created_at < ?", (cutoff,))
            cursor = await db.execute("""
                INSERT INTO pending_alerts (alert_type, payload_json, created_at, delivered_to_device)
                VALUES (?, ?, ?, 0)
            """, (alert_type, json.dumps(payload), time.time()))
            alert_id = cursor.lastrowid
            await db.commit()
            return alert_id

    async def get_pending_alerts(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns unacknowledged alerts from the last 24 hours."""
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cutoff = time.time() - 86400
            async with db.execute("""
                SELECT * FROM pending_alerts
                WHERE delivered_to_device = 0 AND created_at >= ?
                ORDER BY id ASC LIMIT ?
            """, (cutoff, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def mark_alert_delivered(self, alert_id: int):
        """Marks a pending alert as delivered/acknowledged by client device."""
        await self.init_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE pending_alerts SET delivered_to_device = 1 WHERE id = ?", (alert_id,))
            await db.commit()
