import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { kitchenClient, fmtError, formatEur } from "@/lib/api";
import { useKitchenAuth } from "@/context/KitchenAuthContext.jsx";
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
import {
  CheckCircle2,
  XCircle,
  Wifi,
  WifiOff,
  LogOut,
  Printer,
  Clock,
  Volume2,
  AlertTriangle,
} from "lucide-react";

const POLL_MS = 4000;
const REMINDER_MS = 20000;
// If an accepted order still shows "pending" print status this long after
// acceptance, the Pi/tunnel/printer is very likely offline — a normal
// print (even 2 copies) completes in well under this window.
const PRINT_STUCK_MS = 45000;

const TABS = [
  { key: "new", label: "Nouvelles" },
  { key: "accepted", label: "Acceptées" },
  { key: "declined", label: "Refusées" },
];

const FULFILLMENT_LABEL = { pickup: "A EMPORTER", delivery: "LIVRAISON" };
const PAYMENT_LABEL = { cash: "Espèces sur place", card_in_person: "Carte sur place" };

/** Two-tone chime via Web Audio API — no external asset, works offline. */
function playBeep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const now = ctx.currentTime;
    [0, 0.18].forEach((delay, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = i === 0 ? 880 : 1050;
      gain.gain.setValueAtTime(0.0001, now + delay);
      gain.gain.exponentialRampToValueAtTime(0.35, now + delay + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + delay + 0.16);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + delay);
      osc.stop(now + delay + 0.18);
    });
    setTimeout(() => ctx.close(), 500);
  } catch {
    // Some browsers block audio before a user gesture — silently ignore.
  }
}

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function fmtDeliverySlot(order) {
  if (!order.scheduled_delivery_start || !order.scheduled_delivery_end) return null;
  return `${fmtTime(order.scheduled_delivery_start)} — ${fmtTime(order.scheduled_delivery_end)}`;
}

