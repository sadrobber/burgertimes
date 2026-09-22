import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError } from "@/lib/api";
import { Plus, Trash2 } from "lucide-react";

export default function SaucesAdmin() {
  const [items, setItems] = useState([]);
  const [name, setName] = useState("");

  const load = () => adminClient.get("/admin/sauces").then((r) => setItems(r.data || []));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    try {
      await adminClient.post("/admin/sauces", { name: name.trim(), sort_order: items.length, active: true });
      setName("");
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };
  const update = async (s, patch) => {
    try {
      await adminClient.put(`/admin/sauces/${s.id}`, patch);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };
  const del = async (id) => {
    if (!window.confirm("Supprimer ?")) return;
    await adminClient.delete(`/admin/sauces/${id}`);
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">Petits pots</div>
        <h1 className="font-display text-5xl uppercase leading-none">Sauces</h1>
      </div>

      <div className="bt-card p-4 flex flex-col sm:flex-row gap-2">
        <input
          data-testid="sauce-name-input"
          className="bt-input flex-1"
          placeholder="Nom de la sauce"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button onClick={create} data-testid="sauce-create-btn" className="bt-btn-primary py-2 px-4 text-sm">
          <Plus className="w-4 h-4" /> Ajouter
        </button>
      </div>

      <div className="bt-card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs bg-[#0A0A0A]">
              <th className="p-3">Nom</th>
              <th className="p-3">Ticket</th>
              <th className="p-3">Tri</th>
              <th className="p-3">Actif</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} className="border-t border-[#262626]" data-testid={`sauce-row-${s.id}`}>
                <td className="p-3">
                  <input className="bt-input" defaultValue={s.name} onBlur={(e) => update(s, { name: e.target.value })} />
                </td>
                <td className="p-3 w-32">
                  <input
                    className="bt-input"
                    data-testid={`sauce-shortcode-${s.id}`}
                    defaultValue={s.ticket_shortcode || ""}
                    onBlur={(e) => update(s, { ticket_shortcode: e.target.value })}
                    placeholder="Alg"
                  />
                </td>
                <td className="p-3 w-24">
                  <input
                    type="number"
                    className="bt-input"
                    defaultValue={s.sort_order || 0}
                    onBlur={(e) => update(s, { sort_order: parseInt(e.target.value, 10) || 0 })}
                  />
                </td>
                <td className="p-3">
                  <input type="checkbox" checked={!!s.active} onChange={(e) => update(s, { active: e.target.checked })} />
                </td>
                <td className="p-3">
                  <button onClick={() => del(s.id)} className="bt-btn-ghost px-2 text-xs text-[#EF2B2D]">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-[#A1A1A1]">Aucune sauce.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
