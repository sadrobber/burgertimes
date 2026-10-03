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
    dots; no text lines involved, just paper)."""
    return _feed_dots(round(mm * DOTS_PER_MM))


def _feed_dots(dots: int) -> bytes:
    """Blank vertical space of `dots` dots. ESC J's dot count is a single
    byte (0-255), so a big gap is split across several commands."""
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
# Scheduled orders: "PRÉVUE POUR" over the time, in one big black box centred
# (both ways) in that gap. Drawn with Pillow like the other boxes (BOX_LABELS).
SCHEDULE_TIME_PX = 120   # font size of the time — 8 dots = 1 mm
SCHEDULE_LABEL_PX = 34   # font size of "PRÉVUE POUR"

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


# Size of the client block at the end of the ticket (name, phone, address,
# payment...), same 1-10 scale as ITEM_SIZE_LEVEL. 3 = double size.
CLIENT_SIZE_LEVEL = 3  # <---- CHANGE THIS NUMBER (1 to 10)

# Derived from the level you picked above — do not edit these two lines.
_ITEM_W, _ITEM_H = SIZE_LEVELS.get(ITEM_SIZE_LEVEL, SIZE_LEVELS[3])
ITEM_SIZE_BYTE = _size_byte(_ITEM_W, _ITEM_H)
# Wider text = fewer characters per line (an 80mm roll fits ~46 normal chars),
# so we auto-shrink the wrap width to stop long names being cut mid-word.
BIG_LINE_WIDTH = max(6, 46 // _ITEM_W)
_CLIENT_W, _CLIENT_H = SIZE_LEVELS.get(CLIENT_SIZE_LEVEL, SIZE_LEVELS[3])
CLIENT_SIZE_BYTE = _size_byte(_CLIENT_W, _CLIENT_H)
CLIENT_LINE_WIDTH = max(6, 46 // _CLIENT_W)


def _client(text: str = "") -> bytes:
    """One client-block line at CLIENT_SIZE_LEVEL, wrapped at word boundaries."""
    out = b""
    for w in (textwrap.wrap(text, width=CLIENT_LINE_WIDTH) or [""]):
        out += _line(w)
    return out


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

# Label boxes — the drink, kids marker, fries sauces, meat letters and
# modifiers each print as white text in their own black rounded box, drawn
# with Pillow and sent as raster images (GS v 0) like the banner. If Pillow
# isn't installed, or BOX_LABELS is False, the old plain-text labels print.
BOX_LABELS = True      # set to False to go back to plain-text labels
BOX_FONT_PX = 30
BOX_PAD_X = 10         # space between the text and the box edge, left/right
BOX_PAD_Y = 6          # same, top/bottom
BOX_GAP_PX = 6         # vertical gap between rows of boxes
BOX_H_GAP_PX = 8       # horizontal gap between boxes on one row
BOX_RADIUS = 4         # rounded corners
BOX_MARGIN_PX = 8      # boxes never come closer than this to the paper edge
# The printer can't put its own text and an image on the same line, so to
# get the first meat letter and the drink box up on the item name's line,
# every item name and note is drawn into the images too — one 12x24-dot
# bitmap glyph per character, doubled one dot to the right like the
# printer's own bold text — so the whole item section shares one look.
# False = item names and notes stay printer text and the boxes start on
# the line below the name.
ITEM_TEXT_AS_IMAGE = True
_MONO_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Raspberry Pi OS default
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None
    logger.warning("Pillow not installed: banner icons disabled (pip install pillow)")


def _boxes_on() -> bool:
    """Label boxes need Pillow and BOX_LABELS; otherwise plain text prints."""
    return BOX_LABELS and Image is not None


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


def _box_words(text: str) -> list[str]:
    """Words of a label, a lone "+" kept with the word after it
    ("BBQ + Cheddar" -> "BBQ", "+ Cheddar"), so a wrap never strands it."""
    words: list[str] = []
    for word in text.split():
        if words and words[-1] == "+":
            words[-1] += f" {word}"
        else:
            words.append(word)
    return words


def _box_lines(text: str, font, max_w: int) -> list[str]:
    """Split `text` at word boundaries (_box_words) into lines at most max_w
    px wide. A single word wider than max_w is cut, so a box never outgrows
    the paper."""
    def width(s: str) -> int:
        left, _, right, _ = font.getbbox(s)
        return right - left

    lines: list[str] = []
    for word in _box_words(text):
        if lines and width(f"{lines[-1]} {word}") <= max_w:
            lines[-1] += f" {word}"
            continue
        while len(word) > 1 and width(word) > max_w:
            cut = len(word) - 1
            while cut > 1 and width(word[:cut]) > max_w:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        lines.append(word)
    return lines


def _box_image(text: str, max_w: int | None = None):
    """One label as an 'L' image: white text centred in a black rounded box,
    sized to the text plus padding and never wider than max_w (default: the
    paper minus BOX_MARGIN_PX each side; longer labels wrap). Surrounding
    [ ] are dropped. None if it can't be drawn — print plain text instead."""
    if not _boxes_on():
        return None
    try:
        font = _banner_font(BOX_FONT_PX)
        if max_w is None:
            max_w = BANNER_WIDTH_PX - 2 * BOX_MARGIN_PX
        lines = _box_lines(text.strip().strip("[]").strip(), font, max_w - 2 * BOX_PAD_X)
        if not lines:
            return None
        ascent, descent = font.getmetrics()
        line_h = ascent + descent  # same height for every label, descenders or not
        bboxes = [font.getbbox(ln) for ln in lines]
        w = max(r - l for l, _, r, _ in bboxes) + 2 * BOX_PAD_X
        h = line_h * len(lines) + 2 * BOX_PAD_Y
        img = Image.new("L", (w, h), 255)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=BOX_RADIUS, fill=0)
        for i, (ln, (l, _, r, _)) in enumerate(zip(lines, bboxes)):
            d.text(((w - (r - l)) // 2 - l, BOX_PAD_Y + i * line_h), ln, font=font, fill=255)
        return img
    except Exception:  # noqa: BLE001 — never block a print because of a box
        logger.exception("Label box rendering failed, falling back to text")
        return None


def _schedule_gap(hhmm: str) -> bytes | None:
    """The blank gap between the TOTAL and the client block with a scheduled
    order's time in its middle, both ways: "PRÉVUE POUR" over the time in
    large white digits, in one black rounded box. None if there's no time
    or it can't be drawn: print the plain gap, and the time goes in the
    client block as a text line instead."""
    if not _boxes_on() or not hhmm:
        return None
    try:
        label = "PRÉVUE POUR"
        label_font = _banner_font(SCHEDULE_LABEL_PX)
        time_font = _banner_font(SCHEDULE_TIME_PX)
        l0, t0, r0, b0 = label_font.getbbox(label)
        l1, t1, r1, b1 = time_font.getbbox(hhmm)
        pad_x, pad_y, between = 36, 20, 14
        w = max(r0 - l0, r1 - l1) + 2 * pad_x
        h = (b0 - t0) + between + (b1 - t1) + 2 * pad_y
        img = Image.new("L", (w, h), 255)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=BOX_RADIUS, fill=0)
        d.text(((w - (r0 - l0)) // 2 - l0, pad_y - t0), label, font=label_font, fill=255)
        d.text(((w - (r1 - l1)) // 2 - l1, pad_y + (b0 - t0) + between - t1), hhmm,
               font=time_font, fill=255)
        # Full-width canvas printed left-aligned, like the other boxes, so
        # it's centred on the text column whatever the printer's alignment.
        canvas = Image.new("L", (BANNER_WIDTH_PX, h), 255)
        canvas.paste(img, ((BANNER_WIDTH_PX - w) // 2, 0))
        gap = CLIENT_GAP_MM * DOTS_PER_MM
        above = max(0, (gap - h) // 2)
        return (_feed_dots(above) + ALIGN_LEFT + _raster(canvas)
                + _feed_dots(max(0, gap - h - above)))
    except Exception:  # noqa: BLE001 — never block a print because of the box
        logger.exception("Schedule box rendering failed, printing the time as text")
        return None


def _box_row(row: list) -> bytes | None:
    """One row of the item layout — (image, x) pairs, vertically centred —
    as a single raster image BANNER_WIDTH_PX wide (the width of the text
    lines), printed left-aligned so the printer's own alignment never
    matters. None if it can't be drawn — print plain text instead."""
    try:
        height = max(img.height for img, _ in row)
        # BOX_GAP_PX split above and below, so stacked rows are BOX_GAP_PX apart.
        canvas = Image.new("L", (BANNER_WIDTH_PX, height + BOX_GAP_PX), 255)
        for img, x in row:
            canvas.paste(img, (max(0, min(x, BANNER_WIDTH_PX - img.width)),
                               BOX_GAP_PX // 2 + (height - img.height) // 2))
        return ALIGN_LEFT + _raster(canvas)
    except Exception:  # noqa: BLE001 — never block a print because of a box
        logger.exception("Label box row rendering failed, falling back to text")
        return None


_GLYPH_CACHE: dict = {}


def _glyph(ch: str):
    """One character as a 12x24-dot bitmap — the printer's own cell size.
    Drawn 4x oversize in a regular-weight monospace font, shrunk to the cell,
    then doubled one dot to the right, which is how the printer makes its
    bold text. None if no monospace font is installed."""
    if ch not in _GLYPH_CACHE:
        path = next((p for p in _MONO_FONT_CANDIDATES if os.path.exists(p)), None)
        if path is None:
            return None
        ss = 4
        font = ImageFont.truetype(path, 80)  # a 0.6 em advance = 48 px = 12 dots x 4
        ascent, descent = font.getmetrics()
        big = Image.new("L", (12 * ss, 24 * ss), 255)
        ImageDraw.Draw(big).text((0, (24 * ss - ascent - descent) // 2), ch, font=font, fill=0)
        cell = big.resize((12, 24), Image.LANCZOS).point(lambda p: 0 if p < 150 else 255)
        shifted = Image.new("L", (12, 24), 255)
        shifted.paste(cell, (1, 0))
        _GLYPH_CACHE[ch] = ImageChops.darker(cell, shifted)
    return _GLYPH_CACHE[ch]


def _text_image(text: str):
    """`text` as one row of printer-like bitmap glyphs at the item text size
    (12x24 dots per character, scaled by ITEM_SIZE_LEVEL like the printer
    does), so it can share a raster row with the boxes. None when
    ITEM_TEXT_AS_IMAGE is off, no monospace font is installed, or drawing
    fails: the caller prints the printer's own text instead."""
    if not ITEM_TEXT_AS_IMAGE or not _boxes_on() or not text:
        return None
    try:
        glyphs = [_glyph(ch) for ch in text]
        if any(g is None for g in glyphs):
            return None
        strip = Image.new("L", (12 * len(text), 24), 255)
        for i, g in enumerate(glyphs):
            strip.paste(g, (12 * i, 0))
        return strip.resize((12 * _ITEM_W * len(text), 24 * _ITEM_H), Image.NEAREST)
    except Exception:  # noqa: BLE001 — never block a print because of the text
        logger.exception("Item text rendering failed, printing it as text")
        return None


def _text_rows(text: str, align: str = "left") -> list | None:
    """`text` wrapped at BIG_LINE_WIDTH like the printer text would be, as
    one image row (for _box_row) per line, left-aligned or centred.
    None = print plain text instead."""
    rows = []
    for line in textwrap.wrap(text, width=BIG_LINE_WIDTH) or [""]:
        img = _text_image(line)
        if img is None:
            return None
        rows.append([(img, 0 if align == "left" else (BANNER_WIDTH_PX - img.width) // 2)])
    return rows


def _text_block(text: str, align: str = "left") -> bytes | None:
    """_text_rows rendered to printer bytes — used for the notes, so they
    match the drawn item names. None = print plain text instead."""
    rows = _text_rows(text, align)
    if rows is None:
        return None
    out = b""
    for row in rows:
        line = _box_row(row)
        if line is None:
            return None
        out += line
    return out


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


def _item_boxes(head: str, suffix: str, fries: list[str], meats: list[tuple[int, str]],
                mods: list[str], right_item: bool = False) -> bytes | None:
    """One item in the box layout:

        1 x Menu Tacos v3  [T]         [+c] [Cherry]
                           [B]            [Ketchup]
                           [K]           [Moutarde]
                        [BBQ]
                     [Marrocaine]
                       [+ Oeuf]

    The name on the left; the meat letters in a column two characters
    after it (where the text layout puts them), one box per portion, from
    the name's line down; the kids marker + drink flush right on the
    name's line, then one fries sauce per row under them; then the
    modifiers centred, one per row. Everything but the name is a box.
    The name is drawn into the first row's image (ITEM_TEXT_AS_IMAGE) so
    the boxes can start on its line; when it doesn't fit beside them it
    goes on its own line(s) above. A "right" item (admin: encadré à
    droite) has its name in a box on the right instead — first on the top
    row, before the marker and drink — with any meat letters at the left
    margin. None = print the plain-text layout instead."""
    if not _boxes_on():
        return None
    match = re.search(r"\s*(\[[^\]]*\])\s*$", head)
    drink = match.group(1) if match else ""
    name = head[: match.start()].rstrip() if match else head.rstrip()
    top = [x for x in (suffix, drink) if x]
    if right_item:  # "1 x Frites" boxes as "Frites", like the drink; "2 x Frites" stays
        top = [re.sub(r"^1 x ", "", name)] + top
    lo, hi = BOX_MARGIN_PX, BANNER_WIDTH_PX - BOX_MARGIN_PX
    cw = 12 * _ITEM_W  # one printer character, in dots

    # Right column, flush right: [+c] [Cherry], then one fries sauce per row.
    # A top row too wide for the paper is split into one box per row.
    right = []
    for labels in ([top] if top else []) + [[s] for s in fries]:
        boxes = [_box_image(t) for t in labels]
        if any(b is None for b in boxes):
            return None
        total = sum(b.width for b in boxes) + BOX_H_GAP_PX * (len(boxes) - 1)
        if total > hi - lo:
            right += [[(b, hi - b.width)] for b in boxes]
            continue
        x = hi - total
        row = []
        for b in boxes:
            row.append((b, x))
            x += b.width + BOX_H_GAP_PX
        right.append(row)
    right_edge = min((row[0][1] for row in right), default=hi)  # nothing crosses this

    # Letter column: two characters after the name — or at the left margin
    # when there's no name on the left, or a long one leaves no room.
    letters = [_box_image(code) for q, code in meats for _ in range(q)]
    if any(b is None for b in letters):
        return None
    name_w = 0 if right_item else len(name) * cw
    col = lo if right_item else name_w + 2 * cw
    under = bool(letters) and col + max(b.width for b in letters) + BOX_H_GAP_PX > right_edge
    if under:
        col = lo

    # The name: drawn into the first row when it fits beside the boxes, else
    # drawn on its own row(s) above them, else the printer's own text.
    out, rows, base = b"", [], 0
    if not right_item:
        name_img = _text_image(name)
        first_right = right[0][0][1] if right else hi
        if name_img is not None and not under and name_w + BOX_H_GAP_PX <= first_right:
            rows.append([(name_img, 0)])
        elif name_img is not None:
            rows = _text_rows(name) or []
            base = len(rows)
        if not rows:
            out += _wrapped_big(name)
    for i in range(max(len(letters), len(right))):
        r = base + i
        if r == len(rows):
            rows.append([])
        if i < len(letters):
            rows[r].append((letters[i], col))
        if i < len(right):
            rows[r] += right[i]
    for m in mods:
        box = _box_image(m)
        if box is None:
            return None
        rows.append([(box, (BANNER_WIDTH_PX - box.width) // 2)])
    for row in rows:
        line = _box_row(row)
        if line is None:
            return None
        out += line
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
        # Kids-meal marker: the backend appends the admin's kids code (e.g.
        # "c" or "+c") to ticket_mods for kids items and also sends it as
        # "kids_code". Pull it out here and render it right-aligned on the
        # header line, next to the drink, instead of as a centered mod below.
        # Older orders have no "kids_code" field: fall back to KIDS_MARKER.
        kids_code = (item.get("kids_code") or "").strip()
        candidates = {kids_code.lower()} if kids_code else {
            KIDS_MARKER.lower(), f"+{KIDS_MARKER}".lower()
        }
        kids_suffix = ""
        for m in mods:
            if m.strip().lower() in candidates:
                code = m.strip()
                kids_suffix = code if code.startswith("+") else f"+{code}"
                break
        mods = [m for m in mods if m.strip().lower() not in candidates]
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
        fries_sauces = [str(s).strip() for s in raw_fries if s and str(s).strip()]
        name, drink, meats = _resolve_item_meats(item, header)
        out += ALIGN_LEFT
        head = f"{name} v{sum(q for q, _ in meats)} {drink}".strip() if meats else header
        # Items flagged "encadré à droite" in the admin print as a box on the
        # right of the ticket; consecutive ones share one block (no divider).
        right_item = _boxes_on() and item.get("ticket_position") == "right"
        boxed = _item_boxes(head, kids_suffix, fries_sauces, meats, mods, right_item)
        if boxed is not None:
            out += boxed
        elif meats:
            out += _header_line(head, suffix=kids_suffix)
            # Right-justified (not centered) so each sauce sits directly
            # under the drink, one per line, in the order the backend sent.
            for fs in fries_sauces:
                out += _wrapped_big_right(f"[{fs}]")
            out += _meat_column_block(name, meats, mods)
        else:
            out += _header_line(header, suffix=kids_suffix)
            for fs in fries_sauces:
                out += _wrapped_big_right(f"[{fs}]")
            if mods:
                out += ALIGN_CENTER
                for m in mods:
                    out += _wrapped_big(m)
        if item.get("notes"):
            note = _text_block(f"Note: {item['notes']}", "center")
            if note is None:
                out += ALIGN_CENTER
                out += _wrapped_big(f"Note: {item['notes']}")
            else:
                out += note
        # Divider between items, in the same normal-size, non-bold style as
        # the other dashed lines. Skipped after the last item when there's no
        # order note, because the section's closing divider follows directly,
        # and between two "right" items, which share one block.
        nxt = items[idx + 1] if idx + 1 < len(items) else None
        shared = (boxed is not None and right_item
                  and nxt is not None and nxt.get("ticket_position") == "right")
        if (idx < len(items) - 1 or order.get("notes")) and not shared:
            out += BOLD_OFF + SIZE_NORMAL + ALIGN_LEFT
            out += _line(DIVIDER)
            out += BOLD_ON + ITEM_SIZE_BYTE
    if order.get("notes"):
        out += ALIGN_LEFT
        note = _text_block(f"Note: {order['notes']}", "left")
        out += note if note is not None else _wrapped_big(f"Note: {order['notes']}")
    out += BOLD_OFF + SIZE_NORMAL
    out += ALIGN_LEFT
    out += _line(DIVIDER)

    total = order.get("total") or 0
    out += BOLD_ON + SIZE_TALL
    out += _line(f"TOTAL : {total:.2f} EUR".replace(".", ","))
    out += BOLD_OFF + SIZE_NORMAL

    # Blank gap — separates the order/total from the client details below by
    # plain paper space (no dashed divider) so the two sections read as
    # clearly distinct blocks. A scheduled order's time sits big in its middle.
    _, scheduled_time = _fmt_datetime(order.get("scheduled_delivery_start", ""))
    schedule_gap = _schedule_gap(scheduled_time)
    out += schedule_gap or _feed_gap(CLIENT_GAP_MM)

    # Client info block (name, phone, delivery slot, address, city, pickup
    # code, payment) — printed big (CLIENT_SIZE_LEVEL) so it's easy to read
    # at a glance.
    out += BOLD_ON + CLIENT_SIZE_BYTE
    if customer_name:
        out += _client(f"Client : {customer_name}")
    phone = (order.get("customer_phone") or "").strip()
    if phone and order.get("order_source") == "tablet":
        # The tablet stores "<dial code> <number>" (e.g. "+33 612345678");
        # counter staff only want the number, so drop the country code.
        phone = re.sub(r"^\+\d+\s+", "", phone)
    if phone:
        out += _client(f"Tel : {phone}")
    if scheduled_time and schedule_gap is None:  # else it's big in the gap above
        label = "Creneau livraison" if fulfillment == "delivery" else "Prevue pour"
        out += _client(f"{label} : {scheduled_time}")
    if fulfillment == "delivery":
        addr = ", ".join(filter(None, [order.get("address_line1"), order.get("address_line2")]))
        if addr:
            out += _client(f"Adresse : {addr}")
        # `or ""`, not a .get() default: the backend stores missing fields as
        # null, which would otherwise print as "None" ("Ville : None Monaco").
        city_line = f"{order.get('postal_code') or ''} {order.get('city') or ''}".strip()
        if city_line:
            out += _client(f"Ville : {city_line}")
    if order.get("pickup_code"):
        out += _client(f"Code retrait : {order['pickup_code']}")
    # Tablet orders are taken at the counter, so the payment method is
    # irrelevant there — only online orders print it.
    if order.get("order_source") != "tablet":
        out += _client(
            f"Paiement : {PAYMENT_LABEL.get(order.get('payment_method'), order.get('payment_method') or '')}"
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