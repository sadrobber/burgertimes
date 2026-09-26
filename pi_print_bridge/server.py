from __future__ import annotations

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

import logging
import os
import re
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

# Dots-per-mm for the "feed n dots" command below — standard for 80mm
# thermal printers (203 dpi, Sunmi NT311 included): 203 / 25.4 ≈ 8 dots/mm.
DOTS_PER_MM = 8


def _feed_gap(mm: int) -> bytes:
    """Blank vertical space of `mm` millimetres (ESC J — print & feed n
    dots; no text lines involved, just paper). ESC J's dot count is a
    single byte (0-255), so a big gap is split across several commands."""
    dots = round(mm * DOTS_PER_MM)
    out = b""
    while dots > 0:
        step = min(dots, 255)
        out += ESC + b"\x4a" + bytes([step])
        dots -= step
    return out

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
KIDS_MARKER = "c"  # matches the backend's default kids_code (order_service.py)
CLIENT_GAP_MM = 50  # blank gap between the order/total and the client info block

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
ITEM_SIZE_LEVEL = 2  # <---- CHANGE THIS NUMBER (1 to 10)
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


# ---------------------------------------------------------------------------
# Fulfillment banner with icon — "SUR PLACE" centred, icon on the far right
# of the same line. A thermal printer can't mix its own font and a picture
# on one line, so the whole banner line is drawn as one small black & white
# image (Pillow) and sent with the standard ESC/POS raster command GS v 0.
# If Pillow isn't installed, or BANNER_ICONS is False, the old text-only
# banner is printed instead.
# ---------------------------------------------------------------------------
BANNER_ICONS = True          # set to False to go back to the text-only banner
BANNER_WIDTH_PX = 552        # 46 chars x 12 dots = same width as the text lines
BANNER_HEIGHT_PX = 56
BANNER_FONT_PX = 34
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Raspberry Pi OS default
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None
    logger.warning("Pillow not installed: banner icons disabled (pip install pillow)")


