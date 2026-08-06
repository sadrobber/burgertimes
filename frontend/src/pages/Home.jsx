import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Instagram, Phone, MapPin, ArrowRight, Flame } from "lucide-react";
import Header from "@/components/layout/Header.jsx";
import Footer from "@/components/layout/Footer.jsx";
import StatusBanner from "@/components/StatusBanner.jsx";
import ClosedHero from "@/components/ClosedHero.jsx";
import { apiClient } from "@/lib/api";
import { useI18n } from "@/context/I18nContext.jsx";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";

const HERO_IMG =
  "https://images.unsplash.com/photo-1678110707289-ab14382a1625?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzl8MHwxfHNlYXJjaHwyfHxzbWFzaCUyMGJ1cmdlciUyMGJsYWNrJTIwYmFja2dyb3VuZHxlbnwwfHx8fDE3ODU4NzcyNDF8MA&ixlib=rb-4.1.0&q=85";

export default function Home() {
  const { t } = useI18n();
  const [reviews, setReviews] = useState([]);
  const [settings, setSettings] = useState(null);
  const { status } = useRestaurantStatus();
  const isClosed = status?.state === "closed";

  useEffect(() => {
    apiClient.get("/reviews").then((r) => setReviews(r.data || [])).catch(() => {});
    apiClient.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]">
      <Header />

      {isClosed && (
        <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
          <ClosedHero />
        </section>
      )}

      {/* HERO — compact so the order CTA sits above the fold */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-0">
          <img
            src={HERO_IMG}
            alt="Smash burger"
            className="w-full h-full object-cover opacity-60"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A]/70 to-transparent" />
          <div className="absolute inset-0 bt-halftone opacity-20" />
        </div>
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-10 md:pt-10 md:pb-14">
          <div className="max-w-3xl">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 bg-[#EF2B2D] px-3 py-1 font-accent uppercase tracking-widest text-xs"
            >
              <Flame className="w-3 h-3" /> Beausoleil · @burgertimes_bsl
            </motion.div>
            <motion.h1
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="mt-3 md:mt-4 font-display text-5xl sm:text-6xl md:text-7xl uppercase leading-[0.85]"
            >
              <span className="block">Smash.</span>
              <span className="block text-[#EF2B2D]">Sizzle.</span>
              <span className="block">Serve.</span>
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="mt-4 md:mt-5 text-base md:text-lg text-[#D1D1D1] max-w-xl"
            >
              {t("hero.subtitle")}
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="mt-5 md:mt-6 flex flex-wrap items-center gap-3"
            >
              <Link to="/menu" data-testid="hero-order-cta" className="bt-btn-primary">
                {t("cta.order_now")} <ArrowRight className="w-5 h-5" />
              </Link>
            </motion.div>
            <div className="mt-5 md:mt-6">
              <StatusBanner variant="banner" />
            </div>
          </div>
        </div>
      </section>

      {/* Info strip */}
      <section className="bg-[#141414] border-y-2 border-[#262626]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <Phone className="w-6 h-6 text-[#EF2B2D] mt-0.5" />
            <div>
              <div className="font-accent uppercase tracking-widest text-xs text-[#A1A1A1]">Appelle</div>
              <div className="text-lg">{settings?.contact_phone || "04.97.07.17.93"}</div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MapPin className="w-6 h-6 text-[#EF2B2D] mt-0.5" />
            <div>
              <div className="font-accent uppercase tracking-widest text-xs text-[#A1A1A1]">Adresse</div>
              <div className="text-lg">{settings?.contact_address || "6 Avenue de Villaine, 06240 Beausoleil"}</div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Instagram className="w-6 h-6 text-[#EF2B2D] mt-0.5" />
            <div>
              <div className="font-accent uppercase tracking-widest text-xs text-[#A1A1A1]">Instagram</div>
              <div className="text-lg">
                <a
                  href={`https://instagram.com/${(settings?.contact_instagram || "@burgertimes_bsl").replace("@", "")}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-[#EF2B2D]"
                >
                  {settings?.contact_instagram || "@burgertimes_bsl"}
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {reviews.length > 0 && (
        <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <h2 className="font-display text-5xl md:text-6xl mb-10">Ils en ont bavé (bien)</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {reviews.slice(0, 6).map((r) => (
              <div key={r.id} className="bt-card p-6" data-testid={`review-${r.id}`}>
                <div className="text-[#EF2B2D] font-accent tracking-widest text-lg">
                  {"★".repeat(r.rating)}
                  <span className="opacity-30">{"★".repeat(5 - r.rating)}</span>
                </div>
                <p className="mt-3 text-[#D1D1D1]">&laquo; {r.comment} &raquo;</p>
                <div className="mt-4 text-sm font-accent uppercase tracking-widest text-[#A1A1A1]">
                  — {r.author_name}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <Footer />
    </div>
  );
}
