import React from "react";
import { Plus } from "lucide-react";
import ItemConfigurationModal from "@/components/ItemConfigurationModal.jsx";
import { formatEur, menuImageUrl } from "@/lib/api";
import { useCart } from "@/context/CartContext.jsx";
import { useI18n } from "@/context/I18nContext.jsx";
import { toast } from "sonner";

export default function MenuItemCard({ compact = false, dense = false, tablet = false, item, sauceOptions = [], sodaFlavours = [], supplementOptions = [] }) {
  const { addPlainItem } = useCart();
  const { t } = useI18n();
  const [openConfig, setOpenConfig] = React.useState(false);
  const [formula, setFormula] = React.useState("seul");
  const [selectedFormat, setSelectedFormat] = React.useState(item.formats?.[0]?.name || null);
  const [drink, setDrink] = React.useState("");
  const [removals, setRemovals] = React.useState([]);
  const [selectedSauces, setSelectedSauces] = React.useState([]);
  const [selectedSupplements, setSelectedSupplements] = React.useState([]);

  const hasMenu = item.price_menu != null || (item.formats || []).some((f) => f.price_menu != null);
  const needsDrink = formula === "menu";

  const displayPrice = React.useMemo(() => {
    const fmt = (item.formats || []).find((f) => f.name === selectedFormat);
    if (formula === "menu") {
      if (fmt && fmt.price_menu != null) return fmt.price_menu;
      if (item.price_menu != null) return item.price_menu;
    }
    if (fmt) return fmt.price_seul;
    return item.price_seul;
  }, [item, formula, selectedFormat]);

  const canAdd = formula === "seul" || (formula === "menu" && drink);

  const itemSupplements = (supplementOptions || []).filter((s) =>
    (item.supplement_options || []).includes(s.name),
  );
  const suppTotal = itemSupplements
    .filter((s) => selectedSupplements.includes(s.name))
    .reduce((sum, s) => sum + (s.price || 0), 0);
  const totalPrice = displayPrice + suppTotal;

  const doAdd = () => {
    if (!canAdd) {
      toast.error("Choisis une boisson");
      return;
    }
    const nameParts = [item.name];
    if (selectedFormat) nameParts.push(`(${selectedFormat})`);
    if (formula === "menu") nameParts.push("· Menu");
    addPlainItem({
      is_burger: false,
      item_id: item.id,
      name: nameParts.join(" "),
      formula,
      quantity: 1,
      unit_price: totalPrice,
      sauces: selectedSauces,
      included_drink: needsDrink ? drink : null,
      selected_format: selectedFormat,
      selected_variant: null,
      removable_ingredients: removals,
      supplements: selectedSupplements,
      notes: null,
    });
    toast.success("Ajouté au panier", { duration: 500 });
    setOpenConfig(false);
    setFormula("seul");
    setDrink("");
    setRemovals([]);
    setSelectedSauces([]);
    setSelectedSupplements([]);
  };

  const addLabel = compact ? "Personnaliser" : t("menu.add");
  const hasConfig = false;

  return (
    <div
      data-testid={`menu-item-${item.id}`}
      onClick={() => setOpenConfig(true)}
      role="button"
      tabIndex={0}
      className="bt-card relative flex flex-col overflow-hidden cursor-pointer"
    >
      {!compact && <div className="aspect-[4/3] w-full overflow-hidden bg-[#1A1A1A] relative">
        {item.has_image ? (
          <img
            src={menuImageUrl(item.id)}
            alt={item.name}
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bt-halftone">
            <div className="font-display text-4xl text-[#EF2B2D]/40 uppercase">BT</div>
          </div>
        )}
        <div className="absolute top-2 sm:top-3 left-2 sm:left-3">
          <span className="bt-price-pill text-[10px] sm:text-base px-2 sm:px-3 py-0.5 sm:py-1">{formatEur(item.price_seul)}</span>
        </div>
        {item.is_new && (
          <img
            src="/new-badge.png"
            alt="Nouveau"
            data-testid={`item-${item.id}-new-badge`}
            className="absolute -top-2 -right-2 w-9 h-9 sm:w-12 sm:h-12 md:w-14 md:h-14 rotate-12 pointer-events-none"
          />
        )}
      </div>}
      <div className={`${dense ? "p-2" : "p-2.5 sm:p-4"} flex-1 flex flex-col`}>
        <div className={`font-display uppercase leading-none ${dense ? "text-sm sm:text-base" : "text-base sm:text-xl md:text-2xl"}`}>{item.name}</div>
        {!dense && item.description && (
          <p className="text-xs sm:text-sm text-[#B3B3B3] mt-1.5 sm:mt-2 line-clamp-2">{item.description}</p>
        )}

        {openConfig && hasConfig && (
          <div className="mt-3 sm:mt-4 space-y-2 sm:space-y-3">
            {item.formats && item.formats.length > 0 && (
              <div>
                <div className="bt-label">
                  {item.category === "kids" ? "Choix du plat" : "Format"}
                </div>
                {item.category === "kids" ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {item.formats.map((f) => (
                      <button
                        key={f.name}
                        onClick={() => setSelectedFormat(f.name)}
                        data-testid={`item-${item.id}-format-${f.name}`}
                        className={`bt-option ${selectedFormat === f.name ? "selected" : ""} text-left p-3`}
                      >
                        <div className="font-accent uppercase tracking-widest text-sm">{f.name}</div>
                        <div className="text-xs text-[#A1A1A1] mt-1">{formatEur(f.price_seul)}</div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {item.formats.map((f) => (
                      <button
                        key={f.name}
                        onClick={() => setSelectedFormat(f.name)}
                        data-testid={`item-${item.id}-format-${f.name}`}
                        className={`bt-chip ${selectedFormat === f.name ? "active" : ""}`}
                      >
                        {f.name}
                      </button>
                    ))}
                  </div>
                )}
                {item.category === "kids" && (
                  <div className="mt-3 border-l-2 border-[#EF2B2D] pl-3">
                    <div className="bt-label">Inclus dans le menu</div>
                    <div className="text-sm text-[#B3B3B3]">
                      Frites · Capri-Sun · Kinder Maxi · Compote
                    </div>
                  </div>
                )}
              </div>
            )}
            {hasMenu && (
              <div>
                <div className="bt-label">Formule</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setFormula("seul")}
                    data-testid={`item-${item.id}-formula-seul`}
                    className={`bt-chip ${formula === "seul" ? "active" : ""}`}
                  >
                    {t("menu.formula.seul")}
                  </button>
                  <button
                    onClick={() => setFormula("menu")}
                    data-testid={`item-${item.id}-formula-menu`}
                    className={`bt-chip ${formula === "menu" ? "active" : ""}`}
                  >
                    {t("menu.formula.menu")}
                  </button>
                </div>
              </div>
            )}
            {needsDrink && (
              <div>
                <div className="bt-label">{t("menu.select_drink")}</div>
                <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                  {sodaFlavours.map((d) => (
                    <button
                      key={d}
                      data-testid={`item-${item.id}-drink-${d}`}
                      onClick={() => setDrink(d)}
                      className={`bt-chip ${drink === d ? "active" : ""}`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {item.uses_sauces && (
              <div>
                <div className="bt-label">Sauces</div>
                <div className="flex flex-wrap gap-2">
                  {sauceOptions.map((sauce) => (
                    <button
                      key={sauce}
                      data-testid={`item-${item.id}-sauce-${sauce}`}
                      onClick={() =>
                        setSelectedSauces((current) =>
                          current.includes(sauce)
                            ? current.filter((value) => value !== sauce)
                            : [...current, sauce],
                        )
                      }
                      className={`bt-chip ${selectedSauces.includes(sauce) ? "active" : ""}`}
                    >
                      {sauce}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {(item.removable_ingredients || []).length > 0 && (
              <div>
                <div className="bt-label">Retirer des ingrédients</div>
                <div className="flex flex-wrap gap-2">
                  {item.removable_ingredients.map((ingredient) => (
                    <button
                      key={ingredient}
                      data-testid={`item-${item.id}-remove-${ingredient}`}
                      onClick={() =>
                        setRemovals((current) =>
                          current.includes(ingredient)
                            ? current.filter((value) => value !== ingredient)
                            : [...current, ingredient],
                        )
                      }
                      className={`bt-chip ${removals.includes(ingredient) ? "active" : ""}`}
                    >
                      Sans {ingredient}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className={`mt-auto flex items-center gap-2 ${dense ? "pt-2" : "pt-3 sm:pt-4"}`}>
          <button
            onClick={() => setOpenConfig(true)}
            data-testid={`item-${item.id}-configure`}
            className={`bt-btn-primary flex-1 ${dense ? "py-1.5 px-2 text-xs" : "py-2 px-2.5 sm:px-4 text-xs sm:text-sm"}`}
          >
            <Plus className="w-4 h-4" /> {addLabel}
          </button>
        </div>
      </div>
      {openConfig && (
        <ItemConfigurationModal
          canAdd={canAdd}
          drink={drink}
          formula={formula}
          hasMenu={hasMenu}
          item={item}
          onAdd={doAdd}
          onClose={() => setOpenConfig(false)}
          removals={removals}
          sauceOptions={sauceOptions}
          selectedFormat={selectedFormat}
          selectedSauces={selectedSauces}
          setDrink={setDrink}
          setFormula={setFormula}
          setRemovals={setRemovals}
          setSelectedFormat={setSelectedFormat}
          setSelectedSauces={setSelectedSauces}
          selectedSupplements={selectedSupplements}
          setSelectedSupplements={setSelectedSupplements}
          supplementOptions={itemSupplements}
          sodaFlavours={sodaFlavours}
          tablet={tablet}
          total={totalPrice}
        />
      )}
    </div>
  );
}
