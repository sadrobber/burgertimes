"""Burger Times · FastAPI backend.

All routes prefixed with /api. UUID string primary keys. UTC ISO 8601 timestamps.
"""
from __future__ import annotations

from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import base64
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import Response as FAResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from starlette.middleware.cors import CORSMiddleware

from auth import (
    create_admin_token,
    hash_password,
    require_admin,
    require_kitchen,
    require_tablet,
    verify_password,
)
from delivery_scheduling import delivery_slots, validate_delivery_slot
from email_service import send_open_notice, send_order_email
from email_service import is_configured as _email_configured
from models import (
    AdminLoginPayload,
    BuilderImageUpdate,
    BuilderItemCreate,
    Category,
    CategoryCreate,
    CategoryUpdate,
    CheckoutPayload,
    Coupon,
    CouponCreate,
    CouponUpdate,
    KitchenDeclinePayload,
    MenuItem,
    MenuItemCreate,
    MenuItemUpdate,
    OrderStatusUpdate,
    Review,
    ReviewCreate,
    ReviewUpdate,
    Sauce,
    SauceCreate,
    SauceUpdate,
    Settings,
    SettingsUpdate,
    TabletStaffCreate,
    TabletStaffUpdate,
    WaitlistCreate,
    WaitlistEntry,
    gen_id,
    utc_now_iso,
)
from order_service import build_snapshots, gen_order_number, gen_pickup_code, _compose_ticket_line, _short
from pricing import BurgerBuilderConfig
from restaurant_status import compute_status
from seed import force_reseed_reference_data, run_seed
import sunmi_service
from sunmi_receipt import build_test_ticket, to_hex
from printer_bridge import send_print_job
from telegram_notifier import send_commission_alert

# ----- Database ------------------------------------------------------------

mongo_url = os.environ["MONGO_URL"]
# Explicit timeouts so a broken MONGO_URL fails fast (2-4s) with a clear error
# instead of hanging 30s and returning a gateway 504. If prod DB is genuinely
# reachable, the connect happens in <1s so these limits never fire.
client = AsyncIOMotorClient(
    mongo_url,
    serverSelectionTimeoutMS=4000,
    connectTimeoutMS=4000,
    socketTimeoutMS=8000,
)
db = client[os.environ["DB_NAME"]]

# ----- App -----------------------------------------------------------------

