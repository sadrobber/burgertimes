import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import Header from "@/components/layout/Header.jsx";
import Footer from "@/components/layout/Footer.jsx";
import { apiClient, formatEur } from "@/lib/api";
import { useI18n } from "@/context/I18nContext.jsx";

const STATUS_LABEL = {
  pending: "En attente",
  accepted: "Acceptée",
  preparing: "En préparation",
  ready: "Prête",
  delivering: "En livraison",
  delivered: "Livrée",
  cancelled: "Annulée",
  expired: "Expirée",
};

export default function OrderSuccess() {
  const [params] = useSearchParams();
  const orderId = params.get("order_id");
  const [order, setOrder] = useState(null);
  const [err, setErr] = useState(null);
  const { t } = useI18n();

  useEffect(() => {
    if (!orderId) return;
    const fetchOrder = () =>
      apiClient
        .get(`/orders/lookup/${orderId}`)
        .then((r) => setOrder(r.data))
        .catch((e) => setErr(e?.response?.data?.detail || "Introuvable"));
    fetchOrder();
    const id = setInterval(fetchOrder, 15000);
    return () => clearInterval(id);
  }, [orderId]);

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F1E8]">
      <Header />
      <section className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-12 md:py-24">
        {err && (
          <div className="bt-card p-8 text-center" data-testid="order-not-found">
            <div className="font-display text-3xl uppercase">Commande introuvable</div>
            <p className="text-[#A1A1A1] mt-2">{err}</p>
            <Link to="/" className="bt-btn-primary mt-6 inline-flex">
              {t("success.back_home")}
            </Link>
          </div>
        )}
        {order && (
          <div className="space-y-6" data-testid="order-success">
            <div className="text-center">
              <CheckCircle2 className="w-16 h-16 text-[#00FF66] mx-auto" />
              <div className="font-marker text-[#EF2B2D] text-xl -rotate-1 mt-4">
                {t("success.thanks")}, {order.customer_first_name} !
              </div>
              <h1 className="font-display text-5xl md:text-6xl uppercase mt-2">
                {t("success.title")}
              </h1>
              <div className="font-accent uppercase tracking-widest text-[#A1A1A1] mt-2">
                #{order.order_number}
              </div>
            </div>

            {order.pickup_code && (
              <div className="bt-card p-6 text-center border-[#FFB800]" data-testid="pickup-code-card">
                <div className="bt-label">{t("success.pickup_code")}</div>
                <div className="font-display text-6xl text-[#FFB800] tracking-widest mt-1">
                  {order.pickup_code}
                </div>
                <div className="text-xs text-[#A1A1A1] mt-2">
                  Montre ce code au comptoir pour récupérer la commande.
                </div>
              </div>
            )}

            <div className="bt-card p-6">
              <div className="flex items-center justify-between">
                <div className="bt-label m-0">{t("success.status")}</div>
                <span className="bt-badge-red" data-testid="order-status">
                  {STATUS_LABEL[order.status] || order.status}
                </span>
              </div>
              <div className="mt-4 space-y-2">
                {(order.items || []).map((it) => (
                  <div
                    key={it.line_id}
                    className="flex justify-between text-sm border-b border-[#262626] pb-2"
                  >
                    <div>
                      <div>{it.quantity}× {it.name}</div>
                      {it.burger_config && (
                        <div className="text-xs text-[#A1A1A1] mt-1">
                          {(it.burger_config.meats || []).map((m) => m.name).join(", ")}
                        </div>
                      )}
                      {it.formula === "menu" && it.included_drink && (
                        <div className="text-xs text-[#A1A1A1]">Boisson : {it.included_drink}</div>
                      )}
                    </div>
                    <div>{formatEur(it.line_total)}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span>{t("cart.subtotal")}</span>
                  <span>{formatEur(order.subtotal)}</span>
                </div>
                {order.delivery_fee > 0 && (
                  <div className="flex justify-between">
                    <span>{t("cart.delivery")}</span>
                    <span>{formatEur(order.delivery_fee)}</span>
                  </div>
                )}
                <div className="flex justify-between items-baseline pt-2 border-t border-[#262626] mt-2">
                  <span className="font-accent uppercase tracking-widest">{t("cart.total")}</span>
                  <span className="font-display text-2xl text-[#EF2B2D]">
                    {formatEur(order.total)}
                  </span>
                </div>
              </div>
              <div className="mt-4 text-xs text-[#A1A1A1]">
                Paiement : {order.payment_method === "cash" ? "Cash sur place" : "Carte sur place"}
              </div>
            </div>

            <div className="text-center">
              <Link to="/" className="bt-btn-secondary inline-flex">
                {t("success.back_home")}
              </Link>
            </div>
          </div>
        )}
      </section>
      <Footer />
    </div>
  );
}
