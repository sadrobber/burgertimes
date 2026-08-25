"""Local Android ESC/POS print bridge (Bluetooth-paired SUNMI printer).

The Android tablet running the /kitchen page has a companion printing app
(or a small local HTTP service) that owns the Bluetooth pairing to the
SUNMI 80mm printer and accepts a raw ESC/POS byte stream to print. This
module is intentionally the ONLY place that knows about that endpoint, so
it can be repointed later (different app, different payload shape) without
touching any order/kitchen logic.

Configure via ``KITCHEN_PRINT_ENDPOINT`` (unset = not configured yet, which
is a normal, fully-supported state: the rest of the kitchen flow works,
prints just record as ``print_failed`` with a clear reason until it's set).
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _endpoint() -> Optional[str]:
    v = os.environ.get("KITCHEN_PRINT_ENDPOINT")
    return v if v else None


def is_configured() -> bool:
    return bool(_endpoint())


async def print_kitchen_receipt(order: Dict[str, Any], receipt_bytes: bytes) -> Dict[str, Any]:
    """POST the ESC/POS ticket to the local Android printing bridge.

    Never raises — callers persist the returned ``ok``/``error`` onto the
    order's kitchen_print_* fields. Printing failure must never affect the
    order/payment state, only the print status.
    """
    endpoint = _endpoint()
    if not endpoint:
        logger.info(
            "KITCHEN_PRINT_ENDPOINT not configured; skipping print for order %s",
            order.get("order_number"),
        )
        return {"ok": False, "error": "print_bridge_not_configured"}

    payload = {
        "order_number": order.get("order_number"),
        "escpos_base64": base64.b64encode(receipt_bytes).decode("ascii"),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(endpoint, json=payload)
            if r.status_code >= 300:
                logger.warning(
                    "Kitchen print bridge failed for order %s: HTTP %s",
                    order.get("order_number"),
                    r.status_code,
                )
                return {"ok": False, "error": f"bridge_http_{r.status_code}"}
            logger.info("Kitchen print bridge accepted order %s", order.get("order_number"))
            return {"ok": True}
    except Exception:  # noqa: BLE001
        logger.exception("Kitchen print bridge request failed for order %s", order.get("order_number"))
        return {"ok": False, "error": "bridge_request_exception"}
