import React, { useEffect, useState } from "react";
import { BarChart3, CreditCard, PackageCheck, ShoppingBag, Truck, X } from "lucide-react";
import { toast } from "sonner";
import { adminClient, fmtError, formatEur } from "@/lib/api";

const STATUS_LABELS = {
  pending: "En attente",
  accepted: "Acceptée",
  preparing: "Préparation",
  ready: "Prête",
  delivering: "Livraison",
  delivered: "Livrée",
  cancelled: "Annulée",
  expired: "Expirée",
};

export default function TabletOrdersAdmin() {
  const [orders, setOrders] = useState([]);
  const [stats, setStats] = useState(null);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(null);

  const load = () => {
    const query = status ? `?status=${status}` : "";
    Promise.all([
      adminClient.get(`/admin/tablet/orders${query}`),
      adminClient.get("/admin/stats/tablet"),
    ])
      .then(([ordersResponse, statsResponse]) => {
        setOrders(ordersResponse.data || []);
        setStats(statsResponse.data || null);
      })
      .catch((error) => toast.error(fmtError(error)));
  };

  useEffect(() => {
    load();
  }, [status]);

  const kpis = [
    { key: "today_orders", label: "Aujourd'hui", icon: BarChart3, value: stats?.today_orders || 0 },
    { key: "valid_orders", label: "Commandes valides", icon: PackageCheck, value: stats?.valid_orders || 0 },
    { key: "revenue", label: "Chiffre tablette", icon: CreditCard, value: formatEur(stats?.revenue || 0) },
    { key: "avg_basket", label: "Panier moyen", icon: ShoppingBag, value: formatEur(stats?.avg_basket || 0) },
  ];

  return (
    <div className="space-y-7" data-testid="tablet-orders-admin-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="font-marker text-[#EF2B2D] -rotate-1">Canal séparé</div>
          <h1 className="font-display text-5xl uppercase leading-none">Ventes tablette</h1>
          <p className="mt-2 text-sm text-[#A1A1A1]">
            Ces commandes et ces totaux ne sont pas inclus dans Commandes ou Livraisons.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className={`bt-chip ${status === "" ? "active" : ""}`}
            data-testid="tablet-orders-filter-all"
            onClick={() => setStatus("")}
          >
            Toutes
          </button>
          {Object.entries(STATUS_LABELS).slice(0, 5).map(([key, label]) => (
            <button
              className={`bt-chip ${status === key ? "active" : ""}`}
              data-testid={`tablet-orders-filter-${key}`}
              key={key}
              onClick={() => setStatus(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div className="bt-card p-5" data-testid={`tablet-orders-kpi-${kpi.key}`} key={kpi.key}>
              <div className="flex items-center justify-between">
                <div className="bt-label m-0">{kpi.label}</div>
                <Icon className="h-4 w-4 text-[#EF2B2D]" />
              </div>
              <div className="mt-2 font-display text-3xl">{kpi.value}</div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="bt-card p-4 text-sm">
          <Truck className="mr-2 inline h-4 w-4 text-[#EF2B2D]" />
          Livraisons tablette : <b data-testid="tablet-orders-delivery-count">{stats?.delivery_orders || 0}</b>
        </div>
        <div className="bt-card p-4 text-sm">
          <ShoppingBag className="mr-2 inline h-4 w-4 text-[#EF2B2D]" />
          À emporter tablette : <b data-testid="tablet-orders-pickup-count">{stats?.pickup_orders || 0}</b>
        </div>
      </div>

      <div className="bt-card p-4">
        {orders.length === 0 ? (
          <div className="py-10 text-center text-sm text-[#A1A1A1]" data-testid="tablet-orders-empty">
            Aucune commande tablette.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-accent uppercase tracking-widest text-[#A1A1A1]">
                  <th className="py-2 pr-4">N°</th>
                  <th className="py-2 pr-4">Client</th>
                  <th className="py-2 pr-4">Pris par</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Statut</th>
                  <th className="py-2 pr-4 text-right">Total</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr className="border-t border-[#262626]" data-testid={`tablet-admin-order-${order.id}`} key={order.id}>
                    <td className="py-3 pr-4 font-display">{order.order_number}</td>
                    <td className="py-3 pr-4">{order.customer_first_name} {order.customer_last_name}</td>
                    <td className="py-3 pr-4 text-xs text-[#A1A1A1]">{order.tablet_taken_by || "Tablette"}</td>
                    <td className="py-3 pr-4">{order.fulfillment}</td>
                    <td className="py-3 pr-4"><span className="bt-badge-red">{STATUS_LABELS[order.status] || order.status}</span></td>
                    <td className="py-3 pr-4 text-right">{formatEur(order.total)}</td>
                    <td className="py-3 text-right">
                      <button
                        className="bt-btn-ghost px-2 text-xs"
                        data-testid={`tablet-admin-order-detail-${order.id}`}
                        onClick={() => setSelected(order)}
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

      {selected && <TabletOrderDetail order={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function TabletOrderDetail({ order, onClose }) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/70 p-0 md:items-center md:p-4">
      <div className="max-h-[90vh] w-full overflow-y-auto border-2 border-[#EF2B2D] bg-[#141414] p-5 md:max-w-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="font-display text-3xl">#{order.order_number}</div>
            <div className="text-xs text-[#A1A1A1]">{new Date(order.created_at).toLocaleString("fr-FR")}</div>
          </div>
          <button className="bt-btn-ghost h-10 w-10 p-0" data-testid="tablet-admin-close-detail" onClick={onClose}>
            <X className="mx-auto h-4 w-4" />
          </button>
        </div>
        <div className="mt-5 space-y-4 text-sm">
          <div>
            <div className="bt-label">Client</div>
            <div>{order.customer_first_name} {order.customer_last_name}</div>
            <div className="text-[#A1A1A1]">{order.customer_phone}</div>
          </div>
          <div>
            <div className="bt-label">Articles</div>
            {(order.items || []).map((item, index) => (
              <div className="border-b border-[#262626] py-2" key={`${item.name}-${index}`}>
                <div className="flex justify-between"><span>{item.quantity}× {item.name}</span><span>{formatEur(item.line_total)}</span></div>
                {(item.sauces || []).length > 0 && <div className="text-xs text-[#A1A1A1]">Sauces : {item.sauces.join(", ")}</div>}
                {item.notes && <div className="text-xs text-[#EF2B2D]">{item.notes}</div>}
              </div>
            ))}
          </div>
          <div className="flex justify-between border-t-2 border-[#262626] pt-3 font-display text-2xl text-[#EF2B2D]">
            <span>Total</span><span>{formatEur(order.total)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}