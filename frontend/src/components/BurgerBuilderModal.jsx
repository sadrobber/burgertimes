import React, { useEffect, useMemo, useState } from "react";
import { X, ChevronRight, ChevronLeft, Check } from "lucide-react";
import { apiClient, formatEur } from "@/lib/api";
import { useCart } from "@/context/CartContext.jsx";
import { useI18n } from "@/context/I18nContext.jsx";
import { toast } from "sonner";

const STEP_KEYS = ["format", "style", "size", "meats", "cheeses", "supplements", "sauces"];

export default function BurgerBuilderModal({ open, onClose }) {
  const { t } = useI18n();
  const { addBurgerItem } = useCart();
  const [config, setConfig] = useState(null);
  const [settings, setSettings] = useState(null);
  const [sauces, setSauces] = useState([]);
  const [stepIdx, setStepIdx] = useState(0);

  const [formula, setFormula] = useState("seul"); // 'seul' | 'menu'
  const [drink, setDrink] = useState("");
  const [styleId, setStyleId] = useState(null);
  const [sizeId, setSizeId] = useState(null);
  const [meats, setMeats] = useState([]);
  const [cheeses, setCheeses] = useState([]);
  const [supplements, setSupplements] = useState([]);
  const [chosenSauces, setChosenSauces] = useState([]);

  useEffect(() => {
    if (!open) return;
    setStepIdx(0);
    setFormula("seul");
    setDrink("");
    setStyleId(null);
    setSizeId(null);
    setMeats([]);
    setCheeses([]);
    setSupplements([]);
    setChosenSauces([]);
    Promise.all([
      apiClient.get("/burger/config").then((r) => r.data),
      apiClient.get("/settings").then((r) => r.data),
      apiClient.get("/sauces").then((r) => r.data),
    ])
      .then(([cfg, s, sc]) => {
        setConfig(cfg);
        setSettings(s);
        setSauces(sc || []);
        // Auto-select the sole style when only one is configured (e.g. Tacos).
        if ((cfg?.styles || []).length === 1) {
          setStyleId(cfg.styles[0].id);
        }
      })
      .catch(() => toast.error("Impossible de charger la configuration"));
  }, [open]);

  const style = useMemo(
    () => config?.styles?.find((s) => s.id === styleId) || null,
    [config, styleId]
  );
  const size = useMemo(
    () => config?.sizes?.find((s) => s.id === sizeId) || null,
    [config, sizeId]
  );
  const isFlat = !!(style && style.flat_price != null);
  const requiredMeats = isFlat ? style?.max_meats || 1 : size?.nb_meats || 1;

  const steps = useMemo(() => {
    const styles = config?.styles || [];
    const ordered = ["format"];
    // Skip the style step when there's only one style — it's auto-selected below.
    if (styles.length !== 1) ordered.push("style");
    if (!isFlat) ordered.push("size");
    ordered.push("meats");
    if ((config?.cheeses || []).length > 0) ordered.push("cheeses");
    if ((config?.supplements || []).length > 0) ordered.push("supplements");
    if ((sauces || []).length > 0) ordered.push("sauces");
    return ordered;
  }, [config, sauces, isFlat]);
  const currentStep = steps[stepIdx];

  const price = useMemo(() => {
    if (!style) return 0;
    let base;
    if (isFlat) {
      base = formula === "menu" && style.flat_price_menu != null ? style.flat_price_menu : style.flat_price;
    } else {
      if (!size) return 0;
      base = formula === "menu" ? size.price_menu : size.price_simple;
    }
    const supUp = isFlat ? 0 : size?.supplement_upcharge || 0;
    let total = (base || 0) + (style.price_modifier || 0);
    (config?.meats || []).forEach((m) => {
      if (meats.includes(m.id)) total += m.base_price || 0;
    });
    (config?.cheeses || []).forEach((c) => {
      if (cheeses.includes(c.id)) total += c.base_price || 0;
    });
    (config?.supplements || []).forEach((s) => {
      if (supplements.includes(s.id)) total += (s.base_price || 0) + supUp;
    });
    return Math.round(total * 100) / 100;
  }, [style, size, isFlat, formula, config, meats, cheeses, supplements]);

  const toggleMulti = (arr, setArr, id) =>
    setArr(arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);

  const toggleMeats = (id) => {
    if (meats.includes(id)) setMeats(meats.filter((x) => x !== id));
    else if (meats.length < requiredMeats) setMeats([...meats, id]);
    else if (requiredMeats === 1) setMeats([id]);
    else toast.info(`${t("burger.select_meats_hint")} ${requiredMeats}`);
  };

  const canNext = () => {
    if (currentStep === "format") return formula === "seul" || (formula === "menu" && !!drink);
    if (currentStep === "style") return !!styleId;
    if (currentStep === "size") return !!sizeId;
    if (currentStep === "meats") return meats.length === requiredMeats;
    if (currentStep === "cheeses") return true;
    if (currentStep === "supplements") return true;
    if (currentStep === "sauces") return true;
    return true;
  };

  const goNext = () => {
    if (!canNext()) return;
    if (stepIdx < steps.length - 1) setStepIdx(stepIdx + 1);
    else finish();
  };
  const goBack = () => {
    if (stepIdx > 0) setStepIdx(stepIdx - 1);
  };

  const finish = () => {
    if (!styleId) return;
    const nameParts = [style?.name || "Burger"];
    if (!isFlat && size) nameParts.push(size.label);
    const meatNames = (config?.meats || []).filter((m) => meats.includes(m.id)).map((m) => m.name);
    if (meatNames.length) nameParts.push(meatNames.join(", "));
    const displayName = nameParts.join(" · ") + (formula === "menu" ? " (Menu)" : "");
    addBurgerItem({
      is_burger: true,
      item_id: null,
      name: displayName,
      formula,
      quantity: 1,
      unit_price: price,
      sauces: chosenSauces,
      included_drink: formula === "menu" ? drink : null,
      included_drink_variant: null,
      selected_format: null,
      selected_variant: null,
      notes: null,
      burger_config: {
        style_id: styleId,
        size_id: isFlat ? null : sizeId,
        meat_ids: meats,
        cheese_ids: cheeses,
        supplement_ids: supplements,
        sauces: chosenSauces,
      },
    });
    toast.success("Ajouté au panier");
    onClose && onClose();
  };

  if (!open) return null;

  return (
    <div
      data-testid="burger-builder-modal"
      className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/80 backdrop-blur-sm p-0 md:p-6"
    >
      <div className="bg-[#141414] border-2 border-[#EF2B2D] shadow-[8px_8px_0_0_#EF2B2D] w-full md:max-w-3xl max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between border-b-2 border-[#262626] p-4">
          <div>
            <div className="text-xs font-accent tracking-widest text-[#EF2B2D]">
              {t("menu.build_burger")}
            </div>
            <h3 className="font-display text-2xl uppercase leading-none">Tacos sur mesure</h3>
          </div>
          <button
            data-testid="burger-builder-close"
            onClick={onClose}
            className="w-10 h-10 border-2 border-[#262626] hover:border-[#EF2B2D] flex items-center justify-center"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Steps nav */}
        <div className="flex overflow-x-auto gap-2 px-4 pt-3 pb-1 border-b border-[#262626]">
          {steps.map((s, i) => (
            <button
              key={s}
              data-testid={`burger-step-${s}`}
              onClick={() => (i <= stepIdx ? setStepIdx(i) : null)}
              className={`shrink-0 font-accent uppercase tracking-widest text-xs px-3 py-2 border-2 transition-colors ${
                i === stepIdx
                  ? "border-[#EF2B2D] text-[#EF2B2D]"
                  : i < stepIdx
                  ? "border-[#262626] text-[#F5F1E8]"
                  : "border-transparent text-[#666]"
              }`}
            >
              {i + 1}. {t(`burger.step.${s}`)}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 md:p-6">
          {currentStep === "format" && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                {["seul", "menu"].map((f) => (
                  <button
                    key={f}
                    data-testid={`burger-formula-${f}`}
                    onClick={() => setFormula(f)}
                    className={`bt-option ${formula === f ? "selected" : ""} text-left`}
                  >
                    <div className="font-accent uppercase tracking-widest text-lg">
                      {t(`menu.formula.${f}`)}
                    </div>
                    <div className="text-xs text-[#A1A1A1] mt-1">
                      {f === "menu" ? "+ boisson" : "à la carte"}
                    </div>
                  </button>
                ))}
              </div>
              {formula === "menu" && (
                <div>
                  <div className="bt-label">{t("menu.select_drink")}</div>
                  <div className="flex flex-wrap gap-2">
                    {(settings?.soda_flavours || []).map((d) => (
                      <button
                        key={d}
                        data-testid={`burger-drink-${d}`}
                        onClick={() => setDrink(d)}
                        className={`bt-chip ${drink === d ? "active" : ""}`}
                      >
                        {d}
                      </button>
                    ))}
                    {(settings?.soda_flavours || []).length === 0 && (
                      <div className="text-sm text-[#A1A1A1]">
                        Aucune boisson configurée. Ajoute-les depuis l&apos;admin.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {currentStep === "style" && (
            <StepGrid
              testIdPrefix="burger-style"
              items={config?.styles || []}
              selectedId={styleId}
              onSelect={(id) => {
                setStyleId(id);
                setMeats([]);
                setSizeId(null);
              }}
              renderLabel={(s) => (
                <>
                  <div className="font-accent uppercase text-lg tracking-widest">{s.name}</div>
                  {s.description && (
                    <div className="text-xs text-[#A1A1A1] mt-1">{s.description}</div>
                  )}
                  {s.flat_price != null ? (
                    <div className="text-sm mt-2 text-[#EF2B2D]">
                      Dès {formatEur(s.flat_price)}
                    </div>
                  ) : s.price_modifier ? (
                    <div className="text-sm mt-2 text-[#EF2B2D]">
                      +{formatEur(s.price_modifier)}
                    </div>
                  ) : null}
                </>
              )}
              emptyText="Aucun style configuré. Ajoute-en depuis l'admin (Burger Builder → Styles)."
            />
          )}

          {currentStep === "size" && (
            <StepGrid
              testIdPrefix="burger-size"
              items={config?.sizes || []}
              selectedId={sizeId}
              onSelect={(id) => {
                setSizeId(id);
                setMeats([]);
              }}
              renderLabel={(s) => (
                <>
                  <div className="font-accent uppercase text-lg tracking-widest">{s.label}</div>
                  <div className="text-xs text-[#A1A1A1] mt-1">{s.nb_meats} viande(s)</div>
                  <div className="text-sm mt-2 text-[#EF2B2D]">
                    {formatEur(formula === "menu" ? s.price_menu : s.price_simple)}
                  </div>
                </>
              )}
              emptyText="Aucune taille configurée."
            />
          )}

          {currentStep === "meats" && (
            <>
              <div className="text-xs text-[#A1A1A1] font-accent uppercase tracking-widest mb-2">
                {t("burger.select_meats_hint")} {requiredMeats}
              </div>
              <StepGrid
                testIdPrefix="burger-meat"
                items={config?.meats || []}
                multi
                selectedIds={meats}
                onToggle={toggleMeats}
                renderLabel={(m) => (
                  <>
                    <div className="font-accent uppercase text-lg tracking-widest">{m.name}</div>
                    {m.base_price > 0 && (
                      <div className="text-xs text-[#EF2B2D] mt-1">+{formatEur(m.base_price)}</div>
                    )}
                  </>
                )}
                emptyText="Aucune viande configurée."
              />
            </>
          )}

          {currentStep === "cheeses" && (
            <StepGrid
              testIdPrefix="burger-cheese"
              items={config?.cheeses || []}
              multi
              selectedIds={cheeses}
              onToggle={(id) => toggleMulti(cheeses, setCheeses, id)}
              renderLabel={(c) => (
                <>
                  <div className="font-accent uppercase text-lg tracking-widest">{c.name}</div>
                  {c.base_price > 0 && (
                    <div className="text-xs text-[#EF2B2D] mt-1">+{formatEur(c.base_price)}</div>
                  )}
                </>
              )}
              emptyText="Aucun fromage configuré."
            />
          )}

          {currentStep === "supplements" && (
            <StepGrid
              testIdPrefix="burger-supplement"
              items={config?.supplements || []}
              multi
              selectedIds={supplements}
              onToggle={(id) => toggleMulti(supplements, setSupplements, id)}
              renderLabel={(s) => (
                <>
                  <div className="font-accent uppercase text-lg tracking-widest">{s.name}</div>
                  {s.base_price > 0 && (
                    <div className="text-xs text-[#EF2B2D] mt-1">+{formatEur(s.base_price)}</div>
                  )}
                </>
              )}
              emptyText="Aucun supplément."
            />
          )}

          {currentStep === "sauces" && (
            <div className="flex flex-wrap gap-2">
              {(sauces || []).map((s) => (
                <button
                  key={s.id}
                  data-testid={`burger-sauce-${s.id}`}
                  onClick={() =>
                    setChosenSauces(
                      chosenSauces.includes(s.name)
                        ? chosenSauces.filter((x) => x !== s.name)
                        : [...chosenSauces, s.name]
                    )
                  }
                  className={`bt-chip ${chosenSauces.includes(s.name) ? "active" : ""}`}
                >
                  {chosenSauces.includes(s.name) && <Check className="w-3 h-3" />}
                  {s.name}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="border-t-2 border-[#262626] p-4 flex items-center justify-between gap-4 bg-[#0A0A0A]">
          <div className="flex items-center gap-3">
            <button
              onClick={goBack}
              disabled={stepIdx === 0}
              data-testid="burger-builder-back"
              className="bt-btn-secondary py-2 px-4 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" /> {t("burger.back")}
            </button>
            <div className="font-display text-2xl">
              {price > 0 && (style && (isFlat || size)) ? formatEur(price) : "—"}
            </div>
          </div>
          <button
            onClick={goNext}
            disabled={!canNext()}
            data-testid="burger-builder-next"
            className="bt-btn-primary py-3 px-6 text-base disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {stepIdx === steps.length - 1 ? (
              <>
                {t("burger.add_to_cart")}
                {formatEur(price)}
              </>
            ) : (
              <>
                {t("burger.next")} <ChevronRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function StepGrid({
  items,
  selectedId,
  onSelect,
  selectedIds,
  onToggle,
  multi,
  renderLabel,
  testIdPrefix,
  emptyText,
}) {
  if (!items || items.length === 0) {
    return <div className="text-sm text-[#A1A1A1] p-4 border-2 border-[#262626]">{emptyText}</div>;
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
      {items.map((it) => {
        const active = multi ? (selectedIds || []).includes(it.id) : selectedId === it.id;
        return (
          <button
            key={it.id}
            data-testid={`${testIdPrefix}-${it.id}`}
            onClick={() => (multi ? onToggle(it.id) : onSelect(it.id))}
            className={`bt-option text-left ${active ? "selected" : ""}`}
          >
            {renderLabel(it)}
          </button>
        );
      })}
    </div>
  );
}
