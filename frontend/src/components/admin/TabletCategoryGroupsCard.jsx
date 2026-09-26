import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { adminClient, fmtError } from "@/lib/api";
import { TABLET_ICONS, categoryLabel, groupIcon, suggestedIconNames } from "@/lib/tabletCategories";

const labelOf = (cat) => {
  const raw = cat.label;
  const text = typeof raw === "string" ? raw : raw?.fr || raw?.en;
  return (text || "").trim() || categoryLabel(cat.slug);
};

const newId = () =>
  (window.crypto?.randomUUID?.() || `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`);

/** Admin card: merge 2+ menu categories into one tab — tablet only. Saves
 * straight away (no need for the page's "Enregistrer" button). */
export default function TabletCategoryGroupsCard({ groups = [], onSaved }) {
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState([]);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [icon, setIcon] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    adminClient
      .get("/admin/categories")
      .then((r) => setCategories((r.data || []).filter((c) => c.active !== false)))
      .catch(() => {});
  }, []);

  const labels = useMemo(
    () => Object.fromEntries(categories.map((c) => [c.slug, labelOf(c)])),
    [categories],
  );
  const nameFor = (slug) => labels[slug] || categoryLabel(slug);
  const grouped = new Set(groups.flatMap((g) => g.categories || []));

  const suggestedName = selected.map(nameFor).join(" & ");
  const { suggested, others } = suggestedIconNames(selected);
  const icons = [...suggested, ...others];
  const chosenIcon = icon || icons[0];

  const toggle = (slug) =>
    setSelected((cur) => (cur.includes(slug) ? cur.filter((s) => s !== slug) : [...cur, slug]));

  // Keep the suggested name in the field until the admin types their own.
  useEffect(() => {
    if (!nameTouched) setName(suggestedName);
  }, [suggestedName, nameTouched]);

  const persist = async (next, message) => {
    setSaving(true);
    try {
      const { data } = await adminClient.put("/settings", { tablet_category_groups: next });
      onSaved(data);
      toast.success(message);
      return true;
    } catch (e) {
      toast.error(fmtError(e));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const create = async () => {
    if (selected.length < 2) {
      toast.error("Choisis au moins 2 catégories");
      return;
    }
    const finalName = name.trim();
    if (!finalName) {
      toast.error("Donne un nom à la catégorie combinée");
      return;
    }
    const group = { id: newId(), name: finalName, icon: chosenIcon, categories: selected };
    if (await persist([...groups, group], `« ${finalName} » créée`)) {
      setSelected([]);
      setName("");
      setNameTouched(false);
      setIcon("");
    }
  };

  const remove = (group) =>
    persist(groups.filter((g) => g.id !== group.id), `« ${group.name} » supprimée`);

  return (
    <div className="bt-card p-5 space-y-4" data-testid="settings-tablet-category-groups-card">
      <div>
        <div className="font-display text-2xl uppercase">Catégories combinées (tablette)</div>
        <p className="text-sm text-[#A1A1A1]">
          Regroupe plusieurs catégories en un seul bouton sur la tablette. Le site web ne change pas.
          Enregistré automatiquement.
        </p>
      </div>

      {groups.length > 0 && (
        <div className="space-y-2">
          {groups.map((g) => {
            const Icon = groupIcon(g);
            return (
              <div
                className="flex items-center gap-3 border-2 border-[#262626] bg-[#0A0A0A] p-3"
                data-testid={`settings-tablet-group-${g.id}`}
                key={g.id}
              >
                <Icon className="h-8 w-8 shrink-0 text-[#EF2B2D]" strokeWidth={1.5} />
                <div className="min-w-0 flex-1">
                  <div className="font-accent uppercase tracking-widest">{g.name}</div>
                  <div className="text-xs text-[#A1A1A1]">{(g.categories || []).map(nameFor).join(" + ")}</div>
                </div>
                <button
                  aria-label={`Supprimer ${g.name}`}
                  className="bt-btn-ghost h-9 w-9 p-0 text-[#EF2B2D] disabled:opacity-40"
                  data-testid={`settings-tablet-group-delete-${g.id}`}
                  disabled={saving}
                  onClick={() => remove(g)}
                  type="button"
                >
                  <Trash2 className="mx-auto h-4 w-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="space-y-4 border-t-2 border-[#262626] pt-4">
        <div>
          <div className="bt-label">1. Catégories à combiner (au moins 2)</div>
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => {
              const taken = grouped.has(c.slug);
              return (
                <button
                  className={`bt-chip ${selected.includes(c.slug) ? "active" : ""} disabled:opacity-40`}
                  data-testid={`settings-tablet-group-cat-${c.slug}`}
                  disabled={taken}
                  key={c.slug}
                  onClick={() => toggle(c.slug)}
                  title={taken ? "Déjà dans une catégorie combinée" : undefined}
                  type="button"
                >
                  {labelOf(c)}
                </button>
              );
            })}
          </div>
        </div>

        {selected.length >= 2 && (
          <>
            <div>
              <div className="bt-label">2. Nom de la catégorie combinée</div>
              <input
                className="bt-input w-full max-w-md"
                data-testid="settings-tablet-group-name"
                onChange={(e) => {
                  setNameTouched(true);
                  setName(e.target.value);
                }}
                placeholder={suggestedName}
                value={name}
              />
            </div>

            <div>
              <div className="bt-label">3. Icône</div>
              <div className="flex flex-wrap gap-2">
                {icons.map((iconName) => {
                  const Icon = TABLET_ICONS[iconName];
                  const active = chosenIcon === iconName;
                  return (
                    <button
                      aria-label={iconName}
                      className={`relative flex h-14 w-14 items-center justify-center border-2 transition-colors ${
                        active
                          ? "border-[#EF2B2D] bg-[#EF2B2D] text-[#0A0A0A]"
                          : "border-[#262626] bg-[#0A0A0A] hover:border-[#EF2B2D]"
                      }`}
                      data-testid={`settings-tablet-group-icon-${iconName}`}
                      key={iconName}
                      onClick={() => setIcon(iconName)}
                      type="button"
                    >
                      <Icon className="h-7 w-7" strokeWidth={1.5} />
                      {suggested.includes(iconName) && (
                        <span className="absolute -top-2 -right-2 bg-[#FFB800] px-1 text-[9px] font-bold uppercase text-[#0A0A0A]">
                          Suggéré
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}

        <button
          className="bt-btn-primary px-4 disabled:opacity-40"
          data-testid="settings-tablet-group-create"
          disabled={saving || selected.length < 2}
          onClick={create}
          type="button"
        >
          <Plus className="h-4 w-4" /> Créer la catégorie combinée
        </button>
      </div>
    </div>
  );
}