def _banner_font(px: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    try:
        return ImageFont.load_default(size=px)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _draw_icon(d, kind: str, x: int, y: int, w: int, h: int) -> None:
    """Simple solid pictograms that print cleanly on thermal paper."""
    X = lambda f: x + int(f * w)  # noqa: E731
    Y = lambda f: y + int(f * h)  # noqa: E731
    lw = max(3, h // 12)
    if kind == "dine_in":  # down arrow
        d.rectangle([X(0.40), Y(0.0), X(0.60), Y(0.52)], fill=0)
        d.polygon([(X(0.18), Y(0.45)), (X(0.82), Y(0.45)), (X(0.50), Y(1.0))], fill=0)
    elif kind == "pickup":  # take-away bag
        d.arc([X(0.30), Y(0.0), X(0.70), Y(0.50)], 180, 360, fill=0, width=lw)
        d.polygon([(X(0.12), Y(0.25)), (X(0.88), Y(0.25)), (X(0.95), Y(1.0)), (X(0.05), Y(1.0))], fill=0)
        d.line([(X(0.30), Y(0.25)), (X(0.30), Y(0.36))], fill=255, width=lw)
        d.line([(X(0.70), Y(0.25)), (X(0.70), Y(0.36))], fill=255, width=lw)
    # "delivery" is drawn separately by _scooter_icon() (see below).


# Scooter silhouette traced from the reference image (coords in a 910x550 box)
_SCOOTER_BODY = [
    (2, 383), (90, 253), (68, 200), (80, 170), (130, 167), (150, 145),
    (360, 167), (455, 170), (480, 195), (485, 245), (445, 303), (490, 375),
    (580, 387), (620, 345), (640, 265), (620, 185), (540, 70), (550, 35),
    (595, 3), (665, 55), (650, 90), (700, 115), (780, 175), (815, 225),
    (810, 250), (780, 270), (860, 283), (908, 327), (840, 337), (740, 355),
    (725, 350), (660, 435), (520, 457), (120, 445), (80, 405), (90, 365),
    (175, 353), (198, 295), (135, 260),
]
_SCOOTER_WHEELS = [(155, 440), (820, 443)]  # centres
_SCOOTER_BOX = (910, 550)


def _smooth(pts, rounds=2):
    """Chaikin corner-cutting: rounds off the polygon's corners so the
    silhouette looks drawn rather than faceted."""
    for _ in range(rounds):
        out = []
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1),
                    (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        pts = out
    return pts


def _scooter_icon(w: int, h: int):
    """Scooter pictogram rendered 4x oversize then shrunk, so the curves come
    out smooth on thermal paper. Returns an 'L' image of size (w, h)."""
    ss = 4
    bw, bh = _SCOOTER_BOX
    s = min(w / bw, h / bh) * ss
    ox = (w * ss - bw * s) / 2
    oy = (h * ss - bh * s) / 2
    P = lambda px, py: (ox + px * s, oy + py * s)  # noqa: E731
    big = Image.new("L", (w * ss, h * ss), 255)
    d = ImageDraw.Draw(big)
    ro, ri = 108 * s, 58 * s  # thick tyres so they survive thermal printing
    for cx, cy in _SCOOTER_WHEELS:
        x, y = P(cx, cy)
        d.ellipse([x - ro, y - ro, x + ro, y + ro], fill=0)
        d.ellipse([x - ri, y - ri, x + ri, y + ri], fill=255)
    body = [P(*p) for p in _smooth(_SCOOTER_BODY)]
    # thin white gap where the body overlaps the rear wheel, like the reference
    d.line(body + body[:1], fill=255, width=max(2, int(14 * s)), joint="curve")
    d.polygon(body, fill=0)
    # front fork
    d.line([P(775, 385), P(812, 450)], fill=0, width=int(34 * s))
    return big.resize((w, h), Image.LANCZOS)


def _banner_image(fulfillment: str, label: str):
    img = Image.new("L", (BANNER_WIDTH_PX, BANNER_HEIGHT_PX), 255)
    d = ImageDraw.Draw(img)
    font = _banner_font(BANNER_FONT_PX)
    left, top, right, bottom = d.textbbox((0, 0), label, font=font)
    tx = (BANNER_WIDTH_PX - (right - left)) // 2 - left
    ty = (BANNER_HEIGHT_PX - (bottom - top)) // 2 - top
    d.text((tx, ty), label, font=font, fill=0)
    ih = BANNER_HEIGHT_PX - 8
    if fulfillment == "delivery":
        iw = int(ih * 1.65)  # scooter is wider than the other icons
        img.paste(_scooter_icon(iw, ih), (BANNER_WIDTH_PX - iw - 4, 4))
    else:
        iw = int(ih * 1.25)
        _draw_icon(d, fulfillment, BANNER_WIDTH_PX - iw - 4, 4, iw, ih)
    return img


def _raster(img) -> bytes:
    """ESC/POS 'GS v 0' raster bit image (1 bit = black dot)."""
    bw = img.point(lambda p: 255 if p < 128 else 0, mode="1")
    width_bytes = (img.width + 7) // 8
    return (GS + b"v0\x00"
            + bytes([width_bytes & 0xFF, width_bytes >> 8, img.height & 0xFF, img.height >> 8])
            + bw.tobytes())


_BANNER_CACHE: dict[str, bytes] = {}


def _banner_bytes(fulfillment: str, label: str) -> bytes | None:
    """Raster banner for this fulfillment mode, or None to use the text banner."""
    if not BANNER_ICONS or Image is None:
        return None
    if fulfillment not in _BANNER_CACHE:
        try:
            _BANNER_CACHE[fulfillment] = _raster(_banner_image(fulfillment, label))
        except Exception:  # noqa: BLE001 — never block a print because of the icon
            logger.exception("Banner icon rendering failed, falling back to text")
            return None
    return _BANNER_CACHE[fulfillment]


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


def _wrapped_big_right(text: str = "") -> bytes:
    """Like _wrapped_big, but each line is right-justified to BIG_LINE_WIDTH
    instead of left-aligned — used for the fries sauce, so it sits directly
    under the item's bracketed drink on the right rather than centered."""
    out = b""
    for w in (textwrap.wrap(text, width=BIG_LINE_WIDTH) or [""]):
        out += _line(w.rjust(BIG_LINE_WIDTH))
    return out


def _header_line(header: str, suffix: str = "") -> bytes:
    """Print the item's first line with any trailing bracketed drink (e.g.
    "[Coca]") pushed to the far RIGHT of the line, and — if given — a
    right-aligned suffix (the kids marker, e.g. "+c") glued right before it
    on the same right-hand block ("+c [Coca]"). If there's no room to fit
    name + right block on one line, the right block drops to its own
    right-justified line (kept together, never split from each other)."""
    match = re.search(r"\s*(\[[^\]]*\])\s*$", header)
    drink = match.group(1) if match else ""
    name = header[: match.start()].rstrip() if match else header.rstrip()
    right = " ".join(x for x in (suffix, drink) if x)
    if not right:
        return _wrapped_big(name)
    gap = BIG_LINE_WIDTH - len(name) - len(right)
    if gap >= 1:
        return _line(name + (" " * gap) + right)
    out = _wrapped_big(name)
    out += _line(right.rjust(BIG_LINE_WIDTH))
    return out


# ---------------------------------------------------------------------------
# Meat column — "1 Menu Tacos 1 T 1 K 1 P [Cherry]" is printed as
#   "1 Menu Tacos 3                [Cherry]"
# followed by the meat letters stacked in their own column under the count,
# with the sauces/supplements still centred beside them.
# ---------------------------------------------------------------------------
# How many characters to push BOTH the meat column and the modifiers to the
# right. 0 = old position; raise it to move them further right.
MEAT_COLUMN_SHIFT = 4

_DRINK_RE = re.compile(r"\s*(\[[^\]]*\])\s*$")
# A trailing run of "<qty> <LETTER(S)>" pairs at the end of the item name.
_MEAT_RUN_RE = re.compile(r"((?:\s+\d+\s*[A-Z]{1,2})+)\s*$")
_MEAT_PAIR_RE = re.compile(r"(\d+)\s*([A-Z]{1,2})")


def _split_meats(header: str) -> tuple[str, str, list[tuple[int, str]]]:
    """'1 Menu Tacos 1 T 1 K 1 P [Cherry]' -> ('1 Menu Tacos', '[Cherry]',
    [(1, 'T'), (1, 'K'), (1, 'P')]). Returns an empty meat list when the
    header has no trailing meat codes (burgers, drinks, desserts...)."""
    drink = ""
    body = header.rstrip()
    m = _DRINK_RE.search(body)
    if m:
        drink = m.group(1)
        body = body[: m.start()].rstrip()
    run = _MEAT_RUN_RE.search(body)
    if not run:
        return body, drink, []
    name = body[: run.start()].rstrip()
    if not name:  # the whole header was codes — don't touch it
        return body, drink, []
    meats = [(int(q), code) for q, code in _MEAT_PAIR_RE.findall(run.group(1))]
    return name, drink, meats


def _meats_from_field(raw) -> list[tuple[int, str]]:
    """Read the structured "ticket_meats" field sent by the backend:
        [{"qty": 1, "code": "T"}, {"qty": 2, "code": "K"}]
    Plain strings ("T") are accepted too and count as qty 1."""
    meats: list[tuple[int, str]] = []
    for m in raw or []:
        if isinstance(m, dict):
            code = str(m.get("code") or "").strip()
            try:
                qty = int(m.get("qty") or m.get("quantity") or 1)
            except (TypeError, ValueError):
                qty = 1
        else:
            code, qty = str(m).strip(), 1
        if code:
            meats.append((max(1, qty), code))
    return meats


# Leading quantity in any format the backend may send: "1 ", "1x ", "1 x ", "x1 ".
_QTY_RE = re.compile(r"^\s*(?:[xX×]\s*(\d+)|(\d+)\s*[xX×]?)\s+")
# Quantity inside the bracketed drink: "[x1 Cherry]", "[1x Cherry]", "[1 x Cherry]".
_DRINK_QTY_RE = re.compile(r"\[\s*(?:[xX×]\s*(\d+)|(\d+)\s*[xX×])\s*([^\]]*?)\s*\]")


def _with_qty_x(header: str) -> str:
    """Normalise the item header to '1 x Menu Tacos ... [Cherry]'.
    - Leading qty '1', '1x', '1 x' or 'x1' always becomes '1 x '.
    - A drink qty of 1 is dropped ('[x1 Cherry]' -> '[Cherry]'); a bigger
      one is kept in the same style ('[x2 Coca]' -> '[2 x Coca]').
    Never doubles an existing 'x', and leaves names like '1 Xtra Burger' intact."""
    header = _QTY_RE.sub(lambda m: f"{m.group(1) or m.group(2)} x ", header, count=1)

    def _drink(m: re.Match) -> str:
        qty, name = int(m.group(1) or m.group(2)), m.group(3)
        return f"[{name}]" if qty == 1 else f"[{qty} x {name}]"

    return _DRINK_QTY_RE.sub(_drink, header)


def _resolve_item_meats(item: dict, header: str) -> tuple[str, str, list[tuple[int, str]]]:
    """Return (name, drink, meats) for one item.

    - If the backend sent "ticket_meats" (even an empty list), that field is
      the ONLY source of truth: nothing is guessed from the header text, so
      a product name like "Menu 2 XL" can never be mistaken for meats.
      If the header still carries the same codes at the end, they are
      removed so they don't print twice.
    - If the field is missing (older orders / backend not updated yet),
      fall back to reading the codes from the header text."""
    if "ticket_meats" not in item:
        return _split_meats(header)

    meats = _meats_from_field(item.get("ticket_meats"))
    name, drink, text_meats = _split_meats(header)
    if text_meats and sorted(text_meats) != sorted(meats):
        # Trailing text isn't these meats — it's part of the product name.
        name = header[: _DRINK_RE.search(header).start()].rstrip() if drink else header.rstrip()
    return name, drink, meats


def _meat_column_block(name: str, meats: list[tuple[int, str]], mods: list[str]) -> bytes:
    """Meat letters in a left column (under the meat count), modifiers
    centred on the same rows. Lines are laid out manually with spaces and
    printed LEFT-aligned, because ESC/POS can't mix alignments on one line."""
    width = BIG_LINE_WIDTH
    # One line per portion: a doubled meat prints "T" on two lines, not "2 T".
    labels = [code for q, code in meats for _ in range(q)]
    label_w = max(len(lbl) for lbl in labels)

    # Under the "v<count>" on the header line, then shifted right.
    col = len(name) + 1 + MEAT_COLUMN_SHIFT
    if width - (col + label_w + 2) < 10:  # long name: not enough room left
        col = MEAT_COLUMN_SHIFT
    gutter = col + label_w + 2  # modifiers never start left of this

    mod_lines: list[str] = []
    for mod in mods:
        mod_lines.extend(textwrap.wrap(mod, width=width - gutter) or [""])

    out = b""
    for i in range(max(len(labels), len(mod_lines))):
        left = (" " * col + labels[i]) if i < len(labels) else ""
        mod = mod_lines[i] if i < len(mod_lines) else ""
        if mod:
            centred = (width - len(mod)) // 2 + MEAT_COLUMN_SHIFT
            start = max(gutter, min(centred, width - len(mod)))
            row = left.ljust(start) + mod
        else:
            row = left
        out += _line(row.rstrip())
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
    icon_kind = fulfillment if fulfillment in FULFILLMENT_LABEL else "dine_in"
    banner = _banner_bytes(icon_kind, fulfillment_label)
    out += ALIGN_CENTER + BOLD_ON
    if banner:
        out += banner  # "SUR PLACE" + icon on the right, as one image
    else:
        out += SIZE_TALL + _line(fulfillment_label)
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
    items = order.get("items") or []
    for idx, item in enumerate(items):
        header = _with_qty_x(
            item.get("ticket_header") or item.get("ticket_line") or _legacy_item_line(item)
        )
        mods = item.get("ticket_mods") or []
        # Kids-meal marker: the backend appends this bare letter/word (e.g.
        # "c") to ticket_mods for kids items (see order_service.py's
        # kids_code). Pull it out here and render it right-aligned on the
        # header line, next to the drink, instead of as a centered mod below.
        kids_suffix = ""
        for m in mods:
            if m.strip().lower() == KIDS_MARKER.lower():
                kids_suffix = f"+{KIDS_MARKER}"
                break
        mods = [m for m in mods if m.strip().lower() != KIDS_MARKER.lower()]
        # Fries sauce (e.g. "Algerienne"): rendered in its own dedicated slot
        # directly under the header/drink line, never mixed into mods below.
        # Backend now sends up to 2 sauces as a list ("fries_sauces"); old
        # orders may still carry the singular "fries_sauce" string.
        raw_fries = item.get("fries_sauces")
        if raw_fries is None:
            legacy = (item.get("fries_sauce") or "").strip()
            raw_fries = [legacy] if legacy else []
        if isinstance(raw_fries, str):
            raw_fries = [raw_fries]
        # Bracketed like the drink ("[Ketchup]") so it reads as part of that column.
        fries_sauces = [f"[{str(s).strip()}]" for s in raw_fries if s and str(s).strip()]
        name, drink, meats = _resolve_item_meats(item, header)
        out += ALIGN_LEFT
        if meats:
            meat_count = sum(q for q, _ in meats)
            out += _header_line(f"{name} v{meat_count} {drink}".strip(), suffix=kids_suffix)
            # Right-justified (not centered) so each sauce sits directly
            # under the drink, one per line, in the order the backend sent.
            for fs in fries_sauces:
                out += _wrapped_big_right(fs)
            out += _meat_column_block(name, meats, mods)
        else:
            out += _header_line(header, suffix=kids_suffix)
            for fs in fries_sauces:
                out += _wrapped_big_right(fs)
            if mods:
                out += ALIGN_CENTER
                for m in mods:
                    out += _wrapped_big(m)
        if item.get("notes"):
            out += ALIGN_CENTER
            out += _wrapped_big(f"Note: {item['notes']}")
        # Divider between items, in the same normal-size, non-bold style as
        # the other dashed lines. Skipped after the last item when there's no
        # order note, because the section's closing divider follows directly.
        if idx < len(items) - 1 or order.get("notes"):
            out += BOLD_OFF + SIZE_NORMAL + ALIGN_LEFT
            out += _line(DIVIDER)
            out += BOLD_ON + ITEM_SIZE_BYTE
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

    # Blank gap — separates the order/total from the client details below by
    # plain paper space (no dashed divider) so the two sections read as
    # clearly distinct blocks.
    out += _feed_gap(CLIENT_GAP_MM)

    # Client info block (name, phone, delivery slot, address, city, pickup
    # code, payment) — printed bigger (tall), same treatment as the TOTAL
    # line above, so it's easy to read at a glance instead of small text.
    out += BOLD_ON + SIZE_TALL
    if customer_name:
        out += _tall(f"Client : {customer_name}")
    if order.get("customer_phone"):
        out += _tall(f"Tel : {order['customer_phone']}")
    if fulfillment == "delivery":
        _, slot_start = _fmt_datetime(order.get("scheduled_delivery_start", ""))
        if slot_start:
            out += _tall(f"Creneau livraison : {slot_start}")
        addr = ", ".join(filter(None, [order.get("address_line1"), order.get("address_line2")]))
        if addr:
            out += _tall(f"Adresse : {addr}")
        city_line = f"{order.get('postal_code', '')} {order.get('city', '')}".strip()
        if city_line:
            out += _tall(f"Ville : {city_line}")
    if order.get("pickup_code"):
        out += _tall(f"Code retrait : {order['pickup_code']}")
    out += _tall(
        f"Paiement : {PAYMENT_LABEL.get(order.get('payment_method'), order.get('payment_method', ''))}"
    )
    out += BOLD_OFF

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