"""
Raspberry Pi print-bridge for Burger Times' /kitchen tablet.

Receives the full order JSON via POST /print (pushed by the main backend's
printer_bridge.send_print_job() the instant a kitchen order is accepted,
or manually re-triggered via /reprint), formats it into ONE ESC/POS 80mm
ticket, and sends it N times (per the "print_copies" field in the request
body — 3 on accept, 1 on reprint) over a plain TCP socket to the Sunmi
NT311 thermal printer's "raw print" port — 9100 is the de facto standard
raw-print port on network ESC/POS printers.

Run this ON the Raspberry Pi (not in the cloud):
    pip install -r requirements.txt
    python server.py

Then point your tunnel (ngrok, Cloudflare Tunnel, etc.) at this script's
port (5000 by default) and set that public URL + "/print" as
KITCHEN_PRINTER_WEBHOOK_URL in the main app's backend/.env.
"""
from __future__ import annotations

import logging
import os
import socket
import textwrap
import time
from datetime import datetime

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("print_bridge")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config — all from environment variables, sane defaults for this printer.
# ---------------------------------------------------------------------------
PRINTER_IP = os.environ.get("PRINTER_IP", "192.168.1.26")
PRINTER_PORT = int(os.environ.get("PRINTER_PORT", "9100"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "5000"))
# Optional shared secret: if set, /print requires header X-Print-Secret to
# match, so a stranger who stumbles on your public ngrok URL can't spam
# your kitchen printer. Leave unset while you're just getting this running;
# set it (and ask me to add the matching header on the backend side) once
# you're ready to lock it down.
PRINT_BRIDGE_SECRET = os.environ.get("PRINT_BRIDGE_SECRET", "")

# ---------------------------------------------------------------------------
# ESC/POS raw command bytes
# ---------------------------------------------------------------------------
ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"\x40"  # ESC @ — reset printer state
ALIGN_LEFT = ESC + b"\x61\x00"
ALIGN_CENTER = ESC + b"\x61\x01"
BOLD_ON = ESC + b"\x45\x01"
BOLD_OFF = ESC + b"\x45\x00"
SIZE_NORMAL = GS + b"\x21\x00"
SIZE_TALL = GS + b"\x21\x01"  # double height, same width — bigger text without shrinking chars-per-line
SIZE_DOUBLE = GS + b"\x21\x11"  # double width + double height
SIZE_KITCHEN = GS + b"\x21\x11"  # biggest readable size for kitchen instructions
# Character code table — 16 selects a Latin/Western-European table (often
# labelled "WPC1252") on most Epson-compatible ESC/POS printers, needed for
# proper é/è/à/ç rendering. If accents print as garbage, try 0 (CP437) or
# check the Sunmi NT311's command reference for the right table number.
SELECT_CODEPAGE = ESC + b"\x74\x10"
CUT = GS + b"\x56\x00"  # full cut
FEED_LINES = b"\n" * 6

ENCODING = "cp1252"  # matches SELECT_CODEPAGE above


def _text(s: str) -> bytes:
    """Encode for the printer's selected code table; never crash on a
    stray character (emoji etc.) — swap it for '?' instead."""
    return (s or "").encode(ENCODING, errors="replace")


def _line(s: str = "") -> bytes:
    return _text(s) + b"\n"


# Chars-per-line for double-height (SIZE_TALL) body text. ESC/POS's GS !
# command only doubles HEIGHT here (not width), so this matches the same
# ~32-char width as the normal-size divider/header lines. We still
# pre-wrap ourselves with textwrap instead of the printer's own hard
# character-count auto-wrap, because that cuts mid-word for any line
# longer than the limit (which is what caused the original bug — not
# double-height secretly widening characters, just plain hard-wrap on a
# long line, e.g. "...(Viande Hach" / "ee, Kebab)").
TALL_LINE_WIDTH = 32
KITCHEN_LINE_WIDTH = 16


def _tall(text: str = "", indent: str = "") -> bytes:
    """Emit `text` as one or more double-height lines, wrapped at word
    boundaries ourselves rather than left to the printer's own hard-wrap."""
    out = b""
    for w in (textwrap.wrap(text, width=TALL_LINE_WIDTH, subsequent_indent=indent) or [""]):
        out += _line(w)
    return out


def _kitchen(text: str = "", indent: str = "") -> bytes:
    """Emit double-width kitchen text while wrapping at word boundaries."""
    out = b""
    for word_line in (
        textwrap.wrap(text, width=KITCHEN_LINE_WIDTH, subsequent_indent=indent) or [""]
    ):
        out += _line(word_line)
    return out


