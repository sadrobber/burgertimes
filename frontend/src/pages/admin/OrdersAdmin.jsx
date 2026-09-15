import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError, formatEur } from "@/lib/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Trash2, X } from "lucide-react";

const STATUS_FLOW = [
  "pending",
  "accepted",
  "preparing",
  "ready",
  "delivering",
  "delivered",
];

const STATUS_LABEL = {
  pending: "En attente",
  accepted: "Acceptée",
  preparing: "Préparation",
  ready: "Prête",
  delivering: "Livraison",
  delivered: "Livrée",
  cancelled: "Annulée",
  expired: "Expirée",
};

const FULFILLMENT_LABEL = { pickup: "A EMPORTER", delivery: "LIVRAISON" };
const PAYMENT_LABEL = { cash: "Especes sur place", card_in_person: "Carte sur place" };

// Item header line: qty + name (already "Menu ..." prefixed by the
// backend when applicable) + meat names directly in parens right after —
// no "Taille : N Viandes" label, just the meats themselves. Cheeses/
// supplements/sauces get their own "+ ..." line below.
function buildItemLine(it) {
  const cfg = it.burger_config || {};
  const meats = (cfg.meats || []).map((x) => (typeof x === "string" ? x : x.name));
  let line = `${it.quantity}x ${it.name}`;
  if (meats.length) line += ` (${meats.join(", ")})`;
  return line;
}

// Plain-text 80mm ticket for the RawBT Android print app (no HTML/CSS —
// RawBT just spools raw text to the paired thermal printer).
function buildReceiptText(order) {
  const line = "--------------------------------";
  const created = new Date(order.created_at);
  const dateStr = created.toLocaleDateString("fr-FR");
  const timeStr = created.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const customerName = `${order.customer_first_name || ""} ${order.customer_last_name || ""}`.trim();

  const itemLines = (order.items || []).flatMap((it) => {
    const cfg = it.burger_config || {};
    const rows = [buildItemLine(it)];
    [...(cfg.cheeses || []), ...(cfg.supplements || [])].forEach((x) =>
      rows.push(`  + ${typeof x === "string" ? x : x.name}`)
    );
    (it.sauces || []).forEach((s) => rows.push(`  + ${s}`));
    if (it.burger_config && cfg.sauce_fromagere === false) rows.push("  - sans from");
    if (it.formula === "menu" && it.included_drink) rows.push(`  Boisson : ${it.included_drink}`);
    if (it.notes) rows.push(`  Note : ${it.notes}`);
    return rows;
  });

  const rows = [
    "BURGER TIMES",
    line,
    `COMMANDE #${order.order_number}`,
    FULFILLMENT_LABEL[order.fulfillment] || "SUR PLACE",
    `${dateStr} ${timeStr}`,
    line,
    ...itemLines,
    order.notes ? `Note : ${order.notes}` : null,
    line,
    `TOTAL : ${(order.total || 0).toFixed(2).replace(".", ",")} EUR`,
    line,
    customerName ? `Client : ${customerName}` : null,
    order.customer_phone ? `Tel : ${order.customer_phone}` : null,
    order.fulfillment === "delivery"
      ? [order.address_line1, order.address_line2].filter(Boolean).join(", ") || null
      : null,
    order.fulfillment === "delivery" && (order.postal_code || order.city)
      ? `${order.postal_code || ""} ${order.city || ""}`.trim()
      : null,
    order.pickup_code ? `Code retrait : ${order.pickup_code}` : null,
    `Paiement : ${PAYMENT_LABEL[order.payment_method] || order.payment_method}`,
    "",
    "",
  ].filter((r) => r !== null);

  return rows.join("\n");
}

// Hands the receipt straight to the RawBT Android app via its Intent
// scheme — no backend bridge, no SUNMI Cloud API. RawBT (once installed
// and paired with the thermal printer) spools whatever text it receives.
function printOrder(receiptText) {
  const intentUrl =
    "intent:" +
    encodeURIComponent(receiptText) +
    "#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;";
  window.location.href = intentUrl;
}

