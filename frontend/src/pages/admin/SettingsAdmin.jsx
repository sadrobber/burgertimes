import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError, formatEur } from "@/lib/api";
import { Save, Send, Trash2, Bell, CreditCard, Wallet, RefreshCw } from "lucide-react";

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
  const [waitlist, setWaitlist] = useState([]);
  const [notifyingWaitlist, setNotifyingWaitlist] = useState(false);
  const [reseeding, setReseeding] = useState(false);

  useEffect(() => {
    adminClient.get("/settings").then((r) => setS(r.data));
    adminClient.get("/admin/waitlist").then((r) => setWaitlist(r.data || []));
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
        delivery_fee_percent: parseFloat(s.delivery_fee_percent) || 0,
        free_delivery_threshold:
          s.free_delivery_threshold === null || s.free_delivery_threshold === ""
            ? null
            : parseFloat(s.free_delivery_threshold),
        delivery_postal_codes: Array.isArray(s.delivery_postal_codes)
          ? s.delivery_postal_codes.map((v) => String(v).trim()).filter(Boolean)
          : [],
        contact_phone: s.contact_phone,
        contact_address: s.contact_address,
        contact_instagram: s.contact_instagram,
        payment_cash_enabled: !!s.payment_cash_enabled,
        payment_card_enabled: !!s.payment_card_enabled,
        order_limit_enabled: !!s.order_limit_enabled,
        order_limit_period: s.order_limit_period || "day",
        order_limit_max: parseInt(s.order_limit_max, 10) || 0,
        order_limit_message: s.order_limit_message || "",
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

  const notifyWaitlist = async () => {
    if (!window.confirm(`Notifier ${waitlist.length} personne(s) et vider la liste ?`)) return;
    setNotifyingWaitlist(true);
    try {
      const { data } = await adminClient.post("/admin/waitlist/notify");
      if (data.email_configured) {
        toast.success(`${data.emails_sent}/${data.notified} email(s) envoyé(s)`);
      } else {
        toast.success(`${data.notified} personne(s) marquée(s) notifiées (email non configuré — les entrées sont effacées)`);
      }
      const r = await adminClient.get("/admin/waitlist");
      setWaitlist(r.data || []);
    } catch (e) {
      toast.error(fmtError(e));
    } finally {
      setNotifyingWaitlist(false);
    }
  };

  const deleteWaitlistEntry = async (id) => {
    try {
      await adminClient.delete(`/admin/waitlist/${id}`);
      setWaitlist(waitlist.filter((w) => w.id !== id));
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const forceReseed = async () => {
    if (
      !window.confirm(
        "Réinitialiser le menu, les sauces, les tacos, les catégories, les horaires et les frais de livraison depuis les fichiers de base ?\n\nToute modification manuelle sera écrasée. Les commandes et clients ne sont pas touchés.",
      )
    )
      return;
    setReseeding(true);
    try {
      const { data } = await adminClient.post("/admin/seed/reseed");
      toast.success(
        `Menu réinitialisé : ${data.menu_items} plats, ${data.categories} catégories, ${data.sauces} sauces.`,
      );
      const r = await adminClient.get("/settings");
      setS(r.data);
    } catch (e) {
      toast.error(fmtError(e));
    } finally {
      setReseeding(false);
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
          <input
            className="bt-input"
            value={s.closed_message || ""}
            onChange={(e) => set("closed_message", e.target.value)}
          />
        </label>
      </div>

      {/* Paiements */}
      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Paiements acceptés</div>
        <p className="text-sm text-[#A1A1A1]">
          Coupe un mode de paiement quand tu veux — les clients ne le verront plus au checkout.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label
            data-testid="settings-payment-cash-toggle"
            className={`bt-option flex items-start gap-3 cursor-pointer ${s.payment_cash_enabled ? "selected" : ""}`}
          >
            <input
              type="checkbox"
              className="w-4 h-4 mt-1"
              checked={!!s.payment_cash_enabled}
              onChange={(e) => set("payment_cash_enabled", e.target.checked)}
            />
            <div>
              <div className="font-accent uppercase tracking-widest text-lg inline-flex items-center gap-2">
                <Wallet className="w-4 h-4" /> Cash sur place
              </div>
              <div className="text-xs text-[#A1A1A1] mt-1">
                Espèces à la remise de la commande.
              </div>
            </div>
          </label>
          <label
            data-testid="settings-payment-card-toggle"
            className={`bt-option flex items-start gap-3 cursor-pointer ${s.payment_card_enabled ? "selected" : ""}`}
          >
            <input
              type="checkbox"
              className="w-4 h-4 mt-1"
              checked={!!s.payment_card_enabled}
              onChange={(e) => set("payment_card_enabled", e.target.checked)}
            />
            <div>
              <div className="font-accent uppercase tracking-widest text-lg inline-flex items-center gap-2">
                <CreditCard className="w-4 h-4" /> Carte sur place
              </div>
              <div className="text-xs text-[#A1A1A1] mt-1">
                TPE au comptoir à la remise de la commande.
              </div>
            </div>
          </label>
        </div>
        {!s.payment_cash_enabled && !s.payment_card_enabled && (
          <div className="text-xs text-[#FF3B30]">
            Attention : plus aucun mode de paiement n&apos;est activé. Les clients ne pourront pas
            valider leur commande.
          </div>
        )}
      </div>

      {/* Order limits */}
      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Limite de commandes</div>
        <p className="text-sm text-[#A1A1A1]">
          Coupe le robinet automatiquement quand la cuisine sature. Le client voit un message
          personnalisable.
        </p>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            data-testid="settings-order-limit-enabled"
            type="checkbox"
            checked={!!s.order_limit_enabled}
            onChange={(e) => set("order_limit_enabled", e.target.checked)}
          />
          Activer la limite
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="bt-label">Période</div>
            <select
              data-testid="settings-order-limit-period"
              className="bt-input"
              value={s.order_limit_period || "day"}
              onChange={(e) => set("order_limit_period", e.target.value)}
              disabled={!s.order_limit_enabled}
            >
              <option value="day">Par jour</option>
              <option value="week">Par semaine</option>
            </select>
          </label>
          <label className="block">
            <div className="bt-label">Max commandes</div>
            <input
              data-testid="settings-order-limit-max"
              type="number"
              min="1"
              className="bt-input"
              value={s.order_limit_max || 0}
              onChange={(e) => set("order_limit_max", e.target.value)}
              disabled={!s.order_limit_enabled}
            />
          </label>
          <div className="hidden sm:block" />
        </div>
        <label className="block">
          <div className="bt-label">Message affiché au client</div>
          <textarea
            data-testid="settings-order-limit-message"
            className="bt-input min-h-[100px]"
            value={s.order_limit_message || ""}
            onChange={(e) => set("order_limit_message", e.target.value)}
            disabled={!s.order_limit_enabled}
          />
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
                <button
                  onClick={() => addRange(key)}
                  className="bt-btn-ghost text-xs px-2"
                  data-testid={`hours-add-range-${key}`}
                >
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
                  <button
                    onClick={() => removeRange(key, i)}
                    className="bt-btn-ghost text-xs px-2 text-[#EF2B2D]"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Cutoff &amp; ETA</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <label className="block">
            <div className="bt-label">Cutoff (min)</div>
            <input
              type="number"
              className="bt-input"
              value={s.last_order_buffer_minutes || 0}
              onChange={(e) => set("last_order_buffer_minutes", e.target.value)}
            />
          </label>
          <label className="block">
            <div className="bt-label">Ferme bientôt (min)</div>
            <input
              type="number"
              className="bt-input"
              value={s.closing_soon_window_minutes || 0}
              onChange={(e) => set("closing_soon_window_minutes", e.target.value)}
            />
          </label>
          <label className="block">
            <div className="bt-label">ETA par défaut min</div>
            <input
              type="number"
              className="bt-input"
              value={s.eta_default_min || 0}
              onChange={(e) => set("eta_default_min", e.target.value)}
            />
          </label>
          <label className="block">
            <div className="bt-label">ETA par défaut max</div>
            <input
              type="number"
              className="bt-input"
              value={s.eta_default_max || 0}
              onChange={(e) => set("eta_default_max", e.target.value)}
            />
          </label>
          <label className="block">
            <div className="bt-label">ETA busy min</div>
            <input
              type="number"
              className="bt-input"
              value={s.too_busy_eta_min || 0}
              onChange={(e) => set("too_busy_eta_min", e.target.value)}
            />
          </label>
          <label className="block">
            <div className="bt-label">ETA busy max</div>
            <input
              type="number"
              className="bt-input"
              value={s.too_busy_eta_max || 0}
              onChange={(e) => set("too_busy_eta_max", e.target.value)}
            />
          </label>
        </div>
      </div>

      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Livraison</div>
        <p className="text-sm text-[#A1A1A1]">
          Les frais de livraison sont calculés en pourcentage du sous-total —
          c&apos;est ta commission sur chaque livraison, présentée au client comme frais de
          livraison.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <div className="bt-label">% du sous-total</div>
            <div className="relative">
              <input
                type="number"
                step="0.5"
                min="0"
                max="100"
                data-testid="settings-delivery-percent"
                className="bt-input pr-10"
                value={s.delivery_fee_percent ?? 10}
                onChange={(e) => set("delivery_fee_percent", e.target.value)}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[#A1A1A1] font-accent uppercase tracking-widest text-xs">
                %
              </span>
            </div>
            <div className="text-xs text-[#A1A1A1] mt-2">
              Exemple : commande de 30€ → livraison{" "}
              <span className="text-[#EF2B2D] font-bold">
                {formatEur(((parseFloat(s.delivery_fee_percent) || 0) * 30) / 100)}
              </span>
            </div>
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
            <div className="text-xs text-[#A1A1A1] mt-2">
              Laisse vide pour toujours facturer la livraison.
            </div>
          </label>
        </div>
      </div>

      {/* Zone de livraison */}
      <div className="bt-card p-5 space-y-4">
        <div className="font-display text-2xl uppercase">Zone de livraison</div>
        <p className="text-sm text-[#A1A1A1]">
          Codes postaux que tu livres, séparés par des virgules. Les commandes de livraison
          vers un autre code postal seront rejetées au checkout.
          <br />
          <span className="text-[#666]">
            Laisse vide pour accepter toutes les zones.
          </span>
        </p>
        <input
          data-testid="settings-postal-codes"
          className="bt-input"
          placeholder="06240, 06320, 06500, 98000"
          value={(s.delivery_postal_codes || []).join(", ")}
          onChange={(e) =>
            set(
              "delivery_postal_codes",
              e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter(Boolean),
            )
          }
        />
        {(s.delivery_postal_codes || []).length > 0 && (
          <div className="flex flex-wrap gap-1">
            {(s.delivery_postal_codes || []).map((c) => (
              <span key={c} className="bt-badge-red">
                {c}
              </span>
            ))}
          </div>
        )}
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
            <input
              className="bt-input"
              value={s.contact_phone || ""}
              onChange={(e) => set("contact_phone", e.target.value)}
            />
          </label>
          <label className="block sm:col-span-2">
            <div className="bt-label">Adresse</div>
            <input
              className="bt-input"
              value={s.contact_address || ""}
              onChange={(e) => set("contact_address", e.target.value)}
            />
          </label>
          <label className="block sm:col-span-3">
            <div className="bt-label">Instagram</div>
            <input
              className="bt-input"
              value={s.contact_instagram || ""}
              onChange={(e) => set("contact_instagram", e.target.value)}
            />
          </label>
        </div>
      </div>

      {/* Waitlist */}
      <div className="bt-card p-5 space-y-3">
        <div className="flex items-center justify-between gap-4">
          <div className="font-display text-2xl uppercase inline-flex items-center gap-2">
            <Bell className="w-5 h-5 text-[#EF2B2D]" /> Liste d&apos;attente
          </div>
          <button
            onClick={notifyWaitlist}
            disabled={waitlist.length === 0 || notifyingWaitlist}
            data-testid="waitlist-notify"
            className="bt-btn-primary py-2 px-4 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" /> Notifier tout le monde ({waitlist.length})
          </button>
        </div>
        <p className="text-sm text-[#A1A1A1]">
          Emails collectés depuis la page fermée. Le bouton envoie un mail à chaque personne (si
          Resend est configuré) et vide la liste.
        </p>
        {waitlist.length === 0 ? (
          <div className="text-sm text-[#A1A1A1] py-4">Personne pour l&apos;instant.</div>
        ) : (
          <div className="divide-y divide-[#262626]">
            {waitlist.map((w) => (
              <div key={w.id} className="flex items-center justify-between py-2" data-testid={`waitlist-row-${w.id}`}>
                <div>
                  <div className="text-sm">{w.email}</div>
                  <div className="text-xs text-[#A1A1A1]">
                    {new Date(w.created_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={() => deleteWaitlistEntry(w.id)}
                  className="bt-btn-ghost px-2 text-xs text-[#EF2B2D]"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bt-card p-5 space-y-3">
        <div className="font-display text-2xl uppercase">Telegram</div>
        <p className="text-sm text-[#A1A1A1]">
          Configure `TELEGRAM_BOT_TOKEN`, `TELEGRAM_KITCHEN_CHAT_ID` et `TELEGRAM_WEBHOOK_SECRET`
          dans le backend, puis clique ci-dessous pour enregistrer le webhook.
        </p>
        <button
          onClick={syncWebhook}
          data-testid="telegram-sync"
          className="bt-btn-primary py-2 px-4 text-sm"
        >
          <Send className="w-4 h-4" /> Sync webhook Telegram
        </button>
      </div>

      {/* Danger zone — force reseed */}
      <div className="bt-card p-5 space-y-3 border-2 border-[#EF2B2D]">
        <div className="font-display text-2xl uppercase text-[#EF2B2D]">Zone rouge</div>
        <div className="font-accent uppercase tracking-widest text-sm">
          Réinitialiser le menu depuis la sauvegarde
        </div>
        <p className="text-sm text-[#A1A1A1]">
          Si en production le menu est vide ou que les horaires ont sauté après un déploiement,
          clique ce bouton une fois. Ça remet en place tous les plats, catégories, sauces, tacos,
          horaires et le frais de livraison en % (10 % · gratuit dès 30 €) tels qu&apos;ils sont
          définis dans le code. <strong>Toute modification manuelle sera écrasée.</strong>{" "}
          Les commandes, les clients et la liste d&apos;attente ne sont pas touchés.
        </p>
        <button
          onClick={forceReseed}
          disabled={reseeding}
          data-testid="settings-force-reseed"
          className="bt-btn-primary py-2 px-4 text-sm disabled:opacity-40"
        >
          <RefreshCw className={`w-4 h-4 ${reseeding ? "animate-spin" : ""}`} />{" "}
          {reseeding ? "Réinitialisation…" : "Réinitialiser depuis la sauvegarde"}
        </button>
      </div>
    </div>
  );
}