// Category labels + icons for the tablet's category picker, shared with the
// admin "Catégories combinées" card so both show the same names and icons.
import {
  Baby,
  Beef,
  CakeSlice,
  Coffee,
  Cookie,
  Croissant,
  CupSoda,
  Drumstick,
  Fish,
  Flame,
  Hamburger,
  IceCreamCone,
  Pizza,
  Popcorn,
  Salad,
  Sandwich,
  Soup,
  Sparkles,
  Star,
  UtensilsCrossed,
} from "lucide-react";

// Key used in tablet_category_overrides for the "Composer un Tacos" button,
// which sits in the same bar as the categories.
export const TACOS_BUILDER_KEY = "tacos-builder";

export const CATEGORY_LABELS = {
  [TACOS_BUILDER_KEY]: "Composer un Tacos",
  signatures: "Signatures",
  classiques: "Les classiques",
  "smash-burgers": "Smash burgers",
  kids: "Enfants",
  sides: "Accompagnements",
  sandwiches: "Sandwichs",
  drinks: "Boissons",
  desserts: "Desserts",
  wraps: "Wraps",
};

// Icon choices for merged categories, stored in settings by name.
export const TABLET_ICONS = {
  Hamburger,
  Flame,
  Sandwich,
  Salad,
  Drumstick,
  Beef,
  Pizza,
  Fish,
  Popcorn,
  Soup,
  Baby,
  CupSoda,
  Coffee,
  CakeSlice,
  IceCreamCone,
  Croissant,
  Cookie,
  Star,
  Sparkles,
  UtensilsCrossed,
};

export const CATEGORY_ICON_NAMES = {
  [TACOS_BUILDER_KEY]: "UtensilsCrossed",
  signatures: "Hamburger",
  classiques: "Hamburger",
  "smash-burgers": "Flame",
  kids: "Baby",
  sides: "Popcorn",
  sandwiches: "Sandwich",
  drinks: "CupSoda",
  desserts: "CakeSlice",
  wraps: "Salad",
};

export const categoryLabel = (slug) => CATEGORY_LABELS[slug] || slug.replaceAll("-", " ");

export const categoryIcon = (slug) => TABLET_ICONS[CATEGORY_ICON_NAMES[slug]] || Cookie;

/** Name + icon the tablet shows for one category (or the tacos button),
 * honouring the admin's renames in `tablet_category_overrides`. */
export function tabletCategoryDisplay(slug, overrides) {
  const o = (overrides || {})[slug] || {};
  return {
    label: (o.name || "").trim() || categoryLabel(slug),
    Icon: TABLET_ICONS[o.icon] || categoryIcon(slug),
  };
}

export const groupIcon = (group) => TABLET_ICONS[group?.icon] || Cookie;

/** Icons for a merged category: `suggested` are the icons of the categories
 * being merged, `others` every other available icon. */
export function suggestedIconNames(slugs, overrides) {
  const iconOf = (slug) => (overrides || {})[slug]?.icon || CATEGORY_ICON_NAMES[slug];
  const suggested = [...new Set(slugs.map(iconOf).filter((name) => TABLET_ICONS[name]))];
  const others = Object.keys(TABLET_ICONS).filter((name) => !suggested.includes(name));
  return { suggested, others };
}

/** Tabs for the tablet's category picker: each merged group replaces its
 * member categories, as one tab placed where its first member was. */
export function buildTabletTabs(categories, groups, overrides) {
  const valid = (groups || []).filter((g) => (g.categories || []).length > 0);
  const tabs = [];
  const seenGroups = new Set();
  for (const slug of categories) {
    const group = valid.find((g) => g.categories.includes(slug));
    if (!group) {
      tabs.push({ key: slug, ...tabletCategoryDisplay(slug, overrides), categories: [slug] });
    } else if (!seenGroups.has(group.id)) {
      seenGroups.add(group.id);
      tabs.push({
        key: `group:${group.id}`,
        label: group.name,
        Icon: groupIcon(group),
        categories: group.categories,
      });
    }
  }
  return tabs;
}
