import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError } from "@/lib/api";
import { Plus, Trash2, Ticket } from "lucide-react";

const TYPE_LABEL = {
  free_delivery: "Livraison gratuite",
  percent_off_delivery: "% sur la livraison",
};

export default function CouponsAdmin() {
  const [items, setItems] = useState([]);
  const [code, setCode] = useState("");
  const [discountType, setDiscountType] = useState("free_delivery");
  const [percentValue, setPercentValue] = useState(10);
  const [maxUses, setMaxUses] = useState(1);

  const load = () => adminClient.get("/admin/coupons").then((r) => setItems(r.data || []));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!code.trim()) {
      toast.error("Entre un nom de code");
      return;
    }
    try {
      await adminClient.post("/admin/coupons", {
        code: code.trim(),
        discount_type: discountType,
        percent_value: discountType === "percent_off_delivery" ? Number(percentValue) : null,
        max_uses: Number(maxUses) || 1,
      });
      setCode("");
      setPercentValue(10);
      setMaxUses(1);
      toast.success("Code promo créé");
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const update = async (c, patch) => {
    try {
      await adminClient.put(`/admin/coupons/${c.id}`, patch);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const del = async (id) => {
    if (!window.confirm("Supprimer ce code promo ?")) return;
    try {
      await adminClient.delete(`/admin/coupons/${id}`);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">Petites attentions</div>
        <h1 className="font-display text-5xl uppercase leading-none">Codes promo</h1>
        <p className="text-sm text-[#A1A1A1] mt-2">
          Réduction appliquée uniquement sur les frais de livraison. Rejeté si le client
          commande en retrait.
        </p>
      </div>

      <div className="bt-card p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <input
            data-testid="coupon-code-input"
            className="bt-input"
            placeholder="Nom du code (ex: SORRY10)"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
          />
          <select
            data-testid="coupon-type-select"
            className="bt-input"
            value={discountType}
            onChange={(e) => setDiscountType(e.target.value)}
          >
            <option value="free_delivery">Livraison gratuite</option>
            <option value="percent_off_delivery">% sur la livraison</option>
          </select>
          {discountType === "percent_off_delivery" ? (
            <input
              data-testid="coupon-percent-input"
              type="number"
              min={1}
              max={100}
              className="bt-input"
              placeholder="% de réduction"
              value={percentValue}
              onChange={(e) => setPercentValue(e.target.value)}
            />
          ) : (
            <div />
          )}
          <input
            data-testid="coupon-max-uses-input"
            type="number"
            min={1}
            className="bt-input"
            placeholder="Utilisations max"
            value={maxUses}
            onChange={(e) => setMaxUses(e.target.value)}
          />
        </div>
        <button onClick={create} data-testid="coupon-create-btn" className="bt-btn-primary py-2 px-4 text-sm">
          <Plus className="w-4 h-4" /> Créer le code
        </button>
      </div>

      <div className="bt-card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs bg-[#0A0A0A]">
              <th className="p-3">Code</th>
              <th className="p-3">Type</th>
              <th className="p-3">Utilisations</th>
              <th className="p-3">Actif</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-[#262626]" data-testid={`coupon-row-${c.id}`}>
                <td className="p-3 font-display text-lg">{c.code}</td>
                <td className="p-3">
                  {TYPE_LABEL[c.discount_type] || c.discount_type}
                  {c.discount_type === "percent_off_delivery" && c.percent_value != null && (
                    <span className="text-[#EF2B2D]"> ({c.percent_value}%)</span>
                  )}
                </td>
                <td className="p-3">
                  <span className={c.used_count >= c.max_uses ? "text-[#EF2B2D]" : ""}>
                    {c.used_count} / {c.max_uses}
                  </span>
                </td>
                <td className="p-3">
                  <input
                    data-testid={`coupon-active-toggle-${c.id}`}
                    type="checkbox"
                    checked={!!c.active}
                    onChange={(e) => update(c, { active: e.target.checked })}
                  />
                </td>
                <td className="p-3">
                  <button
                    onClick={() => del(c.id)}
                    data-testid={`coupon-delete-${c.id}`}
                    className="bt-btn-ghost px-2 text-xs text-[#EF2B2D]"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-[#A1A1A1]">
                  <Ticket className="w-5 h-5 mx-auto mb-2 text-[#666]" />
                  Aucun code promo.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
