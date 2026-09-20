"""Idempotent seed for Burger Times.

Runs on every backend startup. Loads static reference data (categories, menu
items, sauces, tacos-builder collections) from JSON files in `seed_data/` and
inserts any documents that are missing (matched by primary key). Existing
docs are never overwritten so an admin's edits are safe.

This is critical for production deploys: preview and production have separate
Mongo databases, so bundling the real menu with the code is the only way a
fresh deploy comes up with the full menu already loaded.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from auth import hash_password, verify_password
from models import Settings

logger = logging.getLogger(__name__)


SEED_DATA_DIR = Path(__file__).parent / "seed_data"


DEFAULT_SODA_FLAVOURS = [
    "Coca-Cola",
    "Coca-Cola Zero",
    "Fanta Orange",
    "Sprite",
    "Ice Tea",
    "Oasis Tropical",
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


def _load_json(name: str) -> List[Dict[str, Any]]:
    path = SEED_DATA_DIR / name
    if not path.exists():
        logger.warning("Seed file missing: %s", path)
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.warning("Seed file %s did not contain a JSON array; skipping", name)
            return []
        return data
    except Exception:  # noqa: BLE001
        logger.exception("Failed to load seed file %s", name)
        return []


async def _seed_collection(
    db,
    collection_name: str,
    file_name: str,
    match_key: str = "id",
) -> None:
    """Insert any docs from ``file_name`` that don't already exist in ``collection_name``.

    Matches on ``match_key`` (default ``id``) so re-running is idempotent.
    Docs already present are left untouched — admin edits are preserved.
    """
    docs = _load_json(file_name)
    if not docs:
        return
    inserted = 0
    for doc in docs:
        key_val = doc.get(match_key)
        if key_val is None:
            continue
        existing = await db[collection_name].find_one({match_key: key_val})
        if existing is None:
            await db[collection_name].insert_one(dict(doc))
            inserted += 1
    if inserted:
        logger.info("Seeded %d docs into %s (from %s)", inserted, collection_name, file_name)


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


async def seed_kitchen_user(db) -> None:
    """Seed the dedicated kitchen-tablet account (role='kitchen').

    Separate from the admin account so the shared restaurant tablet doesn't
    need the owner's full admin credentials — but admin accounts can still
    log into /kitchen (see auth.require_kitchen).
    """
    kitchen_email = os.environ.get("KITCHEN_EMAIL")
    kitchen_password = os.environ.get("KITCHEN_PASSWORD")
    if not kitchen_email or not kitchen_password:
        logger.warning("KITCHEN_EMAIL / KITCHEN_PASSWORD not set; skipping kitchen user seed")
        return

    existing = await db.admin_users.find_one({"email": kitchen_email})
    if existing is None:
        doc = {
            "id": _uuid(),
            "email": kitchen_email,
            "password_hash": hash_password(kitchen_password),
            "role": "kitchen",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.admin_users.insert_one(doc)
        logger.info("Seeded kitchen user: %s", kitchen_email)
    elif not verify_password(kitchen_password, existing["password_hash"]):
        await db.admin_users.update_one(
            {"email": kitchen_email},
            {"$set": {"password_hash": hash_password(kitchen_password)}},
        )
        logger.info("Updated kitchen password for: %s", kitchen_email)


async def seed_settings(db) -> None:
    existing = await db.settings.find_one({"id": "singleton"})
    if existing is None:
        s = Settings(soda_flavours=DEFAULT_SODA_FLAVOURS)
        settings_doc = s.model_dump()
        settings_doc["hours_per_day"] = DEFAULT_HOURS
        await db.settings.insert_one(settings_doc)
        logger.info("Seeded settings singleton")
    else:
        # Backfill: ensure keys exist so newly added settings features work on old DBs.
        updates: Dict[str, Any] = {}
        for key, default in {
            "soda_flavours": DEFAULT_SODA_FLAVOURS,
            "delivery_fee_percent": 10.0,
            "delivery_postal_codes": [],
            "scheduled_delivery_enabled": True,
            "delivery_lead_minutes": 40,
            "delivery_window_minutes": 20,
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
            "payment_cash_enabled": True,
            "payment_card_enabled": True,
            "order_limit_enabled": False,
            "order_limit_period": "day",
            "order_limit_max": 100,
            "order_limit_message": "On est débordés — la cuisine tourne à fond sur les commandes en cours. Reviens dans quelques heures, promis on garde de la place pour toi.",
        }.items():
            if key not in existing:
                updates[key] = default
        if "hours_per_day" not in existing or not existing.get("hours_per_day"):
            updates["hours_per_day"] = DEFAULT_HOURS
        if updates:
            await db.settings.update_one({"id": "singleton"}, {"$set": updates})
            logger.info("Backfilled settings keys: %s", list(updates.keys()))


async def seed_menu_data(db) -> None:
    """Seed the full menu, categories, sauces, and tacos-builder from JSON files."""
    await _seed_collection(db, "categories", "categories.json", match_key="slug")
    await _seed_collection(db, "menu_items", "menu_items.json")
    await _seed_collection(db, "sauces", "sauces.json")
    await _seed_collection(db, "burger_styles", "burger_styles.json")
    await _seed_collection(db, "burger_sizes", "burger_sizes.json")
    await _seed_collection(db, "burger_meats", "burger_meats.json")
    await _seed_collection(db, "burger_cheeses", "burger_cheeses.json")
    await _seed_collection(db, "burger_supplements", "burger_supplements.json")


REFERENCE_COLLECTIONS = [
    ("categories", "categories.json"),
    ("menu_items", "menu_items.json"),
    ("sauces", "sauces.json"),
    ("burger_styles", "burger_styles.json"),
    ("burger_sizes", "burger_sizes.json"),
    ("burger_meats", "burger_meats.json"),
    ("burger_cheeses", "burger_cheeses.json"),
    ("burger_supplements", "burger_supplements.json"),
]


async def force_reseed_reference_data(db) -> Dict[str, int]:
    """Wipe and re-insert every reference collection from the JSON files.

    Used by the admin `Reset menu from seed` action to recover a production DB
    whose reference data drifted or was never populated. Does NOT touch
    orders, waitlist, admin_users. Resets a specific subset of settings
    fields (hours_per_day, delivery_fee_percent, free_delivery_threshold,
    delivery_postal_codes) but preserves everything else on the settings doc.
    """
    result: Dict[str, int] = {}
    for coll, filename in REFERENCE_COLLECTIONS:
        docs = _load_json(filename)
        if not docs:
            result[coll] = 0
            continue
        await db[coll].delete_many({})
        if docs:
            await db[coll].insert_many([dict(d) for d in docs])
        result[coll] = len(docs)
        logger.info("Force-reseeded %d docs into %s", len(docs), coll)

    # Reset the operational settings fields the owner cares about.
    settings_reset = {
        "hours_per_day": DEFAULT_HOURS,
        "delivery_fee_percent": 10.0,
        "free_delivery_threshold": 30.0,
        "delivery_postal_codes": [],
    }
    existing = await db.settings.find_one({"id": "singleton"})
    if existing is None:
        s = Settings(soda_flavours=DEFAULT_SODA_FLAVOURS)
        doc = s.model_dump()
        doc.update(settings_reset)
        await db.settings.insert_one(doc)
    else:
        await db.settings.update_one({"id": "singleton"}, {"$set": settings_reset})
    result["settings_reset"] = 1
    logger.info("Force-reseeded settings hours/delivery fields")
    return result


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
    await seed_kitchen_user(db)
    await seed_settings(db)
    await seed_menu_data(db)
