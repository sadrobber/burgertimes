import React, { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, CheckCircle2, Clock, Mail } from "lucide-react";
import { apiClient, fmtError } from "@/lib/api";
import { useI18n } from "@/context/I18nContext.jsx";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";
import { toast } from "sonner";

/** Single digit that flips vertically when its character changes. */
function Digit({ char, size = "hero" }) {
  const widths = { hero: "0.62em", compact: "0.6em" };
  return (
    <div
      className="relative inline-block overflow-hidden leading-none"
      style={{ width: widths[size] || widths.hero, height: "1em" }}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={char}
          initial={{ y: "-105%", opacity: 0, filter: "blur(6px)" }}
          animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
          exit={{ y: "105%", opacity: 0, filter: "blur(6px)" }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="absolute inset-0 flex items-start justify-center tabular-nums will-change-transform"
        >
          {char}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

function Cell({ value, label, testId, pulseKey, compact }) {
  const v = String(value).padStart(2, "0");
  const sizeClass = compact
    ? "text-4xl sm:text-5xl md:text-6xl"
    : "text-5xl sm:text-6xl md:text-8xl";
  return (
    <div className="flex flex-col items-center" data-testid={testId}>
      <motion.div
        key={pulseKey}
        initial={{ scale: 1 }}
        animate={{ scale: [1, 1.045, 1] }}
        transition={{ duration: 0.7, ease: "easeOut" }}
        className="relative"
      >
        <span
          aria-hidden
          className="absolute inset-0 blur-2xl opacity-25"
          style={{
            background:
              "radial-gradient(closest-side, rgba(239,43,45,0.55), transparent 70%)",
          }}
        />
        <div
          className={`relative font-display leading-none flex text-[#F5F1E8] ${sizeClass}`}
        >
          <Digit char={v[0]} size={compact ? "compact" : "hero"} />
          <Digit char={v[1]} size={compact ? "compact" : "hero"} />
        </div>
      </motion.div>
      <div className="font-accent uppercase tracking-widest text-[10px] sm:text-xs text-[#A1A1A1] mt-2">
        {label}
      </div>
    </div>
  );
}

function Colon({ compact }) {
  return (
    <div
      className={`font-display text-[#EF2B2D] leading-none ${
        compact ? "text-3xl md:text-5xl" : "text-5xl md:text-7xl"
      }`}
    >
      <motion.span
        aria-hidden
        animate={{ opacity: [1, 0.25, 1] }}
        transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
        className="inline-block"
      >
        :
      </motion.span>
    </div>
  );
}

export default function ClosedHero({ compact = false }) {
  const { status } = useRestaurantStatus(30000);
  const { t } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  const [formOpen, setFormOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const timeoutRef = useRef(null);

  // Precise second-boundary ticker: fires exactly on the next 1-second wall
  // clock tick, so digits flip in sync with real time (no drift).
  useEffect(() => {
    const tick = () => {
      const t0 = Date.now();
      setNow(t0);
      const drift = t0 % 1000;
      timeoutRef.current = setTimeout(tick, 1000 - drift);
    };
    const drift = Date.now() % 1000;
    timeoutRef.current = setTimeout(tick, 1000 - drift);
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const countdown = useMemo(() => {
    const iso = status?.next_open_at_iso;
    if (!iso) return null;
    const target = new Date(iso).getTime();
    if (Number.isNaN(target)) return null;
    const diff = Math.max(0, target - now);
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    return { h, m, s, total: diff };
  }, [status, now]);

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
    <motion.div
      data-testid="closed-hero"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={`bt-card border-[#EF2B2D] relative overflow-hidden ${
        compact ? "p-6" : "p-6 sm:p-10 md:p-14"
      }`}
    >
      <div className="absolute inset-0 bt-halftone opacity-10 pointer-events-none" />
      <motion.div
        aria-hidden
        className="absolute -top-4 left-8 h-3 w-40 bt-tape opacity-80"
        initial={{ x: -30, rotate: -2 }}
        animate={{ x: 0, rotate: -1 }}
        transition={{ duration: 0.6 }}
      />
      <motion.div
        aria-hidden
        className="absolute -bottom-4 right-12 h-3 w-32 bt-tape opacity-60"
        initial={{ x: 30, rotate: 2 }}
        animate={{ x: 0, rotate: 1 }}
        transition={{ duration: 0.6, delay: 0.05 }}
      />

      <div className="relative">
        <div className="flex items-center gap-2">
          <motion.span
            className="w-2 h-2 rounded-full bg-[#FF3B30]"
            animate={{ opacity: [1, 0.35, 1], scale: [1, 1.35, 1] }}
            transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
          />
          <div className="font-marker text-[#EF2B2D] -rotate-1 text-lg">Pause</div>
        </div>
        <div
          className={`font-display uppercase mt-2 leading-none text-[#F5F1E8] ${
            compact ? "text-4xl md:text-5xl" : "text-5xl sm:text-6xl md:text-8xl"
          }`}
        >
          {t("closed.title", "Fermé pour l'instant")}
        </div>
        <p
          className={`text-[#B3B3B3] mt-4 max-w-xl ${
            compact ? "text-sm" : "text-base md:text-lg"
          }`}
        >
          {subtitle}
        </p>

        {countdown && countdown.total > 0 && (
          <div className="mt-8">
            <div className="bt-label mb-3 inline-flex items-center gap-2 text-[#EF2B2D]">
              <Clock className="w-3 h-3" />
              {t("closed.opens_in", "Réouverture dans")}
            </div>
            <div className="flex items-baseline gap-2 sm:gap-3 md:gap-5">
              <Cell
                value={countdown.h}
                label="H"
                testId="closed-cd-h"
                pulseKey={countdown.h}
                compact={compact}
              />
              <Colon compact={compact} />
              <Cell
                value={countdown.m}
                label="Min"
                testId="closed-cd-m"
                pulseKey={countdown.m}
                compact={compact}
              />
              <Colon compact={compact} />
              <Cell
                value={countdown.s}
                label="Sec"
                testId="closed-cd-s"
                pulseKey={countdown.s}
                compact={compact}
              />
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
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="max-w-md"
            >
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
            </motion.div>
          )}
          {done && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
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
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
