import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { adminClient, fmtError, formatEur, menuImageUrl } from "@/lib/api";
import { Pencil, Plus, Save, Trash2, X, Search } from "lucide-react";

const emptyItem = {
  name: "",
  description: "",
  category: "",
  price_seul: 0,
  price_menu: null,
  formats: [],
  variants: [],
  uses_soda_flavours: false,
  available: true,
  is_new: false,
  sort_order: 0,
  image_base64: null,
};

export default function MenuAdmin() {
  const [items, setItems] = useState([]);
  const [cats, setCats] = useState([]);
  const [editing, setEditing] = useState(null);
  const [query, setQuery] = useState("");
  const [catFilter, setCatFilter] = useState("all");

  const load = () => {
    adminClient.get("/admin/menu").then((r) => setItems(r.data || []));
    adminClient.get("/admin/categories").then((r) => setCats(r.data || []));
  };
  useEffect(() => { load(); }, []);

  const catLabel = (slug) => {
    const c = cats.find((x) => x.slug === slug);
    if (!c) return slug;
    return typeof c.label === "string" ? c.label : c.label?.fr || c.label?.en || slug;
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((it) => {
      if (catFilter !== "all" && it.category !== catFilter) return false;
      if (!q) return true;
      return (
        (it.name || "").toLowerCase().includes(q) ||
        (it.description || "").toLowerCase().includes(q) ||
        (it.category || "").toLowerCase().includes(q) ||
        catLabel(it.category).toLowerCase().includes(q)
      );
    });
  }, [items, query, catFilter, cats]);

  const save = async (item) => {
    try {
      if (item.id) {
        const { id, has_image, ...body } = item;
        await adminClient.put(`/admin/menu/${id}`, body);
      } else {
        await adminClient.post("/admin/menu", item);
      }
      toast.success("Enregistré");
      setEditing(null);
      load();
    } catch (e) {
      toast.error(fmtError(e));
    }
  };

  const del = async (id) => {
    if (!window.confirm("Supprimer ce plat ?")) return;
    await adminClient.delete(`/admin/menu/${id}`);
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="font-marker text-[#EF2B2D] -rotate-1">La carte</div>
          <h1 className="font-display text-5xl uppercase leading-none">Menu</h1>
        </div>
        <button
          data-testid="menu-new-btn"
          onClick={() => setEditing({ ...emptyItem, category: cats[0]?.slug || "" })}
          className="bt-btn-primary self-start md:self-auto"
        >
          <Plus className="w-4 h-4" /> Nouveau
        </button>
      </div>

      {/* Search + category filter */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#A1A1A1] pointer-events-none" />
          <input
            data-testid="menu-search-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Chercher un plat, ex. tacos, sandwich, coca…"
            className="bt-input pl-10"
          />
        </div>
        <select
          data-testid="menu-category-filter"
          value={catFilter}
          onChange={(e) => setCatFilter(e.target.value)}
          className="bt-input sm:w-64"
        >
          <option value="all">Toutes les catégories ({items.length})</option>
          {cats.map((c) => {
            const n = items.filter((it) => it.category === c.slug).length;
            return (
              <option key={c.id} value={c.slug}>
                {catLabel(c.slug)} ({n})
              </option>
            );
          })}
        </select>
        {(query || catFilter !== "all") && (
          <button
            data-testid="menu-filter-clear"
            onClick={() => { setQuery(""); setCatFilter("all"); }}
            className="bt-btn-ghost text-xs px-3"
          >
            <X className="w-3 h-3" /> Effacer
          </button>
        )}
      </div>

      <div className="text-xs text-[#A1A1A1] uppercase tracking-widest" data-testid="menu-result-count">
        {filtered.length} plat{filtered.length > 1 ? "s" : ""} affiché{filtered.length > 1 ? "s" : ""}
        {(query || catFilter !== "all") && ` sur ${items.length}`}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((it) => (
          <div key={it.id} className="bt-card overflow-hidden" data-testid={`admin-menu-item-${it.id}`}>
            <div className="aspect-[4/3] bg-[#0A0A0A] overflow-hidden">
              {it.has_image ? (
                <img src={menuImageUrl(it.id)} alt={it.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center bt-halftone">
                  <div className="font-display text-4xl text-[#EF2B2D]/40">BT</div>
                </div>
              )}
            </div>
            <div className="p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-display text-xl uppercase leading-none">{it.name}</div>
                  <div className="text-xs text-[#A1A1A1] mt-1 uppercase tracking-widest">
                    {it.category} · {formatEur(it.price_seul)}
                    {it.price_menu ? ` / Menu ${formatEur(it.price_menu)}` : ""}
                  </div>
                </div>
                {!it.available && <span className="bt-badge-red">Off</span>}
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  data-testid={`admin-edit-menu-${it.id}`}
                  onClick={() => setEditing({ ...it, image_base64: null })}
                  className="bt-btn-ghost px-2 text-xs"
                >
                  <Pencil className="w-3 h-3" /> Éditer
                </button>
                <button
                  data-testid={`admin-delete-menu-${it.id}`}
                  onClick={() => del(it.id)}
                  className="bt-btn-ghost px-2 text-xs text-[#EF2B2D]"
                >
                  <Trash2 className="w-3 h-3" /> Suppr
                </button>
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-full bt-card p-8 text-center text-sm text-[#A1A1A1]">
            {items.length === 0
              ? "Ajoute ton premier plat."
              : "Aucun plat ne correspond à ta recherche."}
          </div>
        )}
      </div>

      {editing && (
        <EditItem
          item={editing}
          categories={cats}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </div>
  );
}

function EditItem({ item, categories, onClose, onSave }) {
  const [it, setIt] = useState(item);

  const set = (k, v) => setIt((s) => ({ ...s, [k]: v }));

  const readImg = (file) => {
    const reader = new FileReader();
    reader.onload = (e) => set("image_base64", e.target.result);
    reader.readAsDataURL(file);
  };

  const addFormat = () =>
    set("formats", [...(it.formats || []), { name: "", price_seul: 0, price_menu: null }]);
  const updateFormat = (i, patch) => {
    const next = [...(it.formats || [])];
    next[i] = { ...next[i], ...patch };
    set("formats", next);
  };
  const removeFormat = (i) => {
    const next = [...(it.formats || [])];
    next.splice(i, 1);
    set("formats", next);
  };

  return (
    <div className="fixed inset-0 z-40 bg-black/70 flex items-end md:items-center justify-center p-0 md:p-4">
      <div className="bg-[#141414] border-2 border-[#EF2B2D] w-full md:max-w-2xl max-h-[92vh] flex flex-col">
        <div className="p-4 border-b-2 border-[#262626] flex items-center justify-between">
          <div className="font-display text-2xl uppercase">{it.id ? "Éditer" : "Nouveau plat"}</div>
          <button onClick={onClose} className="w-9 h-9 border-2 border-[#262626]">
            <X className="w-4 h-4 mx-auto" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block">
              <div className="bt-label">Nom *</div>
              <input data-testid="menu-input-name" className="bt-input" value={it.name} onChange={(e) => set("name", e.target.value)} />
            </label>
            <label className="block">
              <div className="bt-label">Catégorie *</div>
              <select data-testid="menu-input-category" className="bt-input" value={it.category} onChange={(e) => set("category", e.target.value)}>
                <option value="">—</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.slug}>
                    {typeof c.label === "string" ? c.label : c.label.fr || c.label.en || c.slug}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block">
            <div className="bt-label">Description</div>
            <textarea data-testid="menu-input-desc" className="bt-input min-h-[80px]" value={it.description} onChange={(e) => set("description", e.target.value)} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block">
              <div className="bt-label">Prix seul (€) *</div>
              <input
                data-testid="menu-input-price-seul"
                type="number"
                step="0.1"
                className="bt-input"
                value={it.price_seul}
                onChange={(e) => set("price_seul", parseFloat(e.target.value) || 0)}
              />
            </label>
            <label className="block">
              <div className="bt-label">Prix menu (€)</div>
              <input
                data-testid="menu-input-price-menu"
                type="number"
                step="0.1"
                className="bt-input"
                value={it.price_menu ?? ""}
                onChange={(e) => set("price_menu", e.target.value === "" ? null : parseFloat(e.target.value))}
              />
            </label>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <label className="inline-flex items-center gap-2 text-sm">
              <input
                data-testid="menu-input-uses-soda"
                type="checkbox"
                className="w-4 h-4"
                checked={!!it.uses_soda_flavours}
                onChange={(e) => set("uses_soda_flavours", e.target.checked)}
              />
              Ajoute une boisson au menu
            </label>
            <label className="inline-flex items-center gap-2 text-sm">
              <input
                data-testid="menu-input-available"
                type="checkbox"
                className="w-4 h-4"
                checked={!!it.available}
                onChange={(e) => set("available", e.target.checked)}
              />
              Disponible
            </label>
            <label className="inline-flex items-center gap-2 text-sm">
              <input
                data-testid="menu-input-is-new"
                type="checkbox"
                className="w-4 h-4"
                checked={!!it.is_new}
                onChange={(e) => set("is_new", e.target.checked)}
              />
              <span className="inline-flex items-center gap-1">
                Nouveau
                <span className="inline-block px-1.5 py-0.5 bg-[#EF2B2D] text-[#F5F1E8] font-accent uppercase tracking-widest text-[10px]">
                  NEW
                </span>
              </span>
            </label>
            <label className="inline-flex items-center gap-2 text-sm">
              Tri
              <input
                type="number"
                className="bt-input w-20"
                value={it.sort_order || 0}
                onChange={(e) => set("sort_order", parseInt(e.target.value, 10) || 0)}
              />
            </label>
          </div>
          <div>
            <div className="bt-label">Formats</div>
            <div className="space-y-2">
              {(it.formats || []).map((f, i) => (
                <div key={i} className="grid grid-cols-4 gap-2 items-end">
                  <input placeholder="Nom" className="bt-input col-span-2" value={f.name} onChange={(e) => updateFormat(i, { name: e.target.value })} />
                  <input placeholder="Seul" className="bt-input" type="number" step="0.1" value={f.price_seul} onChange={(e) => updateFormat(i, { price_seul: parseFloat(e.target.value) || 0 })} />
                  <div className="flex gap-2">
                    <input placeholder="Menu" className="bt-input" type="number" step="0.1" value={f.price_menu ?? ""} onChange={(e) => updateFormat(i, { price_menu: e.target.value === "" ? null : parseFloat(e.target.value) })} />
                    <button onClick={() => removeFormat(i)} className="w-10 h-10 border-2 border-[#262626]">
                      <X className="w-4 h-4 mx-auto" />
                    </button>
                  </div>
                </div>
              ))}
              <button onClick={addFormat} className="bt-btn-ghost text-xs px-2">
                <Plus className="w-3 h-3" /> Ajouter un format
              </button>
            </div>
          </div>
          <label className="block">
            <div className="bt-label">Image</div>
            <input data-testid="menu-input-image" type="file" accept="image/*" onChange={(e) => e.target.files?.[0] && readImg(e.target.files[0])} />
            {it.image_base64 && (
              <img src={it.image_base64} alt="" className="mt-2 h-24 border-2 border-[#262626]" />
            )}
            {!it.image_base64 && it.has_image && it.id && (
              <img src={menuImageUrl(it.id)} alt="" className="mt-2 h-24 border-2 border-[#262626]" />
            )}
          </label>
        </div>
        <div className="p-4 border-t-2 border-[#262626] flex justify-end gap-2 bg-[#0A0A0A]">
          <button onClick={onClose} className="bt-btn-secondary py-2 px-4 text-sm">
            Annuler
          </button>
          <button onClick={() => onSave(it)} data-testid="menu-save" className="bt-btn-primary py-2 px-4 text-sm">
            <Save className="w-4 h-4" /> Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
}