export default function OrdersAdmin() {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("");

  const load = () => {
    const q = filter ? `?status=${filter}` : "";
    adminClient.get(`/admin/orders${q}`).then((r) => setOrders(r.data || [])).catch(() => {});
  };

  useEffect(() => { load(); }, [filter]);

  const changeStatus = async (id, status) => {
    try {
      await adminClient.put(`/admin/orders/${id}/status`, { status });
      toast.success(`Statut → ${STATUS_LABEL[status] || status}`);
      load();
      if (selected && selected.id === id) {
        const r = await adminClient.get(`/admin/orders/${id}`);
        setSelected(r.data);
      }
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const hardDelete = async (id) => {
    try {
      await adminClient.delete(`/admin/orders/${id}`);
      toast.success("Commande supprimée");
      setSelected(null);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="font-marker text-[#EF2B2D] -rotate-1">Cuisine</div>
          <h1 className="font-display text-5xl uppercase leading-none">Commandes</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setFilter("")} data-testid="filter-all" className={`bt-chip ${filter === "" ? "active" : ""}`}>
            Toutes
          </button>
          {["pending", "accepted", "preparing", "ready", "cancelled"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              data-testid={`filter-${s}`}
              className={`bt-chip ${filter === s ? "active" : ""}`}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
      </div>

      <div className="bt-card p-4">
        {orders.length === 0 ? (
          <div className="text-sm text-[#A1A1A1] py-10 text-center">Aucune commande.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs">
                  <th className="py-2 pr-4">N°</th>
                  <th className="py-2 pr-4">Client</th>
                  <th className="py-2 pr-4">Tel</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Paiement</th>
                  <th className="py-2 pr-4">Statut</th>
                  <th className="py-2 pr-4 text-right">Total</th>
                  <th className="py-2 pr-4"></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-t border-[#262626]" data-testid={`admin-order-${o.id}`}>
                    <td className="py-3 pr-4 font-display">{o.order_number}</td>
                    <td className="py-3 pr-4">{o.customer_first_name} {o.customer_last_name}</td>
                    <td className="py-3 pr-4">{o.customer_phone}</td>
                    <td className="py-3 pr-4">{o.fulfillment}</td>
                    <td className="py-3 pr-4">{o.payment_method}</td>
                    <td className="py-3 pr-4">
                      <span className="bt-badge-red">{STATUS_LABEL[o.status] || o.status}</span>
                    </td>
                    <td className="py-3 pr-4 text-right">{formatEur(o.total)}</td>
                    <td className="py-3 pr-4 text-right">
                      <button
                        data-testid={`open-order-${o.id}`}
                        onClick={() => setSelected(o)}
                        className="bt-btn-ghost px-2 text-xs"
                      >
                        Détail
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && (
        <OrderDrawer
          order={selected}
          onClose={() => setSelected(null)}
          onStatus={(s) => changeStatus(selected.id, s)}
          onDelete={() => hardDelete(selected.id)}
        />
      )}
    </div>
  );
}

function OrderDrawer({ order, onClose, onStatus, onDelete }) {
  const idx = STATUS_FLOW.indexOf(order.status);
  const nextStatus = idx >= 0 && idx < STATUS_FLOW.length - 1 ? STATUS_FLOW[idx + 1] : null;
  return (
    <div className="fixed inset-0 z-40 bg-black/70 flex items-end md:items-center justify-center p-0 md:p-4" data-testid="order-drawer">
      <div className="bg-[#141414] border-2 border-[#EF2B2D] w-full md:max-w-2xl max-h-[90vh] flex flex-col">
        <div className="p-4 border-b-2 border-[#262626] flex items-center justify-between">
          <div>
            <div className="font-display text-2xl uppercase leading-none">
              #{order.order_number}
            </div>
            <div className="text-xs text-[#A1A1A1] mt-1">
              {new Date(order.created_at).toLocaleString()}
            </div>
          </div>
          <button onClick={onClose} className="w-9 h-9 border-2 border-[#262626]" data-testid="close-drawer">
            <X className="w-4 h-4 mx-auto" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div>
            <div className="bt-label">Client</div>
            <div>{order.customer_first_name} {order.customer_last_name}</div>
            <div className="text-sm text-[#B3B3B3]">{order.customer_phone}</div>
            {order.customer_email && <div className="text-sm text-[#B3B3B3]">{order.customer_email}</div>}
          </div>
          {order.fulfillment === "delivery" && (
            <div>
              <div className="bt-label">Adresse</div>
              <div className="text-sm">
                {order.address_line1}{order.address_line2 ? `, ${order.address_line2}` : ""}, {order.postal_code} {order.city}
              </div>
            </div>
          )}
          <div>
            <div className="bt-label">Items</div>
            <div className="space-y-2">
              {(order.items || []).map((it, i) => (
                <div key={i} className="border-b border-[#262626] pb-2 text-sm">
                  <div className="flex justify-between">
                    <div>{it.quantity}× {it.name}</div>
                    <div>{formatEur(it.line_total)}</div>
                  </div>
                  {it.burger_config && (
                    <div className="text-xs text-[#A1A1A1] mt-1 space-y-0.5">
                      {it.burger_config.size?.label && <div>Taille : {it.burger_config.size.label}</div>}
                      {(it.burger_config.meats || []).length > 0 && (
                        <div>Viandes : {it.burger_config.meats.map((m) => m.name).join(", ")}</div>
                      )}
                      {(it.burger_config.cheeses || []).length > 0 && (
                        <div>Fromages : {it.burger_config.cheeses.map((c) => c.name).join(", ")}</div>
                      )}
                      {(it.burger_config.supplements || []).length > 0 && (
                        <div>Supp. : {it.burger_config.supplements.map((s) => s.name).join(", ")}</div>
                      )}
                      {it.burger_config.sauce_fromagere === false && (
                        <div className="text-[#EF2B2D]">- sans from</div>
                      )}
                    </div>
                  )}
                  {it.formula === "menu" && it.included_drink && (
                    <div className="text-xs text-[#A1A1A1]">Boisson : {it.included_drink}</div>
                  )}
                  {(it.sauces || []).length > 0 && (
                    <div className="text-xs text-[#A1A1A1]">Sauces : {it.sauces.join(", ")}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between"><span>Sous-total</span><span>{formatEur(order.subtotal)}</span></div>
            {order.delivery_fee > 0 && (
              <div className="flex justify-between"><span>Livraison</span><span>{formatEur(order.delivery_fee)}</span></div>
            )}
            <div className="flex justify-between font-display text-2xl text-[#EF2B2D]">
              <span>Total</span><span>{formatEur(order.total)}</span>
            </div>
          </div>
          {order.pickup_code && (
            <div className="bt-card border-[#FFB800] p-4 text-center">
              <div className="bt-label">Code retrait</div>
              <div className="font-display text-4xl text-[#FFB800]">{order.pickup_code}</div>
            </div>
          )}
          {order.notes && (
            <div>
              <div className="bt-label">Notes</div>
              <div className="text-sm">{order.notes}</div>
            </div>
          )}
        </div>
        <div className="p-4 border-t-2 border-[#262626] flex flex-wrap gap-2 justify-between bg-[#0A0A0A]">
          <div className="flex flex-wrap gap-2">
            {nextStatus === "accepted" ? (
              <button
                data-testid="accept-print-order-btn"
                onClick={() => {
                  onStatus("accepted");
                  printOrder(buildReceiptText(order));
                }}
                className="bt-btn-primary py-2 px-4 text-sm"
              >
                Accepter &amp; Imprimer
              </button>
            ) : (
              nextStatus && (
                <button
                  data-testid={`advance-to-${nextStatus}`}
                  onClick={() => onStatus(nextStatus)}
                  className="bt-btn-primary py-2 px-4 text-sm"
                >
                  → {STATUS_LABEL[nextStatus]}
                </button>
              )
            )}
            {order.status !== "cancelled" && order.status !== "delivered" && (
              <button
                data-testid="cancel-order-btn"
                onClick={() => onStatus("cancelled")}
                className="bt-btn-secondary py-2 px-4 text-sm border-[#FF3B30] text-[#FF3B30]"
              >
                Annuler
              </button>
            )}
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
                data-testid="delete-order-btn"
                className="bt-btn-secondary py-2 px-4 text-sm border-[#EF2B2D] text-[#EF2B2D]"
              >
                <Trash2 className="w-4 h-4" /> Supprimer
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent className="bg-[#141414] border-2 border-[#EF2B2D] rounded-none text-[#F5F1E8]">
              <AlertDialogHeader>
                <AlertDialogTitle>Supprimer cette commande ?</AlertDialogTitle>
                <AlertDialogDescription>
                  Action définitive. Utilise-la pour scrub les tests.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel className="rounded-none">Annuler</AlertDialogCancel>
                <AlertDialogAction data-testid="confirm-delete-order" className="rounded-none bg-[#EF2B2D]" onClick={onDelete}>
                  Confirmer
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
    </div>
  );
}
