import React, { useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle2, Clock, Mail } from "lucide-react";
import { apiClient, fmtError } from "@/lib/api";
import { useI18n } from "@/context/I18nContext.jsx";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";
import { toast } from "sonner";

function Cell({ value, label, testId }) {
  const v = String(value).padStart(2, "0");
  return (
    <div className="flex flex-col items-center" data-testid={testId}>
      <div className="relative">
        <div className="font-display text-5xl sm:text-6xl md:text-8xl leading-none tabular-nums text-[#F5F1E8]">
          {v}
        </div>
      </div>
      <div className="font-accent uppercase tracking-widest text-[10px] sm:text-xs text-[#A1A1A1] mt-2">
        {label}
      </div>
    </div>
  );
}

export default function ClosedHero({ compact = false }) {
  const { status } = useRestaurantStatus(30000);
  const { t } = useI18n();
  const [, setTick] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const countdown = useMemo(() => {
    const iso = status?.next_open_at_iso;
    if (!iso) return null;
    const target = new Date(iso).getTime();
    if (Number.isNaN(target)) return null;
    const diff = Math.max(0, target - Date.now());
    const totalHours = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    return { h: totalHours, m, s, total: diff };
  }, [status]);

  const submit = async () => {
    if (!email.trim() || !/^\S+@\S+\.\S+$/.test(email)) {
      toast.error("Email invalide");
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post("/waitlist", { email: email.trim().toLowerCase() });
      setDone(true);
    } catch (e) {
      toast.error(fmtError(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (!status || status.state !== "closed") return null;

  const reason = status.reason;
  const subtitle =
    reason === "day_off"
      ? "On est fermés aujourd'hui — repos oblige. On te retrouve très vite."
      : reason === "force_closed"
      ? status?.closed_message || "Pause exceptionnelle. On revient dès qu'on peut."
      : reason === "before_open"
      ? "On chauffe la plancha. Encore un peu de patience."
      : reason === "after_cutoff"
      ? "Dernière commande passée pour ce service. On te retrouve au prochain."
      : "On reprend le service très vite.";

  return (
    <div
      data-testid="closed-hero"
      className={`bt-card border-[#EF2B2D] relative overflow-hidden ${compact ? "p-6" : "p-6 sm:p-10 md:p-14"}`}
    >
      <div className="absolute inset-0 bt-halftone opacity-10 pointer-events-none" />
      <div className="absolute -top-4 left-8 h-3 w-40 bt-tape opacity-80" />
      <div className="absolute -bottom-4 right-12 h-3 w-32 bt-tape opacity-60" />

      <div className="relative">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#FF3B30] animate-pulse" />
          <div className="font-marker text-[#EF2B2D] -rotate-1 text-lg">Pause</div>
        </div>
        <div
          className={`font-display uppercase mt-2 leading-none text-[#F5F1E8] ${
            compact ? "text-4xl md:text-5xl" : "text-5xl sm:text-6xl md:text-8xl"
          }`}
        >
          {t("closed.title", "Fermé pour l'instant")}
        </div>
        <p className={`text-[#B3B3B3] mt-4 max-w-xl ${compact ? "text-sm" : "text-base md:text-lg"}`}>
          {subtitle}
        </p>

        {countdown && countdown.total > 0 && (
          <div className="mt-8">
            <div className="bt-label mb-3 inline-flex items-center gap-2 text-[#EF2B2D]">
              <Clock className="w-3 h-3" />
              {t("closed.opens_in", "Réouverture dans")}
            </div>
            <div className="flex items-baseline gap-2 sm:gap-3 md:gap-5">
              <Cell value={countdown.h} label="H" testId="closed-cd-h" />
              <div className={`font-display text-[#EF2B2D] leading-none ${compact ? "text-4xl md:text-5xl" : "text-5xl md:text-7xl"}`}>:</div>
              <Cell value={countdown.m} label="Min" testId="closed-cd-m" />
              <div className={`font-display text-[#EF2B2D] leading-none ${compact ? "text-4xl md:text-5xl" : "text-5xl md:text-7xl"}`}>:</div>
              <Cell value={countdown.s} label="Sec" testId="closed-cd-s" />
            </div>
          </div>
        )}

        {status.next_open_at_local && status.next_open_day && (
          <div className="mt-6 text-xs sm:text-sm font-accent uppercase tracking-widest text-[#A1A1A1]">
            <span className="text-[#F5F1E8]">
              {status.next_open_day === "today"
                ? "Aujourd'hui"
                : status.next_open_day === "tomorrow"
                ? "Demain"
                : status.next_open_day}
            </span>
            {" · "}
            {status.next_open_at_local}
          </div>
        )}

        <div className="mt-8">
          {!formOpen && !done && (
            <button
              onClick={() => setFormOpen(true)}
              data-testid="closed-notify-btn"
              className="bt-btn-primary"
            >
              <Bell className="w-4 h-4" />
              {t("closed.notify.button", "Préviens-moi")}
            </button>
          )}
          {formOpen && !done && (
            <div className="max-w-md">
              <div className="bt-label flex items-center gap-2">
                <Mail className="w-3 h-3" />
                {t("closed.notify.hint", "On te prévient dès qu'on rouvre")}
              </div>
              <div className="flex flex-col sm:flex-row gap-2 mt-2">
                <input
                  type="email"
                  data-testid="closed-notify-email"
                  className="bt-input flex-1"
                  placeholder={t("closed.notify.email_placeholder", "ton@email.com")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                />
                <button
                  onClick={submit}
                  disabled={submitting}
                  data-testid="closed-notify-submit"
                  className="bt-btn-primary py-3 px-6 text-sm disabled:opacity-40"
                >
                  {submitting ? "…" : t("closed.notify.subscribe", "OK, préviens-moi")}
                </button>
              </div>
              <button
                onClick={() => setFormOpen(false)}
                className="text-xs text-[#A1A1A1] hover:text-[#EF2B2D] mt-2 font-accent uppercase tracking-widest"
                data-testid="closed-notify-cancel"
              >
                Annuler
              </button>
            </div>
          )}
          {done && (
            <div
              className="bt-card p-4 max-w-md border-[#00FF66] inline-flex items-center gap-3"
              data-testid="closed-notify-done"
            >
              <CheckCircle2 className="w-5 h-5 text-[#00FF66]" />
              <div>
                <div className="font-accent uppercase tracking-widest text-[#00FF66] text-sm">
                  {t("closed.notify.done", "C'est noté !")}
                </div>
                <div className="text-xs text-[#B3B3B3] mt-0.5">
                  On te ping dès qu&apos;on ouvre.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
