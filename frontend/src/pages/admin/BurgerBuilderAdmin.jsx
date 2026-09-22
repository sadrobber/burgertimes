import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError, formatEur } from "@/lib/api";
import { Plus, Trash2 } from "lucide-react";

const TABS = [
  { key: "styles", label: "Styles", fields: ["name", "ticket_shortcode", "description", "price_modifier", "flat_price", "flat_price_menu", "max_meats", "available", "sort_order"] },
  { key: "sizes", label: "Tailles", fields: ["code", "label", "ticket_shortcode", "price_simple", "price_menu", "nb_meats", "supplement_upcharge", "available", "sort_order"] },
  { key: "meats", label: "Viandes", fields: ["name", "ticket_shortcode", "base_price", "available", "sort_order"] },
  { key: "cheeses", label: "Fromages", fields: ["name", "ticket_shortcode", "base_price", "available", "sort_order"] },
  { key: "supplements", label: "Suppléments", fields: ["name", "ticket_shortcode", "base_price", "available", "sort_order"] },
];

const FIELD_LABELS = {
  name: "Nom",
  ticket_shortcode: "Code ticket",
  description: "Description",
  code: "Code",
  label: "Libellé",
  price_modifier: "Modificateur (€)",
  flat_price: "Prix fixe (€)",
  flat_price_menu: "Prix fixe menu (€)",
  max_meats: "Max viandes",
  price_simple: "Prix seul (€)",
  price_menu: "Prix menu (€)",
  nb_meats: "Nb viandes",
  supplement_upcharge: "Surcoût supp (€)",
  base_price: "Prix (€)",
  available: "Actif",
  sort_order: "Tri",
};

const NUMERIC = new Set(["price_modifier", "flat_price", "flat_price_menu", "price_simple", "price_menu", "base_price", "supplement_upcharge"]);
const INTEGER = new Set(["max_meats", "nb_meats", "sort_order"]);

export default function BurgerBuilderAdmin() {
  const [tab, setTab] = useState("styles");
  const [items, setItems] = useState([]);
  const [newItem, setNewItem] = useState({});

  const load = () => adminClient.get(`/admin/burger/${tab}`).then((r) => setItems(r.data || []));

  useEffect(() => {
    load();
    setNewItem({});
     
  }, [tab]);

  const currentTab = TABS.find((t) => t.key === tab);

  const create = async () => {
    try {
      const payload = normalize(newItem, currentTab.fields);
      await adminClient.post(`/admin/burger/${tab}`, payload);
      setNewItem({});
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };
  const update = async (it, patch) => {
    try {
      await adminClient.put(`/admin/burger/${tab}/${it.id}`, patch);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };
  const del = async (id) => {
    if (!window.confirm("Supprimer ?")) return;
    await adminClient.delete(`/admin/burger/${tab}/${id}`);
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">La cuisine</div>
        <h1 className="font-display text-5xl uppercase leading-none">Burger Builder</h1>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            data-testid={`bb-tab-${t.key}`}
            className={`bt-chip ${tab === t.key ? "active" : ""}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="bt-card p-4">
        <div className="text-sm font-accent uppercase tracking-widest text-[#A1A1A1] mb-3">
          Nouveau {currentTab.label.slice(0, -1)}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-2">
          {currentTab.fields.map((f) => (
            <label key={f} className="block">
              <div className="bt-label">{FIELD_LABELS[f] || f}</div>
              {f === "available" ? (
                <input
                  type="checkbox"
                  className="w-4 h-4 mt-2"
                  checked={newItem[f] ?? true}
                  onChange={(e) => setNewItem({ ...newItem, [f]: e.target.checked })}
                />
              ) : (
                <input
                  data-testid={`bb-new-${f}`}
                  className="bt-input"
                  type={NUMERIC.has(f) || INTEGER.has(f) ? "number" : "text"}
                  step={NUMERIC.has(f) ? "0.1" : "1"}
                  value={newItem[f] ?? ""}
                  onChange={(e) => setNewItem({ ...newItem, [f]: e.target.value })}
                />
              )}
            </label>
          ))}
        </div>
        <button onClick={create} data-testid="bb-create-btn" className="bt-btn-primary py-2 px-4 text-sm mt-4">
          <Plus className="w-4 h-4" /> Ajouter
        </button>
      </div>

      <div className="bt-card p-0 overflow-x-auto">
        <table className="w-full text-sm min-w-[900px]">
          <thead>
            <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs bg-[#0A0A0A]">
              {currentTab.fields.map((f) => (
                <th key={f} className="p-3">{FIELD_LABELS[f] || f}</th>
              ))}
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-t border-[#262626]" data-testid={`bb-row-${it.id}`}>
                {currentTab.fields.map((f) => (
                  <td key={f} className="p-3">
                    {f === "available" ? (
                      <input
                        type="checkbox"
                        checked={!!it[f]}
                        onChange={(e) => update(it, { [f]: e.target.checked })}
                      />
                    ) : (
                      <input
                        className="bt-input"
                        type={NUMERIC.has(f) || INTEGER.has(f) ? "number" : "text"}
                        step={NUMERIC.has(f) ? "0.1" : "1"}
                        defaultValue={it[f] ?? ""}
                        onBlur={(e) => update(it, normalize({ [f]: e.target.value }, [f]))}
                      />
                    )}
                  </td>
                ))}
                <td className="p-3">
                  <button onClick={() => del(it.id)} className="bt-btn-ghost px-2 text-xs text-[#EF2B2D]">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={currentTab.fields.length + 1} className="p-6 text-center text-[#A1A1A1]">
                  Rien encore. {formatEur(0)}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function normalize(obj, fields) {
  const out = {};
  for (const f of fields) {
    if (obj[f] === undefined || obj[f] === "") continue;
    if (NUMERIC.has(f)) out[f] = parseFloat(obj[f]);
    else if (INTEGER.has(f)) out[f] = parseInt(obj[f], 10);
    else out[f] = obj[f];
  }
  if ("available" in obj) out.available = !!obj.available;
  return out;
}
