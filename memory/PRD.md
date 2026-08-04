# Burger Times · PRD

## Original problem statement
Build a food-ordering website for **Burger Times** (Instagram: `@burgertimes_bsl`, phone: `04.97.07.17.93`, address: `6 Avenue de Villaine, 06240 Beausoleil`). Bold red-and-black visual identity, `BT-` order-number prefix, custom smash-burger builder (`burger_*` collections: styles, sizes, meats, cheeses, supplements), plus standard menu formulas and drinks. Bilingual FR/EN, pay-on-arrival only, Telegram + Resend integrations (wired but currently unconfigured), admin dashboard.

## Architecture
- **Backend**: FastAPI + Motor/MongoDB (UUID string PKs, UTC ISO 8601 timestamps). Routes prefixed with `/api`. JWT + bcrypt admin auth (24h token, `Bearer` in `Authorization` header). Server-side pricing engine (`pricing.py`, `order_service.py`). Restaurant status engine (`restaurant_status.py`, `Europe/Paris` tz). Telegram + Resend services safe when env vars are unset (`telegram_service.py`, `email_service.py`). Idempotent seed (`seed.py`) on startup: creates admin user + settings singleton + default categories.
- **Frontend**: React 19 + React Router v6 + Tailwind + shadcn/ui. Context: `I18nContext` (FR/EN, `bt_lang`), `CartContext` (localStorage `bt_cart_v1`), `AdminAuthContext` (`bt_admin_token`). Two axios instances in `lib/api.js`: `apiClient` and `adminClient` (auto-inject Bearer, redirect to `/admin/login` on 401). Framer-motion for staggered menu reveal & hero. Sonner for toasts.
- **Design**: brutalist street-food theme — `Anton`/`Bebas Neue` display, `Outfit` body, `Permanent Marker` for hand-scrawled tags. Signal red `#EF2B2D` on near-black `#0A0A0A` off-white `#F5F1E8`. Hard offset shadows, thick borders, halftone dots, grain overlay. `rounded-none` everywhere.

## User personas
- **Customer**: mobile visitor from Beausoleil / Monaco area, browses menu, builds a burger, chooses pickup or delivery, pays cash or card on site.
- **Owner / kitchen staff**: signs into `/admin`, manages orders, edits menu, tweaks opening hours, syncs Telegram webhook.

## Core requirements (static)
- Order flow: Home → Menu → configure items → Cart → Checkout → Success.
- Pay-on-arrival only (`cash` or `card_in_person`).
- Burger builder with flat-price + variable-price styles, meat count constrained by size or style.max_meats.
- Restaurant status engine returns `open|closing_soon|closed`. Backend enforces via HTTP 423 on `/api/checkout/session` when closed.
- Bilingual (FR/EN) via lightweight custom `I18nContext`.
- Admin: dashboard metrics, orders (accept/preparing/ready/delivered/cancel + hard delete), menu CRUD w/ images, categories CRUD, burger builder CRUD, sauces, reviews approval, settings (hours, cutoff, ETA, delivery fee, sodas, force_closed, too_busy).
- Order display IDs prefixed with `BT-`.
- Pickup orders get a 4-digit `pickup_code`.

## Implemented (2026-02-XX)
- Full backend: models, pricing engine, order service, seed, restaurant status, JWT auth, Telegram/Resend services, admin + public routes.
- Full frontend: brutalist red/black theme, Home hero, Menu grid + burger builder modal, Cart, Checkout (with server-side quote), Order Success with pickup code, admin login + layout + all 8 admin pages.
- Admin seeded with the owner email `chahineisgoated@gmail.com` (password in `/app/memory/test_credentials.md`).

## Deferred / P0 backlog
- Telegram bot token + kitchen chat ID (user asked to skip; wiring is in place — set env vars + click "Sync Telegram Webhook" in admin Settings).
- Resend API key + verified sender domain (skipped by user).
- Menu content seeding (user opted to enter items from admin).
- Optional: seeded burger builder starter kit (styles/sizes/meats).

## P1 backlog / next tasks
- Admin sortable / drag-reorder for menu & categories.
- Order-print or receipt view.
- Loyalty / punch-card style repeat-customer perk.
- Analytics: hourly heatmap + top items.
- PWA install + push notifications.
