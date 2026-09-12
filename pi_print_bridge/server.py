"""
Raspberry Pi print-bridge for Burger Times' /kitchen tablet.

Receives the full order JSON via POST /print (pushed by the main backend's
printer_bridge.send_print_job() the instant a kitchen order is accepted),
formats it into TWO separate ESC/POS 80mm tickets — one KITCHEN copy (what
to cook) and one DELIVERY/CUSTOMER copy (who it's for + payment) — and
sends both, one after another, over a plain TCP socket to the Sunmi NT311
thermal printer's "raw print" port — 9100 is the de facto standard
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
SIZE_DOUBLE = GS + b"\x21\x11"  # double width + double height
# Character code table — 16 selects a Latin/Western-European table (often
# labelled "WPC1252") on most Epson-compatible ESC/POS printers, needed for
# proper é/è/à/ç rendering. If accents print as garbage, try 0 (CP437) or
# check the Sunmi NT311's command reference for the right table number.
SELECT_CODEPAGE = ESC + b"\x74\x10"
CUT = GS + b"\x56\x00"  # full cut
FEED_LINES = b"\n" * 4

ENCODING = "cp1252"  # matches SELECT_CODEPAGE above


def _text(s: str) -> bytes:
    """Encode for the printer's selected code table; never crash on a
    stray character (emoji etc.) — swap it for '?' instead."""
    return (s or "").encode(ENCODING, errors="replace")


def _line(s: str = "") -> bytes:
    return _text(s) + b"\n"


# ---------------------------------------------------------------------------
# Shared ticket bits
# ---------------------------------------------------------------------------
FULFILLMENT_LABEL = {"pickup": "A EMPORTER", "delivery": "LIVRAISON"}
PAYMENT_LABEL = {"cash": "Especes sur place", "card_in_person": "Carte sur place"}
DIVIDER = "-" * 32


def _fmt_datetime(iso_str: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat((iso_str or "").replace("Z", "+00:00"))
        local = dt.astimezone()  # converts to the Pi's local system timezone
        return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return "", ""


def _item_lines(item: dict) -> list:
    rows = [f"{item.get('quantity', 1)}x {item.get('name', '')}"]
    cfg = item.get("burger_config") or {}
    size = cfg.get("size") or {}
    if size.get("label"):
        rows.append(f"  Taille : {size['label']}")
    for m in cfg.get("meats") or []:
        rows.append(f"  + {m.get('name', m) if isinstance(m, dict) else m}")
    for c in cfg.get("cheeses") or []:
        rows.append(f"  + {c.get('name', c) if isinstance(c, dict) else c}")
    for s in cfg.get("supplements") or []:
        rows.append(f"  + {s.get('name', s) if isinstance(s, dict) else s}")
    if item.get("formula") == "menu" and item.get("included_drink"):
        rows.append(f"  Boisson : {item['included_drink']}")
    for s in item.get("sauces") or []:
        rows.append(f"  + {s}")
    if item.get("notes"):
        rows.append(f"  Note : {item['notes']}")
    return rows


def _header(out: bytearray, title: str, order: dict) -> None:
    date_str, time_str = _fmt_datetime(order.get("created_at", ""))
    fulfillment_label = FULFILLMENT_LABEL.get(order.get("fulfillment", "pickup"), "SUR PLACE")
    out += INIT
    out += SELECT_CODEPAGE
    out += ALIGN_CENTER + BOLD_ON + SIZE_DOUBLE
    out += _line(title)
    out += SIZE_NORMAL
    out += _line(DIVIDER)
    out += _line(f"COMMANDE #{order.get('order_number', '')}")
    out += BOLD_OFF
    out += _line(fulfillment_label)
    out += _line(f"{date_str} {time_str}")
    out += _line(DIVIDER)
    out += ALIGN_LEFT


# ---------------------------------------------------------------------------
# Ticket 1 — KITCHEN copy: what to cook. No payment/address clutter, just
# the items and any prep notes, so the line cook can act on it fast.
# ---------------------------------------------------------------------------
def build_kitchen_ticket(order: dict) -> bytes:
    out = bytearray()
    _header(out, "CUISINE", order)

    for item in order.get("items") or []:
        for row in _item_lines(item):
            out += _line(row)
        out += _line("")
    out += _line(DIVIDER)

    first = order.get("customer_first_name") or ""
    if first:
        out += BOLD_ON
        out += _line(f"Client : {first}")
        out += BOLD_OFF

    out += FEED_LINES
    out += CUT
    return bytes(out)


# ---------------------------------------------------------------------------
# Ticket 2 — DELIVERY / CUSTOMER copy: who it's for, where it goes, what
# they paid. Goes with the bag / to the customer, kept out of the cook's way.
# ---------------------------------------------------------------------------
def build_delivery_ticket(order: dict) -> bytes:
    first = order.get("customer_first_name") or ""
    last = order.get("customer_last_name") or ""
    customer_name = f"{first} {last}".strip()
    fulfillment = order.get("fulfillment", "pickup")

    out = bytearray()
    _header(out, "LIVRAISON" if fulfillment == "delivery" else "RECU CLIENT", order)

    for item in order.get("items") or []:
        for row in _item_lines(item):
            out += _line(row)
    out += _line(DIVIDER)

    total = order.get("total") or 0
    out += BOLD_ON
    out += _line(f"TOTAL : {total:.2f} EUR".replace(".", ","))
    out += BOLD_OFF
    out += _line(DIVIDER)

    if customer_name:
        out += _line(f"Client : {customer_name}")
    if order.get("customer_phone"):
        out += _line(f"Tel : {order['customer_phone']}")
    if fulfillment == "delivery":
        addr = ", ".join(filter(None, [order.get("address_line1"), order.get("address_line2")]))
        if addr:
            out += _line(addr)
        city_line = f"{order.get('postal_code', '')} {order.get('city', '')}".strip()
        if city_line:
            out += _line(city_line)
    if order.get("pickup_code"):
        out += BOLD_ON
        out += _line(f"Code retrait : {order['pickup_code']}")
        out += BOLD_OFF
    out += _line(
        f"Paiement : {PAYMENT_LABEL.get(order.get('payment_method'), order.get('payment_method', ''))}"
    )

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
    logger.info("Printing order #%s (kitchen + delivery copies)", order_number)
    try:
        send_to_printer(build_kitchen_ticket(order))
        # Small pause so the printer's own buffer/cutter finishes the first
        # ticket cleanly before the second job lands — cheap ESC/POS heads
        # can otherwise interleave/garble back-to-back raw sends.
        time.sleep(0.5)
        send_to_printer(build_delivery_ticket(order))
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        logger.exception("Printer unreachable")
        return jsonify({"ok": False, "error": f"printer unreachable: {e}"}), 502
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to build/send ticket(s)")
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "order_number": order_number, "tickets_printed": 2})


if __name__ == "__main__":
    logger.info(
        "Print bridge listening on 0.0.0.0:%s -> printer %s:%s",
        LISTEN_PORT,
        PRINTER_IP,
        PRINTER_PORT,
    )
    app.run(host="0.0.0.0", port=LISTEN_PORT)
