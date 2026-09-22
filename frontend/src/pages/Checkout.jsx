import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Header from "@/components/layout/Header.jsx";
import Footer from "@/components/layout/Footer.jsx";
import { useCart } from "@/context/CartContext.jsx";
import { useI18n } from "@/context/I18nContext.jsx";
import { apiClient, fmtError, formatEur } from "@/lib/api";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";
import StatusBanner from "@/components/StatusBanner.jsx";
import ClosedHero from "@/components/ClosedHero.jsx";
import { COUNTRY_CODES, DEFAULT_COUNTRY_ISO, findCountry } from "@/lib/countryCodes";
import { getSavedCustomer, setPendingSavePrompt } from "@/lib/savedCustomer";

export default function Checkout() {
  const { items, clear } = useCart();
  const { t } = useI18n();
  const nav = useNavigate();
  const { status } = useRestaurantStatus();
  const [settings, setSettings] = useState(null);

  const [fulfillment, setFulfillment] = useState("pickup");
  const [payment, setPayment] = useState("cash");
  const [form, setForm] = useState({
    first: "",
    last: "",
    phone: "",
    email: "",
    address1: "",
    address2: "",
    postal: "",
    city: "",
    notes: "",
  });
  const [countryIso, setCountryIso] = useState(DEFAULT_COUNTRY_ISO);
  const [submitting, setSubmitting] = useState(false);
  const [quote, setQuote] = useState(null);
  const [couponInput, setCouponInput] = useState("");
  const [appliedCoupon, setAppliedCoupon] = useState(null);
  const [deliverySlots, setDeliverySlots] = useState([]);
  const [selectedDeliveryStart, setSelectedDeliveryStart] = useState("");
  const [scheduleIntent] = useState(() => sessionStorage.getItem("bt_schedule_intent") === "1");

  // "Remember me" — recognize a returning customer from a previous checkout
  // (stored in localStorage, no account/backend involved) and offer to
  // autofill instead of forcing them to retype everything.
  const [savedProfile] = useState(() => getSavedCustomer());
  const [rememberBannerDismissed, setRememberBannerDismissed] = useState(false);
  const showRememberBanner = !!savedProfile && !rememberBannerDismissed;

  const applySavedProfile = () => {
    if (!savedProfile) return;
    setForm((f) => ({
      ...f,
      first: savedProfile.first || "",
      last: savedProfile.last || "",
      phone: savedProfile.phone || "",
      email: savedProfile.email || "",
      address1: savedProfile.address1 || "",
      address2: savedProfile.address2 || "",
      postal: savedProfile.postal || "",
      city: savedProfile.city || "",
    }));
    setCountryIso(savedProfile.countryIso || DEFAULT_COUNTRY_ISO);
    setRememberBannerDismissed(true);
  };

  const cashEnabled = settings?.payment_cash_enabled !== false;
  const cardEnabled = settings?.payment_card_enabled !== false;

  useEffect(() => {
    apiClient.get("/settings").then((r) => setSettings(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (scheduleIntent) setFulfillment("delivery");
  }, [scheduleIntent]);

  useEffect(() => {
    if (fulfillment !== "delivery") {
      setDeliverySlots([]);
      setSelectedDeliveryStart("");
      return;
    }
    let cancelled = false;
    apiClient
      .get("/checkout/delivery-slots")
      .then((r) => {
        if (!cancelled) setDeliverySlots(r.data?.enabled ? r.data.slots || [] : []);
      })
      .catch(() => !cancelled && setDeliverySlots([]));
    return () => {
      cancelled = true;
    };
  }, [fulfillment]);

  // Auto-switch payment if the selected one becomes disabled by admin.
  useEffect(() => {
    if (!settings) return;
    if (payment === "cash" && !cashEnabled && cardEnabled) setPayment("card_in_person");
    if (payment === "card_in_person" && !cardEnabled && cashEnabled) setPayment("cash");
  }, [settings, cashEnabled, cardEnabled, payment]);

  const cartPayload = useMemo(() => {
    return items.map((it) => ({
      line_id: it.line_id,
      item_id: it.item_id || null,
      quantity: it.quantity,
      formula: it.formula || "seul",
      selected_format: it.selected_format || null,
      selected_variant: it.selected_variant || null,
      included_drink: it.included_drink || null,
      included_drink_variant: it.included_drink_variant || null,
      sauces: it.sauces || [],
      removable_ingredients: it.removable_ingredients || [],
      supplements: it.supplements || [],
      notes: it.notes || null,
      is_burger: !!it.is_burger,
      burger_config: it.burger_config
        ? {
            style_id: it.burger_config.style_id,
            size_id: it.burger_config.size_id || null,
            meat_ids: it.burger_config.meat_ids || [],
            cheese_ids: it.burger_config.cheese_ids || [],
            supplement_ids: it.burger_config.supplement_ids || [],
            sauces: it.burger_config.sauces || [],
            sauce_fromagere: it.burger_config.sauce_fromagere ?? true,
          }
        : null,
    }));
  }, [items]);

  const dialCode = findCountry(countryIso).dial;
  const fullPhone = form.phone.trim() ? `${dialCode} ${form.phone.trim()}` : "";

  useEffect(() => {
    if (items.length === 0) {
      setQuote(null);
      return;
    }
    const payload = {
      items: cartPayload,
      fulfillment,
      customer_first_name: form.first || "x",
      customer_last_name: form.last || "x",
      customer_phone: fullPhone || "0000000000",
      payment_method: payment,
      address_line1: form.address1 || null,
      address_line2: form.address2 || null,
      postal_code: form.postal || null,
      city: form.city || null,
      customer_email: form.email || null,
      notes: form.notes,
      coupon_code: appliedCoupon || null,
      scheduled_delivery_start: selectedDeliveryStart || null,
    };
    let cancelled = false;
    apiClient
      .post("/checkout/quote", payload)
      .then((r) => !cancelled && setQuote(r.data))
      .catch((e) => !cancelled && setQuote({ error: fmtError(e) }));
    return () => {
      cancelled = true;
    };
  }, [cartPayload, fulfillment, payment, appliedCoupon, selectedDeliveryStart]);

  const allowedPostalCodes = useMemo(
    () =>
      (settings?.delivery_postal_codes || [])
        .map((v) => String(v).trim())
        .filter(Boolean),
    [settings],
  );
  const postalIsServed =
    fulfillment !== "delivery" ||
    allowedPostalCodes.length === 0 ||
    !form.postal.trim() ||
    allowedPostalCodes.includes(form.postal.trim());

  const canSubmit =
    items.length > 0 &&
    form.first.trim() &&
    form.last.trim() &&
    form.phone.trim() &&
    (fulfillment === "pickup" || (form.address1.trim() && form.postal.trim() && form.city.trim())) &&
    (status?.state !== "closed" || !!selectedDeliveryStart) &&
    (!scheduleIntent || !!selectedDeliveryStart) &&
    ((payment === "cash" && cashEnabled) || (payment === "card_in_person" && cardEnabled)) &&
    postalIsServed &&
    !quote?.error;

  const applyCoupon = () => {
    if (!couponInput.trim()) return;
    setAppliedCoupon(couponInput.trim().toUpperCase());
  };
  const removeCoupon = () => {
    setAppliedCoupon(null);
    setCouponInput("");
  };

  const submit = async () => {
    if (!canSubmit) {
      toast.error("Complète les champs requis");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        items: cartPayload,
        fulfillment,
        customer_first_name: form.first.trim(),
        customer_last_name: form.last.trim(),
        customer_phone: fullPhone,
        customer_email: form.email.trim() || null,
        address_line1: form.address1.trim() || null,
        address_line2: form.address2.trim() || null,
        postal_code: form.postal.trim() || null,
        city: form.city.trim() || null,
        payment_method: payment,
        notes: form.notes,
        coupon_code: appliedCoupon || null,
        scheduled_delivery_start: selectedDeliveryStart || null,
      };
      const { data } = await apiClient.post("/checkout/session", payload);
      sessionStorage.removeItem("bt_schedule_intent");
      // Bridge the just-submitted contact details to the success page, which
      // asks "save this for next time?" — kept out of this page so the
      // question never blocks/delays placing the order itself.
      setPendingSavePrompt({
        first: form.first.trim(),
        last: form.last.trim(),
        phone: form.phone.trim(),
        countryIso,
        email: form.email.trim(),
        address1: form.address1.trim(),
        address2: form.address2.trim(),
        postal: form.postal.trim(),
        city: form.city.trim(),
      });
      clear();
      nav(`/order/success?order_id=${encodeURIComponent(data.order_id)}`);
    } catch (e) {
      toast.error(fmtError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const closed = status?.state === "closed";

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]">
      <Header />
      <section className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12 md:py-20">
        <h1 className="font-display text-5xl md:text-6xl uppercase mb-8">{t("checkout.title")}</h1>

        {closed && (
          <div data-testid="checkout-closed-notice" className="mb-6">
            <ClosedHero />
          </div>
        )}

        {showRememberBanner && (
          <div
            data-testid="checkout-remember-banner"
            className="bt-card p-4 mb-6 flex items-center justify-between gap-4 flex-wrap border-[#EF2B2D]"
          >
            <div className="text-sm">
              Es-tu <span className="font-bold">{savedProfile.first} {savedProfile.last}</span> ?
            </div>
            <div className="flex gap-2">
              <button
                data-testid="checkout-remember-yes"
                onClick={applySavedProfile}
                className="bt-btn-primary py-2 px-4 text-sm"
              >
                Oui, remplir
              </button>
              <button
                data-testid="checkout-remember-no"
                onClick={() => setRememberBannerDismissed(true)}
                className="bt-btn-secondary py-2 px-4 text-sm"
              >
                Non
              </button>
            </div>
          </div>
        )}

        {items.length === 0 ? (
          <div className="bt-card p-8 text-center">
            <div className="mb-4">{t("cart.empty")}</div>
            <Link to="/menu" className="bt-btn-primary inline-flex">{t("cta.see_menu")}</Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-8">
              {/* Fulfillment */}
              <div>
                <div className="bt-label">{t("checkout.fulfillment")}</div>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    data-testid="fulfillment-pickup"
                    onClick={() => setFulfillment("pickup")}
                    className={`bt-option ${fulfillment === "pickup" ? "selected" : ""} text-left`}
                  >
                    <div className="font-accent uppercase tracking-widest text-lg">{t("checkout.pickup")}</div>
                    <div className="text-xs text-[#A1A1A1] mt-1">Retrait sur place</div>
                  </button>
                  <button
                    data-testid="fulfillment-delivery"
                    onClick={() => setFulfillment("delivery")}
                    className={`bt-option ${fulfillment === "delivery" ? "selected" : ""} text-left`}
                  >
                    <div className="font-accent uppercase tracking-widest text-lg">{t("checkout.delivery")}</div>
                    <div className="text-xs text-[#A1A1A1] mt-1">Livraison à ton adresse</div>
                  </button>
                </div>
              </div>

              {/* Contact */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label={t("checkout.first_name")} required>
                  <input
                    data-testid="input-first-name"
                    className="bt-input"
                    value={form.first}
                    onChange={(e) => setForm({ ...form, first: e.target.value })}
                  />
                </Field>
                <Field label={t("checkout.last_name")} required>
                  <input
                    data-testid="input-last-name"
                    className="bt-input"
                    value={form.last}
                    onChange={(e) => setForm({ ...form, last: e.target.value })}
                  />
                </Field>
                <Field label={t("checkout.phone")} required>
                  <div className="flex gap-2">
                    <select
                      data-testid="input-phone-country"
                      className="bt-input w-auto max-w-[9.5rem] flex-shrink-0"
                      value={countryIso}
                      onChange={(e) => setCountryIso(e.target.value)}
                    >
                      {COUNTRY_CODES.map((c) => (
                        <option key={c.iso} value={c.iso}>
                          {c.flag} {c.dial}
                        </option>
                      ))}
                    </select>
                    <input
                      data-testid="input-phone"
                      className="bt-input"
                      placeholder="6 12 34 56 78"
                      value={form.phone}
                      onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    />
                  </div>
                </Field>
                <Field label={t("checkout.email")}>
                  <input
                    data-testid="input-email"
                    className="bt-input"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                  />
                </Field>
              </div>

              {fulfillment === "delivery" && (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="sm:col-span-2">
                      <Field label={t("checkout.address_line1")} required>
                      <input
                        data-testid="input-address1"
                        className="bt-input"
                        value={form.address1}
                        onChange={(e) => setForm({ ...form, address1: e.target.value })}
                      />
                      </Field>
                    </div>
                    <div className="sm:col-span-2">
                      <Field label={t("checkout.address_line2")}>
                      <input
                        data-testid="input-address2"
                        className="bt-input"
                        value={form.address2}
                        onChange={(e) => setForm({ ...form, address2: e.target.value })}
                      />
                      </Field>
                    </div>
                    <Field label={t("checkout.postal_code")} required>
                    <input
                      data-testid="input-postal"
                      className="bt-input"
                      value={form.postal}
                      onChange={(e) => setForm({ ...form, postal: e.target.value })}
                    />
                    {allowedPostalCodes.length > 0 && (
                      <div className="mt-1 text-xs">
                        {form.postal.trim() && !postalIsServed ? (
                          <span
                            data-testid="postal-not-served"
                            className="text-[#FF3B30]"
                          >
                            On ne livre pas ici. Codes acceptés :{" "}
                            {allowedPostalCodes.join(", ")}
                          </span>
                        ) : (
                          <span className="text-[#A1A1A1]">
                            On livre à : {allowedPostalCodes.join(", ")}
                          </span>
                        )}
                      </div>
                    )}
                    </Field>
                    <Field label={t("checkout.city")} required>
                    <input
                      data-testid="input-city"
                      className="bt-input"
                      value={form.city}
                      onChange={(e) => setForm({ ...form, city: e.target.value })}
                    />
                    </Field>
                  </div>
                  {deliverySlots.length > 0 && (
                    <div
                      data-testid="delivery-schedule-panel"
                      className={
                        scheduleIntent && !selectedDeliveryStart
                          ? "motion-safe:animate-pulse border-2 border-[#FFB800] p-3"
                          : scheduleIntent
                            ? "border-2 border-[#FFB800] p-3"
                            : ""
                      }
                    >
                    <Field label={scheduleIntent ? "Choisis ton créneau de livraison" : "Créneau de livraison (optionnel)"}>
                      <select
                        data-testid="delivery-slot-select"
                        className="bt-input"
                        value={selectedDeliveryStart}
                        onChange={(e) => setSelectedDeliveryStart(e.target.value)}
                      >
                        <option value="">{scheduleIntent ? "Choisir un créneau" : "Dès que possible"}</option>
                        {deliverySlots.map((slot) => (
                          <option key={slot.start} value={slot.start}>
                            Aujourd&apos;hui · {slot.label}
                          </option>
                        ))}
                      </select>
                      <div className="mt-1 text-xs text-[#A1A1A1]">
                        La cuisine recevra ta commande à temps pour ce créneau.
                      </div>
                    </Field>
                    </div>
                  )}
                </>
              )}

              {/* Payment */}
              <div>
                <div className="bt-label">{t("checkout.payment")}</div>
                {!cashEnabled && !cardEnabled ? (
                  <div className="bt-card border-[#FF3B30] p-4 text-sm text-[#FF3B30]" data-testid="no-payment-methods">
                    Aucun mode de paiement activé pour l&apos;instant. Contacte le resto.
                  </div>
                ) : (
                  <div className={`grid gap-3 ${cashEnabled && cardEnabled ? "grid-cols-2" : "grid-cols-1"}`}>
                    {cashEnabled && (
                      <button
                        data-testid="payment-cash"
                        onClick={() => setPayment("cash")}
                        className={`bt-option ${payment === "cash" ? "selected" : ""} text-left`}
                      >
                        <div className="font-accent uppercase tracking-widest text-lg">{t("checkout.cash")}</div>
                        <div className="text-xs text-[#A1A1A1] mt-1">Réglé à la remise de la commande</div>
                      </button>
                    )}
                    {cardEnabled && (
                      <button
                        data-testid="payment-card"
                        onClick={() => setPayment("card_in_person")}
                        className={`bt-option ${payment === "card_in_person" ? "selected" : ""} text-left`}
                      >
                        <div className="font-accent uppercase tracking-widest text-lg">{t("checkout.card_in_person")}</div>
                        <div className="text-xs text-[#A1A1A1] mt-1">Payé sur place au comptoir</div>
                      </button>
                    )}
                  </div>
                )}
              </div>

              <Field label={t("checkout.notes")}>
                <textarea
                  data-testid="input-notes"
                  className="bt-input min-h-[100px]"
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </Field>
            </div>

            {/* Summary */}
            <div className="lg:col-span-1">
              <div className="bt-card p-5 sticky top-24">
                <div className="font-accent uppercase tracking-widest text-sm text-[#A1A1A1] mb-3">
                  Récap
                </div>
                <div className="space-y-2 max-h-56 overflow-y-auto">
                  {items.map((it) => (
                    <div key={it.line_id} className="flex justify-between text-sm">
                      <div className="truncate mr-2">
                        {it.quantity}× {it.name}
                      </div>
                      <div>{formatEur(it.unit_price * it.quantity)}</div>
                    </div>
                  ))}
                </div>
                <div className="border-t border-[#262626] mt-4 pt-4 space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span>{t("cart.subtotal")}</span>
                    <span>{formatEur(quote?.subtotal ?? 0)}</span>
                  </div>
                  {quote?.delivery_fee ? (
                    <div className="flex justify-between">
                      <span>{t("cart.delivery")}</span>
                      <span>{formatEur(quote.delivery_fee)}</span>
                    </div>
                  ) : null}
                  {quote?.coupon_discount > 0 && (
                    <div className="flex justify-between text-[#EF2B2D]" data-testid="coupon-discount-line">
                      <span>Code {quote.coupon_code}</span>
                      <span>-{formatEur(quote.coupon_discount)}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-baseline">
                    <span className="font-accent uppercase tracking-widest">{t("cart.total")}</span>
                    <span className="font-display text-2xl text-[#EF2B2D]">
                      {formatEur(quote?.total ?? 0)}
                    </span>
                  </div>
                </div>

                <div className="mt-4">
                  {appliedCoupon ? (
                    <div className="flex items-center justify-between gap-2 border-2 border-[#EF2B2D] px-3 py-2">
                      <span className="text-sm font-accent uppercase tracking-widest">{appliedCoupon}</span>
                      <button
                        onClick={removeCoupon}
                        data-testid="coupon-remove-btn"
                        className="text-xs text-[#A1A1A1] hover:text-[#F5F1E8]"
                      >
                        Retirer
                      </button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <input
                        data-testid="coupon-input"
                        className="bt-input flex-1"
                        placeholder="Code promo"
                        value={couponInput}
                        onChange={(e) => setCouponInput(e.target.value.toUpperCase())}
                      />
                      <button
                        onClick={applyCoupon}
                        data-testid="coupon-apply-btn"
                        className="bt-btn-secondary px-4 text-sm"
                      >
                        Appliquer
                      </button>
                    </div>
                  )}
                </div>

                <button
                  onClick={submit}
                  disabled={!canSubmit || submitting}
                  data-testid="checkout-submit"
                  className="bt-btn-primary w-full mt-6 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submitting ? "..." : t("checkout.place_order")}
                </button>
                {quote?.error && (
                  <div className="text-sm text-[#FF3B30] mt-3" data-testid="checkout-error">
                    {quote.error}
                  </div>
                )}
                <div className="text-xs text-[#A1A1A1] mt-3">
                  Pay-on-arrival · cash ou carte au comptoir.
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
      <Footer />
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <label className="block">
      <div className="bt-label">
        {label} {required ? <span className="text-[#EF2B2D]">*</span> : null}
      </div>
      {children}
    </label>
  );
}