app = FastAPI(title="Burger Times API")
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _strip_mongo(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    d.pop("_id", None)
    return d


def _strip_image(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    d.pop("image_base64", None)
    d.pop("builder_image_base64", None)
    return d


# Menu photos are stored inline as base64 data URLs (~95 kB each). No list
# endpoint ever returns them - _strip_image drops them again immediately, and
# the browser fetches each photo from /menu/{id}/image instead. Without this
# projection every menu listing and every checkout quote pulled the whole
# photo set out of Mongo and into RAM just to throw it away: measured at
# 3.71 MB fetched and 11.3 MB peak allocation per request for a 40-item menu,
# versus 0.01 MB / 0.2 MB with it. That per-request cost is what exhausted the
# 512Mi container under concurrent load (both prod pods OOMKilled 2026-08-25
# 18:18 UTC). Keep this projection on any query that does not serve the image
# itself.
NO_IMAGE_FIELDS = {"image_base64": 0, "builder_image_base64": 0}


# ----- Startup -------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    # Seed is best-effort — if MongoDB is unreachable we still want the app to
    # boot so /api/health can report the failure clearly instead of the
    # process crash-looping.
    import asyncio

    try:
        await asyncio.wait_for(run_seed(db), timeout=12.0)
    except asyncio.TimeoutError:
        logger.error(
            "Seed timed out after 12s — MongoDB is likely unreachable. "
            "Check MONGO_URL env var and network access from this container."
        )
    except Exception:  # noqa: BLE001
        logger.exception("Seed failed")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    client.close()


# ----- Health --------------------------------------------------------------


@app.get("/health")
async def platform_health() -> dict:
    """Bare, unprefixed liveness/readiness probe for the deployment
    platform's Kubernetes health check, which hits the container directly
    on its own port (bypassing the /api ingress prefix). Intentionally does
    NOT touch Mongo — must return instantly even if the DB is briefly
    unreachable, so the pod isn't killed for a transient DB blip. Use
    GET /api/health for the deep check (Mongo ping, menu count, etc.)."""
    return {"status": "ok"}


@api.get("/")
async def root() -> dict:
    return {"name": "burger-times", "status": "ok"}


@api.get("/health")
async def health():
    """Deep health check. Reports Mongo reachability without hanging."""
    import asyncio

    payload: Dict[str, Any] = {"api": "ok"}
    # Mongo ping with a hard 3-second cap so this endpoint is always fast.
    try:
        await asyncio.wait_for(client.admin.command("ping"), timeout=3.0)
        payload["mongo"] = "ok"
    except asyncio.TimeoutError:
        payload["mongo"] = "unreachable (timeout after 3s — check MONGO_URL in this env)"
    except Exception as e:  # noqa: BLE001
        payload["mongo"] = f"error: {type(e).__name__}: {str(e)[:200]}"

    # Menu-items count sanity — helps you see whether the DB is empty.
    try:
        payload["menu_items_count"] = await asyncio.wait_for(
            db.menu_items.count_documents({}), timeout=3.0
        )
    except Exception as e:  # noqa: BLE001
        payload["menu_items_count"] = f"error: {type(e).__name__}"

    payload["integrations"] = {
        "resend_configured": bool(os.environ.get("RESEND_API_KEY")),
        "resend_from": os.environ.get("RESEND_FROM_EMAIL") or None,
    }
    return payload


# ----- Admin auth ----------------------------------------------------------


@api.post("/admin/login")
async def admin_login(payload: AdminLoginPayload):
    email = payload.email.lower().strip()
    user = await db.admin_users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    token = create_admin_token(user["id"], user["email"])
    return {"token": token, "admin": {"email": user["email"]}}


@api.get("/admin/me")
async def admin_me(payload: dict = Depends(require_admin)):
    return {"email": payload.get("email"), "role": payload.get("role")}


@api.get("/admin/tablet-staff")
async def admin_list_tablet_staff(_: dict = Depends(require_admin)):
    docs = await db.admin_users.find({"role": "tablet"}, {"_id": 0, "password_hash": 0}).to_list(200)
    return docs


@api.post("/admin/tablet-staff")
async def admin_create_tablet_staff(payload: TabletStaffCreate, _: dict = Depends(require_admin)):
    email = payload.email.lower().strip()
    if await db.admin_users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé.")
    doc = {
        "id": gen_id(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "role": "tablet",
        "active": True,
        "created_at": utc_now_iso(),
    }
    await db.admin_users.insert_one(doc)
    return {
        key: value
        for key, value in doc.items()
        if key not in {"_id", "password_hash"}
    }


@api.put("/admin/tablet-staff/{staff_id}")
async def admin_update_tablet_staff(
    staff_id: str,
    payload: TabletStaffUpdate,
    _: dict = Depends(require_admin),
):
    changes = payload.model_dump(exclude_unset=True)
    if "password" in changes:
        changes["password_hash"] = hash_password(changes.pop("password"))
    if changes:
        await db.admin_users.update_one({"id": staff_id, "role": "tablet"}, {"$set": changes})
    doc = await db.admin_users.find_one({"id": staff_id, "role": "tablet"}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Compte tablette introuvable.")
    return doc


@api.delete("/admin/tablet-staff/{staff_id}")
async def admin_delete_tablet_staff(staff_id: str, _: dict = Depends(require_admin)):
    result = await db.admin_users.delete_one({"id": staff_id, "role": "tablet"})
    return {"deleted": result.deleted_count}


# ----- Public: settings + status + reviews + sauces + categories -----------


@api.get("/settings")
async def get_settings():
    doc = await db.settings.find_one({"id": "singleton"}, NO_IMAGE_FIELDS)
    if doc is None:
        # Should be seeded; return default just in case.
        return Settings().model_dump()
    return _strip_image(_strip_mongo(doc))


@api.put("/settings")
async def update_settings(
    update: SettingsUpdate,
    background: BackgroundTasks,
    _: dict = Depends(require_admin),
):
    doc = await db.settings.find_one({"id": "singleton"})
    if doc is None:
        base = Settings().model_dump()
        base["id"] = "singleton"
        await db.settings.insert_one(base)
        doc = base
    else:
        _strip_mongo(doc)
    changes = {k: v for k, v in update.model_dump(exclude_unset=True).items() if v is not None}
    if isinstance(changes.get("hours_per_day"), dict) is False and changes.get("hours_per_day") is not None:
        changes["hours_per_day"] = changes["hours_per_day"]
    changes["updated_at"] = utc_now_iso()
    await db.settings.update_one({"id": "singleton"}, {"$set": changes})
    doc.update(changes)
    background.add_task(_maybe_notify_waitlist_on_open)
    return _strip_image(_strip_mongo(doc))


@api.get("/builder-image")
async def builder_image():
    doc = await db.settings.find_one({"id": "singleton"})
    if not doc or not doc.get("builder_image_base64"):
        raise HTTPException(status_code=404, detail="No image")
    raw = doc["builder_image_base64"]
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Invalid image")
    return FAResponse(content=data, media_type="image/jpeg")


@api.put("/admin/settings/builder-image")
async def admin_update_builder_image(payload: BuilderImageUpdate, _: dict = Depends(require_admin)):
    doc = await db.settings.find_one({"id": "singleton"})
    if doc is None:
        base = Settings().model_dump()
        base["id"] = "singleton"
        await db.settings.insert_one(base)
    if payload.image_base64:
        await db.settings.update_one(
            {"id": "singleton"},
            {"$set": {
                "builder_image_base64": payload.image_base64,
                "has_builder_image": True,
                "updated_at": utc_now_iso(),
            }},
        )
    else:
        await db.settings.update_one(
            {"id": "singleton"},
            {
                "$set": {"has_builder_image": False, "updated_at": utc_now_iso()},
                "$unset": {"builder_image_base64": ""},
            },
        )
    return {"has_builder_image": bool(payload.image_base64)}


@api.get("/admin/receipt-preview")
async def admin_receipt_preview(_: dict = Depends(require_admin)):
    """Render a sample thermal-ticket text block using the owner's current
    shortcodes, so they can tune codes without printing real paper."""
    settings = await db.settings.find_one({"id": "singleton"}, NO_IMAGE_FIELDS) or {}

    sauce_docs = await db.sauces.find({}, {"_id": 0}).to_list(500)
    sauce = next((x for x in sauce_docs if x.get("active", True)), None)
    sauce_code = (sauce.get("ticket_shortcode") or sauce.get("name")) if sauce else "Sauce"

    supps = settings.get("supplement_options") or []
    supp_code = (supps[0].get("code") or supps[0].get("name")) if supps else "Supp"

    removals = settings.get("removal_options") or ["tomate"]
    removal_codes = settings.get("removal_shortcodes") or {}
    removal_name = removals[0]
    removal_code = removal_codes.get(removal_name) or removal_name

    drinks = settings.get("soda_flavours") or []
    drink_codes = settings.get("drink_shortcodes") or {}
    drink_name = drinks[0] if drinks else None
    drink_code = (drink_codes.get(drink_name) or drink_name) if drink_name else None

    kids_code = (settings.get("kids_ticket_code") or "c").strip() or "c"

    item_docs = await db.menu_items.find({"available": True}, NO_IMAGE_FIELDS).to_list(2000)
    non_kids = [d for d in item_docs if d.get("category") != "kids"]
    kids = [d for d in item_docs if d.get("category") == "kids"]
    it1_short = (non_kids[0].get("ticket_shortcode") or non_kids[0].get("name")) if non_kids else "Classique"
    it2_short = (non_kids[1].get("ticket_shortcode") or non_kids[1].get("name")) if len(non_kids) > 1 else "Wings"
    kid_short = (kids[0].get("ticket_shortcode") or kids[0].get("name")) if kids else "Menu Enfant"

    n1 = it1_short if it1_short.lower().startswith("menu") else f"Menu {it1_short}"
    nk = kid_short if kid_short.lower().startswith("menu") else f"Menu {kid_short}"

    def _blk(qty, name, meats_inline, drink, mods):
        hdr = f"{qty} {name}"
        if meats_inline:
            hdr += f" {meats_inline}"
        if drink:
            hdr += f" [{drink}]"
        rows = [hdr]
        rows += [m.center(46) for m in mods]
        return rows

    blocks = [
        _blk(1, n1, "", drink_code, [f"no {removal_code}", sauce_code, f"+ {supp_code}"]),
        _blk(2, it2_short, "", None, []),
    ]
    if kids:
        blocks.append(_blk(1, nk, "", drink_code, [kids_code]))

    divider = "-" * 46
    text = ["[ A EMPORTER ]".center(46), "BURGER TIMES".center(46), divider, "COMMANDE #APERCU".center(46), divider]
    for b in blocks:
        text += b
        text.append("")
    text += [divider, "TOTAL : 00,00 EUR", divider, "Client : Apercu"]
    return {"text": "\n".join(text)}


@api.get("/restaurant/status")
async def restaurant_status():
    settings = await db.settings.find_one({"id": "singleton"}, NO_IMAGE_FIELDS) or Settings().model_dump()
    _strip_mongo(settings)
    return compute_status(settings)


@api.get("/checkout/delivery-slots")
async def checkout_delivery_slots():
    settings = await db.settings.find_one({"id": "singleton"}, NO_IMAGE_FIELDS) or Settings().model_dump()
    _strip_mongo(settings)
    return {
        "enabled": bool(settings.get("scheduled_delivery_enabled", True)),
        "lead_minutes": int(settings.get("delivery_lead_minutes", 40) or 40),
        "window_minutes": int(settings.get("delivery_window_minutes", 20) or 20),
        "slots": delivery_slots(settings),
    }


@api.get("/categories")
async def list_categories():
    cats = await db.categories.find({"active": True}).sort("sort_order", 1).to_list(200)
    return [_strip_mongo(c) for c in cats]


@api.get("/admin/categories")
async def admin_list_categories(_: dict = Depends(require_admin)):
    cats = await db.categories.find().sort("sort_order", 1).to_list(500)
    return [_strip_mongo(c) for c in cats]


@api.post("/admin/categories")
async def admin_create_category(payload: CategoryCreate, _: dict = Depends(require_admin)):
    existing = await db.categories.find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Slug déjà utilisé")
    doc = Category(**payload.model_dump()).model_dump()
    await db.categories.insert_one(doc)
    return _strip_mongo(doc)


@api.put("/admin/categories/{cat_id}")
async def admin_update_category(cat_id: str, payload: CategoryUpdate, _: dict = Depends(require_admin)):
    existing = await db.categories.find_one({"id": cat_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updated_at"] = utc_now_iso()
        await db.categories.update_one({"id": cat_id}, {"$set": changes})
    existing.update(changes)
    return _strip_mongo(existing)


@api.delete("/admin/categories/{cat_id}")
async def admin_delete_category(cat_id: str, _: dict = Depends(require_admin)):
    res = await db.categories.delete_one({"id": cat_id})
    return {"deleted": res.deleted_count}


# ----- Menu items ---------------------------------------------------------


@api.get("/menu")
async def list_menu():
    docs = await db.menu_items.find({"available": True}, NO_IMAGE_FIELDS).sort([("sort_order", 1), ("name", 1)]).to_list(500)
    return [_strip_image(_strip_mongo(d)) for d in docs]


@api.get("/admin/menu")
async def admin_list_menu(_: dict = Depends(require_admin)):
    docs = await db.menu_items.find({}, NO_IMAGE_FIELDS).sort([("sort_order", 1), ("name", 1)]).to_list(2000)
    return [_strip_image(_strip_mongo(d)) for d in docs]


@api.get("/menu/{item_id}/image")
async def menu_item_image(item_id: str):
    doc = await db.menu_items.find_one({"id": item_id})
    if not doc or not doc.get("image_base64"):
        raise HTTPException(status_code=404, detail="No image")
    raw = doc["image_base64"]
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Invalid image")
    return FAResponse(content=data, media_type="image/jpeg")


@api.post("/admin/menu")
async def admin_create_menu_item(payload: MenuItemCreate, _: dict = Depends(require_admin)):
    doc = MenuItem(
        **{k: v for k, v in payload.model_dump().items() if k != "image_base64"}
    ).model_dump()
    if payload.image_base64:
        doc["image_base64"] = payload.image_base64
        doc["has_image"] = True
    await db.menu_items.insert_one(doc)
    return _strip_image(_strip_mongo(doc))


@api.put("/admin/menu/{item_id}")
async def admin_update_menu_item(item_id: str, payload: MenuItemUpdate, _: dict = Depends(require_admin)):
    existing = await db.menu_items.find_one({"id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    changes = payload.model_dump(exclude_unset=True)
    if "image_base64" in changes:
        img = changes.pop("image_base64")
        if img:
            changes["image_base64"] = img
            changes["has_image"] = True
    if changes:
        changes["updated_at"] = utc_now_iso()
        await db.menu_items.update_one({"id": item_id}, {"$set": changes})
    doc = await db.menu_items.find_one({"id": item_id})
    return _strip_image(_strip_mongo(doc))


@api.delete("/admin/menu/{item_id}")
async def admin_delete_menu_item(item_id: str, _: dict = Depends(require_admin)):
    res = await db.menu_items.delete_one({"id": item_id})
    return {"deleted": res.deleted_count}


# ----- Sauces --------------------------------------------------------------


@api.get("/sauces")
async def list_sauces():
    docs = await db.sauces.find({"active": True}).sort("sort_order", 1).to_list(200)
    return [_strip_mongo(d) for d in docs]


@api.get("/admin/sauces")
async def admin_list_sauces(_: dict = Depends(require_admin)):
    docs = await db.sauces.find().sort("sort_order", 1).to_list(500)
    return [_strip_mongo(d) for d in docs]


@api.post("/admin/sauces")
async def admin_create_sauce(payload: SauceCreate, _: dict = Depends(require_admin)):
    doc = Sauce(**payload.model_dump()).model_dump()
    await db.sauces.insert_one(doc)
    return _strip_mongo(doc)


@api.put("/admin/sauces/{sid}")
async def admin_update_sauce(sid: str, payload: SauceUpdate, _: dict = Depends(require_admin)):
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        await db.sauces.update_one({"id": sid}, {"$set": changes})
    doc = await db.sauces.find_one({"id": sid})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return _strip_mongo(doc)


@api.delete("/admin/sauces/{sid}")
async def admin_delete_sauce(sid: str, _: dict = Depends(require_admin)):
    res = await db.sauces.delete_one({"id": sid})
    return {"deleted": res.deleted_count}


# ----- Coupons --------------------------------------------------------------


@api.get("/admin/coupons")
async def admin_list_coupons(_: dict = Depends(require_admin)):
    docs = await db.coupons.find().sort("created_at", -1).to_list(500)
    return [_strip_mongo(d) for d in docs]


@api.post("/admin/coupons")
async def admin_create_coupon(payload: CouponCreate, _: dict = Depends(require_admin)):
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code requis.")
    if payload.discount_type not in ("free_delivery", "percent_off_delivery"):
        raise HTTPException(status_code=400, detail="Type de réduction invalide.")
    if payload.discount_type == "percent_off_delivery" and not (
        payload.percent_value and 0 < payload.percent_value <= 100
    ):
        raise HTTPException(status_code=400, detail="Pourcentage invalide (1-100).")
    if payload.max_uses < 1:
        raise HTTPException(status_code=400, detail="Nombre d'utilisations minimum : 1.")
    if await db.coupons.find_one({"code": code}):
        raise HTTPException(status_code=400, detail="Ce code existe déjà.")
    doc = Coupon(
        code=code,
        discount_type=payload.discount_type,
        percent_value=payload.percent_value if payload.discount_type == "percent_off_delivery" else None,
        max_uses=payload.max_uses,
    ).model_dump()
    await db.coupons.insert_one(doc)
    return _strip_mongo(doc)


@api.put("/admin/coupons/{cid}")
async def admin_update_coupon(cid: str, payload: CouponUpdate, _: dict = Depends(require_admin)):
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("code"):
        changes["code"] = changes["code"].strip().upper()
        existing = await db.coupons.find_one({"code": changes["code"], "id": {"$ne": cid}})
        if existing:
            raise HTTPException(status_code=400, detail="Ce code existe déjà.")
    existing_doc = await db.coupons.find_one({"id": cid})
    if not existing_doc:
        raise HTTPException(status_code=404, detail="Not found")
    new_type = changes.get("discount_type", existing_doc.get("discount_type"))
    new_percent = changes.get("percent_value", existing_doc.get("percent_value"))
    if new_type == "percent_off_delivery" and not (new_percent and 0 < new_percent <= 100):
        raise HTTPException(status_code=400, detail="Pourcentage invalide (1-100).")
    if changes:
        await db.coupons.update_one({"id": cid}, {"$set": changes})
    doc = await db.coupons.find_one({"id": cid})
    return _strip_mongo(doc)


@api.delete("/admin/coupons/{cid}")
async def admin_delete_coupon(cid: str, _: dict = Depends(require_admin)):
    res = await db.coupons.delete_one({"id": cid})
    return {"deleted": res.deleted_count}


# ----- Burger builder ------------------------------------------------------


BUILDER_COLLECTIONS = {
    "styles": "burger_styles",
    "sizes": "burger_sizes",
    "meats": "burger_meats",
    "cheeses": "burger_cheeses",
    "supplements": "burger_supplements",
}


@api.get("/burger/config")
async def burger_config():
    result = {}
    for key, coll in BUILDER_COLLECTIONS.items():
        docs = await db[coll].find({"available": True}).sort("sort_order", 1).to_list(500)
        result[key] = [_strip_mongo(d) for d in docs]
    return result


@api.get("/admin/burger/{part}")
async def admin_burger_list(part: str, _: dict = Depends(require_admin)):
    if part not in BUILDER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown builder part")
    docs = await db[BUILDER_COLLECTIONS[part]].find().sort("sort_order", 1).to_list(500)
    return [_strip_mongo(d) for d in docs]


@api.post("/admin/burger/{part}")
async def admin_burger_create(part: str, payload: BuilderItemCreate, _: dict = Depends(require_admin)):
    if part not in BUILDER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown builder part")
    coll = BUILDER_COLLECTIONS[part]
    # Use model_dump() (not exclude_unset) so defaults like available=True are persisted.
    # Otherwise the public /burger/config filter {"available": True} would hide the doc.
    data = {k: v for k, v in payload.model_dump().items() if v is not None or k in ("available",)}
    doc = {"id": gen_id(), **data}
    await db[coll].insert_one(doc)
    return _strip_mongo(doc)


@api.put("/admin/burger/{part}/{item_id}")
async def admin_burger_update(
    part: str,
    item_id: str,
    payload: BuilderItemCreate,
    _: dict = Depends(require_admin),
):
    if part not in BUILDER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown builder part")
    coll = BUILDER_COLLECTIONS[part]
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        await db[coll].update_one({"id": item_id}, {"$set": changes})
    doc = await db[coll].find_one({"id": item_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return _strip_mongo(doc)


@api.delete("/admin/burger/{part}/{item_id}")
async def admin_burger_delete(part: str, item_id: str, _: dict = Depends(require_admin)):
    if part not in BUILDER_COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown builder part")
    coll = BUILDER_COLLECTIONS[part]
    res = await db[coll].delete_one({"id": item_id})
    return {"deleted": res.deleted_count}


# ----- Reviews -------------------------------------------------------------


@api.get("/reviews")
async def list_reviews():
    docs = await db.reviews.find({"approved": True}).sort([("created_at", -1)]).to_list(50)
    return [_strip_mongo(d) for d in docs]


@api.post("/reviews")
async def create_review(payload: ReviewCreate):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")
    doc = Review(**payload.model_dump()).model_dump()
    await db.reviews.insert_one(doc)
    return _strip_mongo(doc)


@api.get("/admin/reviews")
async def admin_list_reviews(_: dict = Depends(require_admin)):
    docs = await db.reviews.find().sort([("created_at", -1)]).to_list(500)
    return [_strip_mongo(d) for d in docs]


@api.put("/admin/reviews/{rid}")
async def admin_update_review(rid: str, payload: ReviewUpdate, _: dict = Depends(require_admin)):
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        await db.reviews.update_one({"id": rid}, {"$set": changes})
    doc = await db.reviews.find_one({"id": rid})
    return _strip_mongo(doc) if doc else {"deleted": True}


@api.delete("/admin/reviews/{rid}")
async def admin_delete_review(rid: str, _: dict = Depends(require_admin)):
    res = await db.reviews.delete_one({"id": rid})
    return {"deleted": res.deleted_count}


# ----- Seed / reset --------------------------------------------------------


@api.post("/admin/seed/reseed")
async def admin_force_reseed(_: dict = Depends(require_admin)):
    """Wipe reference collections and re-insert them from the shipped JSON files.

    Restores the menu, categories, sauces, tacos-builder and the operational
    settings fields (hours, delivery %) after a bad deploy or data drift.
    Does NOT touch orders, admin_users or the waitlist.
    """
    result = await force_reseed_reference_data(db)
    return {"ok": True, **result}


# ----- Checkout / orders ---------------------------------------------------


async def _load_builder_config() -> BurgerBuilderConfig:
    async def _to_map(coll: str) -> Dict[str, dict]:
        docs = await db[coll].find().to_list(2000)
        return {d["id"]: _strip_mongo(d) for d in docs}

    return BurgerBuilderConfig(
        styles=await _to_map("burger_styles"),
        sizes=await _to_map("burger_sizes"),
        meats=await _to_map("burger_meats"),
        cheeses=await _to_map("burger_cheeses"),
        supplements=await _to_map("burger_supplements"),
    )


async def _ensure_accepting_orders(settings: dict) -> None:
    status = compute_status(settings)
    if status["state"] == "closed":
        raise HTTPException(status_code=423, detail={
            "message": "Restaurant is currently closed.",
            "status": status,
        })


async def _check_order_limit(settings: dict) -> None:
    if not settings.get("order_limit_enabled"):
        return
    period = settings.get("order_limit_period") or "day"
    max_orders = int(settings.get("order_limit_max") or 0)
    if max_orders <= 0:
        return
    tz_name = settings.get("timezone") or "Europe/Paris"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Europe/Paris")
    now_local = datetime.now(tz)
    if period == "week":
        start_local = (now_local - timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_iso = start_local.astimezone(timezone.utc).isoformat()
    count = await db.orders.count_documents(
        {
            "created_at": {"$gte": start_iso},
            "status": {"$nin": ["cancelled", "expired"]},
        }
    )
    if count >= max_orders:
        raise HTTPException(
            status_code=429,
            detail={
                "message": settings.get("order_limit_message")
                or "Trop de commandes en cours. Réessaie plus tard.",
                "kind": "order_limit_reached",
                "count": count,
                "max": max_orders,
                "period": period,
            },
        )


def _validate_payment_method(settings: dict, method: str) -> None:
    if method == "cash" and settings.get("payment_cash_enabled", True) is False:
        raise HTTPException(
            status_code=400,
            detail="Le paiement en espèces est désactivé pour l'instant. Choisis la carte.",
        )
    if method == "card_in_person" and settings.get("payment_card_enabled", True) is False:
        raise HTTPException(
            status_code=400,
            detail="Le paiement par carte est désactivé pour l'instant. Choisis les espèces.",
        )


def _compute_delivery_fee(fulfillment: str, subtotal: float, settings: dict) -> float:
    if fulfillment != "delivery":
        return 0.0
    threshold = settings.get("free_delivery_threshold")
    if threshold is not None and subtotal >= float(threshold):
        return 0.0
    percent = float(settings.get("delivery_fee_percent", 10.0) or 0.0)
    return round(subtotal * percent / 100.0, 2)


async def _apply_coupon(
    code: Optional[str], fulfillment: str, delivery_fee: float, create: bool
) -> tuple[float, Optional[dict]]:
    """Validates + applies a coupon against the delivery fee only. Returns
    (possibly-discounted delivery_fee, coupon_info|None). Raises 400 on any
    invalid/inactive/exhausted code or when used on a non-delivery order.
    Usage is only consumed (atomic $inc, race-safe) when create=True — a
    /checkout/quote call never burns through a code's max_uses."""
    if not code or not code.strip():
        return delivery_fee, None
    code = code.strip().upper()
    coupon = await db.coupons.find_one({"code": code})
    if not coupon or not coupon.get("active", True):
        raise HTTPException(status_code=400, detail="Code promo invalide.")
    if coupon.get("used_count", 0) >= coupon.get("max_uses", 1):
        raise HTTPException(
            status_code=400,
            detail="Ce code promo a déjà été utilisé le nombre maximum de fois autorisé.",
        )
    if fulfillment != "delivery":
        raise HTTPException(
            status_code=400, detail="Ce code ne fonctionne que pour les commandes en livraison."
        )

    if coupon["discount_type"] == "free_delivery":
        discount = delivery_fee
    else:
        discount = round(delivery_fee * (coupon.get("percent_value") or 0) / 100.0, 2)
    new_fee = round(max(0.0, delivery_fee - discount), 2)

    if create:
        updated = await db.coupons.find_one_and_update(
            {"id": coupon["id"], "used_count": {"$lt": coupon.get("max_uses", 1)}, "active": True},
            {"$inc": {"used_count": 1}},
        )
        if not updated:
            raise HTTPException(
                status_code=400,
                detail="Ce code promo a déjà été utilisé le nombre maximum de fois autorisé.",
            )

    return new_fee, {"code": code, "discount_type": coupon["discount_type"], "discount_amount": discount}


async def _quote_or_create(
    payload: CheckoutPayload,
    create: bool,
    order_source: str = "web",
    tablet_taken_by: Optional[str] = None,
) -> dict:
    settings = await db.settings.find_one({"id": "singleton"}, NO_IMAGE_FIELDS) or Settings().model_dump()
    _strip_mongo(settings)

    if payload.fulfillment not in ("delivery", "pickup", "dine_in"):
        raise HTTPException(status_code=400, detail="Invalid fulfillment")
    if payload.payment_method not in ("cash", "card_in_person"):
        raise HTTPException(status_code=400, detail="Invalid payment method")

    scheduled_slot = None
    if payload.scheduled_delivery_start:
        if payload.fulfillment != "delivery":
            raise HTTPException(status_code=400, detail="Un créneau est réservé aux livraisons.")
        scheduled_slot = validate_delivery_slot(settings, payload.scheduled_delivery_start)

    if create:
        if not scheduled_slot:
            tablet_closed_override = order_source == "tablet" and settings.get(
                "tablet_orders_when_closed",
                False,
            )
            if not tablet_closed_override:
                await _ensure_accepting_orders(settings)
        elif compute_status(settings).get("reason") == "force_closed":
            raise HTTPException(status_code=423, detail="Le restaurant est fermé exceptionnellement.")
        _validate_payment_method(settings, payload.payment_method)
        await _check_order_limit(settings)

    if payload.fulfillment == "delivery" and create:
        required = [payload.address_line1, payload.city]
        if order_source != "tablet":
            required.append(payload.postal_code)
        if not all(required):
            raise HTTPException(status_code=400, detail="Adresse de livraison requise")
        allowed = [
            str(x).strip()
            for x in (settings.get("delivery_postal_codes") or [])
            if str(x).strip()
        ]
        if allowed and order_source != "tablet":
            incoming = (payload.postal_code or "").strip()
            if incoming not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": (
                            f"On ne livre pas au {incoming}. "
                            f"Codes acceptés : {', '.join(allowed)}."
                        ),
                        "kind": "postal_code_not_served",
                        "allowed_postal_codes": allowed,
                        "postal_code": incoming,
                    },
                )

    # Load menu items (only available)
    menu_docs = await db.menu_items.find({"available": True}, NO_IMAGE_FIELDS).to_list(2000)
    menu_items = {d["id"]: _strip_mongo(d) for d in menu_docs}
    burger_cfg = await _load_builder_config()

    sauce_docs = await db.sauces.find({}, {"_id": 0}).to_list(500)
    sauce_codes = {s["name"]: s.get("ticket_shortcode") for s in sauce_docs if s.get("ticket_shortcode")}
    drink_codes = settings.get("drink_shortcodes") or {}
    supplement_prices = {
        s.get("name"): float(s.get("price") or 0.0)
        for s in (settings.get("supplement_options") or [])
        if s.get("name")
    }
    supplement_codes = {
        s.get("name"): s.get("code")
        for s in (settings.get("supplement_options") or [])
        if s.get("name") and s.get("code")
    }
    removal_codes = settings.get("removal_shortcodes") or {}
    kids_code = (settings.get("kids_ticket_code") or "c").strip() or "c"

    snapshots, subtotal = await build_snapshots(
        [line.model_dump() for line in payload.items],
        menu_items,
        burger_cfg,
        settings.get("soda_flavours") or [],
        sauce_codes=sauce_codes,
        drink_codes=drink_codes,
        supplement_prices=supplement_prices,
        supplement_codes=supplement_codes,
        removal_codes=removal_codes,
        kids_code=kids_code,
        fries_sauces=settings.get("fries_sauces") or [],
    )
    delivery_fee = _compute_delivery_fee(payload.fulfillment, subtotal, settings)
    coupon_discount = 0.0
    coupon_applied = None
    tablet_delivery_waived = order_source == "tablet" and payload.fulfillment == "delivery"
    if tablet_delivery_waived:
        delivery_fee = 0.0
    elif payload.coupon_code:
        delivery_fee, coupon_applied = await _apply_coupon(
            payload.coupon_code, payload.fulfillment, delivery_fee, create
        )
        if coupon_applied:
            coupon_discount = coupon_applied["discount_amount"]
    total = round(subtotal + delivery_fee, 2)

    if not create:
        return {
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "coupon_code": coupon_applied["code"] if coupon_applied else None,
            "coupon_discount": coupon_discount,
            "tablet_delivery_waived": tablet_delivery_waived,
            "total": total,
            "items": snapshots,
            "scheduled_delivery_start": scheduled_slot["start"] if scheduled_slot else None,
            "scheduled_delivery_end": scheduled_slot["end"] if scheduled_slot else None,
        }

    order_number = gen_order_number()
    # avoid collisions (extremely unlikely)
    for _ in range(3):
        if await db.orders.find_one({"order_number": order_number}) is None:
            break
        order_number = gen_order_number()

    notes = (payload.notes or "").strip()
    test_order = notes.startswith("[TEST ORDER]")
    order = {
        "id": gen_id(),
        "order_number": order_number,
        "items": snapshots,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "coupon_code": coupon_applied["code"] if coupon_applied else None,
        "coupon_discount": coupon_discount,
        "total": total,
        "fulfillment": payload.fulfillment,
        "customer_first_name": payload.customer_first_name.strip(),
        "customer_last_name": payload.customer_last_name.strip(),
        "customer_phone": payload.customer_phone.strip(),
        "customer_email": (payload.customer_email or "").strip() or None,
        "address_line1": payload.address_line1,
        "address_line2": payload.address_line2,
        "postal_code": payload.postal_code,
        "city": payload.city,
        "notes": notes,
        "payment_method": payload.payment_method,
        "payment_status": "cash_pending" if payload.payment_method == "cash" else "card_pending_in_person",
        "status": "pending",
        "pickup_code": gen_pickup_code() if payload.fulfillment == "pickup" else None,
        "status_history": [
            {
                "status": "pending",
                "at": utc_now_iso(),
                "actor": "customer",
                "note": None,
            }
        ],
        "test_order": test_order,
        "kitchen_decision": None,
        "kitchen_decision_at": None,
        "kitchen_decision_by": None,
        "kitchen_decline_reason": None,
        "kitchen_print_status": "pending",
        "kitchen_print_attempts": 0,
        "kitchen_printed_at": None,
        "scheduled_delivery_start": scheduled_slot["start"] if scheduled_slot else None,
        "scheduled_delivery_end": scheduled_slot["end"] if scheduled_slot else None,
        "kitchen_release_at": (
            (
                datetime.fromisoformat(scheduled_slot["start"]) - timedelta(
                    minutes=int(settings.get("delivery_lead_minutes", 40) or 40)
                )
            ).isoformat()
            if scheduled_slot
            else None
        ),
        "order_source": order_source,
        "tablet_taken_by": tablet_taken_by,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    await db.orders.insert_one(dict(order))
    await _upsert_customer(order)
    if not order.get("test_order") and order.get("order_source") != "tablet":
        asyncio.create_task(send_commission_alert(order))

    # Fire-and-forget notification
    try:
        await send_order_email(order, "order_confirmed")
    except Exception:  # noqa: BLE001
        logger.exception("Email fire-and-forget failed")

    return {
        "url": None,
        "session_id": None,
        "order_id": order["id"],
        "order_number": order["order_number"],
        "payment_method": order["payment_method"],
    }


@api.post("/checkout/quote")
async def checkout_quote(payload: CheckoutPayload):
    return await _quote_or_create(payload, create=False)


@api.post("/checkout/session")
async def checkout_session(payload: CheckoutPayload):
    return await _quote_or_create(payload, create=True)


@api.post("/tablet/quote")
async def tablet_quote(payload: CheckoutPayload, _: dict = Depends(require_tablet)):
    return await _quote_or_create(payload, create=False, order_source="tablet")


@api.post("/tablet/orders")
async def tablet_create_order(payload: CheckoutPayload, staff: dict = Depends(require_tablet)):
    result = await _quote_or_create(
        payload,
        create=True,
        order_source="tablet",
        tablet_taken_by=staff.get("email"),
    )
    if payload.scheduled_delivery_start:
        return {**result, "print_queued": False}

    order_id = result["order_id"]
    now = utc_now_iso()
    claimed = await db.orders.find_one_and_update(
        {
            "id": order_id,
            "$or": [{"kitchen_decision": None}, {"kitchen_decision": {"$exists": False}}],
        },
        {
            "$set": {
                "kitchen_decision": "accepted",
                "kitchen_decision_at": now,
                "kitchen_decision_by": staff.get("email", "tablet"),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if claimed is None:
        raise HTTPException(status_code=409, detail="La commande a déjà été traitée.")
    accepted = await _finalize_order_status(
        order_id,
        "accepted",
        staff.get("email", "tablet"),
        note="Confirmée et imprimée depuis /tablet",
    )
    asyncio.create_task(_push_print_job_background(order_id, accepted, copies=2))
    return {**result, "print_queued": True}


def _phone_key(phone: Optional[str]) -> str:
    return "".join(char for char in (phone or "") if char.isdigit())


def _phone_search_parts(phone: Optional[str]) -> set[str]:
    digits = _phone_key(phone)
    if not digits:
        return set()
    parts = {digits}
    if digits.startswith("00"):
        parts.add(digits[2:])
    if digits.startswith("0"):
        parts.add(digits[1:])
    if len(digits) >= 6:
        parts.add(digits[-9:])
    return {part for part in parts if len(part) >= 3}


def _source_phone(source: Dict[str, Any]) -> str:
    customer = source.get("customer") if isinstance(source.get("customer"), dict) else {}
    return source.get("phone") or source.get("customer_phone") or customer.get("phone") or ""


def _customer_payload(source: Dict[str, Any]) -> Dict[str, str]:
    return {
        "first": source.get("first") or source.get("customer_first_name") or "",
        "last": source.get("last") or source.get("customer_last_name") or "",
        "phone": _source_phone(source),
        "email": source.get("email") or source.get("customer_email") or "",
        "address1": source.get("address1") or source.get("address_line1") or "",
        "address2": source.get("address2") or source.get("address_line2") or "",
        "postal": source.get("postal") or source.get("postal_code") or "",
        "city": source.get("city") or source.get("city") or "",
    }


async def _upsert_customer(order: Dict[str, Any]) -> None:
    if order.get("test_order"):
        return
    phone_key = _phone_key(order.get("customer_phone"))
    if not phone_key:
        return
    customer = _customer_payload(order)
    now = utc_now_iso()
    await db.customers.update_one(
        {"phone_key": phone_key},
        {
            "$set": {**customer, "phone_key": phone_key, "updated_at": now},
            "$setOnInsert": {"id": gen_id(), "created_at": now},
            "$inc": {"order_count": 1},
        },
        upsert=True,
    )


async def _matching_customers(phone: str, limit: int = 5) -> list[Dict[str, str]]:
    search_parts = _phone_search_parts(phone)
    if not search_parts:
        return []
    matches: dict[str, Dict[str, str]] = {}
    customers = await db.customers.find({}, {"_id": 0}).sort("updated_at", -1).to_list(5000)
    for customer in customers:
        saved = customer.get("phone_key") or _phone_key(_source_phone(customer))
        if any(part in saved or saved.endswith(part) for part in search_parts):
            matches.setdefault(saved, _customer_payload(customer))
            if len(matches) >= limit:
                return list(matches.values())

    legacy_orders = await db.orders.find(
        {
            "test_order": {"$ne": True},
            "$or": [
                {"customer_phone": {"$exists": True}},
                {"phone": {"$exists": True}},
                {"customer.phone": {"$exists": True}},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(5000)
    for order in legacy_orders:
        saved = _phone_key(_source_phone(order))
        if saved and any(part in saved or saved.endswith(part) for part in search_parts):
            matches.setdefault(saved, _customer_payload(order))
            if len(matches) >= limit:
                break
    return list(matches.values())


@api.get("/tablet/customers/suggestions")
async def tablet_customer_suggestions(
    phone: str = Query(min_length=3),
    _: dict = Depends(require_tablet),
):
    return {"customers": await _matching_customers(phone)}


@api.get("/tablet/customers/lookup")
async def tablet_customer_lookup(
    phone: str = Query(min_length=4),
    _: dict = Depends(require_tablet),
):
    """Return the latest real customer record matching a restaurant phone call."""
    incoming_parts = _phone_search_parts(phone)
    if not incoming_parts or max(map(len, incoming_parts)) < 4:
        raise HTTPException(status_code=400, detail="Numéro de téléphone incomplet.")
    for customer in await _matching_customers(phone, limit=20):
        saved = _phone_key(customer["phone"])
        saved_parts = _phone_search_parts(saved)
        if any(part in saved_parts for part in incoming_parts):
            return {"found": True, "customer": customer}
    return {"found": False}


PUBLIC_ORDER_FIELDS = {
    "id",
    "order_number",
    "items",
    "subtotal",
    "delivery_fee",
    "total",
    "fulfillment",
    "customer_first_name",
    "customer_last_name",
    "payment_method",
    "payment_status",
    "status",
    "pickup_code",
    "created_at",
    "notes",
}


@api.get("/orders/lookup/{order_id}")
async def order_lookup(order_id: str):
    doc = await db.orders.find_one({"id": order_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    _strip_mongo(doc)
    # strip [TEST ORDER] sentinel from notes for display
    if doc.get("notes"):
        doc["notes"] = doc["notes"].replace("[TEST ORDER]", "").strip()
    return {k: v for k, v in doc.items() if k in PUBLIC_ORDER_FIELDS}


@api.get("/admin/orders")
async def admin_orders(
    _: dict = Depends(require_admin),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    q: Dict[str, Any] = {"order_source": {"$ne": "tablet"}}
    if status:
        q["status"] = status
    docs = await db.orders.find(q).sort([("created_at", -1)]).to_list(limit)
    return [_strip_mongo(d) for d in docs]


@api.get("/admin/tablet/orders")
async def admin_tablet_orders(
    _: dict = Depends(require_admin),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    query: Dict[str, Any] = {"order_source": "tablet"}
    if status:
        query["status"] = status
    docs = await db.orders.find(query).sort([("created_at", -1)]).to_list(limit)
    return [_strip_mongo(doc) for doc in docs]


@api.get("/admin/orders/{order_id}")
async def admin_order_detail(order_id: str, _: dict = Depends(require_admin)):
    doc = await db.orders.find_one({"id": order_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return _strip_mongo(doc)


VALID_STATUS = {
    "pending",
    "accepted",
    "preparing",
    "ready",
    "delivering",
    "delivered",
    "cancelled",
    "expired",
}


async def _apply_status(order_id: str, new_status: str, actor: str, note: Optional[str] = None) -> Optional[dict]:
    if new_status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="Invalid status")
    doc = await db.orders.find_one({"id": order_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    history = doc.get("status_history") or []
    history.append({"status": new_status, "at": utc_now_iso(), "actor": actor, "note": note})
    await db.orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "status": new_status,
                "updated_at": utc_now_iso(),
                "status_history": history,
            }
        },
    )
    doc["status"] = new_status
    doc["status_history"] = history
    return _strip_mongo(doc)


async def _finalize_order_status(order_id: str, status: str, actor: str, note: Optional[str] = None) -> dict:
    """Apply a status transition + fire the existing email side effect.

    Shared by the admin orders dashboard AND the /kitchen accept/decline
    endpoints so both surfaces stay in sync with the same order lifecycle.
    """
    updated = await _apply_status(order_id, status, actor, note)
    try:
        template_map = {
            "accepted": "order_accepted",
            "preparing": "order_accepted",
            "ready": "order_ready",
            "delivering": "out_for_delivery",
            "delivered": None,
            "cancelled": "order_cancelled",
            "expired": "order_cancelled",
        }
        tpl = template_map.get(status)
        if tpl:
            await send_order_email(updated, tpl)
    except Exception:  # noqa: BLE001
        logger.exception("email send failed")
    return updated


@api.put("/admin/orders/{order_id}/status")
async def admin_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    admin: dict = Depends(require_admin),
):
    return await _finalize_order_status(order_id, payload.status, admin.get("email", "admin"), payload.note)


@api.delete("/admin/orders/{order_id}")
async def admin_delete_order(order_id: str, _: dict = Depends(require_admin)):
    res = await db.orders.delete_one({"id": order_id})
    return {"deleted": res.deleted_count}


# ----- Kitchen tablet (real-time accept/decline; auto-push print to Pi) ---


@api.post("/kitchen/login")
async def kitchen_login(payload: AdminLoginPayload):
    email = payload.email.lower().strip()
    user = await db.admin_users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    role = user.get("role", "kitchen")
    if role not in ("admin", "kitchen"):
        raise HTTPException(status_code=403, detail="Accès cuisine refusé")
    token = create_admin_token(user["id"], user["email"], role=role)
    return {"token": token, "user": {"email": user["email"], "role": role}}


@api.post("/tablet/login")
async def tablet_login(payload: AdminLoginPayload):
    email = payload.email.lower().strip()
    user = await db.admin_users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    role = user.get("role", "")
    if role not in ("admin", "tablet") or user.get("active", True) is False:
        raise HTTPException(status_code=403, detail="Accès tablette refusé")
    token = create_admin_token(user["id"], user["email"], role=role)
    return {"token": token, "user": {"email": user["email"], "role": role}}


@api.get("/tablet/me")
async def tablet_me(payload: dict = Depends(require_tablet)):
    return {"email": payload.get("email"), "role": payload.get("role")}


@api.get("/kitchen/me")
async def kitchen_me(payload: dict = Depends(require_kitchen)):
    return {"email": payload.get("email"), "role": payload.get("role")}


@api.get("/kitchen/orders")
async def kitchen_orders(_: dict = Depends(require_kitchen)):
    since = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    now = utc_now_iso()
    docs = await db.orders.find(
        {
            "created_at": {"$gte": since},
            "$or": [
                {"scheduled_delivery_start": None},
                {"scheduled_delivery_start": {"$exists": False}},
                {"kitchen_release_at": {"$lte": now}},
                {"kitchen_decision": {"$in": ["accepted", "declined"]}},
            ],
        }
    ).sort([("created_at", -1)]).to_list(300)
    docs = [_strip_mongo(d) for d in docs]
    new_orders = [d for d in docs if d.get("status") == "pending" and not d.get("kitchen_decision")]
    accepted_orders = [d for d in docs if d.get("kitchen_decision") == "accepted"]
    declined_orders = [d for d in docs if d.get("kitchen_decision") == "declined"]
    return {
        "new": new_orders,
        "accepted": accepted_orders,
        "declined": declined_orders,
        "server_time": utc_now_iso(),
    }


async def _mark_order_printed(order_id: str) -> bool:
    """Best-effort telemetry only — flips the "Imprimé" badge on the kitchen
    dashboard once the Pi print-bridge has accepted the job. Never gates
    order status; failures here are logged and swallowed by callers.
    Returns False if the order doesn't exist."""
    now = utc_now_iso()
    res = await db.orders.update_one(
        {"id": order_id},
        {"$set": {"kitchen_print_status": "printed", "kitchen_printed_at": now, "updated_at": now}},
    )
    return res.matched_count > 0


async def _push_print_job_background(
    order_id: str,
    order: Dict[str, Any],
    copies: int = 3,
) -> None:
    """Runs detached from the request/response cycle so a slow or
    unreachable Pi/tunnel never delays the Accept response for the tablet.
    The kitchen dashboard's polling picks up the resulting print-status
    badge a few seconds later regardless of when this finishes."""
    try:
        # 3 physical copies on accept — kitchen counter, delivery bag, and
        # a spare per owner's request.
        if await send_print_job(order, copies=copies):
            await _mark_order_printed(order_id)
    except Exception:  # noqa: BLE001
        logger.exception("Printer push failed")


@api.post("/kitchen/orders/{order_id}/accept")
async def kitchen_accept_order(order_id: str, kitchen: dict = Depends(require_kitchen)):
    now = utc_now_iso()
    actor = kitchen.get("email", "kitchen")
    # Atomic, concurrency-safe transition: only the FIRST tap (or duplicate
    # retry) wins the decision — a second concurrent request matches zero
    # documents and is treated as an idempotent no-op below.
    claimed = await db.orders.find_one_and_update(
        {
            "id": order_id,
            "$or": [{"kitchen_decision": None}, {"kitchen_decision": {"$exists": False}}],
        },
        {"$set": {"kitchen_decision": "accepted", "kitchen_decision_at": now, "kitchen_decision_by": actor}},
        return_document=ReturnDocument.AFTER,
    )
    if claimed is None:
        existing = await db.orders.find_one({"id": order_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Commande introuvable")
        return {"already_decided": True, "order": _strip_mongo(existing)}

    updated = await _finalize_order_status(order_id, "accepted", actor, note="Acceptée depuis /kitchen")
    # Fire-and-forget push to the Raspberry Pi print-bridge, detached via
    # create_task so a slow/unreachable Pi never delays this response —
    # replaces the old client-side window.print() entirely; the tablet no
    # longer prints anything itself.
    asyncio.create_task(_push_print_job_background(order_id, updated, copies=3))
    return {"already_decided": False, "order": updated}


@api.post("/kitchen/orders/{order_id}/decline")
async def kitchen_decline_order(
    order_id: str,
    payload: KitchenDeclinePayload,
    kitchen: dict = Depends(require_kitchen),
):
    now = utc_now_iso()
    actor = kitchen.get("email", "kitchen")
    reason = (payload.reason or "").strip() or None
    claimed = await db.orders.find_one_and_update(
        {
            "id": order_id,
            "$or": [{"kitchen_decision": None}, {"kitchen_decision": {"$exists": False}}],
        },
        {
            "$set": {
                "kitchen_decision": "declined",
                "kitchen_decision_at": now,
                "kitchen_decision_by": actor,
                "kitchen_decline_reason": reason,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if claimed is None:
        existing = await db.orders.find_one({"id": order_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Commande introuvable")
        return {"already_decided": True, "order": _strip_mongo(existing)}

    updated = await _finalize_order_status(order_id, "cancelled", actor, note=reason or "Refusée depuis /kitchen")
    return {"already_decided": False, "order": updated}


@api.post("/kitchen/orders/{order_id}/mark-printed")
async def kitchen_mark_printed(order_id: str, _: dict = Depends(require_kitchen)):
    """Manual override — lets staff flag an order printed even if the
    automated Pi push failed (e.g. tunnel was briefly down)."""
    found = await _mark_order_printed(order_id)
    if not found:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    order = _strip_mongo(await db.orders.find_one({"id": order_id}))
    return {"ok": True, "order": order}


@api.post("/kitchen/orders/{order_id}/reprint")
async def kitchen_reprint_order(order_id: str, _: dict = Depends(require_kitchen)):
    """Manually re-push a ticket to the Pi print-bridge (e.g. after a paper
    jam) — does not touch order status."""
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    order = _strip_mongo(order)
    # Only 1 copy on a manual reprint (e.g. paper jam) — accept already
    # sent three copies the first time.
    ok = await send_print_job(order, copies=1)
    if ok:
        await _mark_order_printed(order_id)
    return {"ok": ok}


@api.post("/kitchen/test-print")
async def kitchen_test_print(_: dict = Depends(require_kitchen)):
    """Fires one synthetic test ticket straight at the Pi print-bridge so
    staff can verify the printer/tunnel is reachable on demand. Never
    touches the `orders` collection at all — nothing is persisted, so this
    can never show up in any order list or stats query."""
    test_order = {
        "order_number": "TEST",
        "created_at": utc_now_iso(),
        "fulfillment": "pickup",
        "customer_first_name": "Test imprimante",
        "customer_last_name": "",
        "customer_phone": "",
        "items": [{"quantity": 1, "name": "Ticket de test", "burger_config": {}}],
        "total": 0.0,
        "payment_method": "cash",
        "pickup_code": "0000",
    }
    ok = await send_print_job(test_order, copies=1)
    return {"ok": ok}


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    docs = await db.orders.find(
        {"order_source": {"$ne": "tablet"}, "test_order": {"$ne": True}}
    ).to_list(5000)
    void = {"cancelled", "expired"}
    in_flight = {"pending", "accepted", "preparing", "ready", "delivering"}
    total_orders = len(docs)
    paid = [d for d in docs if d.get("status") not in void]
    revenue = round(sum(float(d.get("total", 0.0)) for d in paid), 2)
    pending = sum(1 for d in docs if d.get("status") in in_flight)
    avg = round(revenue / len(paid), 2) if paid else 0.0
    return {
        "total_orders": total_orders,
        "paid_orders": len(paid),
        "pending_orders": pending,
        "revenue": revenue,
        "avg_basket": avg,
    }


@api.get("/admin/stats/tablet")
async def admin_tablet_stats(_: dict = Depends(require_admin)):
    docs = await db.orders.find({"order_source": "tablet", "test_order": {"$ne": True}}).to_list(5000)
    void = {"cancelled", "expired"}
    paid = [doc for doc in docs if doc.get("status") not in void]
    revenue = round(sum(float(doc.get("total") or 0.0) for doc in paid), 2)
    today = datetime.now(timezone.utc).date().isoformat()
    today_docs = [doc for doc in paid if (doc.get("created_at") or "")[:10] == today]
    pickup = sum(1 for doc in paid if doc.get("fulfillment") == "pickup")
    delivery = sum(1 for doc in paid if doc.get("fulfillment") == "delivery")
    return {
        "total_orders": len(docs),
        "valid_orders": len(paid),
        "today_orders": len(today_docs),
        "revenue": revenue,
        "avg_basket": round(revenue / len(paid), 2) if paid else 0.0,
        "pickup_orders": pickup,
        "delivery_orders": delivery,
    }


@api.get("/admin/stats/delivery-fees")
async def admin_delivery_fee_stats(
    _: dict = Depends(require_admin),
    days: int = Query(default=30, ge=1, le=365),
    start_date: Optional[str] = Query(default=None, description="YYYY-MM-DD, use with end_date for a custom range"),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD, use with start_date for a custom range"),
):
    """Return per-day delivery-fee totals in the restaurant's local timezone.

    Counts only real (non-test) delivery orders (fulfillment='delivery')
    that were not cancelled or expired. Returns:
      - daily: [{date, orders, delivery_fees, subtotal, avg_fee}]
      - totals: {today, this_week, this_month, all_time, in_range}
      - by_payment: {cash, card_in_person} breakdown for the "in_range" window
        (either the last `days` days, or the custom start_date/end_date range)
    """
    settings = await db.settings.find_one({"id": "singleton"}, NO_IMAGE_FIELDS) or {}
    tz_name = settings.get("timezone") or "Europe/Paris"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Europe/Paris")

    void = {"cancelled", "expired"}
    docs = await db.orders.find(
        {
            "fulfillment": "delivery",
            "status": {"$nin": list(void)},
            "test_order": {"$ne": True},
            "order_source": {"$ne": "tablet"},
        }
    ).to_list(20000)

    now_local = datetime.now(tz)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start_local = (today_local - timedelta(days=today_local.weekday()))
    month_start_local = today_local.replace(day=1)

    is_custom_range = bool(start_date and end_date)
    if is_custom_range:
        try:
            range_start_local = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
            range_end_local = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=tz
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date/end_date doivent être au format AAAA-MM-JJ")
        if range_end_local < range_start_local:
            raise HTTPException(status_code=400, detail="end_date doit être postérieure ou égale à start_date")
        if (range_end_local - range_start_local).days > 400:
            raise HTTPException(status_code=400, detail="Période trop longue (400 jours max)")
    else:
        range_start_local = today_local - timedelta(days=days - 1)
        range_end_local = now_local

    daily_map: Dict[str, Dict[str, float]] = {}
    totals = {"today": 0.0, "this_week": 0.0, "this_month": 0.0, "all_time": 0.0, "in_range": 0.0}
    counts = {"today": 0, "this_week": 0, "this_month": 0, "all_time": 0, "in_range": 0}
    subtotals = {"today": 0.0, "this_week": 0.0, "this_month": 0.0, "all_time": 0.0, "in_range": 0.0}
    by_payment = {
        "cash": {"delivery_fees": 0.0, "subtotal": 0.0, "orders": 0},
        "card_in_person": {"delivery_fees": 0.0, "subtotal": 0.0, "orders": 0},
    }

    for d in docs:
        fee = float(d.get("delivery_fee") or 0.0)
        sub = float(d.get("subtotal") or 0.0)
        created = d.get("created_at")
        if not created:
            continue
        try:
            dt_utc = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            continue
        dt_local = dt_utc.astimezone(tz)
        day_key = dt_local.strftime("%Y-%m-%d")

        entry = daily_map.setdefault(day_key, {"date": day_key, "orders": 0, "delivery_fees": 0.0, "subtotal": 0.0})
        entry["orders"] += 1
        entry["delivery_fees"] = round(entry["delivery_fees"] + fee, 2)
        entry["subtotal"] = round(entry["subtotal"] + sub, 2)

        totals["all_time"] += fee
        subtotals["all_time"] += sub
        counts["all_time"] += 1
        if dt_local >= today_local:
            totals["today"] += fee
            subtotals["today"] += sub
            counts["today"] += 1
        if dt_local >= week_start_local:
            totals["this_week"] += fee
            subtotals["this_week"] += sub
            counts["this_week"] += 1
        if dt_local >= month_start_local:
            totals["this_month"] += fee
            subtotals["this_month"] += sub
            counts["this_month"] += 1
        if range_start_local <= dt_local <= range_end_local:
            totals["in_range"] += fee
            subtotals["in_range"] += sub
            counts["in_range"] += 1
            pm = d.get("payment_method")
            if pm in by_payment:
                by_payment[pm]["delivery_fees"] = round(by_payment[pm]["delivery_fees"] + fee, 2)
                by_payment[pm]["subtotal"] = round(by_payment[pm]["subtotal"] + sub, 2)
                by_payment[pm]["orders"] += 1

    # Fill every day in the requested range so the chart has no gaps.
    daily = []
    cursor = range_start_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_cursor = range_end_local.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor <= end_cursor:
        key = cursor.strftime("%Y-%m-%d")
        e = daily_map.get(key, {"date": key, "orders": 0, "delivery_fees": 0.0, "subtotal": 0.0})
        daily.append({
            "date": e["date"],
            "orders": e["orders"],
            "delivery_fees": round(e["delivery_fees"], 2),
            "subtotal": round(e["subtotal"], 2),
        })
        cursor += timedelta(days=1)

    return {
        "range_days": days,
        "range_start": range_start_local.strftime("%Y-%m-%d"),
        "range_end": range_end_local.strftime("%Y-%m-%d"),
        "is_custom_range": is_custom_range,
        "timezone": tz_name,
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "counts": counts,
        "subtotals": {k: round(v, 2) for k, v in subtotals.items()},
        "by_payment": by_payment,
        "daily": daily,
    }


# ----- SUNMI kitchen printer (test phase — no automatic order printing yet) -


@api.get("/admin/sunmi/status")
async def admin_sunmi_status(_: dict = Depends(require_admin)):
    if not sunmi_service.is_configured():
        return {"configured": False, "online": None, "raw": None}
    result = await sunmi_service.check_online()
    return {"configured": True, "online": sunmi_service.extract_online(result), "raw": result}


@api.post("/admin/sunmi/test-print")
async def admin_sunmi_test_print(_: dict = Depends(require_admin)):
    if not sunmi_service.is_configured():
        raise HTTPException(
            status_code=400,
            detail="SUNMI n'est pas configuré (variables d'environnement manquantes).",
        )
    ticket = build_test_ticket()
    trade_no = f"BT-TEST-{gen_id()[:8].upper()}"
    result = await sunmi_service.push_content(to_hex(ticket), trade_no)
    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail={"message": "Échec d'impression du ticket de test.", "sunmi": result},
        )
    return {"ok": True, "trade_no": trade_no, "sunmi": result}


# ----- Waitlist ------------------------------------------------------------


@api.post("/waitlist")
async def create_waitlist(payload: WaitlistCreate):
    email = payload.email.lower().strip()
    existing = await db.waitlist.find_one({"email": email, "active": True})
    if existing:
        return {"ok": True, "already_subscribed": True}
    doc = WaitlistEntry(email=email).model_dump()
    await db.waitlist.insert_one(doc)
    return {"ok": True, "already_subscribed": False}


@api.get("/admin/waitlist")
async def admin_list_waitlist(_: dict = Depends(require_admin)):
    docs = await db.waitlist.find({"active": True}).sort([("created_at", -1)]).to_list(1000)
    return [_strip_mongo(d) for d in docs]


@api.delete("/admin/waitlist/{wid}")
async def admin_delete_waitlist(wid: str, _: dict = Depends(require_admin)):
    res = await db.waitlist.delete_one({"id": wid})
    return {"deleted": res.deleted_count}


@api.post("/admin/waitlist/notify")
async def admin_notify_waitlist(_: dict = Depends(require_admin)):
    docs = await db.waitlist.find({"active": True}).to_list(2000)
    emails_sent = 0
    if _email_configured():
        for d in docs:
            try:
                if await send_open_notice(d["email"]):
                    emails_sent += 1
            except Exception:  # noqa: BLE001
                logger.exception("send_open_notice failed for %s", d.get("email"))
    if docs:
        ts = utc_now_iso()
        await db.waitlist.update_many(
            {"active": True},
            {"$set": {"notified_at": ts, "active": False}},
        )
    return {
        "notified": len(docs),
        "emails_sent": emails_sent,
        "email_configured": _email_configured(),
    }


# ----- Auto-notify waitlist on open transition ----------------------------


def _verify_cron_auth(request: Request) -> None:
    secret = os.environ.get("WEBHOOK_CRON_SECRET")
    if not secret:
        raise HTTPException(status_code=401, detail="Cron secret not configured")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:].strip()
    if not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


async def _maybe_notify_waitlist_on_open() -> Dict[str, Any]:
    """Detect a closed → open transition and email active waitlist subscribers.

    Idempotent: after notifying, subscribers are marked ``active=false`` so they
    are not re-notified on the next open. First observation (prev state = None)
    just records the current state without sending anything, to avoid a spurious
    blast on system boot when the restaurant is already open.
    """
    settings = await db.settings.find_one({"id": "singleton"})
    if settings is None:
        return {"skipped": True, "reason": "no_settings"}
    _strip_mongo(settings)
    status = compute_status(settings)
    current = status["state"]
    prev = settings.get("last_notified_open_state")

    result: Dict[str, Any] = {
        "prev_state": prev,
        "current_state": current,
        "notified": False,
    }

    should_notify = prev == "closed" and current != "closed"
    if should_notify:
        docs = await db.waitlist.find({"active": True}).to_list(5000)
        emails_sent = 0
        if _email_configured():
            for d in docs:
                try:
                    if await send_open_notice(d["email"]):
                        emails_sent += 1
                except Exception:  # noqa: BLE001
                    logger.exception("send_open_notice failed for %s", d.get("email"))
        if docs:
            ts = utc_now_iso()
            await db.waitlist.update_many(
                {"active": True},
                {"$set": {"notified_at": ts, "active": False}},
            )
        result.update(
            {
                "notified": True,
                "recipient_count": len(docs),
                "emails_sent": emails_sent,
                "email_configured": _email_configured(),
            }
        )
        logger.info(
            "Auto-notified waitlist on open transition: %d recipients, %d emails sent",
            len(docs),
            emails_sent,
        )

    if prev != current:
        await db.settings.update_one(
            {"id": "singleton"},
            {"$set": {"last_notified_open_state": current}},
        )
    return result


@api.post("/cron/notify-waitlist-on-open")
async def cron_notify_waitlist(request: Request, background: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    _verify_cron_auth(request)
    background.add_task(_maybe_notify_waitlist_on_open)
    return {"ok": True, "queued": True}


app.include_router(api)
