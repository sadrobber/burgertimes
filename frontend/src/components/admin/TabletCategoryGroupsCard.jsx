import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { adminClient, fmtError } from "@/lib/api";
import {
  CATEGORY_ICON_NAMES,
  TABLET_ICONS,
  TACOS_BUILDER_KEY,
  categoryLabel,
  groupIcon,
  suggestedIconNames,
  tabletCategoryDisplay,
} from "@/lib/tabletCategories";

const newId = () =>
  (window.crypto?.randomUUID?.() || `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`);

/** Admin card for the tablet's category bar (tablet only, website unchanged):
 *  1. rename / change the icon of each category button (+ "Composer un Tacos"),
 *  2. merge 2+ categories into one button.
 * Saves straight to settings (no need for the page's "Enregistrer" button). */
export default function TabletCategoryGroupsCard({ groups = [], overrides = {}, onSaved }) {
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    adminClient
      .get("/admin/categories")
      .then((r) => setCategories((r.data || []).filter((c) => c.active !== false)))
      .catch(() => {});
  }, []);

  const persist = async (changes, message) => {
    setSaving(true);
    try {
      const { data } = await adminClient.put("/settings", changes);
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

  const slugs = categories.map((c) => c.slug);

  return (
    <div className="bt-card p-5 space-y-6" data-testid="settings-tablet-category-groups-card">
      <div>
        <div className="font-display text-2xl uppercase">Catégories de la tablette</div>
        <p className="text-sm text-[#A1A1A1]">
          Change le nom et l&apos;icône des boutons de catégorie, ou regroupe plusieurs catégories en
          un seul bouton. Uniquement sur la tablette — le site web ne change pas.
        </p>
      </div>

      <CategoryNamesSection
        groups={groups}
        overrides={overrides}
        persist={persist}
        saving={saving}
        slugs={slugs}
      />

      <CategoryGroupsSection
        groups={groups}
        overrides={overrides}
        persist={persist}
        saving={saving}
        slugs={slugs}
      />
    </div>
  );
}

function CategoryNamesSection({ groups, overrides, persist, saving, slugs }) {
  const [draft, setDraft] = useState(overrides);
  const [openPicker, setOpenPicker] = useState(null);

  // Re-sync only when the *saved* overrides actually change (after a save).
  // Compared by content: the parent passes a fresh {} on every render.
  const savedKey = JSON.stringify(overrides || {});
  useEffect(() => setDraft(JSON.parse(savedKey)), [savedKey]);

  const rows = [...slugs, TACOS_BUILDER_KEY];
  const groupOf = (slug) => groups.find((g) => (g.categories || []).includes(slug));

  const update = (slug, patch) =>
    setDraft((cur) => ({ ...cur, [slug]: { ...(cur[slug] || {}), ...patch } }));
  const reset = (slug) =>
    setDraft((cur) => {
      const next = { ...cur };
      delete next[slug];
      return next;
    });

  const save = () => {
    // Only keep real changes: a blank name or the default icon means "default".
    const cleaned = {};
    for (const [slug, o] of Object.entries(draft)) {
      const name = (o?.name || "").trim();
      const icon = o?.icon && o.icon !== CATEGORY_ICON_NAMES[slug] ? o.icon : "";
      if (name || icon) cleaned[slug] = { ...(name && { name }), ...(icon && { icon }) };
    }
    persist({ tablet_category_overrides: cleaned }, "Noms des catégories enregistrés");
  };

  return (
    <div className="space-y-3 border-t-2 border-[#262626] pt-4">
      <div>
        <div className="bt-label">Nom et icône des boutons</div>
        <p className="text-xs text-[#A1A1A1]">
          Laisse le nom vide pour garder le nom par défaut. Touche l&apos;icône pour la changer.
        </p>
      </div>

      <div className="space-y-2">
        {rows.map((slug) => {
          const { Icon } = tabletCategoryDisplay(slug, draft);
          const group = groupOf(slug);
          const changed = !!draft[slug];
          return (
            <div key={slug}>
              <div className="flex items-center gap-2" data-testid={`settings-tablet-cat-row-${slug}`}>
                <button
                  aria-label="Changer l'icône"
                  className={`flex h-11 w-11 shrink-0 items-center justify-center border-2 transition-colors ${
                    openPicker === slug ? "border-[#EF2B2D] text-[#EF2B2D]" : "border-[#262626] hover:border-[#EF2B2D]"
                  }`}
                  data-testid={`settings-tablet-cat-icon-${slug}`}
                  onClick={() => setOpenPicker((cur) => (cur === slug ? null : slug))}
                  type="button"
                >
                  <Icon className="h-6 w-6" strokeWidth={1.5} />
                </button>
                <input
                  className="bt-input min-w-0 flex-1"
                  data-testid={`settings-tablet-cat-name-${slug}`}
                  onChange={(e) => update(slug, { name: e.target.value })}
                  placeholder={categoryLabel(slug)}
                  value={draft[slug]?.name || ""}
                />
                <button
                  aria-label="Remettre par défaut"
                  className="bt-btn-ghost h-11 w-11 shrink-0 p-0 disabled:opacity-30"
                  data-testid={`settings-tablet-cat-reset-${slug}`}
                  disabled={!changed}
                  onClick={() => reset(slug)}
                  title="Remettre le nom et l'icône par défaut"
                  type="button"
                >
                  <RotateCcw className="mx-auto h-4 w-4" />
                </button>
              </div>
              {group && (
                <div className="ml-[3.25rem] mt-1 text-xs text-[#FFB800]">
                  Dans « {group.name} » : ce nom ne s&apos;affiche pas tant qu&apos;elle est combinée.
                </div>
              )}
              {openPicker === slug && (
                <div className="ml-[3.25rem] mt-2">
                  <IconPicker
                    onPick={(name) => {
                      update(slug, { icon: name });
                      setOpenPicker(null);
                    }}
                    suggested={[CATEGORY_ICON_NAMES[slug]].filter(Boolean)}
                    value={draft[slug]?.icon || CATEGORY_ICON_NAMES[slug]}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        className="bt-btn-primary px-4 disabled:opacity-40"
        data-testid="settings-tablet-cat-names-save"
        disabled={saving}
        onClick={save}
        type="button"
      >
        Enregistrer les noms
      </button>
    </div>
  );
}

function CategoryGroupsSection({ groups, overrides, persist, saving, slugs }) {
  const [selected, setSelected] = useState([]);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [icon, setIcon] = useState("");

  // Same names the tablet shows (renames included).
  const nameFor = (slug) => tabletCategoryDisplay(slug, overrides).label;
  const grouped = new Set(groups.flatMap((g) => g.categories || []));

  const suggestedName = selected.map(nameFor).join(" & ");
  const { suggested } = suggestedIconNames(selected, overrides);
  const chosenIcon = icon || suggested[0] || Object.keys(TABLET_ICONS)[0];

  const toggle = (slug) =>
    setSelected((cur) => (cur.includes(slug) ? cur.filter((s) => s !== slug) : [...cur, slug]));

  // Keep the suggested name in the field until the admin types their own.
  useEffect(() => {
    if (!nameTouched) setName(suggestedName);
  }, [suggestedName, nameTouched]);

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
    if (await persist({ tablet_category_groups: [...groups, group] }, `« ${finalName} » créée`)) {
      setSelected([]);
      setName("");
      setNameTouched(false);
      setIcon("");
    }
  };

  const remove = (group) =>
    persist(
      { tablet_category_groups: groups.filter((g) => g.id !== group.id) },
      `« ${group.name} » supprimée`,
    );

  return (
    <div className="space-y-4 border-t-2 border-[#262626] pt-4">
      <div className="bt-label">Catégories combinées</div>

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

      <div>
        <div className="mb-2 text-xs text-[#A1A1A1]">1. Catégories à combiner (au moins 2)</div>
        <div className="flex flex-wrap gap-2">
          {slugs.map((slug) => {
            const taken = grouped.has(slug);
            return (
              <button
                className={`bt-chip ${selected.includes(slug) ? "active" : ""} disabled:opacity-40`}
                data-testid={`settings-tablet-group-cat-${slug}`}
                disabled={taken}
                key={slug}
                onClick={() => toggle(slug)}
                title={taken ? "Déjà dans une catégorie combinée" : undefined}
                type="button"
              >
                {nameFor(slug)}
              </button>
            );
          })}
        </div>
      </div>

      {selected.length >= 2 && (
        <>
          <div>
            <div className="mb-2 text-xs text-[#A1A1A1]">2. Nom de la catégorie combinée</div>
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
            <div className="mb-2 text-xs text-[#A1A1A1]">3. Icône</div>
            <IconPicker onPick={setIcon} suggested={suggested} value={chosenIcon} />
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
  );
}

/** Grid of icon choices; `suggested` ones come first with a "Suggéré" tag. */
function IconPicker({ onPick, suggested = [], value }) {
  const icons = [...suggested, ...Object.keys(TABLET_ICONS).filter((n) => !suggested.includes(n))];
  return (
    <div className="flex flex-wrap gap-2">
      {icons.map((iconName) => {
        const Icon = TABLET_ICONS[iconName];
        const active = value === iconName;
        return (
          <button
            aria-label={iconName}
            className={`relative flex h-14 w-14 items-center justify-center border-2 transition-colors ${
              active
                ? "border-[#EF2B2D] bg-[#EF2B2D] text-[#0A0A0A]"
                : "border-[#262626] bg-[#0A0A0A] hover:border-[#EF2B2D]"
            }`}
            data-testid={`settings-tablet-icon-${iconName}`}
            key={iconName}
            onClick={() => onPick(iconName)}
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
  );
}
