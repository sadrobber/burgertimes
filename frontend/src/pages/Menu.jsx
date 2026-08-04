import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import Header from "@/components/layout/Header.jsx";
import Footer from "@/components/layout/Footer.jsx";
import MenuItemCard from "@/components/MenuItemCard.jsx";
import BurgerBuilderModal from "@/components/BurgerBuilderModal.jsx";
import StatusBanner from "@/components/StatusBanner.jsx";
import { apiClient } from "@/lib/api";
import { useI18n } from "@/context/I18nContext.jsx";

export default function Menu() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [settings, setSettings] = useState(null);
  const [activeCat, setActiveCat] = useState("all");
  const [loading, setLoading] = useState(true);
  const [builderOpen, setBuilderOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      apiClient.get("/menu").then((r) => r.data),
      apiClient.get("/categories").then((r) => r.data),
      apiClient.get("/settings").then((r) => r.data),
    ])
      .then(([m, c, s]) => {
        setItems(m || []);
        setCategories(c || []);
        setSettings(s);
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (activeCat === "all") return items;
    return items.filter((it) => it.category === activeCat);
  }, [items, activeCat]);

  const labelFor = (label) => {
    if (!label) return "";
    if (typeof label === "string") return label;
    return label[lang] || label.fr || label.en || "";
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]">
      <Header />
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 md:py-20">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
          <div>
            <div className="font-marker text-[#EF2B2D] text-xl -rotate-2">Chaud devant</div>
            <h1 className="font-display text-6xl md:text-7xl uppercase mt-2">{t("menu.title")}</h1>
          </div>
          <StatusBanner variant="banner" />
        </div>

        {/* Build-a-burger CTA */}
        <div
          data-testid="build-burger-cta"
          className="bt-card p-6 md:p-8 flex flex-col md:flex-row items-start md:items-center gap-4 md:gap-6 mb-10 border-[#EF2B2D]"
        >
          <div className="flex-1">
            <div className="font-marker text-[#EF2B2D] text-lg -rotate-1">Sur mesure</div>
            <div className="font-display text-3xl md:text-4xl uppercase leading-none mt-1">
              Compose ton burger
            </div>
            <p className="text-[#D1D1D1] mt-2 max-w-lg">
              Style, taille, viandes, fromages, suppléments. Signature Burger Times.
            </p>
          </div>
          <button
            onClick={() => setBuilderOpen(true)}
            data-testid="open-burger-builder"
            className="bt-btn-primary"
          >
            <Sparkles className="w-4 h-4" /> {t("menu.build_burger")}
          </button>
        </div>

        {/* Category tabs */}
        <div className="flex flex-wrap gap-2 mb-8">
          <button
            onClick={() => setActiveCat("all")}
            data-testid="cat-all"
            className={`bt-chip ${activeCat === "all" ? "active" : ""}`}
          >
            {t("menu.all")}
          </button>
          {categories.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveCat(c.slug)}
              data-testid={`cat-${c.slug}`}
              className={`bt-chip ${activeCat === c.slug ? "active" : ""}`}
            >
              {labelFor(c.label)}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-[#A1A1A1] py-20 text-center">Chargement…</div>
        ) : filtered.length === 0 ? (
          <div className="bt-card p-10 text-center" data-testid="menu-empty">
            <div className="font-display text-2xl uppercase mb-2">Rien à afficher</div>
            <div className="text-[#A1A1A1]">
              Ajoute des articles depuis l&apos;admin pour peupler le menu.
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
            {filtered.map((it, i) => (
              <motion.div
                key={it.id}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: Math.min(i * 0.03, 0.4) }}
              >
                <MenuItemCard item={it} sodaFlavours={settings?.soda_flavours || []} />
              </motion.div>
            ))}
          </div>
        )}
      </section>

      <BurgerBuilderModal open={builderOpen} onClose={() => setBuilderOpen(false)} />
      <Footer />
    </div>
  );
}
