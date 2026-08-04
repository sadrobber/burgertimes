import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError } from "@/lib/api";
import { Save, Send } from "lucide-react";

const DAYS = [
  ["mon", "Lundi"],
  ["tue", "Mardi"],
  ["wed", "Mercredi"],
  ["thu", "Jeudi"],
  ["fri", "Vendredi"],
  ["sat", "Samedi"],
  ["sun", "Dimanche"],
];

export default function SettingsAdmin() {
  const [s, setS] = useState(null);

  useEffect(() => {
    adminClient.get("/settings").then((r) => setS(r.data));
  }, []);

  if (!s) return <div>Chargement…</div>;

  const set = (k, v) => setS({ ...s, [k]: v });

  const save = async () => {
    try {
      const { data } = await adminClient.put("/settings", {
        force_closed: s.force_closed,
        closed_message: s.closed_message,
        timezone: s.timezone,
        hours_per_day: s.hours_per_day,
        last_order_buffer_minutes: parseInt(s.last_order_buffer_minutes, 10) || 0,
        closing_soon_window_minutes: parseInt(s.closing_soon_window_minutes, 10) || 0,
        too_busy: s.too_busy,
        too_busy_eta_min: parseInt(s.too_busy_eta_min, 10) || 0,
        too_busy_eta_max: parseInt(s.too_busy_eta_max, 10) || 0,
        eta_default_min: parseInt(s.eta_default_min, 10) || 0,
        eta_default_max: parseInt(s.eta_default_max, 10) || 0,
        soda_flavours: (s.soda_flavours || []).map((v) => v.trim()).filter(Boolean),
        delivery_fee: parseFloat(s.delivery_fee) || 0,
        free_delivery_threshold: s.free_delivery_threshold === null || s.free_delivery_threshold === "" ? null : parseFloat(s.free_delivery_threshold),
        contact_phone: s.contact_phone,
        contact_address: s.contact_address,
        contact_instagram: s.contact_instagram,
      });
      setS(data);
      toast.success("Enregistré");
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const setDay = (key, patch) => {
    const next = { ...(s.hours_per_day || {}) };
    next[key] = { ...(next[key] || { is_open: false, ranges: [] }), ...patch };
    set("hours_per_day", next);
  };
  const addRange = (key) => {
    const day = { ...(s.hours_per_day?.[key] || { is_open: true, ranges: [] }) };
    day.ranges = [...(day.ranges || []), { open: "11:30", close: "14:30" }];
    setDay(key, day);
  };
  const updateRange = (key, i, patch) => {
    const day = { ...(s.hours_per_day?.[key] || { is_open: true, ranges: [] }) };
    day.ranges = [...(day.ranges || [])];
    day.ranges[i] = { ...day.ranges[i], ...patch };
    setDay(key, day);
  };
  const removeRange = (key, i) => {
    const day = { ...(s.hours_per_day?.[key] || { is_open: true, ranges: [] }) };
    day.ranges = [...(day.ranges || [])];
    day.ranges.splice(i, 1);
    setDay(key, day);
  };

  const syncWebhook = async () => {
    try {
      const { data } = await adminClient.post("/telegram/set-webhook");
      if (data.ok) toast.success("Webhook Telegram synchronisé");
      else toast.error(data.description || data.error || "Impossible de synchroniser");
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between">
        <div>
          <div className="font-marker text-[#EF2B2D] -rotate-1">Config</div>
          <h1 className="font-display text-5xl uppercase leading-none">Réglages</h1>
        </div>
        <button onClick={save} data-testid="settings-save" className="bt-btn-primary">
          <Save className="w-4 h-4" /> Enregistrer
        </button>
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Statut</div>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            data-testid="settings-force-closed"
            type="checkbox"
            checked={!!s.force_closed}
            onChange={(e) => set("force_closed", e.target.checked)}
          />
          Fermé manuellement (force_closed)
        </label>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            data-testid="settings-too-busy"
            type="checkbox"
            checked={!!s.too_busy}
            onChange={(e) => set("too_busy", e.target.checked)}
          />
          Trop chargé (ETA rallongée)
        </label>
        <label className="block">
          <div className="bt-label">Message de fermeture</div>
          <input className="bt-input" value={s.closed_message || ""} onChange={(e) => set("closed_message", e.target.value)} />
        </label>
      </div>

      <div className="bt-card p-5 space-y-3">
        <div className="font-display text-2xl uppercase">Horaires</div>
        {DAYS.map(([key, label]) => {
          const d = s.hours_per_day?.[key] || { is_open: false, ranges: [] };
          return (
            <div key={key} className="border border-[#262626] p-3">
              <div className="flex items-center justify-between mb-2">
                <label className="inline-flex items-center gap-2">
                  <input
                    data-testid={`hours-open-${key}`}
                    type="checkbox"
                    checked={!!d.is_open}
                    onChange={(e) => setDay(key, { is_open: e.target.checked })}
                  />
                  <span className="font-accent uppercase tracking-widest">{label}</span>
                </label>
                <button onClick={() => addRange(key)} className="bt-btn-ghost text-xs px-2" data-testid={`hours-add-range-${key}`}>
                  + Créneau
                </button>
              </div>
              {(d.ranges || []).map((r, i) => (
                <div key={i} className="flex items-center gap-2 mt-2">
                  <input
                    type="time"
                    className="bt-input w-32"
                    value={r.open}
                    onChange={(e) => updateRange(key, i, { open: e.target.value })}
                  />
                  <span>—</span>
                  <input
                    type="time"
                    className="bt-input w-32"
                    value={r.close}
                    onChange={(e) => updateRange(key, i, { close: e.target.value })}
                  />
                  <button onClick={() => removeRange(key, i)} className="bt-btn-ghost text-xs px-2 text-[#EF2B2D]">
                    ×
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Cutoff & ETA</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="bt-label">Cutoff (min)</div>
            <input type="number" className="bt-input" value={s.last_order_buffer_minutes || 0} onChange={(e) => set("last_order_buffer_minutes", e.target.value)} />
          </label>
          <label className="block">
            <div className="bt-label">Ferme bientôt (min)</div>
            <input type="number" className="bt-input" value={s.closing_soon_window_minutes || 0} onChange={(e) => set("closing_soon_window_minutes", e.target.value)} />
          </label>
          <label className="block">
            <div className="bt-label">ETA par défaut min</div>
            <input type="number" className="bt-input" value={s.eta_default_min || 0} onChange={(e) => set("eta_default_min", e.target.value)} />
          </label>
          <label className="block">
            <div className="bt-label">ETA par défaut max</div>
            <input type="number" className="bt-input" value={s.eta_default_max || 0} onChange={(e) => set("eta_default_max", e.target.value)} />
          </label>
          <label className="block">
            <div className="bt-label">ETA busy min</div>
            <input type="number" className="bt-input" value={s.too_busy_eta_min || 0} onChange={(e) => set("too_busy_eta_min", e.target.value)} />
          </label>
          <label className="block">
            <div className="bt-label">ETA busy max</div>
            <input type="number" className="bt-input" value={s.too_busy_eta_max || 0} onChange={(e) => set("too_busy_eta_max", e.target.value)} />
          </label>
        </div>
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Livraison</div>
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <div className="bt-label">Frais de livraison (€)</div>
            <input type="number" step="0.1" className="bt-input" value={s.delivery_fee || 0} onChange={(e) => set("delivery_fee", e.target.value)} />
          </label>
          <label className="block">
            <div className="bt-label">Livraison offerte dès (€)</div>
            <input
              type="number"
              step="0.1"
              className="bt-input"
              value={s.free_delivery_threshold ?? ""}
              onChange={(e) => set("free_delivery_threshold", e.target.value)}
            />
          </label>
        </div>
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Boissons du menu</div>
        <textarea
          data-testid="settings-sodas"
          className="bt-input min-h-[120px]"
          placeholder="Une par ligne"
          value={(s.soda_flavours || []).join("\n")}
          onChange={(e) => set("soda_flavours", e.target.value.split("\n"))}
        />
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Contact</div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="block sm:col-span-1">
            <div className="bt-label">Téléphone</div>
            <input className="bt-input" value={s.contact_phone || ""} onChange={(e) => set("contact_phone", e.target.value)} />
          </label>
          <label className="block sm:col-span-2">
            <div className="bt-label">Adresse</div>
            <input className="bt-input" value={s.contact_address || ""} onChange={(e) => set("contact_address", e.target.value)} />
          </label>
          <label className="block sm:col-span-3">
            <div className="bt-label">Instagram</div>
            <input className="bt-input" value={s.contact_instagram || ""} onChange={(e) => set("contact_instagram", e.target.value)} />
          </label>
        </div>
      </div>

      <div className="bt-card p-5 space-y-3">
        <div className="font-display text-2xl uppercase">Telegram</div>
        <p className="text-sm text-[#A1A1A1]">
          Configure `TELEGRAM_BOT_TOKEN`, `TELEGRAM_KITCHEN_CHAT_ID` et `TELEGRAM_WEBHOOK_SECRET`
          dans le backend, puis clique ci-dessous pour enregistrer le webhook.
        </p>
        <button onClick={syncWebhook} data-testid="telegram-sync" className="bt-btn-primary py-2 px-4 text-sm">
          <Send className="w-4 h-4" /> Sync webhook Telegram
        </button>
      </div>
    </div>
  );
}
