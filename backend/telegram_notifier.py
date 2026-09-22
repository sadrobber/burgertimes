"""Non-blocking Telegram notifications for real Burger Times orders."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _format_euro(amount: Any) -> str:
    value = round(float(amount or 0.0), 2)
    return f"{value:.2f}".replace(".", ",")


async def send_commission_alert(order: dict[str, Any]) -> bool:
    """Send a delivery-fee commission alert without blocking order success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_COMMISSION_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram commission notification is not configured")
        return False

    commission = _format_euro(order.get("delivery_fee"))
    message = f"🚨 New order: +{commission}€ 💰"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return True
    except Exception as error:  # noqa: BLE001
        logger.warning("Telegram commission notification failed: %s", type(error).__name__)
        return False