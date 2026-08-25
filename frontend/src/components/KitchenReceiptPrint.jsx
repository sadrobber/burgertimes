import React from "react";

const FULFILLMENT_LABEL = { pickup: "A EMPORTER", delivery: "LIVRAISON" };
const PAYMENT_LABEL = { cash: "Especes sur place", card_in_person: "Carte sur place" };

function fmtDateTime(iso) {
  try {
    const d = new Date(iso);
    return {
      date: d.toLocaleDateString("fr-FR"),
      time: d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }),
    };
  } catch {
    return { date: "", time: "" };
  }
}

/**
 * Hidden-on-screen, visible-only-in-@media-print 80mm kitchen ticket.
 * Rendered from the authoritative order object returned by the backend
 * (never from cart/frontend-only state). See index.css for the print rules
 * that hide the rest of the kitchen UI and size this for an 80mm printer.
 */
export default function KitchenReceiptPrint({ order }) {
  if (!order) return null;

  const { date, time } = fmtDateTime(order.created_at);
  const customerName = `${order.customer_first_name || ""} ${order.customer_last_name || ""}`.trim();
  const cleanNote = (order.notes || "").replace("[TEST ORDER]", "").trim();
  const fulfillmentLabel = FULFILLMENT_LABEL[order.fulfillment] || "SUR PLACE";

  return (
    <div id="kitchen-print-area">
      <div className="kr-center kr-bold kr-xl">BURGER TIMES</div>
      <div className="kr-divider" />
      <div className="kr-center kr-bold kr-xxl">COMMANDE #{order.order_number}</div>
      <div className="kr-center kr-bold">{fulfillmentLabel}</div>
      <div className="kr-row">
        <span>{date}</span>
        <span>{time}</span>
      </div>
      <div className="kr-divider" />

      {(order.items || []).map((it, i) => (
        <div key={i} className="kr-item">
          <div className="kr-bold">
            {it.quantity}x {it.name}
          </div>
          <div className="kr-mods">
            {it.burger_config?.size?.label && <div>Taille : {it.burger_config.size.label}</div>}
            {(it.burger_config?.meats || []).map((m) => (
              <div key={m.id || m.name}>+ {m.name}</div>
            ))}
            {(it.burger_config?.cheeses || []).map((c) => (
              <div key={c.id || c.name}>+ {c.name}</div>
            ))}
            {(it.burger_config?.supplements || []).map((s) => (
              <div key={s.id || s.name}>+ {s.name}</div>
            ))}
            {it.selected_format && <div>{it.selected_format}</div>}
            {it.formula === "menu" && it.included_drink && <div>Boisson : {it.included_drink}</div>}
            {(it.sauces || []).map((s) => (
              <div key={s}>+ {s}</div>
            ))}
          </div>
          {it.notes && <div className="kr-callout">{it.notes}</div>}
          <div className="kr-divider-thin" />
        </div>
      ))}

      {cleanNote && (
        <div className="kr-note">
          <div className="kr-bold">NOTE CLIENT :</div>
          <div className="kr-bold">{cleanNote.toUpperCase()}</div>
        </div>
      )}

      <div className="kr-divider" />
      <div className="kr-row kr-bold kr-lg">
        <span>TOTAL :</span>
        <span>{(order.total || 0).toFixed(2).replace(".", ",")} EUR</span>
      </div>
      <div className="kr-divider" />

      {order.fulfillment === "delivery" ? (
        <div className="kr-block">
          <div className="kr-bold">LIVRAISON</div>
          {customerName && <div>Client : {customerName}</div>}
          {order.customer_phone && <div>Tel : {order.customer_phone}</div>}
          {(order.address_line1 || order.address_line2) && (
            <div>
              {order.address_line1}
              {order.address_line2 ? `, ${order.address_line2}` : ""}
            </div>
          )}
          {(order.postal_code || order.city) && (
            <div>
              {order.postal_code} {order.city}
            </div>
          )}
        </div>
      ) : (
        <div className="kr-block">
          <div className="kr-bold">{fulfillmentLabel}</div>
          {customerName && <div>Client : {customerName}</div>}
          {order.customer_phone && <div>Tel : {order.customer_phone}</div>}
          {order.pickup_code && <div>Code retrait : {order.pickup_code}</div>}
        </div>
      )}

      <div className="kr-block">Paiement : {PAYMENT_LABEL[order.payment_method] || order.payment_method}</div>
    </div>
  );
}
