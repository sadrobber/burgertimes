"""Telegram kitchen notifications — safe when token/chat are unset."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _bot_token() -> Optional[str]:
    v = os.environ.get("TELEGRAM_BOT_TOKEN")
    return v if v else None


def _kitchen_chat() -> Optional[str]:
    v = os.environ.get("TELEGRAM_KITCHEN_CHAT_ID")
    return v if v else None


def is_configured() -> bool:
    return bool(_bot_token() and _kitchen_chat())


def _format_phone_spaced(raw: str) -> str:
    if not raw:
        return ""
    digits = raw.replace(" ", "")
    # +33...
    if digits.startswith("+"):
        cc = digits[:3]
        rest = re.sub(r"\D", "", digits[3:])
        chunks = [rest[i : i + 2] for i in range(0, len(rest), 2)]
        return cc + " " + " ".join(chunks)
    digits = re.sub(r"\D", "", digits)
    chunks = [digits[i : i + 2] for i in range(0, len(digits), 2)]
    return " ".join(chunks)


def _line_render(item: Dict[str, Any]) -> str:
    base = f"• {item['quantity']}× <b>{item['name']}</b>"
    subs = []
    burger_cfg = item.get("burger_config")
    if burger_cfg:
        size = burger_cfg.get("size")
        if size and size.get("label"):
            subs.append(f"↳ Taille : {size['label']}")
        meats = burger_cfg.get("meats") or []
        if meats:
            subs.append("↳ Viandes : " + ", ".join(m["name"] for m in meats))
        cheeses = burger_cfg.get("cheeses") or []
        if cheeses:
            subs.append("↳ Fromages : " + ", ".join(c["name"] for c in cheeses))
        supps = burger_cfg.get("supplements") or []
        if supps:
            subs.append("↳ Suppléments : " + ", ".join(s["name"] for s in supps))
    if item.get("selected_format"):
        subs.append(f"↳ Format : {item['selected_format']}")
    if item.get("formula") == "menu":
        drink = item.get("included_drink") or "Boisson"
        variant = item.get("included_drink_variant")
        subs.append(f"↳ Menu — Boisson : {drink}" + (f" ({variant})" if variant else ""))
    if item.get("sauces"):
        subs.append("↳ Sauces : " + ", ".join(item["sauces"]))
    if item.get("notes"):
        subs.append(f"↳ Note : {item['notes']}")
    return "\n".join([base, *[f"   {s}" for s in subs]])


def build_kitchen_message(order: Dict[str, Any]) -> str:
    test_banner = ""
    if order.get("test_order") or (order.get("notes") or "").startswith("[TEST ORDER]"):
        test_banner = "⚠️ <b>TEST ORDER — DO NOT DELIVER</b>\n\n"

    payment_label = {"cash": "Cash", "card_in_person": "Card (at counter)"}.get(
        order.get("payment_method"), order.get("payment_method")
    )
    fulfillment_label = "🛵 Delivery" if order.get("fulfillment") == "delivery" else "🏠 Takeaway"

    address = ""
    if order.get("fulfillment") == "delivery":
        parts = [order.get("address_line1")]
        if order.get("address_line2"):
            parts.append(order["address_line2"])
        loc = " ".join(x for x in [order.get("postal_code"), order.get("city")] if x)
        if loc:
            parts.append(loc)
        address = ", ".join(p for p in parts if p)

    phone = _format_phone_spaced(order.get("customer_phone", ""))
    name = f"{order.get('customer_first_name','')} {order.get('customer_last_name','')}".strip()

    header = f"📦 <b>NEW ORDER · #{order.get('order_number')}</b>\n"
    header += f"👤 Client : <code>{name}</code>\n"
    header += f"📞 Tel : <code>{phone}</code>\n"
    if address:
        header += f"📍 Address : <code>{address}</code>\n"
    header += f"💰 Mode : <code>{payment_label}</code>\n"
    header += f"💸 Total : <b>{order.get('total', 0):.2f} €</b>\n"
    header += "━━━━━━━━━━━━━━\n"

    lines = "\n".join(_line_render(i) for i in (order.get("items") or []))
    footer = "\n━━━━━━━━━━━━━━\n"
    if order.get("pickup_code"):
        footer += f"🔐 Pickup code : <code>{order['pickup_code']}</code>\n"
    pay_line = (
        "💵 COLLECT ON SITE (Cash)"
        if order.get("payment_method") == "cash"
        else "💳 CARD AT COUNTER"
    )
    footer += pay_line + "\n"

    notes = (order.get("notes") or "").replace("[TEST ORDER]", "").strip()
    if notes:
        footer += f"\n📝 {notes}\n"
    footer += f"\n{fulfillment_label}"

    return test_banner + header + lines + footer


def build_keyboard_for_status(order_id: str, status: str) -> Dict[str, Any]:
    buttons = []
    if status == "pending":
        buttons.append([{"text": "✅ Accept", "callback_data": f"order|accept|{order_id}"}])
        buttons.append([{"text": "❌ Cancel", "callback_data": f"order|cancel|{order_id}"}])
    elif status == "accepted":
        buttons.append([{"text": "🔥 Preparing", "callback_data": f"order|preparing|{order_id}"}])
        buttons.append([{"text": "❌ Cancel", "callback_data": f"order|cancel|{order_id}"}])
    elif status == "preparing":
        buttons.append([{"text": "📦 Ready", "callback_data": f"order|ready|{order_id}"}])
        buttons.append([{"text": "❌ Cancel", "callback_data": f"order|cancel|{order_id}"}])
    elif status == "ready":
        buttons.append([{"text": "🚚 Delivered", "callback_data": f"order|delivered|{order_id}"}])
    return {"inline_keyboard": buttons}


async def send_kitchen_order(order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not is_configured():
        logger.info("Telegram not configured; skipping send_kitchen_order")
        return None
    text = build_kitchen_message(order)
    keyboard = build_keyboard_for_status(order["id"], order.get("status", "pending"))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{TELEGRAM_API}/bot{_bot_token()}/sendMessage",
                json={
                    "chat_id": _kitchen_chat(),
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": True,
                },
            )
            data = r.json()
            if not data.get("ok"):
                logger.warning("Telegram sendMessage failed: %s", data)
                return None
            return {
                "message_id": data["result"]["message_id"],
                "chat_id": str(data["result"]["chat"]["id"]),
            }
    except Exception:  # noqa: BLE001
        logger.exception("Telegram send failed")
        return None


async def edit_kitchen_message(
    chat_id: str, message_id: int, order: Dict[str, Any], status_line: str
) -> None:
    if not is_configured():
        return
    text = build_kitchen_message(order) + f"\n\n<b>Statut :</b> {status_line}"
    keyboard = build_keyboard_for_status(order["id"], order.get("status", "pending"))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{TELEGRAM_API}/bot{_bot_token()}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": True,
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception("Telegram edit failed")


async def answer_callback_query(callback_query_id: str, text: str = "OK") -> None:
    if not is_configured():
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{TELEGRAM_API}/bot{_bot_token()}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )
    except Exception:  # noqa: BLE001
        logger.exception("Telegram answerCallbackQuery failed")


async def set_webhook(public_base_url: str) -> Dict[str, Any]:
    if not _bot_token():
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    url = public_base_url.rstrip("/") + "/api/telegram/webhook"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{TELEGRAM_API}/bot{_bot_token()}/setWebhook",
                json={"url": url, "secret_token": secret, "drop_pending_updates": True},
            )
            return r.json()
    except Exception as e:  # noqa: BLE001
        logger.exception("Telegram setWebhook failed")
        return {"ok": False, "error": str(e)}
