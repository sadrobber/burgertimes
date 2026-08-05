"""Burger Times · FastAPI backend.

All routes prefixed with /api. UUID string primary keys. UTC ISO 8601 timestamps.
"""
from __future__ import annotations

from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

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
from starlette.middleware.cors import CORSMiddleware

from auth import create_admin_token, require_admin, verify_password
from email_service import send_open_notice, send_order_email
from email_service import is_configured as _email_configured
from models import (
    AdminLoginPayload,
    BuilderItemCreate,
    Category,
    CategoryCreate,
    CategoryUpdate,
    CheckoutPayload,
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
    WaitlistCreate,
    WaitlistEntry,
    gen_id,
    utc_now_iso,
)
from order_service import build_snapshots, gen_order_number, gen_pickup_code
from pricing import BurgerBuilderConfig
from restaurant_status import compute_status
from seed import force_reseed_reference_data, run_seed
from telegram_service import (
    answer_callback_query,
    edit_kitchen_message,
    send_kitchen_order,
    set_webhook as tg_set_webhook,
)

# ----- Database ------------------------------------------------------------

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
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
    return d


# ----- Startup -------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    try:
        await run_seed(db)
    except Exception:  # noqa: BLE001
        logger.exception("Seed failed")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    client.close()


# ----- Health --------------------------------------------------------------


@api.get("/")
async def root() -> dict:
    return {"name": "burger-times", "status": "ok"}


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


# ----- Public: settings + status + reviews + sauces + categories -----------


@api.get("/settings")
async def get_settings():
    doc = await db.settings.find_one({"id": "singleton"})
    if doc is None:
        # Should be seeded; return default just in case.
        return Settings().model_dump()
    return _strip_mongo(doc)


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
    return _strip_mongo(doc)


@api.get("/restaurant/status")
async def restaurant_status():
    settings = await db.settings.find_one({"id": "singleton"}) or Settings().model_dump()
    _strip_mongo(settings)
    return compute_status(settings)


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
    docs = await db.menu_items.find({"available": True}).sort([("sort_order", 1), ("name", 1)]).to_list(500)
    return [_strip_image(_strip_mongo(d)) for d in docs]


@api.get("/admin/menu")
async def admin_list_menu(_: dict = Depends(require_admin)):
    docs = await db.menu_items.find().sort([("sort_order", 1), ("name", 1)]).to_list(2000)
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
        else:
            changes["has_image"] = False
            await db.menu_items.update_one({"id": item_id}, {"$unset": {"image_base64": ""}})
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


