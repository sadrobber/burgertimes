"""Idempotent seed: admin user + default settings singleton + empty builder placeholders."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from auth import hash_password, verify_password
from models import Settings

logger = logging.getLogger(__name__)


DEFAULT_SODA_FLAVOURS = [
    "Coca-Cola",
    "Coca-Cola Zero",
    "Fanta Orange",
    "Sprite",
    "Ice Tea",
    "Oasis Tropical",
    "Perrier",
    "Eau plate",
]

DEFAULT_HOURS = {
    "mon": {"is_open": False, "ranges": []},
    "tue": {"is_open": True, "ranges": [{"open": "11:30", "close": "14:30"}, {"open": "18:30", "close": "22:30"}]},
    "wed": {"is_open": True, "ranges": [{"open": "11:30", "close": "14:30"}, {"open": "18:30", "close": "22:30"}]},
    "thu": {"is_open": True, "ranges": [{"open": "11:30", "close": "14:30"}, {"open": "18:30", "close": "22:30"}]},
    "fri": {"is_open": True, "ranges": [{"open": "11:30", "close": "14:30"}, {"open": "18:30", "close": "23:00"}]},
    "sat": {"is_open": True, "ranges": [{"open": "11:30", "close": "23:00"}]},
    "sun": {"is_open": True, "ranges": [{"open": "18:30", "close": "22:30"}]},
}


DEFAULT_CATEGORIES = [
    {"slug": "burgers", "label": {"fr": "Burgers", "en": "Burgers"}, "sort_order": 1},
    {"slug": "sandwiches", "label": {"fr": "Sandwiches", "en": "Sandwiches"}, "sort_order": 2},
    {"slug": "wraps", "label": {"fr": "Wraps", "en": "Wraps"}, "sort_order": 3},
    {"slug": "sides", "label": {"fr": "Accompagnements", "en": "Sides"}, "sort_order": 4},
    {"slug": "drinks", "label": {"fr": "Boissons", "en": "Drinks"}, "sort_order": 5},
    {"slug": "desserts", "label": {"fr": "Desserts", "en": "Desserts"}, "sort_order": 6},
]


async def seed_admin(db) -> None:
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        logger.warning("ADMIN_EMAIL / ADMIN_PASSWORD not set; skipping admin seed")
        return

    existing = await db.admin_users.find_one({"email": admin_email})
    if existing is None:
        doc = {
            "id": _uuid(),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.admin_users.insert_one(doc)
        logger.info("Seeded admin user: %s", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.admin_users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )
        logger.info("Updated admin password for: %s", admin_email)


async def seed_settings(db) -> None:
    existing = await db.settings.find_one({"id": "singleton"})
    if existing is None:
        s = Settings(soda_flavours=DEFAULT_SODA_FLAVOURS)
        # apply default hours
        s.hours_per_day = s.hours_per_day.model_copy()
        settings_doc = s.model_dump()
        settings_doc["hours_per_day"] = DEFAULT_HOURS
        await db.settings.insert_one(settings_doc)
        logger.info("Seeded settings singleton")
    else:
        # Backfill: ensure keys exist
        updates: Dict[str, Any] = {}
        for key, default in {
            "soda_flavours": DEFAULT_SODA_FLAVOURS,
            "delivery_fee": 3.0,
            "eta_default_min": 20,
            "eta_default_max": 30,
            "last_order_buffer_minutes": 15,
            "closing_soon_window_minutes": 30,
            "too_busy": False,
            "force_closed": False,
            "closed_message": "Nous sommes fermés. Revenez pendant nos heures d'ouverture !",
            "timezone": "Europe/Paris",
            "contact_phone": "04.97.07.17.93",
            "contact_address": "6 Avenue de Villaine, 06240 Beausoleil",
            "contact_instagram": "@burgertimes_bsl",
        }.items():
            if key not in existing:
                updates[key] = default
        if "hours_per_day" not in existing or not existing.get("hours_per_day"):
            updates["hours_per_day"] = DEFAULT_HOURS
        if updates:
            await db.settings.update_one({"id": "singleton"}, {"$set": updates})
            logger.info("Backfilled settings keys: %s", list(updates.keys()))


async def seed_categories(db) -> None:
    for cat in DEFAULT_CATEGORIES:
        existing = await db.categories.find_one({"slug": cat["slug"]})
        if existing is None:
            doc = {
                "id": _uuid(),
                "slug": cat["slug"],
                "label": cat["label"],
                "sort_order": cat["sort_order"],
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.categories.insert_one(doc)
    logger.info("Categories seeded")


async def ensure_indexes(db) -> None:
    await db.admin_users.create_index("email", unique=True)
    await db.categories.create_index("slug", unique=True)
    await db.menu_items.create_index("category")
    await db.orders.create_index("order_number", unique=True)
    await db.orders.create_index([("created_at", -1)])
    logger.info("Indexes ensured")


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


async def run_seed(db) -> None:
    await ensure_indexes(db)
    await seed_admin(db)
    await seed_settings(db)
    await seed_categories(db)
