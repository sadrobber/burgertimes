// Country calling codes for the checkout phone field.
// Order: Monaco, Italie, États-Unis pinned first (core local audience for a
// Beausoleil restaurant on the Monaco/Italy border + English-speaking
// tourists), then everything else in normal French alphabetical order.
// Flags are derived from the ISO-3166-1 alpha-2 code so we never hand-type
// emoji (each letter -> a Unicode regional-indicator symbol).
function flagFromIso(iso2) {
  return iso2
    .toUpperCase()
    .replace(/./g, (c) => String.fromCodePoint(0x1f1e6 + (c.charCodeAt(0) - 65)));
}

const RAW = [
  // --- pinned first ---
  { name: "Monaco", iso: "MC", dial: "+377" },
  { name: "Italie", iso: "IT", dial: "+39" },
  { name: "États-Unis", iso: "US", dial: "+1" },
  // --- rest, alphabetical (French) ---
  { name: "Allemagne", iso: "DE", dial: "+49" },
  { name: "Andorre", iso: "AD", dial: "+376" },
  { name: "Autriche", iso: "AT", dial: "+43" },
  { name: "Belgique", iso: "BE", dial: "+32" },
  { name: "Canada", iso: "CA", dial: "+1" },
  { name: "Chine", iso: "CN", dial: "+86" },
  { name: "Danemark", iso: "DK", dial: "+45" },
  { name: "Espagne", iso: "ES", dial: "+34" },
  { name: "Finlande", iso: "FI", dial: "+358" },
  { name: "France", iso: "FR", dial: "+33" },
  { name: "Grèce", iso: "GR", dial: "+30" },
  { name: "Irlande", iso: "IE", dial: "+353" },
  { name: "Islande", iso: "IS", dial: "+354" },
  { name: "Japon", iso: "JP", dial: "+81" },
  { name: "Liechtenstein", iso: "LI", dial: "+423" },
  { name: "Luxembourg", iso: "LU", dial: "+352" },
  { name: "Malte", iso: "MT", dial: "+356" },
  { name: "Maroc", iso: "MA", dial: "+212" },
  { name: "Norvège", iso: "NO", dial: "+47" },
  { name: "Pays-Bas", iso: "NL", dial: "+31" },
  { name: "Pologne", iso: "PL", dial: "+48" },
  { name: "Portugal", iso: "PT", dial: "+351" },
  { name: "Roumanie", iso: "RO", dial: "+40" },
  { name: "Royaume-Uni", iso: "GB", dial: "+44" },
  { name: "Russie", iso: "RU", dial: "+7" },
  { name: "Saint-Marin", iso: "SM", dial: "+378" },
  { name: "Suède", iso: "SE", dial: "+46" },
  { name: "Suisse", iso: "CH", dial: "+41" },
  { name: "Tunisie", iso: "TN", dial: "+216" },
  { name: "Turquie", iso: "TR", dial: "+90" },
  { name: "Ukraine", iso: "UA", dial: "+380" },
];

export const COUNTRY_CODES = RAW.map((c) => ({ ...c, flag: flagFromIso(c.iso) }));

export const DEFAULT_COUNTRY_ISO = "FR";

export function findCountry(iso) {
  return COUNTRY_CODES.find((c) => c.iso === iso) || COUNTRY_CODES.find((c) => c.iso === DEFAULT_COUNTRY_ISO);
}
