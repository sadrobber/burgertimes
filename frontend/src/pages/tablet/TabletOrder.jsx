import React, { useEffect, useMemo, useState } from "react";
import {
  Baby,
  Bike,
  CakeSlice,
  Cookie,
  CupSoda,
  Flame,
  Hamburger,
  LogOut,
  Minus,
  Plus,
  Popcorn,
  Salad,
  Sandwich,
  ShoppingBag,
  ShoppingCart,
  Store,
  Trash2,
  UtensilsCrossed,
} from "lucide-react";
import { toast } from "sonner";
import BurgerBuilderModal from "@/components/BurgerBuilderModal.jsx";
import MenuItemCard from "@/components/MenuItemCard.jsx";
import { useCart } from "@/context/CartContext.jsx";
import { useTabletAuth } from "@/context/TabletAuthContext.jsx";
import { COUNTRY_CODES, DEFAULT_COUNTRY_ISO, findCountry } from "@/lib/countryCodes";
import { apiClient, fmtError, formatEur, tabletClient } from "@/lib/api";

const initialForm = {
  first: "",
  last: "",
  phone: "",
  address1: "",
  address2: "",
  city: "",
  notes: "",
};

const CATEGORY_LABELS = {
  signatures: "Signatures",
  classiques: "Les classiques",
  "smash-burgers": "Smash burgers",
  kids: "Enfants",
  sides: "Accompagnements",
  sandwiches: "Sandwichs",
  drinks: "Boissons",
  desserts: "Desserts",
  wraps: "Wraps",
};

const CATEGORY_ICONS = {
  signatures: Hamburger,
  classiques: Hamburger,
  "smash-burgers": Flame,
  kids: Baby,
  sides: Popcorn,
  sandwiches: Sandwich,
  drinks: CupSoda,
  desserts: CakeSlice,
  wraps: Salad,
};

function phoneParts(phone) {
  const digits = (phone || "").replace(/\D/g, "");
  const country = [...COUNTRY_CODES]
    .sort((left, right) => right.dial.length - left.dial.length)
    .find((item) => digits.startsWith(item.dial.replace("+", "")));
  if (!country) return { countryIso: DEFAULT_COUNTRY_ISO, number: phone || "" };
  return {
    countryIso: country.iso,
    number: digits.slice(country.dial.replace("+", "").length),
  };
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 15000);
    return () => window.clearInterval(id);
  }, []);
  const time = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(now);
  const date = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(now);
  return { time, date: date.charAt(0).toUpperCase() + date.slice(1) };
}

