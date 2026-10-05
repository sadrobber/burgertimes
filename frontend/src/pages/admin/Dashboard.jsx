import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminClient, formatEur } from "@/lib/api";
import { useAdminAuth } from "@/context/AdminAuthContext.jsx";
import { ClipboardList, Euro, ShoppingBag, Timer } from "lucide-react";

export default function Dashboard() {
  const { role } = useAdminAuth();
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    adminClient.get("/admin/stats").then((r) => setStats(r.data)).catch(() => {});
    adminClient.get("/admin/orders?limit=6").then((r) => setRecent(r.data || [])).catch(() => {});
  }, []);

  const cards = [
    { key: "total_orders", label: "Total commandes", icon: ShoppingBag, color: "#F5F1E8" },
    { key: "paid_orders", label: "Payées", icon: Euro, color: "#00FF66" },
    { key: "pending_orders", label: "En cours", icon: Timer, color: "#FFB800" },
    { key: "revenue", label: "Chiffre d\u2019affaires", icon: Euro, color: "#EF2B2D", fmt: (v) => formatEur(v) },
  ];

  return (
    <div className="space-y-8">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">État des lieux</div>
        <h1 className="font-display text-5xl uppercase leading-none">Dashboard</h1>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div key={c.key} className="bt-card p-5" data-testid={`stat-${c.key}`}>
            <div className="flex items-center justify-between">
              <div className="bt-label m-0">{c.label}</div>
              <c.icon className="w-4 h-4" style={{ color: c.color }} />
            </div>
            <div className="font-display text-4xl mt-2" style={{ color: c.color }}>
              {stats ? (c.fmt ? c.fmt(stats[c.key]) : stats[c.key]) : "…"}
            </div>
          </div>
        ))}
      </div>

      <div className="bt-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="font-display text-2xl uppercase">Commandes récentes</div>
          {role !== "manager" && (
            <Link to="/admin/orders" className="bt-btn-ghost px-2 text-sm">Tout voir</Link>
          )}
        </div>
        {recent.length === 0 ? (
          <div className="text-sm text-[#A1A1A1] py-8 text-center">Aucune commande pour l&apos;instant.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs">
                  <th className="py-2 pr-4">N°</th>
                  <th className="py-2 pr-4">Client</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Statut</th>
                  <th className="py-2 pr-4 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((o) => (
                  <tr key={o.id} className="border-t border-[#262626]" data-testid={`recent-order-${o.id}`}>
                    <td className="py-3 pr-4 font-display">{o.order_number}</td>
                    <td className="py-3 pr-4">{o.customer_first_name} {o.customer_last_name}</td>
                    <td className="py-3 pr-4">{o.fulfillment}</td>
                    <td className="py-3 pr-4">
                      <span className="bt-badge-red">{o.status}</span>
                    </td>
                    <td className="py-3 pr-4 text-right">{formatEur(o.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
