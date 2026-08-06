# Burger Times · PRD

## Original problem statement
Build a food-ordering website for **Burger Times** (Instagram: `@burgertimes_bsl`, phone: `04.97.07.17.93`, address: `6 Avenue de Villaine, 06240 Beausoleil`). Bold red-and-black brutalist visual identity, `BT-` order-number prefix, custom **Tacos Builder** (1/2/3 meats · sauces · supplements · replaces the initial burger builder), plus standard menu formulas and drinks. Bilingual FR/EN, pay-on-arrival only, Telegram + Resend integrations, admin dashboard. **Production domain:** `https://burgertimes.fr`.

## Architecture
- **Backend**: FastAPI + Motor/MongoDB (UUID string PKs, UTC ISO 8601 timestamps). Routes prefixed with `/api`. JWT + bcrypt admin auth (24 h token). Server-side pricing engine (`pricing.py`, `order_service.py`). Restaurant status engine (`restaurant_status.py`, `Europe/Paris` tz). Telegram + Resend services safe when env vars unset. **Idempotent seed** now loads reference data (categories, menu items, sauces, tacos builder) from `backend/seed_data/*.json` on every startup — critical because preview and production have separate Mongo databases.
- **Frontend**: React 19 + React Router v6 + Tailwind + shadcn/ui. Context: `I18nContext` (FR/EN), `CartContext`, `AdminAuthContext`. Two axios instances in `lib/api.js`. Framer-motion for animations. Sonner for toasts.
- **Design**: brutalist street-food — `Anton`/`Bebas Neue` display, `Outfit` body, `Permanent Marker` accents. Signal red `#EF2B2D` on near-black `#0A0A0A`, off-white `#F5F1E8`. Hard offset shadows, thick borders, halftone dots, grain overlay, `rounded-none` everywhere.

## User personas
- **Customer**: mobile visitor from Beausoleil / Monaco area, browses menu, builds a tacos, chooses pickup or delivery, pays cash or card on site.
- **Owner / kitchen staff**: signs into `/admin`, manages orders, edits menu, tweaks opening hours, receives Telegram tickets.

## Core requirements
- Order flow: Home → Menu → configure items → Cart → Checkout → Success.
- Pay-on-arrival only (`cash` or `card_in_person`).
- Tacos builder with size-based pricing (1/2/3 meats), sauces & supplements.
- Restaurant status engine returns `open|closing_soon|closed`. Backend blocks `/api/checkout/session` (HTTP 423) when closed. Closed-state hero with live countdown + waitlist capture.
- Bilingual (FR/EN) via lightweight `I18nContext`.
- Admin: dashboard metrics, orders (accept/preparing/ready/delivered/cancel + hard delete), menu CRUD w/ images, categories CRUD, tacos builder CRUD, sauces, reviews approval, settings (hours, cutoff, ETA, % delivery fee, sodas, force_closed, too_busy, payment toggles, order limits, delivery postal codes).
- Order display IDs prefixed with `BT-`. Pickup orders get 4-digit `pickup_code`.

