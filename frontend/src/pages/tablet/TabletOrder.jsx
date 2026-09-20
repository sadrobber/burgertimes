import React, { useEffect, useMemo, useState } from "react";
import { LogOut, Minus, Plus, ShoppingBag, Trash2, UtensilsCrossed } from "lucide-react";
import { toast } from "sonner";
import BurgerBuilderModal from "@/components/BurgerBuilderModal.jsx";
import MenuItemCard from "@/components/MenuItemCard.jsx";
import { useCart } from "@/context/CartContext.jsx";
import { useTabletAuth } from "@/context/TabletAuthContext.jsx";
import { apiClient, fmtError, formatEur, tabletClient } from "@/lib/api";

const initialForm = {
  first: "",
  last: "",
  phone: "",
  email: "",
  address1: "",
  address2: "",
  postal: "",
  city: "",
  notes: "",
};

export default function TabletOrder() {
  const { clear, items, removeLine, totalPrice, updateQuantity } = useCart();
  const { email, logout } = useTabletAuth();
  const [menu, setMenu] = useState([]);
  const [settings, setSettings] = useState(null);
  const [fulfillment, setFulfillment] = useState("pickup");
  const [payment, setPayment] = useState("cash");
  const [form, setForm] = useState(initialForm);
  const [slots, setSlots] = useState([]);
  const [scheduledStart, setScheduledStart] = useState("");
  const [quote, setQuote] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [lookupLoading, setLookupLoading] = useState(false);

  useEffect(() => {
    Promise.all([apiClient.get("/menu"), apiClient.get("/settings")])
      .then(([menuResponse, settingsResponse]) => {
        setMenu(menuResponse.data || []);
        setSettings(settingsResponse.data || null);
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
    apiClient
      .post("/checkout/quote", {
        items: cartPayload,
        fulfillment,
        customer_first_name: form.first || "Tablette",
        customer_last_name: form.last || "Client",
        customer_phone: form.phone || "0000000000",
        customer_email: form.email || null,
        address_line1: form.address1 || null,
        address_line2: form.address2 || null,
        postal_code: form.postal || null,
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
  }, [cartPayload, fulfillment, items.length, payment, scheduledStart]);

  const canSubmit =
    items.length > 0 &&
    form.first.trim() &&
    form.last.trim() &&
    form.phone.trim() &&
    (fulfillment === "pickup" ||
      (form.address1.trim() && form.postal.trim() && form.city.trim())) &&
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
        customer_phone: form.phone.trim(),
        customer_email: form.email.trim() || null,
        address_line1: form.address1.trim() || null,
        address_line2: form.address2.trim() || null,
        postal_code: form.postal.trim() || null,
        city: form.city.trim() || null,
        notes: form.notes.trim(),
        payment_method: payment,
        scheduled_delivery_start: scheduledStart || null,
      });
      toast.success(`Commande #${data.order_number} enregistrée`);
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
      setForm((current) => ({ ...current, ...data.customer }));
      toast.success("Informations client retrouvées");
    } catch (error) {
      toast.error(fmtError(error));
    } finally {
      setLookupLoading(false);
    }
  };

  const categories = [...new Set(menu.map((item) => item.category))];

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]" data-testid="tablet-order-page">
      <header className="sticky top-0 z-20 border-b-2 border-[#EF2B2D] bg-[#141414] px-4 py-3">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
          <div>
            <div className="font-display text-3xl uppercase leading-none">Prise de commande</div>
            <div className="mt-1 text-xs font-accent uppercase tracking-widest text-[#A1A1A1]">
              {email}
            </div>
          </div>
          <button
            className="bt-btn-ghost px-3 text-xs text-[#EF2B2D]"
            data-testid="tablet-logout"
            onClick={logout}
          >
            <LogOut className="h-4 w-4" /> Sortir
          </button>
        </div>
      </header>

      <main
        className="mx-auto grid max-w-[1600px] grid-cols-1 gap-5 p-4
          xl:grid-cols-[minmax(0,1fr)_380px]"
      >
        <section className="min-w-0 space-y-7">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="font-marker text-[#EF2B2D]">Sans les photos</div>
              <h1 className="font-display text-5xl uppercase leading-none">Le menu</h1>
            </div>
            <button
              className="bt-btn-primary px-4 text-sm"
              data-testid="tablet-open-tacos-builder"
              onClick={() => setBuilderOpen(true)}
            >
              <UtensilsCrossed className="h-4 w-4" /> Composer un Tacos
            </button>
          </div>
          {categories.map((category) => (
            <section key={category} data-testid={`tablet-category-${category}`}>
              <h2 className="mb-3 font-accent text-sm uppercase tracking-widest text-[#EF2B2D]">
                {category}
              </h2>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
                {menu
                  .filter((item) => item.category === category)
                  .map((item) => (
                    <MenuItemCard
                      compact
                      item={item}
                      key={item.id}
                      sodaFlavours={settings?.soda_flavours || []}
                    />
                  ))}
              </div>
            </section>
          ))}
        </section>

        <aside className="xl:sticky xl:top-20 xl:h-[calc(100vh-6rem)] xl:overflow-y-auto">
          <div className="bt-card p-5 space-y-5" data-testid="tablet-order-summary">
            <div className="flex items-center gap-2 font-display text-3xl uppercase">
              <ShoppingBag className="h-6 w-6 text-[#EF2B2D]" /> Commande
            </div>
            <div className="max-h-52 space-y-3 overflow-y-auto">
              {items.length === 0 ? (
                <div className="text-sm text-[#A1A1A1]" data-testid="tablet-cart-empty">
                  Panier vide.
                </div>
              ) : (
                items.map((item) => (
                  <div className="border-b border-[#262626] pb-3" key={item.line_id}>
                    <div className="flex justify-between gap-2 text-sm font-bold">
                      <span>{item.name}</span>
                      <span>{formatEur(item.unit_price * item.quantity)}</span>
                    </div>
                    {item.notes && <div className="mt-1 text-xs text-[#EF2B2D]">{item.notes}</div>}
                    <div className="mt-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <button
                          className="h-7 w-7 border-2 border-[#262626]"
                          data-testid={`tablet-line-${item.line_id}-dec`}
                          onClick={() => updateQuantity(item.line_id, item.quantity - 1)}
                        >
                          <Minus className="mx-auto h-3 w-3" />
                        </button>
                        <span data-testid={`tablet-line-${item.line_id}-qty`}>{item.quantity}</span>
                        <button
                          className="h-7 w-7 border-2 border-[#262626]"
                          data-testid={`tablet-line-${item.line_id}-inc`}
                          onClick={() => updateQuantity(item.line_id, item.quantity + 1)}
                        >
                          <Plus className="mx-auto h-3 w-3" />
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
                ))
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <ChoiceButton
                active={fulfillment === "pickup"}
                label="À emporter"
                onClick={() => setFulfillment("pickup")}
                testId="tablet-fulfillment-pickup"
              />
              <ChoiceButton
                active={fulfillment === "delivery"}
                label="Livraison"
                onClick={() => setFulfillment("delivery")}
                testId="tablet-fulfillment-delivery"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Prénom *">
                <input
                  className="bt-input"
                  data-testid="tablet-customer-first"
                  onChange={(e) => setForm({ ...form, first: e.target.value })}
                  value={form.first}
                />
              </Field>
              <Field label="Nom *">
                <input
                  className="bt-input"
                  data-testid="tablet-customer-last"
                  onChange={(e) => setForm({ ...form, last: e.target.value })}
                  value={form.last}
                />
              </Field>
              <Field label="Téléphone *">
                <div className="flex gap-2">
                  <input
                    className="bt-input min-w-0"
                    data-testid="tablet-customer-phone"
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    value={form.phone}
                  />
                  <button
                    className="bt-btn-secondary shrink-0 px-3 text-xs disabled:opacity-40"
                    data-testid="tablet-customer-lookup"
                    disabled={lookupLoading}
                    onClick={lookupCustomer}
                    type="button"
                  >
                    {lookupLoading ? "..." : "Rechercher"}
                  </button>
                </div>
              </Field>
              <Field label="Email">
                <input
                  className="bt-input"
                  data-testid="tablet-customer-email"
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  value={form.email}
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
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Code postal *">
                    <input
                      className="bt-input"
                      data-testid="tablet-postal"
                      onChange={(e) => setForm({ ...form, postal: e.target.value })}
                      value={form.postal}
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
                </div>
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
                          {slot.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
              </div>
            )}

            <Field label="Note cuisine">
              <textarea
                className="bt-input min-h-[72px]"
                data-testid="tablet-order-note"
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                value={form.notes}
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <ChoiceButton
                active={payment === "cash"}
                label="Espèces"
                onClick={() => setPayment("cash")}
                testId="tablet-payment-cash"
              />
              <ChoiceButton
                active={payment === "card_in_person"}
                label="Carte"
                onClick={() => setPayment("card_in_person")}
                testId="tablet-payment-card"
              />
            </div>
            <div className="border-t-2 border-[#262626] pt-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span>Sous-total</span>
                <span>{formatEur(quote?.subtotal ?? totalPrice)}</span>
              </div>
              {quote?.delivery_fee > 0 && (
                <div className="flex justify-between text-sm">
                  <span>Livraison</span>
                  <span>{formatEur(quote.delivery_fee)}</span>
                </div>
              )}
              <div
                className="flex justify-between font-display text-3xl text-[#EF2B2D]"
                data-testid="tablet-order-total"
              >
                <span>Total</span>
                <span>{formatEur(quote?.total ?? totalPrice)}</span>
              </div>
            </div>
            {quote?.error && (
              <div className="text-sm text-[#FF3B30]" data-testid="tablet-quote-error">
                {quote.error}
              </div>
            )}
            <button
              className="bt-btn-primary w-full disabled:opacity-40"
              data-testid="tablet-submit-order"
              disabled={!canSubmit || submitting}
              onClick={submit}
            >
              {submitting ? "..." : "Enregistrer la commande"}
            </button>
          </div>
        </aside>
      </main>
      <BurgerBuilderModal open={builderOpen} onClose={() => setBuilderOpen(false)} />
    </div>
  );
}

function ChoiceButton({ active, label, onClick, testId }) {
  return (
    <button
      className={`bt-option p-2 text-xs ${active ? "selected" : ""}`}
      data-testid={testId}
      onClick={onClick}
    >
      {label}
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