# ---------------------------------------------------------------------------
# Ticket content — one combined ticket (items, total, customer, payment)
# printed as many times as "print_copies" asks for.
# ---------------------------------------------------------------------------
FULFILLMENT_LABEL = {"pickup": "A EMPORTER", "delivery": "LIVRAISON", "dine_in": "SUR PLACE"}
PAYMENT_LABEL = {"cash": "Especes sur place", "card_in_person": "Carte sur place"}
DIVIDER = "-" * 46
NORMAL_LINE_WIDTH = 46

# ===========================================================================
# >>>>>  ITEM TEXT SIZE — PICK YOUR LEVEL HERE  (1 = smallest ... 10 = biggest)
# ===========================================================================
# This controls how BIG the item lines (item name, sauces, supplements,
# removals, notes) are printed on the kitchen ticket.
#
# HOW TO FIND YOUR PERFECT SIZE:
#   1. Change the number below to any value from 1 to 10.
#   2. Save this file.
#   3. On the Raspberry Pi, restart the bridge:  python server.py
#   4. Print (or reprint) a ticket and look at it.
#   5. Repeat with a different number until it looks right.
#
ITEM_SIZE_LEVEL = 3   # <---- CHANGE THIS NUMBER (1 to 10)
#
# What each level looks like  (width x height, ESC/POS max is 8 x 8):
#   Level 1  = 1x1   normal size
#   Level 2  = 1x2   a bit taller
#   Level 3  = 2x2   double size   (this was the old default)
#   Level 4  = 2x3
#   Level 5  = 3x3
#   Level 6  = 3x4
#   Level 7  = 4x4
#   Level 8  = 5x5
#   Level 9  = 6x6
#   Level 10 = 8x8   maximum / huge
# ===========================================================================
SIZE_LEVELS = {
    1:  (1, 1),
    2:  (1, 2),
    3:  (2, 2),
    4:  (2, 3),
    5:  (3, 3),
    6:  (3, 4),
    7:  (4, 4),
    8:  (5, 5),
    9:  (6, 6),
    10: (8, 8),
}


def _size_byte(width_mult: int, height_mult: int) -> bytes:
    """Build the ESC/POS 'GS !' size byte from width/height multipliers (1-8)."""
    w = max(1, min(8, width_mult)) - 1
    h = max(1, min(8, height_mult)) - 1
    return GS + b"\x21" + bytes([(w << 4) | h])


