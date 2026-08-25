"""ESC/POS kitchen ticket builder for the 80mm SUNMI printer (local bridge).

Standalone module — no dependency on the earlier SUNMI Cloud API test-print
code (sunmi_receipt.py). Renders from the authoritative saved order document
only; never from cart/frontend state.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

WIDTH = 32  # standard 80mm ESC/POS text width in Font A (12x24)

ESC = b"\x1b"
GS = b"\x1d"

INIT = ESC + b"\x40"
ALIGN_CENTER = ESC + b"\x61\x01"
ALIGN_LEFT = ESC + b"\x61\x00"
BOLD_ON = ESC + b"\x45\x01"
BOLD_OFF = ESC + b"\x45\x00"
DOUBLE_SIZE_ON = GS + b"\x21\x11"
DOUBLE_SIZE_OFF = GS + b"\x21\x00"
FEED_CUT = b"\n\n\n" + GS + b"\x56\x00"

FULFILLMENT_LABEL = {"pickup": "A EMPORTER", "delivery": "LIVRAISON"}
PAYMENT_LABEL = {"cash": "ESPECES SUR PLACE", "card_in_person": "CARTE SUR PLACE"}


def _ascii(text: Any) -> str:
    """Strip accents so firmware without full UTF-8 support prints cleanly."""
    text = str(text or "")
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _line(text: str = "") -> bytes:
    return text.encode("ascii", errors="replace") + b"\n"


def _split_row(left: str, right: str, width: int = WIDTH) -> str:
    left = left[: max(0, width - len(right) - 1)]
    gap = max(1, width - len(left) - len(right))
    return f"{left}{' ' * gap}{right}"


def _local_dt(iso_str: str):
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:  # noqa: BLE001
        return None


def build_kitchen_ticket(order: Dict[str, Any]) -> bytes:
    out = bytearray()
    out += INIT
    out += ALIGN_CENTER
    out += BOLD_ON
    out += _line("=" * WIDTH)
    out += _line("BURGER TIMES")
    out += _line("=" * WIDTH)
    out += BOLD_OFF
    out += _line()

    out += DOUBLE_SIZE_ON + BOLD_ON
    out += _line(_ascii(f"COMMANDE #{order.get('order_number', '')}"))
    out += DOUBLE_SIZE_OFF + BOLD_OFF

    fulfillment = order.get("fulfillment")
    out += BOLD_ON
    out += _line(FULFILLMENT_LABEL.get(fulfillment, "SUR PLACE"))
    out += BOLD_OFF
    out += _line()

    out += ALIGN_LEFT
    local_dt = _local_dt(order.get("created_at", ""))
    if local_dt:
        out += _line(_split_row(local_dt.strftime("%d/%m/%Y"), local_dt.strftime("%H:%M")))
    out += _line("-" * WIDTH)

    for item in order.get("items") or []:
        qty = item.get("quantity", 1)
        name = _ascii(item.get("name", "")).upper()
        out += BOLD_ON
        out += _line(f"{qty}x {name}")
        out += BOLD_OFF

        burger_cfg = item.get("burger_config") or {}
        for group_key in ("meats", "cheeses", "supplements"):
            for entry in burger_cfg.get(group_key) or []:
                out += _line(f"   + {_ascii(entry.get('name', ''))}")
        if item.get("selected_format"):
            out += _line(f"   {_ascii(item['selected_format'])}")
        if item.get("formula") == "menu" and item.get("included_drink"):
            out += _line(f"   {_ascii(item['included_drink'])}")
        for sauce in item.get("sauces") or []:
            out += _line(f"   + {_ascii(sauce)}")
        if item.get("notes"):
            out += BOLD_ON
            out += _line(f"   {_ascii(item['notes']).upper()}")
            out += BOLD_OFF
        out += _line("-" * WIDTH)

    if order.get("notes"):
        out += _line()
        out += BOLD_ON
        out += _line("NOTE CLIENT:")
        out += _line(_ascii(order["notes"]).upper())
        out += BOLD_OFF
        out += _line()

    out += _line("=" * WIDTH)
    total_str = f"{order.get('total', 0):.2f} EUR".replace(".", ",")
    out += BOLD_ON
    out += _line(_split_row("TOTAL:", total_str))
    out += BOLD_OFF
    out += _line("=" * WIDTH)
    out += _line()

    customer_name = f"{order.get('customer_first_name', '')} {order.get('customer_last_name', '')}".strip()
    if fulfillment == "delivery":
        out += BOLD_ON
        out += _line("LIVRAISON")
        out += BOLD_OFF
        if customer_name:
            out += _line(f"Client: {_ascii(customer_name)}")
        if order.get("customer_phone"):
            out += _line(f"Tel: {order['customer_phone']}")
        addr_lines = [order.get("address_line1"), order.get("address_line2")]
        loc = " ".join(x for x in [order.get("postal_code"), order.get("city")] if x)
        if loc:
            addr_lines.append(loc)
        addr_lines = [a for a in addr_lines if a]
        if addr_lines:
            out += _line("Adresse:")
            for line in addr_lines:
                out += _line(_ascii(line))
    else:
        out += BOLD_ON
        out += _line(FULFILLMENT_LABEL.get(fulfillment, "SUR PLACE"))
        out += BOLD_OFF
        if customer_name:
            out += _line(f"Client: {_ascii(customer_name)}")
        if order.get("customer_phone"):
            out += _line(f"Tel: {order['customer_phone']}")
        if order.get("pickup_code"):
            out += _line(f"Code retrait: {order['pickup_code']}")

    out += _line()
    out += _line(f"Paiement: {PAYMENT_LABEL.get(order.get('payment_method'), order.get('payment_method') or '')}")

    decided_local = _local_dt(order.get("kitchen_decision_at") or "")
    if decided_local and order.get("kitchen_decision") == "accepted":
        out += _line(f"ACCEPTEE A {decided_local.strftime('%H:%M')}")

    out += FEED_CUT
    return bytes(out)