export default function Kitchen() {
  const { logout } = useKitchenAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState("new");
  const [orders, setOrders] = useState({ new: [], accepted: [], declined: [] });
  const [online, setOnline] = useState(true);
  const [busyIds, setBusyIds] = useState({});
  const [soundOn, setSoundOn] = useState(false);
  const [testingPrinter, setTestingPrinter] = useState(false);
  const seenIds = useRef(new Set());
  const initialized = useRef(false);
  const soundOnRef = useRef(false);

  // Printing is fully automated server-side now: the backend pushes the
  // ticket straight to the restaurant's Raspberry Pi print-bridge (Flask +
  // Sunmi NT311) the instant an order is accepted — no browser print
  // dialog, no tab juggling, nothing for the tablet to do at all.

  const load = useCallback(async () => {
    try {
      const { data } = await kitchenClient.get("/kitchen/orders");
      setOnline(true);
      const incomingIds = new Set(data.new.map((o) => o.id));
      if (initialized.current) {
        const freshlyArrived = [...incomingIds].filter((id) => !seenIds.current.has(id));
        if (freshlyArrived.length > 0 && soundOnRef.current) playBeep();
      } else {
        initialized.current = true;
      }
      seenIds.current = incomingIds;
      setOrders(data);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (orders.new.length === 0) return undefined;
    const id = setInterval(() => {
      if (soundOnRef.current) playBeep();
    }, REMINDER_MS);
    return () => clearInterval(id);
  }, [orders.new.length]);

  const enableSound = () => {
    soundOnRef.current = true;
    setSoundOn(true);
    playBeep();
  };

  const setBusy = (id, val) => setBusyIds((s) => ({ ...s, [id]: val }));

  const withBusy = async (order, fn) => {
    if (busyIds[order.id]) return;
    setBusy(order.id, true);
    try {
      await fn();
    } catch (e) {
      toast.error(fmtError(e));
    } finally {
      setBusy(order.id, false);
    }
  };

  const accept = (order) =>
    withBusy(order, async () => {
      const { data } = await kitchenClient.post(`/kitchen/orders/${order.id}/accept`);
      if (data.already_decided) {
        toast.info(`Commande #${order.order_number} déjà traitée`);
      } else {
        toast.success(`Commande #${order.order_number} acceptée`);
      }
      load();
    });

  const decline = (order, reason) =>
    withBusy(order, async () => {
      await kitchenClient.post(`/kitchen/orders/${order.id}/decline`, { reason });
      toast.success(`Commande #${order.order_number} refusée`);
      load();
    });

  const reprint = (order) =>
    withBusy(order, async () => {
      const { data } = await kitchenClient.post(`/kitchen/orders/${order.id}/reprint`);
      if (data.ok) toast.success(`Ticket #${order.order_number} renvoyé à l'imprimante`);
      else toast.error("Imprimante injoignable — réessaie dans un instant");
      load();
    });

  const doLogout = () => {
    logout();
    nav("/kitchen/login", { replace: true });
  };

  const testPrinter = async () => {
    if (testingPrinter) return;
    setTestingPrinter(true);
    try {
      const { data } = await kitchenClient.post("/kitchen/test-print");
      if (data.ok) toast.success("Ticket de test envoyé — vérifie l'imprimante");
      else toast.error("Imprimante injoignable — le ticket de test n'est pas parti");
    } catch (e) {
      toast.error(fmtError(e));
    } finally {
      setTestingPrinter(false);
    }
  };

  const printerLikelyOffline = orders.accepted.some(
    (o) =>
      o.kitchen_print_status !== "printed" &&
      o.kitchen_decision_at &&
      Date.now() - new Date(o.kitchen_decision_at).getTime() > PRINT_STUCK_MS
  );

  const list = orders[tab] || [];

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8] select-none" data-testid="kitchen-page">
      <header className="sticky top-0 z-20 bg-[#141414] border-b-2 border-[#EF2B2D] px-3 md:px-5 py-3 flex items-center justify-between gap-2 flex-wrap">
        <div className="font-display text-2xl uppercase leading-none">
          <span className="text-[#F5F1E8]">Burger</span>
          <span className="text-[#EF2B2D]">Times</span>
          <span className="text-[#666] text-sm font-accent tracking-widest ml-2">Cuisine</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            data-testid="kitchen-connection-status"
            className={`flex items-center gap-1.5 px-2.5 py-1.5 border-2 text-xs font-accent uppercase tracking-widest ${
              online ? "border-[#3DDC97] text-[#3DDC97]" : "border-[#EF2B2D] text-[#EF2B2D] animate-pulse"
            }`}
          >
            {online ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
            {online ? "En ligne" : "Hors ligne"}
          </div>
          {!soundOn && (
            <button
              onClick={enableSound}
              data-testid="kitchen-enable-sound"
              className="bt-btn-ghost text-xs px-2 py-1.5"
            >
              <Volume2 className="w-3.5 h-3.5" /> Activer le son
            </button>
          )}
          <button
            onClick={testPrinter}
            disabled={testingPrinter}
            data-testid="kitchen-test-printer"
            className="bt-btn-ghost text-xs px-2 py-1.5 disabled:opacity-40"
          >
            <Printer className="w-3.5 h-3.5" /> {testingPrinter ? "Envoi…" : "Tester l'imprimante"}
          </button>
          <button
            onClick={doLogout}
            data-testid="kitchen-logout"
            className="bt-btn-ghost text-xs px-2 py-1.5 text-[#EF2B2D]"
          >
            <LogOut className="w-4 h-4" /> Sortir
          </button>
        </div>
      </header>

      {!online && (
        <div
          data-testid="kitchen-offline-banner"
          className="bg-[#EF2B2D] text-[#0A0A0A] text-center py-2 font-accent uppercase tracking-widest text-sm"
        >
          Connexion perdue — nouvelle tentative automatique…
        </div>
      )}

      {online && printerLikelyOffline && (
        <div
          data-testid="kitchen-printer-offline-banner"
          className="bg-[#FFB800] text-[#0A0A0A] text-center py-2 font-accent uppercase tracking-widest text-sm flex items-center justify-center gap-2 flex-wrap px-3"
        >
          <AlertTriangle className="w-4 h-4" />
          Imprimante hors ligne — les tickets ne s&apos;impriment plus. Vérifie le Raspberry Pi / ngrok.
          <button
            onClick={testPrinter}
            disabled={testingPrinter}
            data-testid="kitchen-printer-offline-test-btn"
            className="underline underline-offset-2 disabled:opacity-50"
          >
            Tester maintenant
          </button>
        </div>
      )}

      <div className="flex gap-2 p-3 bg-[#141414] border-b-2 border-[#262626]">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            data-testid={`kitchen-tab-${t.key}`}
            className={`flex-1 py-4 text-base md:text-lg font-accent uppercase tracking-widest border-2 transition-colors ${
              tab === t.key ? "bg-[#EF2B2D] border-[#EF2B2D] text-[#F5F1E8]" : "border-[#262626] text-[#B3B3B3]"
            }`}
          >
            {t.label}
            {orders[t.key]?.length ? ` (${orders[t.key].length})` : ""}
          </button>
        ))}
      </div>

      <main className="p-3 md:p-5 space-y-4 max-w-4xl mx-auto pb-16">
        {list.length === 0 ? (
          <div className="text-center text-[#666] py-24 text-lg" data-testid="kitchen-empty-state">
            {tab === "new" && "Aucune nouvelle commande."}
            {tab === "accepted" && "Aucune commande acceptée."}
            {tab === "declined" && "Aucune commande refusée."}
          </div>
        ) : (
          list.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              tab={tab}
              busy={!!busyIds[order.id]}
              onAccept={() => accept(order)}
              onDecline={(reason) => decline(order, reason)}
              onReprint={() => reprint(order)}
            />
          ))
        )}
      </main>
    </div>
  );
}