## Implemented (2026-02-XX)
- **Fixed NEW badge** (2026-02-XX): the user-attached PNG had NO fully-transparent pixels (every corner was `rgba(0,0,0,128)` — half-opaque black), so the badge rendered as a dark rectangle covering food photos. Post-processed the alpha channel (`alpha < 240 → 0`, rest → 255), cropped to bounding box, saved as `/app/frontend/public/new-badge.png` (481×465, 160 KB, 36 % transparent, 51 % fully opaque). Also shrank badge from 64/80 px → 48/56 px and repositioned to `-top-2 -right-2` so it sits like a stamp on the corner instead of occupying image real estate.
- **"Mark as new" per menu item** (2026-02-XX): added `is_new` field to `MenuItem` / `MenuItemCreate` / `MenuItemUpdate` (default `false`, admin toggles via a **Nouveau** checkbox in the item edit modal at `/admin/menu`). When `is_new=true` the customer menu card shows the red starburst NEW badge stamped on the top-right corner of the image.
- Full backend + frontend brutalist theme, tacos builder, checkout, admin dashboard (all 8 pages).
- Payment toggles (cash/card), daily/weekly order limits, percentage delivery fee, delivery postal-code allowlist.
- Closed-state hero with buttery-smooth live countdown (framer-motion) + waitlist email capture.
- **Telegram** kitchen bot integration (`@BurgerTimes_bot`, live) with inline accept/ready/cancel buttons.
- **Resend** email integration **direct API** (2026-02-XX): uses owner's own Resend API key sending from verified custom domain `orders@burgertimes.fr` (order confirmations, waitlist blasts, auto-notify on closed → open transition via Emergent Cron). Domain verified in Resend eu-west-1. Test send succeeded (message id af6e11ad-89b6-48e8-b58a-b350f1bf2411).
- Full menu seeded (40 items across Signatures / Classiques / Smash / Wraps / Sandwiches / Tex Mex-Sides / Kids / Desserts / Drinks) + 12 sauces + 6 meats + 6 supplements + tacos sizes 1/2/3.
- **Auto-seed of full menu data on every backend startup** (2026-02-XX): `backend/seed.py` now loads `categories.json`, `menu_items.json`, `sauces.json`, `burger_styles.json`, `burger_sizes.json`, `burger_meats.json`, `burger_supplements.json` from `backend/seed_data/`. Idempotent (matched by id/slug, never overwrites edits). This ensures fresh production deploys come up with the full menu already loaded.
- **Admin force-reseed (Zone rouge)** (2026-02-XX): `POST /api/admin/seed/reseed` wipes and re-inserts every reference collection from the shipped JSON files AND resets `hours_per_day`, `delivery_fee_percent=10`, `free_delivery_threshold=30`, `delivery_postal_codes=[]` on the settings singleton. Surfaced as a red-bordered "Zone rouge" panel at the bottom of `/admin/settings` (`data-testid="settings-force-reseed"`). Orders, admin users, and waitlist are untouched.
- **Delivery-fee quote fix** (2026-02-XX): `_quote_or_create` in `server.py` used to hard-reject any delivery quote missing an address, which meant the checkout page never displayed the delivery-fee line to customers before they typed a full address. Address requirement is now gated on `create=True` only; quotes always compute the fee.

## P1 backlog (upcoming)
- **Live Order Sound** — play a ping + flash the admin dashboard when a fresh order lands.
- **Kitchen Print Ticket** — thermal-printer-friendly ticket in the admin order drawer.

## Hardened — Fail-fast DB + /api/health diagnostic (2026-02-XX)
- Set explicit Motor timeouts on the Mongo client: `serverSelectionTimeoutMS=4000, connectTimeoutMS=4000, socketTimeoutMS=8000`. Prior default was 30s — any broken `MONGO_URL` used to look like a 504 gateway timeout to the customer. Now it fails fast with a real error.
- Wrapped `run_seed(db)` in `asyncio.wait_for(..., timeout=12s)` so the app boots even if Mongo is unreachable at startup (logs a clear error instead of crash-looping).
- New public endpoint `GET /api/health` returns a snapshot of Mongo reachability (`mongo: ok | unreachable | error`), `menu_items_count`, and the `integrations` block showing which env vars are configured in the current environment (`resend_configured`, `telegram_bot_configured`, etc.). This is the one-shot production diagnostic — hit `https://www.burgertimes.fr/api/health` any time to see exactly what's missing.

## Fixed — Sticky nav layout (2026-02-XX)
- Sticky category chip strip on `/menu` now uses `md:flex-wrap md:justify-center` (no forced `flex-1`), so chips take their natural width and center-align on desktop/tablet, wrapping to a 2nd centered row only when the viewport genuinely can't hold them all. On mobile the strip still scrolls horizontally with `.no-scrollbar`.
- Screenshots + testing agent verify zero chip overlap at 1440 / 900 / 375, all 9 chips render at every viewport, scrollspy still highlights the correct chip on scroll.