async def _quote_or_create(payload: CheckoutPayload, create: bool) -> dict:
    settings = await db.settings.find_one({"id": "singleton"}) or Settings().model_dump()
    _strip_mongo(settings)

    if create:
        await _ensure_accepting_orders(settings)
        _validate_payment_method(settings, payload.payment_method)
        await _check_order_limit(settings)

    if payload.fulfillment not in ("delivery", "pickup"):
        raise HTTPException(status_code=400, detail="Invalid fulfillment")
    if payload.payment_method not in ("cash", "card_in_person"):
        raise HTTPException(status_code=400, detail="Invalid payment method")

    if payload.fulfillment == "delivery" and create:
        if not (payload.address_line1 and payload.postal_code and payload.city):
            raise HTTPException(status_code=400, detail="Adresse de livraison requise")
        allowed = [
            str(x).strip()
            for x in (settings.get("delivery_postal_codes") or [])
            if str(x).strip()
        ]
        if allowed:
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
    menu_docs = await db.menu_items.find({"available": True}).to_list(2000)
    menu_items = {d["id"]: _strip_mongo(d) for d in menu_docs}
    burger_cfg = await _load_builder_config()

    snapshots, subtotal = await build_snapshots(
        [line.model_dump() for line in payload.items],
        menu_items,
        burger_cfg,
        settings.get("soda_flavours") or [],
    )
    delivery_fee = _compute_delivery_fee(payload.fulfillment, subtotal, settings)
    total = round(subtotal + delivery_fee, 2)

    if not create:
        return {
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total,
            "items": snapshots,
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
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    await db.orders.insert_one(dict(order))

    # Fire-and-forget notifications
    try:
        tg = await send_kitchen_order(order)
        if tg:
            await db.orders.update_one(
                {"id": order["id"]},
                {
                    "$set": {
                        "kitchen_message_id": tg["message_id"],
                        "kitchen_chat_id": tg["chat_id"],
                    }
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception("Telegram fire-and-forget failed")
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
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    docs = await db.orders.find(q).sort([("created_at", -1)]).to_list(limit)
    return [_strip_mongo(d) for d in docs]


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


@api.put("/admin/orders/{order_id}/status")
async def admin_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    admin: dict = Depends(require_admin),
):
    updated = await _apply_status(order_id, payload.status, admin.get("email", "admin"), payload.note)
    # Fire email + edit telegram (best effort)
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
        tpl = template_map.get(payload.status)
        if tpl:
            await send_order_email(updated, tpl)
    except Exception:  # noqa: BLE001
        logger.exception("email send failed")
    try:
        if updated.get("kitchen_chat_id") and updated.get("kitchen_message_id"):
            await edit_kitchen_message(
                updated["kitchen_chat_id"],
                updated["kitchen_message_id"],
                updated,
                payload.status.upper(),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Telegram edit failed")
    return updated


@api.delete("/admin/orders/{order_id}")
async def admin_delete_order(order_id: str, _: dict = Depends(require_admin)):
    res = await db.orders.delete_one({"id": order_id})
    return {"deleted": res.deleted_count}


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    docs = await db.orders.find().to_list(5000)
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


@api.get("/admin/stats/delivery-fees")
async def admin_delivery_fee_stats(
    _: dict = Depends(require_admin),
    days: int = Query(default=30, ge=1, le=365),
):
    """Return per-day delivery-fee totals in the restaurant's local timezone.

    Counts only delivery orders (fulfillment='delivery') that were not
    cancelled or expired. Returns:
      - daily: [{date, orders, delivery_fees, subtotal, avg_fee}]
      - totals: {today, this_week, this_month, all_time, in_range}
    """
    settings = await db.settings.find_one({"id": "singleton"}) or {}
    tz_name = settings.get("timezone") or "Europe/Paris"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Europe/Paris")

    void = {"cancelled", "expired"}
    docs = await db.orders.find(
        {"fulfillment": "delivery", "status": {"$nin": list(void)}}
    ).to_list(20000)

    now_local = datetime.now(tz)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start_local = (today_local - timedelta(days=today_local.weekday()))
    month_start_local = today_local.replace(day=1)
    range_start_local = today_local - timedelta(days=days - 1)

    daily_map: Dict[str, Dict[str, float]] = {}
    totals = {"today": 0.0, "this_week": 0.0, "this_month": 0.0, "all_time": 0.0, "in_range": 0.0}
    counts = {"today": 0, "this_week": 0, "this_month": 0, "all_time": 0, "in_range": 0}
    subtotals = {"today": 0.0, "this_week": 0.0, "this_month": 0.0, "all_time": 0.0, "in_range": 0.0}

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
        if dt_local >= range_start_local:
            totals["in_range"] += fee
            subtotals["in_range"] += sub
            counts["in_range"] += 1

    # Fill every day in the requested range so the chart has no gaps.
    daily = []
    cursor = range_start_local
    while cursor <= today_local:
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
        "timezone": tz_name,
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "counts": counts,
        "subtotals": {k: round(v, 2) for k, v in subtotals.items()},
        "daily": daily,
    }


# ----- Telegram webhook ----------------------------------------------------


@api.post("/telegram/set-webhook")
async def tg_set_webhook_route(
    request: Request,
    public_base_url: Optional[str] = Query(default=None),
    _: dict = Depends(require_admin),
):
    if not public_base_url:
        # infer from request
        proto = request.headers.get("x-forwarded-proto") or ("https" if request.url.scheme == "https" else "http")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        public_base_url = f"{proto}://{host}"
    result = await tg_set_webhook(public_base_url)
    return result


@api.post("/telegram/webhook")
async def tg_webhook(request: Request):
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected or header != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    body = await request.json()
    cbq = body.get("callback_query")
    if not cbq:
        return {"ok": True}
    data = cbq.get("data", "")
    parts = data.split("|")
    if len(parts) != 3 or parts[0] != "order":
        await answer_callback_query(cbq["id"], "Unknown action")
        return {"ok": True}
    _, action, order_id = parts
    status_map = {
        "accept": "accepted",
        "preparing": "preparing",
        "ready": "ready",
        "delivered": "delivered",
        "cancel": "cancelled",
    }
    new_status = status_map.get(action)
    if not new_status:
        await answer_callback_query(cbq["id"], "Unknown action")
        return {"ok": True}
    updated = await _apply_status(order_id, new_status, "kitchen", None)
    try:
        if updated and updated.get("kitchen_chat_id") and updated.get("kitchen_message_id"):
            await edit_kitchen_message(
                updated["kitchen_chat_id"],
                updated["kitchen_message_id"],
                updated,
                new_status.upper(),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Telegram edit after webhook failed")
    try:
        template_map = {
            "accepted": "order_accepted",
            "ready": "order_ready",
            "delivered": None,
            "cancelled": "order_cancelled",
        }
        tpl = template_map.get(new_status)
        if tpl and updated:
            await send_order_email(updated, tpl)
    except Exception:  # noqa: BLE001
        logger.exception("Email after webhook failed")
    await answer_callback_query(cbq["id"], f"✅ {new_status.upper()}")
    return {"ok": True}


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
