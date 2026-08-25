"""ESC/POS ticket builders for the SUNMI 80mm kitchen printer.

Only the fixed admin "Test Kitchen Printer" ticket lives here for now — real
order tickets are a separate, not-yet-enabled phase (see server.py TODO near
the checkout flow before wiring automatic printing).
"""
from __future__ import annotations

from datetime import datetime

ESC = b"\x1b"
GS = b"\x1d"

INIT = ESC + b"\x40"
ALIGN_CENTER = ESC + b"\x61\x01"
ALIGN_LEFT = ESC + b"\x61\x00"
BOLD_ON = ESC + b"\x45\x01"
BOLD_OFF = ESC + b"\x45\x00"
DOUBLE_SIZE_ON = GS + b"\x21\x11"
DOUBLE_SIZE_OFF = GS + b"\x21\x00"
FEED_CUT = b"\n\n" + GS + b"\x56\x00"


def _line(text: str) -> bytes:
    return text.encode("ascii", errors="replace") + b"\n"


def build_test_ticket() -> bytes:
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M:%S")

    out = bytearray()
    out += INIT
    out += ALIGN_CENTER
    out += BOLD_ON + DOUBLE_SIZE_ON
    out += _line("BURGER TIMES")
    out += DOUBLE_SIZE_OFF + BOLD_OFF
    out += b"\n"
    out += BOLD_ON
    out += _line("TEST IMPRESSION")
    out += BOLD_OFF
    out += b"\n"
    out += _line("Imprimante connectee avec succes")
    out += b"\n"
    out += ALIGN_LEFT
    out += _line(f"Date: {date_str}")
    out += _line(f"Heure: {time_str}")
    out += FEED_CUT
    return bytes(out)


def to_hex(data: bytes) -> str:
    return data.hex()