## Implemented — Vertical menu with scrollspy + Tacos Builder card (2026-02-XX)
- `/menu` no longer filters to a single category. All visible categories are rendered as stacked sections with `[data-testid="section-{slug}"]` anchors and a big red slug + French heading.
- A sticky red-bordered category strip lives directly under the site header (`top-16 md:top-20`), with one chip per visible category. Chips smooth-scroll to their section on click and light up automatically via IntersectionObserver as the visitor scrolls (rootMargin `-40% 0px -40% 0px`).
- The **Tacos Builder** is now shown as a menu-item-shaped card (`TacosBuilderCard.jsx`, `data-testid="menu-item-tacos-builder"`) inline at the top of the first visible category (Signatures). It has a real tacos photo from Unsplash with a graceful "BT" halftone fallback, a "Nouveau" ribbon + "Sur mesure" price pill, and both the card and its button open the existing builder modal (`data-testid="open-burger-builder"`).
- Removed the old big red "Sur mesure · Compose ton Tacos" CTA banner that used to sit above the menu.

## Fixed — Resend key rotation (2026-02-XX)
- Previous `RESEND_API_KEY` (`re_2xiY...jgt`) was revoked on Resend's side (raw curl returned 401 "API key is invalid"). User provided fresh key `re_B5bcMqLa_...QJ`, updated in `/app/backend/.env` and applied via `sudo supervisorctl restart backend`. Order-confirmation + status-update emails now return HTTP 200 from api.resend.com and log 'Resend email sent to ...' — verified by testing agent iteration_8 (30/30 backend tests pass, no 401s in logs).
- Hardened `load_dotenv(ROOT_DIR / '.env', override=True)` in `server.py` so future env rotations survive a WatchFiles hot-reload without a supervisor restart.

## Implemented — Menu polish & auto scroll-to-top (2026-02-XX)
- Removed the "Tous" chip and any empty categories (like the legacy `burgers`) from the customer menu at `/menu`. Category chips are filtered to only those with at least one menu item so future stale categories stay hidden automatically. Default active tab is now the first real category (Signatures) so items are visible immediately.
- New `ScrollToTop` component mounted inside `<BrowserRouter>` — every route change fires `window.scrollTo({top:0})` instantly, so navigating from any page to `/menu` lands the visitor on the **Compose ton Tacos** CTA.

## Implemented — Delivery-fee analytics (2026-02-XX)
- New backend endpoint `GET /api/admin/stats/delivery-fees?days=N` (default 30, 1-365). Aggregates orders where `fulfillment='delivery'` and `status ∉ {cancelled, expired}` in the restaurant's local tz (`Europe/Paris`). Returns `totals` + `counts` + `subtotals` for {today, this_week, this_month, all_time, in_range} plus a `daily` array (every day in the range, zero-filled for gap-free charting).
- New admin page `/admin/stats/delivery` (`DeliveryStatsAdmin.jsx`) with: range picker chips (7d / 14d / 30d / 90d / 1y), 4 KPI cards, 3 summary tiles (period fees / period subtotal / avg fee per delivery), a **recharts** bar chart of fees per day, and a chronological daily journal table. Uses the existing brutalist theme.
- Nav link **Livraisons** (`Truck` icon) added to `AdminLayout.jsx` between Commandes and Menu (`data-testid="admin-nav-delivery-stats"`).

## P2 backlog
- Admin sortable / drag-reorder for menu & categories.
- Loyalty / punch-card repeat-customer perk.
- Analytics: hourly heatmap + top items.
- PWA install + push notifications.
- Rename `BurgerBuilder*` components → `TacosBuilder*` (cosmetic).

## Notes
- Admin owner email: `chahineisgoated@gmail.com` (password in `/app/memory/test_credentials.md`).
- Language: user speaks English; UI labels in French.
- Emergent Emails uses managed proxy — do NOT switch to plain Resend SDK.
