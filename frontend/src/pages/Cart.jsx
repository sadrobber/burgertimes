import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { Minus, Plus, Trash2 } from "lucide-react";
import Header from "@/components/layout/Header.jsx";
import Footer from "@/components/layout/Footer.jsx";
import { useCart } from "@/context/CartContext.jsx";
import { useI18n } from "@/context/I18nContext.jsx";
import { formatEur } from "@/lib/api";

export default function Cart() {
  const { items, removeLine, updateQuantity, totalPrice } = useCart();
  const { t } = useI18n();
  const nav = useNavigate();

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]">
      <Header />
      <section className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 md:py-20">
        <h1 className="font-display text-5xl md:text-6xl uppercase mb-8">{t("cart.title")}</h1>

        {items.length === 0 ? (
          <div className="bt-card p-10 text-center" data-testid="cart-empty">
            <div className="font-display text-2xl uppercase mb-2">{t("cart.empty")}</div>
            <Link to="/menu" className="bt-btn-primary mt-6 inline-flex" data-testid="cart-empty-cta">
              {t("cta.see_menu")}
            </Link>
          </div>
        ) : (
          <>
            <div className="space-y-4">
              {items.map((line) => (
                <div key={line.line_id} className="bt-card p-4 md:p-5" data-testid={`cart-line-${line.line_id}`}>
                  <div className="flex items-start gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="font-display text-xl uppercase leading-none">{line.name}</div>
                      {line.burger_config && (
                        <div className="text-sm text-[#B3B3B3] mt-1 space-y-0.5">
                          {line.burger_config.size?.label && <div>Taille : {line.burger_config.size.label}</div>}
                          {(line.burger_config.meats || []).length > 0 && (
                            <div>Viandes : {line.burger_config.meats.map((m) => m.name).join(", ")}</div>
                          )}
                          {(line.burger_config.cheeses || []).length > 0 && (
                            <div>Fromages : {line.burger_config.cheeses.map((c) => c.name).join(", ")}</div>
                          )}
                          {(line.burger_config.supplements || []).length > 0 && (
                            <div>Suppléments : {line.burger_config.supplements.map((s) => s.name).join(", ")}</div>
                          )}
                        </div>
                      )}
                      {line.formula === "menu" && line.included_drink && (
                        <div className="text-sm text-[#B3B3B3] mt-1">Menu · {line.included_drink}</div>
                      )}
                      {(line.sauces || []).length > 0 && (
                        <div className="text-sm text-[#B3B3B3] mt-1">Sauces : {line.sauces.join(", ")}</div>
                      )}
                    </div>
                    <div className="text-right">
                      <div className="font-display text-xl">{formatEur(line.unit_price * line.quantity)}</div>
                      <div className="text-xs text-[#A1A1A1]">{formatEur(line.unit_price)} × {line.quantity}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <div className="inline-flex items-center gap-2">
                      <button
                        onClick={() => updateQuantity(line.line_id, line.quantity - 1)}
                        data-testid={`cart-line-${line.line_id}-dec`}
                        className="w-9 h-9 border-2 border-[#262626] hover:border-[#EF2B2D] flex items-center justify-center"
                      >
                        <Minus className="w-4 h-4" />
                      </button>
                      <div className="w-8 text-center font-accent uppercase tracking-widest" data-testid={`cart-line-${line.line_id}-qty`}>
                        {line.quantity}
                      </div>
                      <button
                        onClick={() => updateQuantity(line.line_id, line.quantity + 1)}
                        data-testid={`cart-line-${line.line_id}-inc`}
                        className="w-9 h-9 border-2 border-[#262626] hover:border-[#EF2B2D] flex items-center justify-center"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                    <button
                      onClick={() => removeLine(line.line_id)}
                      data-testid={`cart-line-${line.line_id}-remove`}
                      className="text-sm text-[#B3B3B3] hover:text-[#EF2B2D] inline-flex items-center gap-1 font-accent uppercase tracking-widest"
                    >
                      <Trash2 className="w-4 h-4" /> {t("cart.remove")}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="bt-card p-6 mt-8">
              <div className="flex items-center justify-between text-lg">
                <div className="font-accent uppercase tracking-widest">{t("cart.subtotal")}</div>
                <div className="font-display text-2xl">{formatEur(totalPrice)}</div>
              </div>
              <div className="text-xs text-[#A1A1A1] mt-1">
                * Les frais de livraison éventuels sont calculés au paiement.
              </div>
            </div>

            <div className="mt-8 flex flex-col sm:flex-row gap-3">
              <Link to="/menu" className="bt-btn-secondary flex-1 sm:flex-none">{t("cta.see_menu")}</Link>
              <button
                onClick={() => nav("/checkout")}
                data-testid="cart-checkout-cta"
                className="bt-btn-primary flex-1"
              >
                {t("cart.checkout")}
              </button>
            </div>
          </>
        )}
      </section>
      <Footer />
    </div>
  );
}
