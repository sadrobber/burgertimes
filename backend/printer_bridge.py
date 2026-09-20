"""Pushes a fire-and-forget HTTP print job to the restaurant's own
Raspberry Pi print-bridge (a small Flask server sitting next to the Sunmi
NT311 thermal printer on the local network, reached through a tunnel such
as ngrok). Safe no-op when KITCHEN_PRINTER_WEBHOOK_URL is unset.

This REPLACES the old client-side browser print (window.print()) — the
tablet no longer touches printing at all. The backend calls this the
moment an order is accepted (or manually re-triggered via /reprint), and
the Pi formats + sends the raw ESC/POS ticket to the printer itself.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger("printer_bridge")


async def send_print_job(order: Dict[str, Any], copies: int = 1) -> bool:
    """POST the order JSON (plus a "print_copies" count) to the Pi's /print
    endpoint. Returns True only on a 200 response — callers use that to
    flag the order as printed."""
    url = os.environ.get("KITCHEN_PRINTER_WEBHOOK_URL")
    if not url:
        logger.warning("KITCHEN_PRINTER_WEBHOOK_URL not set — skipping printer push")
        return False
    payload = {**order, "print_copies": copies}
    secret = os.environ.get("KITCHEN_PRINTER_SECRET")
    headers = {"X-Print-Secret": secret} if secret else None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            return True
        logger.warning("Printer webhook returned %s: %s", resp.status_code, resp.text[:300])
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Printer webhook POST failed")
        return False
