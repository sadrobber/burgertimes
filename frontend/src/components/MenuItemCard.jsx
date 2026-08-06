import React from "react";
import { Plus } from "lucide-react";
import { formatEur, menuImageUrl } from "@/lib/api";
import { useCart } from "@/context/CartContext.jsx";
import { useI18n } from "@/context/I18nContext.jsx";
import { toast } from "sonner";

export default function MenuItemCard({ item, sodaFlavours = [] }) {
  const { addPlainItem } = useCart();
  const { t } = useI18n();
  const [openConfig, setOpenConfig] = React.useState(false);
  const [formula, setFormula] = React.useState("seul");
  const [selectedFormat, setSelectedFormat] = React.useState(item.formats?.[0]?.name || null);
  const [drink, setDrink] = React.useState("");

  const hasMenu = item.price_menu != null || (item.formats || []).some((f) => f.price_menu != null);
  const needsDrink = formula === "menu" && item.uses_soda_flavours;

  const displayPrice = React.useMemo(() => {
    const fmt = (item.formats || []).find((f) => f.name === selectedFormat);
    if (formula === "menu") {
      if (fmt && fmt.price_menu != null) return fmt.price_menu;
      if (item.price_menu != null) return item.price_menu;
    }
    if (fmt) return fmt.price_seul;
    return item.price_seul;
  }, [item, formula, selectedFormat]);

  const canAdd = formula === "seul" || (formula === "menu" && (!item.uses_soda_flavours || drink));

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
      unit_price: displayPrice,
      sauces: [],
      included_drink: needsDrink ? drink : null,
      selected_format: selectedFormat,
      selected_variant: null,
      notes: null,
    });
    toast.success("Ajouté au panier");
    setOpenConfig(false);
    setFormula("seul");
    setDrink("");
  };

  const hasConfig = hasMenu || (item.formats && item.formats.length > 0);

  return (
    <div
      data-testid={`menu-item-${item.id}`}
      className="bt-card relative flex flex-col overflow-hidden"
    >
      <div className="aspect-[4/3] w-full overflow-hidden bg-[#1A1A1A] relative">
        {item.has_image ? (
          <img
            src={menuImageUrl(item.id)}
            alt={item.name}
            className="w-full h-full object-cover"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bt-halftone">
            <div className="font-display text-4xl text-[#EF2B2D]/40 uppercase">BT</div>
          </div>
        )}
        <div className="absolute top-3 left-3">
          <span className="bt-price-pill">{formatEur(item.price_seul)}</span>
        </div>
        {item.is_new && (
          <img
            src="/new-badge.png"
            alt="Nouveau"
            data-testid={`item-${item.id}-new-badge`}
            className="absolute -top-2 -right-2 w-12 h-12 md:w-14 md:h-14 rotate-12 pointer-events-none"
          />
        )}
      </div>
      <div className="p-4 flex-1 flex flex-col">
        <div className="font-display text-2xl uppercase leading-none">{item.name}</div>
        {item.description && (
          <p className="text-sm text-[#B3B3B3] mt-2 line-clamp-2">{item.description}</p>
        )}

        {openConfig && hasConfig && (
          <div className="mt-4 space-y-3">
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
          </div>
        )}

        <div className="mt-auto pt-4 flex items-center gap-2">
          {hasConfig && !openConfig ? (
            <button
              onClick={() => setOpenConfig(true)}
              data-testid={`item-${item.id}-configure`}
              className="bt-btn-primary py-2 px-4 text-sm flex-1"
            >
              {t("menu.add")}
            </button>
          ) : hasConfig && openConfig ? (
            <>
              <div className="font-display text-xl">{formatEur(displayPrice)}</div>
              <button
                onClick={doAdd}
                data-testid={`item-${item.id}-add-to-cart`}
                disabled={!canAdd}
                className="bt-btn-primary py-2 px-4 text-sm ml-auto disabled:opacity-40"
              >
                <Plus className="w-4 h-4" /> {t("menu.add")}
              </button>
            </>
          ) : (
            <button
              onClick={doAdd}
              data-testid={`item-${item.id}-add-to-cart`}
              className="bt-btn-primary py-2 px-4 text-sm flex-1"
            >
              <Plus className="w-4 h-4" /> {t("menu.add")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
