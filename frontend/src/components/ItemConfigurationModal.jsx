import React from "react";
import { createPortal } from "react-dom";
import { Plus, X } from "lucide-react";
import { formatEur } from "@/lib/api";

const MAX_REMOVALS = 2;
const MAX_SAUCES = 2;

export default function ItemConfigurationModal({
  canAdd,
  drink,
  formula,
  hasMenu,
  item,
  onAdd,
  onClose,
  removals,
  sauceOptions,
  selectedFormat,
  selectedSauces,
  setDrink,
  setFormula,
  setRemovals,
  setSelectedFormat,
  setSelectedSauces,
  selectedSupplements = [],
  setSelectedSupplements = () => {},
  supplementOptions = [],
  sodaFlavours,
  friesSauces = [],
  friesSauce,
  setFriesSauce = () => {},
  tablet = false,
  total,
}) {
  const chooseFormula = (nextFormula) => {
    setFormula(nextFormula);
    if (nextFormula === "seul") {
      setDrink("");
    }
  };

  const toggleSauce = (sauce) => {
    setSelectedSauces((current) => {
      if (current.includes(sauce)) return current.filter((value) => value !== sauce);
      if (current.length >= MAX_SAUCES) return current;
      return [...current, sauce];
    });
  };

  const toggleRemoval = (ingredient) => {
    setRemovals((current) => {
      if (current.includes(ingredient)) return current.filter((value) => value !== ingredient);
      if (current.length >= MAX_REMOVALS) return current;
      return [...current, ingredient];
    });
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-end bg-black/75 p-0 sm:items-center sm:p-6"
      data-testid={`item-${item.id}-config-modal`}
      onClick={onClose}
      role="presentation"
    >
      <section
        aria-modal="true"
        aria-labelledby={`item-${item.id}-config-title`}
        className="max-h-[92vh] w-full overflow-y-auto border-2 border-[#EF2B2D] bg-[#141414] p-5 shadow-2xl sm:max-w-2xl sm:p-7"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div style={tablet ? { zoom: 2 } : undefined}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="font-marker text-[#EF2B2D]">Personnalise ta commande</div>
            <h2
              className="font-display text-3xl uppercase leading-none sm:text-4xl"
              id={`item-${item.id}-config-title`}
            >
              {item.name}
            </h2>
          </div>
          <button
            aria-label="Fermer"
            className="bt-btn-ghost h-10 w-10 p-0"
            data-testid={`item-${item.id}-config-close`}
            onClick={onClose}
            type="button"
          >
            <X className="mx-auto h-5 w-5" />
          </button>
        </div>

        <div className="mt-6 space-y-6">
          {(item.formats || []).length > 0 && (
            <OptionGroup label={item.category === "kids" ? "Choix du plat" : "Format"}>
              <div className="flex flex-wrap gap-2">
                {item.formats.map((format) => (
                  <button
                    className={`bt-chip ${selectedFormat === format.name ? "active" : ""}`}
                    data-testid={`item-${item.id}-format-${format.name}`}
                    key={format.name}
                    onClick={() => setSelectedFormat(format.name)}
                    type="button"
                  >
                    {format.name}
                  </button>
                ))}
              </div>
            </OptionGroup>
          )}

          {hasMenu && (
            <OptionGroup label="Ta formule">
              <div className="grid grid-cols-2 gap-3">
                <button
                  className={`bt-option p-4 text-left ${formula === "seul" ? "selected" : ""}`}
                  data-testid={`item-${item.id}-formula-seul`}
                  onClick={() => chooseFormula("seul")}
                  type="button"
                >
                  <div className="font-accent uppercase tracking-widest">Sans menu</div>
                  <div className="mt-1 text-xs text-[#A1A1A1]">À la carte</div>
                </button>
                <button
                  className={`bt-option p-4 text-left ${formula === "menu" ? "selected" : ""}`}
                  data-testid={`item-${item.id}-formula-menu`}
                  onClick={() => chooseFormula("menu")}
                  type="button"
                >
                  <div className="font-accent uppercase tracking-widest">Menu</div>
                  {item.menu_fries_included !== false && (
                    <div className="mt-1 text-xs text-[#A1A1A1]">Frites incluses</div>
                  )}
                </button>
              </div>
            </OptionGroup>
          )}

          {(item.removable_ingredients || []).length > 0 && (
            <OptionGroup label={`Retirer jusqu'à ${MAX_REMOVALS} ingrédients`}>
              <div className="flex flex-wrap gap-2">
                {item.removable_ingredients.map((ingredient) => {
                  const selected = removals.includes(ingredient);
                  const limitReached = !selected && removals.length >= MAX_REMOVALS;
                  return (
                    <button
                      className={`bt-chip ${selected ? "active" : ""} disabled:opacity-40`}
                      data-testid={`item-${item.id}-remove-${ingredient}`}
                      disabled={limitReached}
                      key={ingredient}
                      onClick={() => toggleRemoval(ingredient)}
                      type="button"
                    >
                      Sans {ingredient}
                    </button>
                  );
                })}
              </div>
            </OptionGroup>
          )}

          {item.uses_sauces && (
            <OptionGroup label={`Choisis jusqu'à ${MAX_SAUCES} sauces`}>
              <div className="flex flex-wrap gap-2">
                {sauceOptions.map((sauce) => {
                  const selected = selectedSauces.includes(sauce);
                  const limitReached = !selected && selectedSauces.length >= MAX_SAUCES;
                  return (
                    <button
                      className={`bt-chip ${selected ? "active" : ""} disabled:opacity-40`}
                      data-testid={`item-${item.id}-sauce-${sauce}`}
                      disabled={limitReached}
                      key={sauce}
                      onClick={() => toggleSauce(sauce)}
                      type="button"
                    >
                      {sauce}
                    </button>
                  );
                })}
              </div>
            </OptionGroup>
          )}

          {(supplementOptions || []).length > 0 && (
            <OptionGroup label="Suppléments">
              <div className="flex flex-wrap gap-2">
                {supplementOptions.map((sup) => {
                  const selected = selectedSupplements.includes(sup.name);
                  return (
                    <button
                      className={`bt-chip ${selected ? "active" : ""}`}
                      data-testid={`item-${item.id}-supplement-${sup.name}`}
                      key={sup.name}
                      onClick={() =>
                        setSelectedSupplements((current) =>
                          current.includes(sup.name)
                            ? current.filter((value) => value !== sup.name)
                            : [...current, sup.name],
                        )
                      }
                      type="button"
                    >
                      {sup.name}{sup.price ? ` +${formatEur(sup.price)}` : ""}
                    </button>
                  );
                })}
              </div>
            </OptionGroup>
          )}

          {formula === "menu" && (
            <OptionGroup label="Ta boisson">
              <div className="flex max-h-36 flex-wrap gap-2 overflow-y-auto">
                {sodaFlavours.map((soda) => (
                  <button
                    className={`bt-chip ${drink === soda ? "active" : ""}`}
                    data-testid={`item-${item.id}-drink-${soda}`}
                    key={soda}
                    onClick={() => setDrink(soda)}
                    type="button"
                  >
                    {soda}
                  </button>
                ))}
              </div>
            </OptionGroup>
          )}

          {formula === "menu"
            && item.menu_fries_included !== false
            && (friesSauces || []).length > 0 && (
            <OptionGroup label="Sauce pour tes frites">
              <div className="flex max-h-36 flex-wrap gap-2 overflow-y-auto">
                {friesSauces.map((sauce) => (
                  <button
                    className={`bt-chip ${friesSauce === sauce ? "active" : ""}`}
                    data-testid={`item-${item.id}-fries-sauce-${sauce}`}
                    key={sauce}
                    onClick={() => setFriesSauce(sauce)}
                    type="button"
                  >
                    {sauce}
                  </button>
                ))}
              </div>
            </OptionGroup>
          )}
        </div>

        <div className="mt-7 flex items-center justify-between gap-4 border-t-2 border-[#262626] pt-5">
          <div className="font-display text-3xl text-[#EF2B2D]">{formatEur(total)}</div>
          <button
            className="bt-btn-primary disabled:opacity-40"
            data-testid={`item-${item.id}-add-to-cart`}
            disabled={!canAdd}
            onClick={onAdd}
            type="button"
          >
            <Plus className="h-4 w-4" /> Ajouter
          </button>
        </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
function OptionGroup({ children, label }) {
  return (
    <div>
      <div className="bt-label">{label}</div>
      {children}
    </div>
  );
}