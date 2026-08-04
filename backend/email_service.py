"""Emergent-managed Resend email service.

Sends transactional emails through the platform proxy at
``https://integrations.emergentagent.com``. Authenticated with a per-app
``X-Email-Key`` header. The ``from_name`` (display name) is REQUIRED on every
send and read from the ``EMAIL_FROM_NAME`` env var; the from-address itself is
managed by the platform and cannot be overridden.

Safe when ``EMERGENT_EMAIL_KEY`` is unset — every call becomes a no-op.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# CONSTANT — do not read from env. This survives deployment.
EMAIL_BASE_URL = "https://integrations.emergentagent.com"


def _email_key() -> Optional[str]:
    v = os.environ.get("EMERGENT_EMAIL_KEY")
    return v if v else None


def _from_name() -> str:
    return os.environ.get("EMAIL_FROM_NAME") or "Burger Times"


def is_configured() -> bool:
    return bool(_email_key())


def _fmt_eur(v: float) -> str:
    return f"{v:.2f} €"


def _wrap(title: str, status_pill: str, body: str) -> str:
    """Table-based email shell with inline styles for max client compatibility."""
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
      style="background:#0A0A0A;padding:24px 0;font-family:Arial,Helvetica,sans-serif;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0"
            style="max-width:560px;width:100%;background:#141414;border:2px solid #EF2B2D;">
            <tr>
              <td style="padding:24px;color:#F5F1E8;">
                <div style="font-family:Impact,'Arial Black',Arial,sans-serif;text-transform:uppercase;color:#EF2B2D;font-size:22px;letter-spacing:1px;margin:0 0 12px 0;">Burger Times</div>
                <div style="display:inline-block;padding:4px 10px;background:#EF2B2D;color:#F5F1E8;font-weight:bold;text-transform:uppercase;font-size:12px;letter-spacing:1px;margin-bottom:16px;">{status_pill}</div>
                <h2 style="margin:0 0 12px 0;color:#F5F1E8;font-size:22px;">{title}</h2>
                {body}
                <hr style="border:none;border-top:1px solid #262626;margin:24px 0;" />
                <p style="color:#666;font-size:12px;margin:0;line-height:1.5;">
                  Burger Times &middot; 6 Avenue de Villaine, 06240 Beausoleil &middot; 04.97.07.17.93
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


def _items_html(order: Dict[str, Any]) -> str:
    rows = []
    for it in (order.get("items") or []):
        rows.append(
            f"<tr>"
            f"<td style='padding:6px 0;color:#F5F1E8;'>{it['quantity']}&times; {it['name']}</td>"
            f"<td style='padding:6px 0;color:#F5F1E8;text-align:right;'>{_fmt_eur(it['line_total'])}</td>"
            f"</tr>"
        )
    return (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
        "style='border-collapse:collapse;'>"
        + "".join(rows)
        + "</table>"
    )


def _template(order: Dict[str, Any], template: str) -> Tuple[str, str]:
    name = f"{order.get('customer_first_name','')} {order.get('customer_last_name','')}".strip()
    total = _fmt_eur(order.get("total", 0))
    subtotal = _fmt_eur(order.get("subtotal", 0))
    delivery_fee = order.get("delivery_fee", 0)
    pay = "Cash sur place" if order.get("payment_method") == "cash" else "Carte sur place"
    fulfillment = "Retrait" if order.get("fulfillment") == "pickup" else "Livraison"
    pickup_code = order.get("pickup_code")

    items_html = _items_html(order)
    delivery_line = (
        f"<p style='color:#F5F1E8;margin:0 0 4px 0;'>Livraison : {_fmt_eur(delivery_fee)}</p>"
        if delivery_fee
        else ""
    )
    totals_html = (
        f"<p style='color:#F5F1E8;margin:12px 0 4px 0;'>Sous-total : {subtotal}</p>"
        f"{delivery_line}"
        f"<p style='color:#EF2B2D;font-size:20px;font-weight:bold;margin:0;'>Total : {total}</p>"
    )
    pickup_html = (
        f"<p style='color:#FFB800;font-weight:bold;margin:12px 0;'>&#128274; Code de retrait : {pickup_code}</p>"
        if pickup_code
        else ""
    )

    if template == "order_confirmed":
        subject = f"Commande confirmée · #{order.get('order_number')}"
        body = (
            f"<p style='color:#F5F1E8;'>Bonjour {name},</p>"
            f"<p style='color:#F5F1E8;'>On a bien reçu ta commande <b>#{order.get('order_number')}</b>. On la prépare bientôt.</p>"
            f"<p style='color:#F5F1E8;'>Type : <b>{fulfillment}</b> &middot; Paiement : <b>{pay}</b></p>"
            f"{pickup_html}"
            f"{items_html}"
            f"{totals_html}"
        )
        return subject, _wrap("Commande reçue", "En attente", body)
    if template == "order_accepted":
        subject = f"Commande acceptée · #{order.get('order_number')}"
        body = (
            f"<p style='color:#F5F1E8;'>Bonjour {name},</p>"
            f"<p style='color:#F5F1E8;'>Ta commande <b>#{order.get('order_number')}</b> est acceptée. Elle passe en cuisine.</p>"
            f"{pickup_html}"
        )
        return subject, _wrap("Acceptée", "Acceptée", body)
    if template == "order_ready":
        subject = f"Commande prête · #{order.get('order_number')}"
        body = (
            f"<p style='color:#F5F1E8;'>Bonjour {name},</p>"
            f"<p style='color:#F5F1E8;'>Ta commande <b>#{order.get('order_number')}</b> est prête. À toi de jouer !</p>"
            f"{pickup_html}"
        )
        return subject, _wrap("Prête", "Ready", body)
    if template == "out_for_delivery":
        subject = f"En livraison · #{order.get('order_number')}"
        body = (
            f"<p style='color:#F5F1E8;'>Bonjour {name},</p>"
            f"<p style='color:#F5F1E8;'>Ta commande est partie en livraison.</p>"
        )
        return subject, _wrap("En livraison", "In transit", body)
    if template == "order_cancelled":
        subject = f"Commande annulée · #{order.get('order_number')}"
        body = (
            f"<p style='color:#F5F1E8;'>Bonjour {name},</p>"
            f"<p style='color:#F5F1E8;'>Ta commande <b>#{order.get('order_number')}</b> a été annulée. On est désolé pour la gêne.</p>"
        )
        return subject, _wrap("Annulée", "Cancelled", body)

    subject = f"Mise à jour · #{order.get('order_number')}"
    body = f"<p style='color:#F5F1E8;'>Bonjour {name}, mise à jour de commande.</p>"
    return subject, _wrap("Mise à jour", template, body)


async def _post_email(to: str, subject: str, html: str) -> bool:
    """Low-level send. Never raises. Returns True on 2xx."""
    if not is_configured() or not to:
        return False
    payload: Dict[str, Any] = {
        "to": [to],
        "subject": subject,
        "html": html,
        "from_name": _from_name(),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": _email_key()},
                json=payload,
            )
            if r.status_code >= 300:
                logger.warning("Email send failed: %s %s", r.status_code, r.text)
                return False
            logger.info("Email sent to %s (subject=%r)", to, subject)
            return True
    except Exception:  # noqa: BLE001
        logger.exception("Email send exception")
        return False


async def send_order_email(order: Dict[str, Any], template: str) -> None:
    """Fire-and-forget order lifecycle email. Never raises."""
    if not is_configured():
        logger.info("Email not configured; skipping %s", template)
        return
    email = order.get("customer_email")
    if not email:
        return
    subject, html = _template(order, template)
    await _post_email(email, subject, html)


async def send_open_notice(email: str) -> bool:
    """Notify a waitlist subscriber that the restaurant just opened."""
    if not is_configured() or not email:
        return False
    subject = "Burger Times · On est ouvert !"
    body = (
        "<p style='color:#F5F1E8;'>Tu voulais être prévenu — c'est l'heure.</p>"
        "<p style='color:#F5F1E8;'>La cuisine est chaude, les smash sont prêts. "
        "Passe commande tant qu'il y a de la place.</p>"
    )
    html = _wrap("On est ouvert", "Open", body)
    return await _post_email(email, subject, html)
