import React, { useMemo } from "react";
import { useI18n } from "@/context/I18nContext.jsx";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";

const styles = {
  open: "border-[#00FF66] text-[#00FF66] bg-[#00FF66]/10",
  closing_soon: "border-[#FFB800] text-[#FFB800] bg-[#FFB800]/10",
  closed: "border-[#FF3B30] text-[#FF3B30] bg-[#FF3B30]/10",
};

export default function StatusBanner({ variant = "pill" }) {
  const { t } = useI18n();
  const { status } = useRestaurantStatus();

  const info = useMemo(() => {
    if (!status) return null;
    const label =
      status.state === "open"
        ? t("status.open")
        : status.state === "closing_soon"
        ? t("status.closing_soon")
        : t("status.closed");
    let sub = null;
    if (status.state === "closed") {
      if (status.next_open_at_local) {
        const day =
          status.next_open_day === "today"
            ? t("status.today")
            : status.next_open_day === "tomorrow"
            ? t("status.tomorrow")
            : status.next_open_day;
        sub = `${t("status.next_open")} ${day} · ${status.next_open_at_local}`;
      }
    } else if (status.state === "closing_soon") {
      sub = status.closing_at_local ? `→ ${status.closing_at_local}` : null;
    } else if (status.state === "open") {
      sub = `${t("status.eta")} ${status.eta_min}–${status.eta_max} min`;
    }
    return { label, sub };
  }, [status, t]);

  if (!status || !info) return null;

  if (variant === "banner") {
    return (
      <div
        data-testid="status-banner"
        className={`w-full border-2 px-4 py-3 flex items-center gap-3 font-accent tracking-widest uppercase ${styles[status.state] || styles.closed}`}
      >
        <span className={`w-2 h-2 rounded-full ${status.state === "open" ? "bg-[#00FF66]" : status.state === "closing_soon" ? "bg-[#FFB800]" : "bg-[#FF3B30]"} animate-pulse`} />
        <span className="text-sm md:text-base">{info.label}</span>
        {info.sub && <span className="text-xs md:text-sm opacity-80">{info.sub}</span>}
      </div>
    );
  }

  return (
    <span
      data-testid={`status-pill-${status.state}`}
      className={`inline-flex items-center gap-2 px-3 py-1 font-accent tracking-widest text-xs sm:text-sm border-2 uppercase ${styles[status.state] || styles.closed}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${status.state === "open" ? "bg-[#00FF66]" : status.state === "closing_soon" ? "bg-[#FFB800]" : "bg-[#FF3B30]"} animate-pulse`} />
      {info.label}
      {info.sub && <span className="opacity-80 normal-case tracking-normal ml-1">· {info.sub}</span>}
    </span>
  );
}
