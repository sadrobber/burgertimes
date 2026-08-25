"""SUNMI Cloud Printer OpenAPI (Cloud-to-Cloud, V2, HMAC-SHA256).

Safe when SUNMI_APP_ID / SUNMI_APP_KEY / SUNMI_PRINTER_SN are unset: every
call becomes a no-op returning ``{"ok": False, "error": "sunmi_not_configured"}``.
Never logs the AppKey.

Signing (per SUNMI production V2 partner contract, confirmed 2026-02):
    dataToSign = EXACT_JSON_BODY + APP_ID + TIMESTAMP + NONCE
    Sunmi-Sign = HMAC-SHA256(key=APP_KEY, message=dataToSign).hexdigest()

``EXACT_JSON_BODY`` is the literal compact-serialized JSON string sent as the
HTTP body — signing and sending use the identical byte string (``_serialize``
is the single source of truth for that string).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

SUNMI_BASE_URL = "https://openapi.sunmi.com"

STATUS_PATH = "/v2/printer/open/open/device/onlineStatus"
PUSH_CONTENT_PATH = "/v2/printer/open/open/device/pushContent"
PRINT_STATUS_PATH = "/v2/printer/open/open/ticket/printStatus"


def _app_id() -> Optional[str]:
    v = os.environ.get("SUNMI_APP_ID")
    return v if v else None


def _app_key() -> Optional[str]:
    v = os.environ.get("SUNMI_APP_KEY")
    return v if v else None


def _printer_sn() -> Optional[str]:
    v = os.environ.get("SUNMI_PRINTER_SN")
    return v if v else None


def is_configured() -> bool:
    return bool(_app_id() and _app_key() and _printer_sn())


def _serialize(payload: Dict[str, Any]) -> str:
    """Canonical compact JSON. Used identically for signing AND sending."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _sign(body_str: str, timestamp: str, nonce: str) -> str:
    app_id = _app_id()
    app_key = _app_key()
    data_to_sign = f"{body_str}{app_id}{timestamp}{nonce}"
    return hmac.new(
        app_key.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _request(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not is_configured():
        return {"ok": False, "error": "sunmi_not_configured"}
    body_str = _serialize(payload)
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    sign = _sign(body_str, timestamp, nonce)
    headers = {
        "Sunmi-Appid": _app_id(),
        "Sunmi-Timestamp": timestamp,
        "Sunmi-Nonce": nonce,
        "Sunmi-Sign": sign,
        "Source": "openapi",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(base_url=SUNMI_BASE_URL, timeout=15) as client:
            r = await client.post(path, content=body_str.encode("utf-8"), headers=headers)
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                data = {"raw_text": r.text[:500]}
            if r.status_code >= 300:
                logger.warning("SUNMI %s failed: HTTP %s %s", path, r.status_code, data)
                return {
                    "ok": False,
                    "http_status": r.status_code,
                    "error": "sunmi_http_error",
                    "response": data,
                }
            logger.info("SUNMI %s succeeded: HTTP %s", path, r.status_code)
            return {"ok": True, "http_status": r.status_code, "response": data}
    except Exception:  # noqa: BLE001
        logger.exception("SUNMI request failed (path=%s)", path)
        return {"ok": False, "error": "sunmi_request_exception"}


async def check_online() -> Dict[str, Any]:
    return await _request(STATUS_PATH, {"sn": _printer_sn()})


async def push_content(escpos_hex: str, trade_no: str) -> Dict[str, Any]:
    payload = {"sn": _printer_sn(), "tradeNo": trade_no, "data": escpos_hex}
    return await _request(PUSH_CONTENT_PATH, payload)


async def query_print_status(trade_no: str) -> Dict[str, Any]:
    payload = {"sn": _printer_sn(), "tradeNo": trade_no}
    return await _request(PRINT_STATUS_PATH, payload)


def extract_online(result: Dict[str, Any]) -> Optional[bool]:
    """Best-effort parse of the online flag from a check_online() response.

    Response field names are confirmed against the real SUNMI production API
    during the admin "Vérifier le statut" test — this stays permissive so the
    admin UI can also show the raw response for one-time verification.
    """
    resp = result.get("response") if isinstance(result, dict) else None
    if not isinstance(resp, dict):
        return None
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("online", "isOnline", "onlineStatus", "status"):
            if key in data:
                val = data[key]
                if isinstance(val, bool):
                    return val
                if isinstance(val, (int, str)):
                    return str(val).strip().lower() in ("1", "true", "online")
    return None
