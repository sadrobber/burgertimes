import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError } from "@/lib/api";
import { Plus, Trash2 } from "lucide-react";

export default function CategoriesAdmin() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ slug: "", labelFr: "", labelEn: "", sort_order: 0 });

  const load = () => adminClient.get("/admin/categories").then((r) => setItems(r.data || []));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.slug || !form.labelFr) return toast.error("Slug et libellé requis");
    try {
      await adminClient.post("/admin/categories", {
        slug: form.slug.trim(),
        label: { fr: form.labelFr, en: form.labelEn || form.labelFr },
        sort_order: parseInt(form.sort_order, 10) || 0,
        active: true,
      });
      setForm({ slug: "", labelFr: "", labelEn: "", sort_order: 0 });
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const update = async (c, patch) => {
    try {
      await adminClient.put(`/admin/categories/${c.id}`, patch);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };
  const del = async (id) => {
    if (!window.confirm("Supprimer ?")) return;
    await adminClient.delete(`/admin/categories/${id}`);
    load();
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="font-marker text-[#EF2B2D] -rotate-1">Rangement</div>
        <h1 className="font-display text-5xl uppercase leading-none">Catégories</h1>
      </div>

      <div className="bt-card p-4">
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 items-end">
          <label className="block">
            <div className="bt-label">Slug</div>
            <input data-testid="cat-input-slug" className="bt-input" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
          </label>
          <label className="block">
            <div className="bt-label">Libellé FR</div>
            <input data-testid="cat-input-label-fr" className="bt-input" value={form.labelFr} onChange={(e) => setForm({ ...form, labelFr: e.target.value })} />
          </label>
          <label className="block">
            <div className="bt-label">Libellé EN</div>
            <input data-testid="cat-input-label-en" className="bt-input" value={form.labelEn} onChange={(e) => setForm({ ...form, labelEn: e.target.value })} />
          </label>
          <label className="block">
            <div className="bt-label">Tri</div>
            <input type="number" className="bt-input" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} />
          </label>
          <button onClick={create} data-testid="cat-create-btn" className="bt-btn-primary py-2 px-4 text-sm">
            <Plus className="w-4 h-4" /> Ajouter
          </button>
        </div>
      </div>

      <div className="bt-card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left font-accent uppercase tracking-widest text-[#A1A1A1] text-xs bg-[#0A0A0A]">
              <th className="p-3">Slug</th>
              <th className="p-3">Libellé FR</th>
              <th className="p-3">Libellé EN</th>
              <th className="p-3">Tri</th>
              <th className="p-3">Actif</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-[#262626]" data-testid={`admin-cat-${c.id}`}>
                <td className="p-3">{c.slug}</td>
                <td className="p-3">
                  <input
                    className="bt-input"
                    defaultValue={typeof c.label === "string" ? c.label : c.label?.fr || ""}
                    onBlur={(e) => update(c, { label: { fr: e.target.value, en: (typeof c.label === "object" ? c.label?.en : "") || e.target.value } })}
                  />
                </td>
                <td className="p-3">
                  <input
                    className="bt-input"
                    defaultValue={typeof c.label === "string" ? "" : c.label?.en || ""}
                    onBlur={(e) => update(c, { label: { fr: (typeof c.label === "object" ? c.label?.fr : c.label) || "", en: e.target.value } })}
                  />
                </td>
                <td className="p-3 w-24">
                  <input
                    type="number"
                    className="bt-input"
                    defaultValue={c.sort_order || 0}
                    onBlur={(e) => update(c, { sort_order: parseInt(e.target.value, 10) || 0 })}
                  />
                </td>
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={!!c.active}
                    onChange={(e) => update(c, { active: e.target.checked })}
                  />
                </td>
                <td className="p-3">
                  <button onClick={() => del(c.id)} className="bt-btn-ghost px-2 text-xs text-[#EF2B2D]">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