function OrderCard({ order, tab, busy, onAccept, onDecline, onReprint }) {
  const [declineReason, setDeclineReason] = useState("");
  const isNew = tab === "new";
  const cleanNote = (order.notes || "").replace("[TEST ORDER]", "").trim();
  const scheduledSlot = fmtDeliverySlot(order);

  return (
    <div
      data-testid={`kitchen-order-${order.id}`}
      className={`bt-card p-4 md:p-5 border-2 ${isNew ? "border-[#EF2B2D] animate-pulse" : "border-[#262626]"}`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-display text-4xl md:text-5xl leading-none">#{order.order_number}</div>
          <div className="text-sm text-[#A1A1A1] mt-1 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" /> {fmtTime(order.created_at)}
            {order.test_order && <span className="bt-badge-red ml-2">TEST</span>}
          </div>
        </div>
        <span className="bt-price-pill text-base">
          {FULFILLMENT_LABEL[order.fulfillment] || order.fulfillment}
        </span>
      </div>

      <div className="mt-3 text-lg">
        <div className="font-accent uppercase tracking-widest text-xs text-[#666]">Client</div>
        <div>
          {order.customer_first_name} {order.customer_last_name}
        </div>
        {order.customer_phone && <div className="text-[#B3B3B3]">{order.customer_phone}</div>}
      </div>

      {order.fulfillment === "delivery" && (
        <div className="mt-2 text-base">
          <div className="font-accent uppercase tracking-widest text-xs text-[#666]">Adresse</div>
          <div>
            {order.address_line1}
            {order.address_line2 ? `, ${order.address_line2}` : ""}, {order.postal_code} {order.city}
          </div>
          {scheduledSlot && (
            <div className="mt-2 border-2 border-[#FFB800] px-2 py-1 text-sm font-bold text-[#FFB800]">
              Créneau : {scheduledSlot}
            </div>
          )}
        </div>
      )}

      <div className="mt-4 space-y-3 border-t-2 border-[#262626] pt-3">
        {(order.items || []).map((it, i) => (
          <div key={i} className="text-lg">
            <div className="font-bold">
              {it.quantity}× {it.name}
            </div>
            <div className="pl-4 text-sm text-[#B3B3B3] space-y-0.5 mt-0.5">
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
            {it.notes && (
              <div className="mt-1 inline-block bg-[#EF2B2D] text-[#F5F1E8] px-2 py-1 font-accent uppercase tracking-wide text-sm">
                {it.notes}
              </div>
            )}
          </div>
        ))}
      </div>

      {cleanNote && (
        <div className="mt-3 border-2 border-[#EF2B2D] p-3">
          <div className="font-accent uppercase tracking-widest text-xs text-[#EF2B2D] mb-1">Note client</div>
          <div className="font-bold">{cleanNote}</div>
        </div>
      )}

      <div className="mt-4 flex items-center justify-between border-t-2 border-[#262626] pt-3">
        <div className="text-sm text-[#A1A1A1]">{PAYMENT_LABEL[order.payment_method] || order.payment_method}</div>
        <div className="font-display text-3xl text-[#EF2B2D]">{formatEur(order.total)}</div>
      </div>
      {order.pickup_code && (
        <div className="mt-2 text-center border-2 border-[#FFB800] p-2">
          <span className="text-xs uppercase tracking-widest text-[#FFB800]">Code retrait </span>
          <span className="font-display text-2xl text-[#FFB800]">{order.pickup_code}</span>
        </div>
      )}

      {tab === "new" && (
        <div className="mt-4 grid grid-cols-2 gap-3">
          <button
            data-testid={`kitchen-accept-${order.id}`}
            onClick={onAccept}
            disabled={busy}
            className="bt-btn-primary py-5 text-base md:text-lg disabled:opacity-40"
          >
            <CheckCircle2 className="w-5 h-5" /> Accepter &amp; Imprimer
          </button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
                data-testid={`kitchen-decline-${order.id}`}
                disabled={busy}
                className="bt-btn-secondary py-5 text-base md:text-lg border-[#EF2B2D] text-[#EF2B2D] disabled:opacity-40"
              >
                <XCircle className="w-5 h-5" /> Refuser
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent className="bg-[#141414] border-2 border-[#EF2B2D] rounded-none text-[#F5F1E8]">
              <AlertDialogHeader>
                <AlertDialogTitle>Refuser la commande #{order.order_number} ?</AlertDialogTitle>
                <AlertDialogDescription>
                  Le client sera notifié. Cette action est définitive.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <textarea
                data-testid={`kitchen-decline-reason-${order.id}`}
                className="bt-input min-h-[80px]"
                placeholder="Raison (optionnel)"
                value={declineReason}
                onChange={(e) => setDeclineReason(e.target.value)}
              />
              <AlertDialogFooter>
                <AlertDialogCancel className="rounded-none">Annuler</AlertDialogCancel>
                <AlertDialogAction
                  data-testid={`kitchen-decline-confirm-${order.id}`}
                  className="rounded-none bg-[#EF2B2D]"
                  onClick={() => onDecline(declineReason)}
                >
                  Confirmer le refus
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}

      {tab === "accepted" && (
        <div className="mt-4 flex items-center justify-between gap-3 flex-wrap">
          <PrintStatusBadge status={order.kitchen_print_status} />
          <button
            data-testid={`kitchen-reprint-${order.id}`}
            onClick={onReprint}
            disabled={busy}
            className="bt-btn-ghost py-3 px-4 text-sm"
          >
            <Printer className="w-4 h-4" /> Réimprimer
          </button>
        </div>
      )}

      {tab === "declined" && order.kitchen_decline_reason && (
        <div className="mt-4 text-sm text-[#A1A1A1] border-t-2 border-[#262626] pt-3">
          Raison : {order.kitchen_decline_reason}
        </div>
      )}
    </div>
  );
}

function PrintStatusBadge({ status }) {
  const cfg =
    { printed: { color: "#3DDC97", label: "Imprimé", Icon: CheckCircle2 } }[status] || {
      color: "#FFB800",
      label: "En attente d'impression",
      Icon: Clock,
    };
  const { color, label, Icon } = cfg;
  return (
    <span
      data-testid="kitchen-print-badge"
      className="inline-flex items-center gap-2 text-sm font-accent uppercase tracking-widest"
      style={{ color }}
    >
      <Icon className="w-4 h-4" /> {label}
    </span>
  );
}
