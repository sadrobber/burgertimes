"""Resend transactional email — safe when RESEND_API_KEY is unset."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _api_key() -> Optional[str]:
    v = os.environ.get("RESEND_API_KEY")
    return v if v else None


def _from_email() -> str:
    return os.environ.get("RESEND_FROM_EMAIL", "Burger Times <noreply@example.com>")


def is_configured() -> bool:
    return bool(_api_key())


def _fmt_eur(v: float) -> str:
    return f"{v:.2f} €"


def _wrap(title: str, status_pill: str, body: str) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; background:#0A0A0A; padding:24px; color:#F5F1E8;">
      <div style="max-width:560px;margin:0 auto;background:#141414;padding:24px;border:2px solid #EF2B2D;">
        <h1 style="font-family:Impact,'Arial Black',sans-serif;text-transform:uppercase;color:#EF2B2D;margin:0 0 12px 0;letter-spacing:1px;">Burger Times</h1>
        <div style="display:inline-block;padding:4px 10px;background:#EF2B2D;color:#F5F1E8;font-weight:bold;text-transform:uppercase;font-size:12px;margin-bottom:16px;">{status_pill}</div>
        <h2 style="margin:0 0 12px 0;color:#F5F1E8;">{title}</h2>
        {body}
        <hr style="border:none;border-top:1px solid #262626;margin:24px 0;" />
        <p style="color:#666;font-size:12px;margin:0;">Burger Times · 6 Avenue de Villaine, 06240 Beausoleil · 04.97.07.17.93</p>
      </div>
    </div>
    """


def _items_html(order: Dict[str, Any]) -> str:
    rows = []
    for it in (order.get("items") or []):
        rows.append(
            f"<tr><td style='padding:6px 0;'>{it['quantity']}× {it['name']}</td>"
            f"<td style='padding:6px 0;text-align:right;'>{_fmt_eur(it['line_total'])}</td></tr>"
        )
    return "<table style='width:100%;border-collapse:collapse;color:#F5F1E8;'>" + "".join(rows) + "</table>"


def _template(order: Dict[str, Any], template: str) -> tuple[str, str]:
    name = f"{order.get('customer_first_name','')} {order.get('customer_last_name','')}".strip()
    total = _fmt_eur(order.get("total", 0))
    subtotal = _fmt_eur(order.get("subtotal", 0))
    delivery_fee = order.get("delivery_fee", 0)
    pay = "Cash sur place" if order.get("payment_method") == "cash" else "Carte sur place"
    fulfillment = "Retrait" if order.get("fulfillment") == "pickup" else "Livraison"
    pickup_code = order.get("pickup_code")

    items_html = _items_html(order)
    totals_html = (
        f"<p style='color:#F5F1E8;margin:12px 0 4px 0;'>Sous-total : {subtotal}</p>"
        + (f"<p style='color:#F5F1E8;margin:0 0 4px 0;'>Livraison : {_fmt_eur(delivery_fee)}</p>" if delivery_fee else "")
        + f"<p style='color:#EF2B2D;font-size:18px;font-weight:bold;margin:0;'>Total : {total}</p>"
    )
    pickup_html = f"<p style='color:#FFB800;font-weight:bold;'>🔐 Code de retrait : {pickup_code}</p>" if pickup_code else ""

    if template == "order_confirmed":
        subject = f"Commande confirmée · #{order.get('order_number')}"
        body = (
            f"<p>Bonjour {name},</p>"
            f"<p>On a bien reçu ta commande <b>#{order.get('order_number')}</b>. On la prépare bientôt.</p>"
            f"<p>Type : <b>{fulfillment}</b> · Paiement : <b>{pay}</b></p>"
            f"{pickup_html}"
            f"{items_html}"
            f"{totals_html}"
        )
        return subject, _wrap("Commande reçue", "En attente", body)
    if template == "order_accepted":
        subject = f"Commande acceptée · #{order.get('order_number')}"
        body = (
            f"<p>Bonjour {name},</p>"
            f"<p>Ta commande <b>#{order.get('order_number')}</b> est acceptée. Elle passe en cuisine.</p>"
            f"{pickup_html}"
        )
        return subject, _wrap("Acceptée", "Acceptée", body)
    if template == "order_ready":
        subject = f"Commande prête · #{order.get('order_number')}"
        body = (
            f"<p>Bonjour {name},</p>"
            f"<p>Ta commande <b>#{order.get('order_number')}</b> est prête. À toi de jouer !</p>"
            f"{pickup_html}"
        )
        return subject, _wrap("Prête", "Ready", body)
    if template == "out_for_delivery":
        subject = f"En livraison · #{order.get('order_number')}"
        body = (
            f"<p>Bonjour {name},</p>"
            f"<p>Ta commande est partie en livraison.</p>"
        )
        return subject, _wrap("En livraison", "In transit", body)
    if template == "order_cancelled":
        subject = f"Commande annulée · #{order.get('order_number')}"
        body = (
            f"<p>Bonjour {name},</p>"
            f"<p>Ta commande <b>#{order.get('order_number')}</b> a été annulée. On est désolé pour la gêne.</p>"
        )
        return subject, _wrap("Annulée", "Cancelled", body)

    subject = f"Mise à jour · #{order.get('order_number')}"
    body = f"<p>Bonjour {name}, mise à jour de commande.</p>"
    return subject, _wrap("Mise à jour", template, body)


async def send_order_email(order: Dict[str, Any], template: str) -> None:
    """Fire-and-forget: never raise. Wrap the caller in try/except anyway."""
    if not is_configured():
        logger.info("Resend not configured; skipping email %s", template)
        return
    email = order.get("customer_email")
    if not email:
        return
    subject, html = _template(order, template)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": _from_email(),
                    "to": [email],
                    "subject": subject,
                    "html": html,
                },
            )
            if r.status_code >= 300:
                logger.warning("Resend send failed: %s %s", r.status_code, r.text)
    except Exception:  # noqa: BLE001
        logger.exception("Resend send exception")