export default function TabletOrder() {
  const { clear, items, removeLine, totalPrice, updateQuantity } = useCart();
  const { email, logout } = useTabletAuth();
  const clock = useClock();
  const payment = "cash";
  const [menu, setMenu] = useState([]);
  const [settings, setSettings] = useState(null);
  const [sauces, setSauces] = useState([]);
  const [fulfillment, setFulfillment] = useState("pickup");
  const [countryIso, setCountryIso] = useState(DEFAULT_COUNTRY_ISO);
  const [form, setForm] = useState(initialForm);
  const [slots, setSlots] = useState([]);
  const [scheduledStart, setScheduledStart] = useState("");
  const [quote, setQuote] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [suggesting, setSuggesting] = useState(false);
  const [activeCategory, setActiveCategory] = useState(null);
  const dialCode = findCountry(countryIso).dial;
  const fullPhone = form.phone.trim() ? `${dialCode} ${form.phone.trim()}` : "";

  // Lock the document while the kiosk is open: body's global min-height: 100vh
  // is taller than the visible area on iPad Safari, which let the page scroll
  // into empty space below the layout. Only the inner panels should scroll.
  useEffect(() => {
    const html = document.documentElement.style;
    const body = document.body.style;
    // Never set overflow on body: with the fixed layout it has zero height, and
    // Safari then clips the whole page to nothing (blank screen).
    const prev = [html.overflow, html.overscrollBehavior, body.overscrollBehavior, body.minHeight];
    html.overflow = "hidden";
    html.overscrollBehavior = "none";
    body.overscrollBehavior = "none";
    body.minHeight = "0";

    // iOS Safari still drags the page from non-scrollable areas; only let a
    // touch move when it starts inside something that can actually scroll.
    const canScroll = (node) => {
      for (let el = node; el && el !== document.body; el = el.parentElement) {
        const { overflowX, overflowY } = window.getComputedStyle(el);
        const scrolls = (value) => value === "auto" || value === "scroll";
        if (scrolls(overflowY) && el.scrollHeight > el.clientHeight) return true;
        if (scrolls(overflowX) && el.scrollWidth > el.clientWidth) return true;
      }
      return false;
    };
    const blockPageDrag = (event) => {
      if (!canScroll(event.target)) event.preventDefault();
    };
    // Closing the on-screen keyboard can leave the page shifted up, showing a
    // blank strip at the bottom. Snap back once focus leaves an input.
    let resetTimer;
    const resetPageScroll = () => {
      window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => window.scrollTo(0, 0), 100);
    };
    document.addEventListener("touchmove", blockPageDrag, { passive: false });
    document.addEventListener("focusout", resetPageScroll);

    return () => {
      document.removeEventListener("touchmove", blockPageDrag);
      document.removeEventListener("focusout", resetPageScroll);
      window.clearTimeout(resetTimer);
      [html.overflow, html.overscrollBehavior, body.overscrollBehavior, body.minHeight] = prev;
    };
  }, []);

  useEffect(() => {
    Promise.all([apiClient.get("/menu"), apiClient.get("/settings"), apiClient.get("/sauces")])
      .then(([menuResponse, settingsResponse, saucesResponse]) => {
        const menuData = menuResponse.data || [];
        setMenu(menuData);
        setSettings(settingsResponse.data || null);
        setSauces((saucesResponse.data || []).map((sauce) => sauce.name));
        const firstCategory = [...new Set(menuData.map((item) => item.category))][0];
        if (firstCategory) setActiveCategory((current) => current || firstCategory);
      })
      .catch(() => toast.error("Impossible de charger le menu"));
  }, []);

  useEffect(() => {
    if (fulfillment !== "delivery") {
      setSlots([]);
      setScheduledStart("");
      return undefined;
    }
    let cancelled = false;
    apiClient
      .get("/checkout/delivery-slots")
      .then((response) => {
        if (!cancelled) setSlots(response.data?.enabled ? response.data.slots || [] : []);
      })
      .catch(() => !cancelled && setSlots([]));
    return () => {
      cancelled = true;
    };
  }, [fulfillment]);

  useEffect(() => {
    const phone = form.phone.trim();
    if (phone.replace(/\D/g, "").length < 3) {
      setSuggestions([]);
      return undefined;
    }
    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      setSuggesting(true);
      try {
        const { data } = await tabletClient.get("/tablet/customers/suggestions", {
          params: { phone },
        });
        if (!cancelled) setSuggestions(data.customers || []);
      } catch {
        if (!cancelled) setSuggestions([]);
      } finally {
        if (!cancelled) setSuggesting(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [form.phone]);

  const cartPayload = useMemo(
    () =>
      items.map((item) => ({
        line_id: item.line_id,
        item_id: item.item_id || null,
        quantity: item.quantity,
        formula: item.formula || "seul",
        selected_format: item.selected_format || null,
        selected_variant: item.selected_variant || null,
        included_drink: item.included_drink || null,
        included_drink_variant: item.included_drink_variant || null,
        sauces: item.sauces || [],
        removable_ingredients: item.removable_ingredients || [],
        notes: item.notes || null,
        is_burger: !!item.is_burger,
        burger_config: item.burger_config
          ? {
              style_id: item.burger_config.style_id,
              size_id: item.burger_config.size_id || null,
              meat_ids: item.burger_config.meat_ids || [],
              cheese_ids: item.burger_config.cheese_ids || [],
              supplement_ids: item.burger_config.supplement_ids || [],
              sauces: item.burger_config.sauces || [],
              sauce_fromagere: item.burger_config.sauce_fromagere ?? true,
            }
          : null,
      })),
    [items],
  );

  useEffect(() => {
    if (!items.length) {
      setQuote(null);
      return undefined;
    }
    let cancelled = false;
    tabletClient
      .post("/tablet/quote", {
        items: cartPayload,
        fulfillment,
        customer_first_name: form.first || "",
        customer_last_name: form.last || "",
        customer_phone: fullPhone || "0000000000",
        customer_email: null,
        address_line1: form.address1 || null,
        address_line2: form.address2 || null,
        postal_code: null,
        city: form.city || null,
        notes: form.notes,
        payment_method: payment,
        scheduled_delivery_start: scheduledStart || null,
      })
      .then((response) => !cancelled && setQuote(response.data))
      .catch((error) => !cancelled && setQuote({ error: fmtError(error) }));
    return () => {
      cancelled = true;
    };
  }, [cartPayload, fulfillment, items.length, scheduledStart]);

  const needsAddress = fulfillment === "delivery";
  const canSubmit =
    items.length > 0 &&
    form.first.trim() &&
    form.phone.trim() &&
    (!needsAddress || (form.address1.trim() && form.city.trim())) &&
    !quote?.error;

  const submit = async () => {
    if (!canSubmit) {
      toast.error("Complète les informations client requises");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await tabletClient.post("/tablet/orders", {
        items: cartPayload,
        fulfillment,
        customer_first_name: form.first.trim(),
        customer_last_name: form.last.trim(),
        customer_phone: fullPhone,
        customer_email: null,
        address_line1: form.address1.trim() || null,
        address_line2: form.address2.trim() || null,
        postal_code: null,
        city: form.city.trim() || null,
        notes: form.notes.trim(),
        payment_method: payment,
        scheduled_delivery_start: scheduledStart || null,
      });
      toast.success(
        data.print_queued
          ? `Commande #${data.order_number} enregistrée et envoyée à l'impression`
          : `Commande #${data.order_number} programmée`,
      );
      clear();
      setForm(initialForm);
      setScheduledStart("");
    } catch (error) {
      toast.error(fmtError(error));
    } finally {
      setSubmitting(false);
    }
  };

  const lookupCustomer = async () => {
    if (form.phone.trim().length < 4) {
      toast.error("Saisis un numéro de téléphone complet");
      return;
    }
    setLookupLoading(true);
    try {
      const { data } = await tabletClient.get("/tablet/customers/lookup", {
        params: { phone: form.phone.trim() },
      });
      if (!data.found) {
        toast.message("Aucun client trouvé pour ce numéro");
        return;
      }
      const parts = phoneParts(data.customer.phone);
      setCountryIso(parts.countryIso);
      setForm((current) => ({ ...current, ...data.customer, phone: parts.number }));
      setSuggestions([]);
      toast.success("Informations client retrouvées");
    } catch (error) {
      toast.error(fmtError(error));
    } finally {
      setLookupLoading(false);
    }
  };

  const selectCustomer = (customer) => {
    const parts = phoneParts(customer.phone);
    setCountryIso(parts.countryIso);
    setForm((current) => ({ ...current, ...customer, phone: parts.number }));
    setSuggestions([]);
  };

  const categories = [...new Set(menu.map((item) => item.category))];
  const activeCategoryLabel = activeCategory
    ? CATEGORY_LABELS[activeCategory] || activeCategory.replaceAll("-", " ")
    : null;
  const visibleItems = menu.filter((item) => item.category === activeCategory);

  return (
    <div className="fixed inset-0 flex flex-col overflow-hidden bg-[#0A0A0A] text-[#F5F1E8]" data-testid="tablet-order-page">
      {/* Top bar */}
      <header className="flex items-center justify-between gap-4 border-b-2 border-[#EF2B2D] bg-[#141414] px-5 py-3">
        <div className="leading-none">
          <div className="font-display text-3xl uppercase tracking-tight">
            Burger <span className="text-[#EF2B2D]">Times</span>
          </div>
          <div className="mt-0.5 font-accent text-[10px] uppercase tracking-[0.3em] text-[#A1A1A1]">
            Good burgers. Good mood.
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right leading-tight" data-testid="tablet-clock">
            <div className="font-display text-2xl">{clock.time}</div>
            <div className="text-xs text-[#A1A1A1]">{clock.date}</div>
          </div>
          <button
            className="flex items-center gap-2 border-2 border-[#EF2B2D] px-4 py-2 font-accent uppercase tracking-widest text-[#EF2B2D] transition-colors hover:bg-[#EF2B2D] hover:text-[#0A0A0A]"
            data-testid="tablet-logout"
            onClick={logout}
            title={email}
          >
            <LogOut className="h-4 w-4" /> Sortir
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_300px] lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_380px]">
        {/* LEFT: fixed category tabs + scrolling products */}
        <div className="flex min-h-0 flex-col">
          <nav
            className="grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-2 border-b border-[#262626] bg-[#0F0F0F] px-3 py-2.5"
            data-testid="tablet-category-picker"
          >
            {categories.map((category) => {
              const Icon = CATEGORY_ICONS[category] || Cookie;
              const active = activeCategory === category;
              return (
                <button
                  className={`flex min-h-[84px] flex-col items-center justify-center gap-2 rounded-[10px] border-2 px-1.5 py-2.5 text-center font-accent uppercase tracking-widest transition-colors ${
                    active
                      ? "border-[#EF2B2D] bg-[#EF2B2D] text-[#0A0A0A]"
                      : "border-[#262626] bg-[#141414] text-[#F5F1E8] hover:border-[#EF2B2D]"
                  }`}
                  data-testid={`tablet-category-select-${category}`}
                  key={category}
                  onClick={() => setActiveCategory(category)}
                >
                  <Icon className="h-8 w-8 shrink-0" strokeWidth={1.5} />
                  <span className="text-xs leading-tight">
                    {CATEGORY_LABELS[category] || category.replaceAll("-", " ")}
                  </span>
                </button>
              );
            })}
            <button
              className="flex min-h-[84px] flex-col items-center justify-center gap-2 rounded-[10px] border-2 border-[#262626] bg-[#141414] px-1.5 py-2.5 text-center font-accent uppercase tracking-widest text-[#F5F1E8] transition-colors hover:border-[#EF2B2D]"
              data-testid="tablet-open-tacos-builder"
              onClick={() => setBuilderOpen(true)}
            >
              <UtensilsCrossed className="h-8 w-8 shrink-0" strokeWidth={1.5} />
              <span className="text-xs leading-tight">Composer un Tacos</span>
            </button>
          </nav>

          <section className="min-w-0 flex-1 overflow-y-auto overscroll-contain p-3">
            <div className="mb-3 flex items-center gap-3">
              <h2 className="flex items-center gap-3 font-display text-2xl uppercase leading-none text-[#EF2B2D] sm:text-3xl">
                <span className="h-6 w-1.5 bg-[#EF2B2D]" />
                {activeCategoryLabel || "Menu"}
              </h2>
            </div>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3" data-testid={`tablet-category-${activeCategory}`}>
              {visibleItems.map((item) => (
                <MenuItemCard
                  dense
                  item={item}
                  key={item.id}
                  sauceOptions={sauces}
                  sodaFlavours={settings?.soda_flavours || []}
                />
              ))}
            </div>
          </section>
        </div>

        {/* Order panel */}
        <aside className="flex min-h-0 flex-col border-t-2 border-[#262626] bg-[#141414] md:border-l-2 md:border-t-0" data-testid="tablet-order-summary">
          <div className="flex items-center justify-between gap-2 border-b border-[#262626] px-5 py-4">
            <div className="flex items-center gap-2 font-display text-2xl uppercase">
              <ShoppingCart className="h-6 w-6 text-[#EF2B2D]" /> Votre commande
            </div>
            {items.length > 0 && (
              <button
                className="text-[#A1A1A1] transition-colors hover:text-[#EF2B2D]"
                data-testid="tablet-clear-cart"
                onClick={clear}
                title="Vider le panier"
              >
                <Trash2 className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Fulfillment mode (always visible, top of panel) */}
          <div className="border-b border-[#262626] px-5 py-3">
            <div className="flex flex-wrap gap-2" data-testid="tablet-fulfillment-group">
              <FulfillmentButton
                active={fulfillment === "pickup"}
                icon={ShoppingBag}
                label="À emporter"
                onClick={() => setFulfillment("pickup")}
                testId="tablet-fulfillment-pickup"
              />
              <FulfillmentButton
                active={fulfillment === "delivery"}
                icon={Bike}
                label="Livraison"
                onClick={() => setFulfillment("delivery")}
                testId="tablet-fulfillment-delivery"
              />
              <FulfillmentButton
                active={fulfillment === "dine_in"}
                icon={Store}
                label="Sur place"
                onClick={() => setFulfillment("dine_in")}
                testId="tablet-fulfillment-dine-in"
              />
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain px-5 py-4">
            {/* Cart lines */}
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center" data-testid="tablet-cart-empty">
                <ShoppingCart className="h-14 w-14 text-[#262626]" strokeWidth={1.4} />
                <div className="mt-4 font-display text-xl uppercase">Votre panier est vide</div>
                <div className="mt-1 text-xs text-[#A1A1A1]">
                  Ajoutez des produits en touchant les cartes à gauche.
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {items.map((item) => (
                  <div className="border-b border-[#262626] pb-3" key={item.line_id}>
                    <div className="flex justify-between gap-2 text-sm font-bold">
                      <span>{item.name}</span>
                      <span>{formatEur(item.unit_price * item.quantity)}</span>
                    </div>
                    {item.notes && <div className="mt-1 text-xs text-[#EF2B2D]">{item.notes}</div>}
                    <div className="mt-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <button
                          className="flex h-8 w-8 items-center justify-center border-2 border-[#262626] hover:border-[#EF2B2D]"
                          data-testid={`tablet-line-${item.line_id}-dec`}
                          onClick={() => updateQuantity(item.line_id, item.quantity - 1)}
                        >
                          <Minus className="h-3.5 w-3.5" />
                        </button>
                        <span className="w-6 text-center font-bold" data-testid={`tablet-line-${item.line_id}-qty`}>
                          {item.quantity}
                        </span>
                        <button
                          className="flex h-8 w-8 items-center justify-center border-2 border-[#262626] hover:border-[#EF2B2D]"
                          data-testid={`tablet-line-${item.line_id}-inc`}
                          onClick={() => updateQuantity(item.line_id, item.quantity + 1)}
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      <button
                        className="text-[#EF2B2D]"
                        data-testid={`tablet-line-${item.line_id}-remove`}
                        onClick={() => removeLine(item.line_id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Customer search */}
            <section className="border-y-2 border-[#EF2B2D] py-4" data-testid="tablet-customer-search-section">
              <div className="font-display text-xl uppercase">Retrouver un client</div>
              <p className="mt-1 text-xs text-[#A1A1A1]">Recherche par numéro de téléphone.</p>
              <Field label="Téléphone *">
                <div className="mt-1 grid grid-cols-[88px_minmax(0,1fr)] gap-2">
                  <select
                    className="bt-input px-2"
                    data-testid="tablet-phone-country"
                    onChange={(event) => setCountryIso(event.target.value)}
                    value={countryIso}
                  >
                    {COUNTRY_CODES.map((country) => (
                      <option key={country.iso} value={country.iso}>
                        {country.flag} {country.dial}
                      </option>
                    ))}
                  </select>
                  <input
                    className="bt-input min-w-0"
                    data-testid="tablet-customer-phone"
                    onChange={(event) => setForm({ ...form, phone: event.target.value })}
                    value={form.phone}
                  />
                </div>
                <button
                  className="bt-btn-secondary mt-2 w-full py-3 text-sm disabled:opacity-40"
                  data-testid="tablet-customer-lookup"
                  disabled={lookupLoading}
                  onClick={lookupCustomer}
                  type="button"
                >
                  {lookupLoading ? "Recherche…" : "Rechercher ce client"}
                </button>
              </Field>
              {suggesting && (
                <div className="mt-2 text-xs text-[#A1A1A1]" data-testid="tablet-customer-suggesting">
                  Recherche dans les anciens clients…
                </div>
              )}
              {suggestions.length > 0 && (
                <div className="mt-2 border-2 border-[#EF2B2D] bg-[#0A0A0A] p-1" data-testid="tablet-customer-suggestions">
                  {suggestions.map((customer) => (
                    <button
                      className="block w-full px-3 py-3 text-left text-sm hover:bg-[#262626]"
                      data-testid={`tablet-customer-suggestion-${customer.phone}`}
                      key={customer.phone}
                      onClick={() => selectCustomer(customer)}
                      type="button"
                    >
                      <span className="block font-bold">
                        {customer.first} {customer.last}
                      </span>
                      <span className="text-[#A1A1A1]">{customer.phone}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            {/* Customer name */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Prénom *">
                <input
                  className="bt-input"
                  data-testid="tablet-customer-first"
                  onChange={(e) => setForm({ ...form, first: e.target.value })}
                  value={form.first}
                />
              </Field>
              <Field label="Nom (optionnel)">
                <input
                  className="bt-input"
                  data-testid="tablet-customer-last"
                  onChange={(e) => setForm({ ...form, last: e.target.value })}
                  value={form.last}
                />
              </Field>
            </div>

            {fulfillment === "delivery" && (
              <div className="space-y-3 border-t-2 border-[#262626] pt-4">
                <Field label="Adresse *">
                  <input
                    className="bt-input"
                    data-testid="tablet-address-one"
                    onChange={(e) => setForm({ ...form, address1: e.target.value })}
                    value={form.address1}
                  />
                </Field>
                <Field label="Complément">
                  <input
                    className="bt-input"
                    data-testid="tablet-address-two"
                    onChange={(e) => setForm({ ...form, address2: e.target.value })}
                    value={form.address2}
                  />
                </Field>
                <Field label="Ville *">
                  <input
                    className="bt-input"
                    data-testid="tablet-city"
                    onChange={(e) => setForm({ ...form, city: e.target.value })}
                    value={form.city}
                  />
                </Field>
                {slots.length > 0 && (
                  <Field label="Créneau aujourd'hui">
                    <select
                      className="bt-input"
                      data-testid="tablet-delivery-slot"
                      onChange={(event) => setScheduledStart(event.target.value)}
                      value={scheduledStart}
                    >
                      <option value="">Dès que possible</option>
                      {slots.map((slot) => (
                        <option key={slot.start} value={slot.start}>
                          {slot.time || slot.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
              </div>
            )}

            <Field label="Note cuisine">
              <textarea
                className="bt-input min-h-[64px]"
                data-testid="tablet-order-note"
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                value={form.notes}
              />
            </Field>
          </div>

          {/* Footer: total, validate, fulfillment */}
          <div className="border-t-2 border-[#262626] px-5 py-4">
            <div className="mb-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span>Sous-total</span>
                <span>{formatEur(quote?.subtotal ?? totalPrice)}</span>
              </div>
              {fulfillment === "delivery" && quote?.tablet_delivery_waived && (
                <div
                  className="flex justify-between text-sm text-[#3DDC97]"
                  data-testid="tablet-delivery-fee-waived"
                >
                  <span>Livraison tablette</span>
                  <span>Offerte</span>
                </div>
              )}
              <div
                className="flex justify-between font-display text-3xl text-[#EF2B2D]"
                data-testid="tablet-order-total"
              >
                <span>Total</span>
                <span>{formatEur(quote?.total ?? totalPrice)}</span>
              </div>
              {quote?.error && (
                <div className="text-sm text-[#FF3B30]" data-testid="tablet-quote-error">
                  {quote.error}
                </div>
              )}
            </div>
            <button
              className="bt-btn-primary w-full py-4 text-xl disabled:opacity-40"
              data-testid="tablet-submit-order"
              disabled={!canSubmit || submitting}
              onClick={submit}
            >
              {submitting ? "..." : "Valider / Encaisser"}
            </button>
          </div>
        </aside>
      </div>
      <BurgerBuilderModal open={builderOpen} onClose={() => setBuilderOpen(false)} />
    </div>
  );
}

function FulfillmentButton({ active, icon: Icon, label, onClick, testId }) {
  return (
    <button
      className={`flex flex-1 basis-[100px] flex-col items-center gap-1 border-2 py-2.5 font-accent uppercase tracking-widest transition-colors ${
        active
          ? "border-[#EF2B2D] bg-[#EF2B2D] text-[#0A0A0A]"
          : "border-[#262626] bg-[#0A0A0A] text-[#F5F1E8] hover:border-[#EF2B2D]"
      }`}
      data-testid={testId}
      onClick={onClick}
    >
      <Icon className="h-5 w-5" strokeWidth={1.7} />
      <span className="text-xs leading-none">{label}</span>
    </button>
  );
}

function Field({ children, label }) {
  return (
    <label className="block text-sm">
      <span className="bt-label">{label}</span>
      {children}
    </label>
  );
}
