import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import Header from "@/components/layout/Header.jsx";
import Footer from "@/components/layout/Footer.jsx";
import MenuItemCard from "@/components/MenuItemCard.jsx";
import TacosBuilderCard from "@/components/TacosBuilderCard.jsx";
import BurgerBuilderModal from "@/components/BurgerBuilderModal.jsx";
import { apiClient } from "@/lib/api";
import { useI18n } from "@/context/I18nContext.jsx";

/**
 * Menu page: all categories rendered as vertically stacked sections. A sticky
 * category nav sits under the site header and highlights the section currently
 * in view via IntersectionObserver. Clicking a nav chip smooth-scrolls to
 * that section. The Tacos Builder appears as a normal menu-item card at the
 * top of the first category.
 */
export default function Menu() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [settings, setSettings] = useState(null);
  const [activeCat, setActiveCat] = useState(null);
  const [loading, setLoading] = useState(true);
  const [builderOpen, setBuilderOpen] = useState(false);

  // Refs to each section so IntersectionObserver can watch them.
  const sectionRefs = useRef({});
  // While a programmatic scroll is animating, ignore IO updates so the click
  // doesn't briefly light up a chip on the way past.
  const programmaticScroll = useRef(false);

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

  // Only show categories that have at least one menu item.
  const visibleCategories = useMemo(() => {
    const withItems = new Set(items.map((it) => it.category));
    return categories.filter((c) => withItems.has(c.slug));
  }, [items, categories]);

  useEffect(() => {
    if (activeCat === null && visibleCategories.length > 0) {
      setActiveCat(visibleCategories[0].slug);
    }
  }, [activeCat, visibleCategories]);

  const itemsByCategory = useMemo(() => {
    const out = {};
    for (const c of visibleCategories) {
      out[c.slug] = items.filter((it) => it.category === c.slug);
    }
    return out;
  }, [items, visibleCategories]);

  // Scrollspy: mark the section closest to the top of the viewport as active.
  useEffect(() => {
    if (!visibleCategories.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (programmaticScroll.current) return;
        // pick the entry with the greatest intersection ratio that is intersecting
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length) {
          const slug = visible[0].target.dataset.categorySlug;
          if (slug) setActiveCat(slug);
        }
      },
      {
        // A section is "in view" once its top has crossed 40% down and while its
        // bottom is still above 40% up — i.e. it fills the middle of the screen.
        rootMargin: "-40% 0px -40% 0px",
        threshold: [0, 0.1, 0.5, 1],
      },
    );
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [visibleCategories]);

  const scrollToCat = useCallback((slug) => {
    const el = sectionRefs.current[slug];
    if (!el) return;
    programmaticScroll.current = true;
    setActiveCat(slug); // immediate feedback
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    // release the IO lock after the animation settles
    window.setTimeout(() => {
      programmaticScroll.current = false;
    }, 750);
  }, []);

  const labelFor = (label) => {
    if (!label) return "";
    if (typeof label === "string") return label;
    return label[lang] || label.fr || label.en || "";
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]">
      <Header />

      {/* Sticky category nav — highlights the section currently on screen */}
      <div
        data-testid="menu-cat-nav"
        className="sticky top-16 md:top-20 z-30 bg-[#0A0A0A]/95 backdrop-blur border-y-2 border-[#EF2B2D]"
      >
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
          <div className="flex gap-1.5 sm:gap-2 overflow-x-auto md:overflow-visible md:flex-wrap md:justify-center py-2.5 md:py-3 no-scrollbar">
            {visibleCategories.map((c) => (
              <button
                key={c.id}
                onClick={() => scrollToCat(c.slug)}
                data-testid={`cat-${c.slug}`}
                className={`bt-chip whitespace-nowrap text-xs sm:text-sm ${activeCat === c.slug ? "active" : ""}`}
              >
                {labelFor(c.label)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-16">
        <div className="mb-8">
          <div className="font-marker text-[#EF2B2D] text-xl -rotate-2">Chaud devant</div>
          <h1 className="font-display text-6xl md:text-7xl uppercase mt-2">{t("menu.title")}</h1>
        </div>

        {loading ? (
          <div className="text-[#A1A1A1] py-20 text-center">Chargement…</div>
        ) : visibleCategories.length === 0 ? (
          <div className="bt-card p-10 text-center" data-testid="menu-empty">
            <div className="font-display text-2xl uppercase mb-2">Rien à afficher</div>
            <div className="text-[#A1A1A1]">
              Ajoute des articles depuis l&apos;admin pour peupler le menu.
            </div>
          </div>
        ) : (
          <div className="space-y-14 md:space-y-20">
            {visibleCategories.map((c, ci) => {
              const catItems = itemsByCategory[c.slug] || [];
              return (
                <section
                  key={c.slug}
                  ref={(el) => (sectionRefs.current[c.slug] = el)}
                  data-category-section
                  data-category-slug={c.slug}
                  data-testid={`section-${c.slug}`}
                  className="scroll-mt-40"
                >
                  <div className="flex items-baseline gap-3 mb-6">
                    <div className="w-2 h-8 bg-[#EF2B2D]" />
                    <h2 className="font-display text-3xl md:text-5xl uppercase leading-none">
                      {labelFor(c.label)}
                    </h2>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-6">
                    {/* Tacos builder card lives inside the first visible category */}
                    {ci === 0 && (
                      <motion.div
                        initial={{ opacity: 0, y: 14 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, amount: 0.2 }}
                        transition={{ duration: 0.35 }}
                      >
                        <TacosBuilderCard onOpen={() => setBuilderOpen(true)} />
                      </motion.div>
                    )}
                    {catItems.map((it, i) => (
                      <motion.div
                        key={it.id}
                        initial={{ opacity: 0, y: 14 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, amount: 0.2 }}
                        transition={{
                          duration: 0.35,
                          delay: Math.min((i % 6) * 0.05, 0.3),
                        }}
                      >
                        <MenuItemCard item={it} sodaFlavours={settings?.soda_flavours || []} />
                      </motion.div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </section>

      <BurgerBuilderModal open={builderOpen} onClose={() => setBuilderOpen(false)} />
      <Footer />
    </div>
  );
}
