import React, { useEffect, useMemo, useState } from "react";
import { adminClient, formatEur } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Truck, Wallet, CalendarDays, Receipt, TrendingUp, Banknote, CreditCard } from "lucide-react";

const RANGES = [
  { key: 7, label: "7 jours" },
  { key: 14, label: "14 jours" },
  { key: 30, label: "30 jours" },
  { key: 90, label: "90 jours" },
  { key: 365, label: "1 an" },
];

const RED = "#EF2B2D";

function ShortDate({ iso }) {
  // "2026-02-14" -> "14 fév"
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="bt-card p-3 text-xs">
      <div className="font-accent uppercase tracking-widest text-[#EF2B2D]">
        <ShortDate iso={p.date} />
      </div>
      <div className="mt-1">Livraisons : <b>{p.orders}</b></div>
      <div>Frais collectés : <b>{formatEur(p.delivery_fees)}</b></div>
      <div className="text-[#A1A1A1] mt-1">Panier livraison : {formatEur(p.subtotal)}</div>
    </div>
  );
}

export default function DeliveryStatsAdmin() {
  const [stats, setStats] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  // Only the applied dates trigger a fetch — typing in the inputs alone
  // shouldn't refire the request on every keystroke.
  const [appliedRange, setAppliedRange] = useState(null); // { start, end } | null

  useEffect(() => {
    setLoading(true);
    const params = appliedRange
      ? `start_date=${appliedRange.start}&end_date=${appliedRange.end}`
      : `days=${days}`;
    adminClient
      .get(`/admin/stats/delivery-fees?${params}`)
      .then((r) => setStats(r.data))
      .catch((e) => toast.error(e?.response?.data?.detail || "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [days, appliedRange]);

  const applyCustomRange = () => {
    if (!customStart || !customEnd) {
      toast.error("Choisis une date de début et de fin");
      return;
    }
    if (customEnd < customStart) {
      toast.error("La date de fin doit être après la date de début");
      return;
    }
    setAppliedRange({ start: customStart, end: customEnd });
  };

  const resetToPreset = (r) => {
    setAppliedRange(null);
    setCustomStart("");
    setCustomEnd("");
    setDays(r);
  };

  const maxFee = useMemo(() => {
    if (!stats?.daily?.length) return 0;
    return Math.max(...stats.daily.map((d) => d.delivery_fees));
  }, [stats]);

  const kpis = [
    {
      key: "today",
      label: "Aujourd'hui",
      icon: Truck,
      color: "#F5F1E8",
    },
    {
      key: "this_week",
      label: "Cette semaine",
      icon: CalendarDays,
      color: "#FFB800",
    },
    {
      key: "this_month",
      label: "Ce mois",
      icon: Receipt,
      color: "#00FF66",
    },
    {
      key: "all_time",
      label: "Depuis toujours",
      icon: Wallet,
      color: RED,
    },
  ];

  const avgFeeInRange =
    stats && stats.counts?.in_range
      ? stats.totals.in_range / stats.counts.in_range
      : 0;

  return (
    <div className="space-y-8" data-testid="delivery-stats-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="font-marker text-[#EF2B2D] -rotate-1">Livraisons</div>
          <h1 className="font-display text-5xl uppercase leading-none">
            Frais de livraison
          </h1>
          <div className="text-sm text-[#A1A1A1] mt-2">
            Combien tu as encaissé sur la livraison. Fuseau {stats?.timezone || "Europe/Paris"}.
          </div>
        </div>
        <div className="flex flex-col gap-2 items-end">
          <div className="flex flex-wrap gap-2 justify-end">
            {RANGES.map((r) => (
              <button
                key={r.key}
                data-testid={`delivery-stats-range-${r.key}`}
                onClick={() => resetToPreset(r.key)}
                className={`bt-chip ${!appliedRange && days === r.key ? "active" : ""}`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2" data-testid="delivery-stats-custom-range">
            <input
              type="date"
              data-testid="delivery-stats-start-date"
              className="bt-input py-1.5 px-2 text-sm w-auto"
              value={customStart}
              max={customEnd || undefined}
              onChange={(e) => setCustomStart(e.target.value)}
            />
            <span className="text-[#666] text-sm">→</span>
            <input
              type="date"
              data-testid="delivery-stats-end-date"
              className="bt-input py-1.5 px-2 text-sm w-auto"
              value={customEnd}
              min={customStart || undefined}
              onChange={(e) => setCustomEnd(e.target.value)}
            />
            <button
              onClick={applyCustomRange}
              data-testid="delivery-stats-apply-range"
              className="bt-btn-primary py-1.5 px-3 text-xs"
            >
              Appliquer
            </button>
            {appliedRange && (
              <button
                onClick={() => resetToPreset(30)}
                data-testid="delivery-stats-clear-range"
                className="bt-btn-ghost py-1.5 px-2 text-xs text-[#EF2B2D]"
              >
                Réinitialiser
              </button>
            )}
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map((c) => {
          const fee = stats?.totals?.[c.key] ?? 0;
          const cnt = stats?.counts?.[c.key] ?? 0;
          const Icon = c.icon;
          return (
            <div
              key={c.key}
              data-testid={`delivery-stats-kpi-${c.key}`}
              className="bt-card p-5"
            >
              <div className="flex items-center justify-between">
                <div className="bt-label m-0">{c.label}</div>
                <Icon className="w-4 h-4" style={{ color: c.color }} />
              </div>
              <div
                className="font-display text-4xl mt-2"
                style={{ color: c.color }}
              >
                {loading ? "…" : formatEur(fee)}
              </div>
              <div className="text-xs text-[#A1A1A1] mt-1">
                {cnt} livraison{cnt > 1 ? "s" : ""}
              </div>
            </div>
          );
        })}
      </div>

      {/* Range summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bt-card p-5" data-testid="delivery-stats-in-range">
          <div className="bt-label">Frais sur la période</div>
          <div className="font-display text-3xl text-[#EF2B2D]">
            {stats ? formatEur(stats.totals.in_range) : "…"}
          </div>
          <div className="text-xs text-[#A1A1A1] mt-1">
            {stats?.counts?.in_range || 0} livraison{(stats?.counts?.in_range || 0) > 1 ? "s" : ""} ·{" "}
            {stats?.is_custom_range ? (
              <>
                du <ShortDate iso={stats.range_start} /> au <ShortDate iso={stats.range_end} />
              </>
            ) : (
              `derniers ${days}j`
            )}
          </div>
        </div>
        <div className="bt-card p-5">
          <div className="bt-label">Panier livraison sur la période</div>
          <div className="font-display text-3xl">
            {stats ? formatEur(stats.subtotals.in_range) : "…"}
          </div>
          <div className="text-xs text-[#A1A1A1] mt-1">Somme des sous-totaux</div>
        </div>
        <div className="bt-card p-5">
          <div className="bt-label flex items-center gap-2">
            <TrendingUp className="w-3 h-3" /> Frais moyen / livraison
          </div>
          <div className="font-display text-3xl">
            {stats ? formatEur(avgFeeInRange) : "…"}
          </div>
          <div className="text-xs text-[#A1A1A1] mt-1">
            {stats?.is_custom_range ? "Sur la période sélectionnée" : `Sur les ${days} derniers jours`}
          </div>
        </div>
      </div>

      {/* Payment method breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="delivery-stats-by-payment">
        <div className="bt-card p-5" data-testid="delivery-stats-payment-cash">
          <div className="flex items-center justify-between">
            <div className="bt-label m-0">Frais encaissés en espèces</div>
            <Banknote className="w-4 h-4 text-[#00FF66]" />
          </div>
          <div className="font-display text-3xl mt-2" style={{ color: "#00FF66" }}>
            {stats ? formatEur(stats.by_payment?.cash?.delivery_fees || 0) : "…"}
          </div>
          <div className="text-xs text-[#A1A1A1] mt-1">
            {stats?.by_payment?.cash?.orders || 0} livraison{(stats?.by_payment?.cash?.orders || 0) > 1 ? "s" : ""} sur la période
          </div>
        </div>
        <div className="bt-card p-5" data-testid="delivery-stats-payment-card">
          <div className="flex items-center justify-between">
            <div className="bt-label m-0">Frais encaissés en carte</div>
            <CreditCard className="w-4 h-4 text-[#FFB800]" />
          </div>
          <div className="font-display text-3xl mt-2" style={{ color: "#FFB800" }}>
            {stats ? formatEur(stats.by_payment?.card_in_person?.delivery_fees || 0) : "…"}
          </div>
          <div className="text-xs text-[#A1A1A1] mt-1">
            {stats?.by_payment?.card_in_person?.orders || 0} livraison{(stats?.by_payment?.card_in_person?.orders || 0) > 1 ? "s" : ""} sur la période
          </div>
        </div>
      </div>

      {/* Bar chart */}
      <div className="bt-card p-5" data-testid="delivery-stats-chart">
        <div className="flex items-center justify-between mb-4">
          <div className="font-display text-2xl uppercase">Frais par jour</div>
          <div className="text-xs text-[#A1A1A1]">{stats?.daily?.length || 0} jours</div>
        </div>
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={stats?.daily || []} margin={{ top: 8, right: 8, left: 0, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis
                dataKey="date"
                stroke="#A1A1A1"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => {
                  const d = new Date(v + "T12:00:00");
                  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
                }}
                interval="preserveStartEnd"
              />
              <YAxis
                stroke="#A1A1A1"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => `${v}€`}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(239,43,45,0.08)" }} />
              <Bar dataKey="delivery_fees" radius={[0, 0, 0, 0]}>
                {(stats?.daily || []).map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.delivery_fees > 0 ? RED : "#262626"}
                    opacity={
                      maxFee > 0 && entry.delivery_fees > 0
                        ? 0.35 + 0.65 * (entry.delivery_fees / maxFee)
                        : 1
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Daily table */}
      <div className="bt-card p-5">
        <div className="font-display text-2xl uppercase mb-4">Journal des jours</div>
        {stats?.daily?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs">
                  <th className="py-2 pr-4">Jour</th>
                  <th className="py-2 pr-4 text-right">Livraisons</th>
                  <th className="py-2 pr-4 text-right">Panier</th>
                  <th className="py-2 pr-4 text-right">Frais encaissés</th>
                </tr>
              </thead>
              <tbody>
                {[...stats.daily].reverse().map((d) => (
                  <tr
                    key={d.date}
                    className="border-t border-[#262626]"
                    data-testid={`delivery-stats-row-${d.date}`}
                  >
                    <td className="py-3 pr-4 font-accent uppercase tracking-widest">
                      <ShortDate iso={d.date} />
                    </td>
                    <td className="py-3 pr-4 text-right">{d.orders}</td>
                    <td className="py-3 pr-4 text-right text-[#A1A1A1]">
                      {formatEur(d.subtotal)}
                    </td>
                    <td className="py-3 pr-4 text-right font-display text-lg text-[#EF2B2D]">
                      {formatEur(d.delivery_fees)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-sm text-[#A1A1A1] py-8 text-center">
            Aucune livraison enregistrée sur la période.
          </div>
        )}
      </div>
    </div>
  );
}