# Derived from the level you picked above — do not edit these two lines.
_ITEM_W, _ITEM_H = SIZE_LEVELS.get(ITEM_SIZE_LEVEL, SIZE_LEVELS[3])
ITEM_SIZE_BYTE = _size_byte(_ITEM_W, _ITEM_H)
# Wider text = fewer characters per line (an 80mm roll fits ~46 normal chars),
# so we auto-shrink the wrap width to stop long names being cut mid-word.
BIG_LINE_WIDTH = max(6, 46 // _ITEM_W)


def _fmt_datetime(iso_str: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat((iso_str or "").replace("Z", "+00:00"))
        local = dt.astimezone()  # converts to the Pi's local system timezone
        return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return "", ""


def _wrapped(text: str = "", indent: str = "  ") -> bytes:
    """Emit `text` as normal-size line(s), wrapped at word boundaries at
    NORMAL_LINE_WIDTH so nothing is cut mid-word on the narrow roll."""
    out = b""
    for w in (textwrap.wrap(text, width=NORMAL_LINE_WIDTH, subsequent_indent=indent) or [""]):
        out += _line(w)
    return out


def _wrapped_big(text: str = "") -> bytes:
    """Wrap for the big double-size kitchen font (~22 cols on an 80mm roll)."""
    out = b""
    for w in (textwrap.wrap(text, width=BIG_LINE_WIDTH) or [""]):
        out += _line(w)
    return out


def _legacy_item_line(item: dict) -> str:
    """Fallback compact line for orders created before ticket_line existed."""
    cfg = item.get("burger_config") or {}
    meats = [x.get("name", x) if isinstance(x, dict) else x for x in cfg.get("meats") or []]
    line = f"{item.get('quantity', 1)}x {item.get('name', '')}"
    parts = list(meats)
    if cfg.get("sauce_fromagere") is False:
        parts.append("sans from")
    if parts:
        line += f" ({', '.join(parts)})"
    for group in ("cheeses", "supplements"):
        for x in cfg.get(group) or []:
            line += f" +{x.get('name', x) if isinstance(x, dict) else x}"
    for s in item.get("sauces") or []:
        line += f" +{s}"
    if item.get("included_drink"):
        line += f" - {item['included_drink']}"
    return line


def build_escpos_ticket(order: dict) -> bytes:
    date_str, time_str = _fmt_datetime(order.get("created_at", ""))
    first = order.get("customer_first_name") or ""
    last = order.get("customer_last_name") or ""
    customer_name = f"{first} {last}".strip()
    fulfillment = order.get("fulfillment", "pickup")
    fulfillment_label = FULFILLMENT_LABEL.get(fulfillment, "SUR PLACE")

    out = bytearray()
    out += INIT
    out += SELECT_CODEPAGE

    # Fulfillment mode banner at the very top (bold, tall).
    out += ALIGN_CENTER + BOLD_ON + SIZE_TALL
    out += _line(fulfillment_label)
    out += SIZE_DOUBLE
    out += _line("BURGER TIMES")
    out += SIZE_NORMAL
    out += _line(DIVIDER)
    out += _line(f"COMMANDE #{order.get('order_number', '')}")
    out += BOLD_OFF
    out += _line(f"{date_str} {time_str}")
    out += _line(DIVIDER)

    # Two-tier item blocks: header LEFT (with [drink]), modifiers CENTERED.
    # Item text size comes from ITEM_SIZE_LEVEL you set at the top of this file.
    out += BOLD_ON + ITEM_SIZE_BYTE
    for item in order.get("items") or []:
        header = item.get("ticket_header") or item.get("ticket_line") or _legacy_item_line(item)
        mods = item.get("ticket_mods") or []
        out += ALIGN_LEFT
        out += _wrapped_big(header)
        if mods:
            out += ALIGN_CENTER
            for m in mods:
                out += _wrapped_big(m)
        if item.get("notes"):
            out += ALIGN_CENTER
            out += _wrapped_big(f"Note: {item['notes']}")
        out += _line("")
    if order.get("notes"):
        out += ALIGN_LEFT
        out += _wrapped_big(f"Note: {order['notes']}")
    out += BOLD_OFF + SIZE_NORMAL
    out += ALIGN_LEFT
    out += _line(DIVIDER)

    total = order.get("total") or 0
    out += BOLD_ON + SIZE_TALL
    out += _line(f"TOTAL : {total:.2f} EUR".replace(".", ","))
    out += BOLD_OFF + SIZE_NORMAL
    out += _line(DIVIDER)

    if customer_name:
        out += _line(f"Client : {customer_name}")
    if order.get("customer_phone"):
        out += _line(f"Tel : {order['customer_phone']}")
    if fulfillment == "delivery":
        _, slot_start = _fmt_datetime(order.get("scheduled_delivery_start", ""))
        if slot_start:
            out += _line(f"Creneau livraison : {slot_start}")
        addr = ", ".join(filter(None, [order.get("address_line1"), order.get("address_line2")]))
        if addr:
            out += _line(addr)
        city_line = f"{order.get('postal_code', '')} {order.get('city', '')}".strip()
        if city_line:
            out += _line(city_line)
    if order.get("pickup_code"):
        out += _line(f"Code retrait : {order['pickup_code']}")
    out += _line(
        f"Paiement : {PAYMENT_LABEL.get(order.get('payment_method'), order.get('payment_method', ''))}"
    )

    out += SIZE_NORMAL
    out += FEED_LINES
    out += CUT
    return bytes(out)


# ---------------------------------------------------------------------------
# Printer transport — raw "JetDirect-style" TCP socket.
# ---------------------------------------------------------------------------
def send_to_printer(ticket_bytes: bytes) -> None:
    with socket.create_connection((PRINTER_IP, PRINTER_PORT), timeout=5) as sock:
        sock.sendall(ticket_bytes)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "printer_ip": PRINTER_IP, "printer_port": PRINTER_PORT})


@app.route("/print", methods=["POST"])
def print_order():
    if PRINT_BRIDGE_SECRET:
        if request.headers.get("X-Print-Secret") != PRINT_BRIDGE_SECRET:
            logger.warning("Rejected /print: bad or missing X-Print-Secret header")
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    order = request.get_json(silent=True)
    if not order:
        return jsonify({"ok": False, "error": "no JSON body"}), 400

    order_number = order.get("order_number", "?")
    # Backend sends 3 on normal kitchen accept, 2 on tablet confirmation,
    # and 1 on manual reprint. Defaults to 1 if the field is missing.
    copies = max(1, int(order.get("print_copies", 1) or 1))
    logger.info("Printing order #%s (%d copies)", order_number, copies)
    try:
        ticket = build_escpos_ticket(order)
        for i in range(copies):
            send_to_printer(ticket)
            if i < copies - 1:
                # Small pause between copies so the cutter finishes cleanly
                # before the next job lands.
                time.sleep(0.5)
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        logger.exception("Printer unreachable")
        return jsonify({"ok": False, "error": f"printer unreachable: {e}"}), 502
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to build/send ticket")
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "order_number": order_number, "copies_printed": copies})


if __name__ == "__main__":
    logger.info(
        "Print bridge listening on 0.0.0.0:%s -> printer %s:%s",
        LISTEN_PORT,
        PRINTER_IP,
        PRINTER_PORT,
    )
    app.run(host="0.0.0.0", port=LISTEN_PORT)
