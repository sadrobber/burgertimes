import React from "react";
import { Instagram, Phone, MapPin } from "lucide-react";
import { useI18n } from "@/context/I18nContext.jsx";
import { apiClient } from "@/lib/api";

export default function Footer() {
  const { t } = useI18n();
  const [settings, setSettings] = React.useState(null);
  const [status, setStatus] = React.useState(null);
  React.useEffect(() => {
    apiClient.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
    apiClient.get("/restaurant/status").then((r) => setStatus(r.data)).catch(() => {});
  }, []);
  const phone = settings?.contact_phone || "04.97.07.17.93";
  const address = settings?.contact_address || "6 Avenue de Villaine, 06240 Beausoleil";
  const ig = settings?.contact_instagram || "@burgertimes_bsl";

  const days = [
    ["mon", "Lundi"],
    ["tue", "Mardi"],
    ["wed", "Mercredi"],
    ["thu", "Jeudi"],
    ["fri", "Vendredi"],
    ["sat", "Samedi"],
    ["sun", "Dimanche"],
  ];

  return (
    <footer className="border-t-2 border-[#262626] bg-[#0A0A0A] mt-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
          <div>
            <div className="font-display text-4xl uppercase leading-none">
              <span className="text-[#F5F1E8]">Burger</span>
              <span className="text-[#EF2B2D]">Times</span>
            </div>
            <p className="text-sm text-[#A1A1A1] mt-4 max-w-xs">
              Smash burgers, sandwiches et wraps. Cuits à la commande, pris sans détour.
            </p>
            <div className="mt-6 h-2 bt-tape w-24" />
          </div>

          <div>
            <div className="bt-label mb-3">{t("footer.contact")}</div>
            <a
              href={`tel:${phone.replace(/\./g, "")}`}
              data-testid="footer-phone"
              className="flex items-center gap-2 hover:text-[#EF2B2D] transition-colors"
            >
              <Phone className="w-4 h-4" /> {phone}
            </a>
            <a
              href={`https://instagram.com/${ig.replace("@", "")}`}
              target="_blank"
              rel="noreferrer"
              data-testid="footer-instagram"
              className="flex items-center gap-2 mt-2 hover:text-[#EF2B2D] transition-colors"
            >
              <Instagram className="w-4 h-4" /> {ig}
            </a>
            <div className="flex items-start gap-2 mt-2 text-[#B3B3B3]" data-testid="footer-address">
              <MapPin className="w-4 h-4 mt-0.5" />
              <span>{address}</span>
            </div>
          </div>

          <div>
            <div className="bt-label mb-3">{t("footer.hours")}</div>
            <ul className="text-sm space-y-1 text-[#B3B3B3]">
              {days.map(([key, label]) => {
                const cfg = settings?.hours_per_day?.[key];
                const open = cfg?.is_open && (cfg.ranges || []).length > 0;
                return (
                  <li key={key} className="flex justify-between gap-4">
                    <span className="uppercase tracking-wider text-[#F5F1E8]">{label}</span>
                    <span>
                      {open
                        ? (cfg.ranges || [])
                            .map((r) => `${r.open}–${r.close}`)
                            .join(", ")
                        : "Fermé"}
                    </span>
                  </li>
                );
              })}
            </ul>
            {status && (
              <div className="mt-4 text-xs uppercase tracking-widest text-[#A1A1A1]">
                {status.state === "open"
                  ? "Ouvert · commandes acceptées"
                  : status.state === "closing_soon"
                  ? "Ferme bientôt"
                  : "Fermé"}
              </div>
            )}
          </div>
        </div>
        <div className="mt-16 pt-6 border-t border-[#262626] text-xs text-[#666] flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <div>© Burger Times · Beausoleil</div>
          <div>Site fait avec les mains sales.</div>
        </div>
      </div>
    </footer>
  );
}
