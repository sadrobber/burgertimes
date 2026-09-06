# Prompt — Build a food-ordering website (any cuisine)

Paste this whole document to your AI builder. It describes **only how the site and menu work** — no design, no branding, no theme. Your AI is free to invent all visual identity for the new restaurant.

---

## 0. Scope

Build a **mobile-first customer-facing site + admin dashboard** for a food-ordering business.

Customer flow: **Home → Menu → configure items → Cart → Checkout → Success**
Payment: **PAY-ON-ARRIVAL ONLY** — `cash` or `card_in_person`. **No online payment provider whatsoever** (no Stripe, no Apple Pay, no PayPal).
Notifications: **Resend** transactional emails to the customer, plus a dedicated **`/kitchen` tablet dashboard** for order intake — a protected, polling-based screen the kitchen staff keeps open on an Android tablet, with audio alerts for new orders and thermal-receipt printing (see §7). No chat-bot integration needed.
Admin: full CRUD on the menu, categories, item builders, orders (with Accept / Preparing / Ready / Cancel actions), settings (opening hours, ETA, cutoff, delivery fee, etc.).
Bilingual FR + EN (custom lightweight i18n context).

---

## 1. Tech stack (non-negotiable)

**Backend**
- FastAPI (Python 3.11+), Motor for MongoDB
- Pydantic v2 for models & responses
- httpx for outbound HTTP
- bcrypt + PyJWT for admin/kitchen auth
- timezone-aware datetimes (`datetime.now(timezone.utc)`)
- **UUID strings** for every primary key — never Mongo ObjectId

**Frontend**
- React 18 + React Router v6
- Tailwind CSS + shadcn/ui primitives (from `@/components/ui/*`)
- Context API for cart + i18n
- framer-motion for micro-animations
- lucide-react for icons (never emojis in UI chrome)
- sonner for toasts
- axios with **one** `apiClient` (`baseURL = REACT_APP_BACKEND_URL + "/api"`) and a separate `adminClient` (and, if you build the kitchen dashboard, a third `kitchenClient`) that injects `Authorization: Bearer <token>` from `localStorage` using its own token key — the admin token and kitchen token must never be interchangeable.

**Environment variables (never hardcode)**
- `REACT_APP_BACKEND_URL` (frontend, no trailing `/api`)
- `MONGO_URL`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL` (verified sender)
- `ADMIN_JWT_SECRET`
- `KITCHEN_JWT_SECRET` (if the kitchen dashboard uses a distinct secret from admin — or reuse `ADMIN_JWT_SECRET` and distinguish purely by a `role` claim in the token payload; either works, just be consistent and check the role server-side on every kitchen route)

**Routing rules (deployment breaks otherwise)**
- Every backend route prefixed with `/api`. Ingress typically routes `/api/*` → backend, everything else → frontend.
- Backend binds `0.0.0.0:8001`. Frontend calls `${REACT_APP_BACKEND_URL}/api/...`.
- Run services under a process manager (supervisor / pm2 / docker) — never launch `python server.py` directly.
- Expose a **bare, unprefixed `GET /health`** route directly on the FastAPI `app` (not the `/api`-prefixed router) that returns instantly with zero DB calls (e.g. `{"status": "ok"}`). Most Kubernetes-based deploy platforms send liveness/readiness probes straight to the container's port, bypassing the `/api` ingress prefix entirely — if the only health route you have is `/api/health`, the platform's probe 404s and can flag/kill the deployment even though the app itself is running fine. Keep a separate, deeper `/api/health` (Mongo ping, sanity counts) for your own debugging; the bare `/health` must stay fast and dependency-free so a transient DB blip never fails the probe.

---

## 2. Data model (MongoDB)

All primary keys are `str(uuid.uuid4())` stored as field `id`. All timestamps are UTC ISO 8601 strings from `datetime.now(timezone.utc).isoformat()`.

### `admin_users`
`{ id, email (unique), password_hash, role="admin", created_at }`

### `kitchen_users` (separate role, separate login surface)
`{ id, email (unique), password_hash, role="kitchen", created_at }`
Keep this in its own collection (or the same collection distinguished by `role`) but ALWAYS check the `role` claim server-side on every `/api/kitchen/*` and `/api/admin/*` route — a kitchen token must never unlock admin routes, and an admin token should not silently work on kitchen routes either (separate `require_admin` / `require_kitchen` dependencies).

### `categories`
`{ id, slug (unique), label ({fr,en} or string), sort_order, active }`

### `menu_items`
```
{ id, name, description, category (slug),
  price_seul,                             # base "à la carte" price
  price_menu (nullable),                  # optional upcharge for a "menu / combo" variant that adds a drink
  formats: [{name, price_seul, price_menu}]   # optional per-item variants (e.g. Normal / Extra / Grilled)
  variants: [str]                         # legacy free-form list; usually superseded by uses_soda_flavours
  uses_soda_flavours: bool                # true → the item's drink options come from settings.soda_flavours (single global list)
  available: bool,
  sort_order, created_at, updated_at }
```
Image storage: never inline `image_base64` in list responses. Expose `GET /api/menu/{id}/image` returning raw bytes.

### `settings` (singleton at id="singleton")
```
{ id: "singleton",
  is_open: bool,                          # global override
  force_closed: bool,                     # manual "closed today" toggle
  closed_message: str,
  timezone: "Europe/Paris",               # or whatever
  hours_per_day: {
    mon: { is_open, ranges: [{ open: "HH:MM", close: "HH:MM" }] },
    tue: {...}, ..., sun: {...}
  },
  last_order_buffer_minutes: 15,          # kitchen cutoff BEFORE closing
  closing_soon_window_minutes: 30,        # UI banner window
  delivery_cutoff_minutes: 0,             # 0=disabled. If >0, DELIVERY stops N min before close while pickup stays open until the normal cutoff — see §5b
  too_busy: bool,
  too_busy_eta_min, too_busy_eta_max,
  eta_default_min, eta_default_max,
  soda_flavours: [str],                   # single global list for uses_soda_flavours items
  delivery_fee: 3.0,
  free_delivery_threshold: nullable,
  contact_phone, contact_address,
  updated_at }
```

### `sauces` (optional per-item selector)
`{ id, name, sort_order, active }`

### Customizable-item-builders (generic pattern — reuse for burgers, bowls, pizzas, sandwiches, tacos, anything)
Each **builder family** is 5 admin-managed collections + a singleton for kids-style flat-price mini-menus. Example for a "tacos" builder:
- `tacos_styles`   `{ id, name, description, price_modifier, flat_price?, flat_price_menu?, max_meats?, image_base64?, available, sort_order }`
- `tacos_sizes`    `{ id, code, label, price_simple, price_menu, nb_meats, supplement_upcharge, gratinage_price, available, sort_order }`
- `tacos_meats`    `{ id, name, base_price, available, sort_order }`
- `tacos_supplements` `{ id, name, base_price, available, sort_order }`
- `tacos_gratinages` `{ id, name, available, sort_order }` (single-choice optional extra)

Pricing formula (server-side, in `pricing.py`):
```
if style.flat_price is set:
   base = style.flat_price_menu if formula=="menu" and flat_price_menu else style.flat_price
   allowed_meats = style.max_meats
   size step is SKIPPED on the frontend, size_id can be null on the payload
else:
   base = size.price_menu if formula=="menu" else size.price_simple
   allowed_meats = size.nb_meats
total = base + style.price_modifier + sum(supplement.base_price + size.supplement_upcharge for supplement in supplements) + (size.gratinage_price if gratinage else 0)
```
Validate: `len(meat_ids) == allowed_meats` — reject otherwise.

Rename `tacos_*` collections to whatever fits the new business (e.g. `bowl_*`, `pizza_*`).

### `kids_menu` (singleton at id="singleton") — flat-price mini-menu template
```
{ id: "singleton",
  base_price: 8.0,
  included_sides_label: "Free-form text shown to customer + kitchen",
  mains:    [ { id: "main_a", name, image_base64 }, ... ],   # ~2-4 options
  desserts: [ { id: "dessert_a", name, image_base64 }, ... ],
  updated_at }
```
Option IDs (`main_a`, `main_b`, `dessert_a`, `dessert_b`) are **stable** — even if the admin renames, historical orders keep their snapshotted names.
Image storage: inline base64 is OK here because ≤ 4 images and admin edits are frequent → simpler than dedicated endpoints.

### `orders`
```
{ id, order_number: "AB-XXXXXX",                # short display id, prefix your choice
  items: [ OrderItemSnapshot ],                 # server-built, never trust client price
  subtotal, delivery_fee, total,
  fulfillment: "delivery" | "pickup",
  customer_first_name, customer_last_name, customer_email,
  customer_phone,                               # NATIONAL number ONLY — no country code, no leading '+'
  customer_phone_country_code,                  # e.g. "+33" — stored separately, see §10b
  customer_phone_country_name,                  # e.g. "France" — denormalized for display
  customer_phone_country_flag,                  # e.g. "🇫🇷" — denormalized for display
  address_line1, address_line2, postal_code, city,
  notes: str,                                   # if starts with "[TEST ORDER]" → banner on the kitchen dashboard, stripped from display
  payment_method: "cash" | "card_in_person",
  payment_status: "cash_pending" | "card_pending_in_person" | "unpaid",
  status: "pending" | "accepted" | "preparing" | "ready" | "delivering" | "delivered" | "cancelled" | "expired",
  pickup_code: "1234",                          # only for fulfillment=pickup, 4 digits
  kitchen_print_status: "unprinted" | "printed", printed_at,   # best-effort telemetry only, see §7 — NEVER gates order status
  accepted_by, status_history: [{status, at, actor, note}],
  on_hold: bool, hold_minutes: int|null, hold_until: iso|null, hold_set_by: str|null,   # kitchen "put on hold" — see §7b
  test_order: bool,
  created_at, updated_at }
```

### `OrderItemSnapshot` (embedded)
```
{ line_id (frontend-generated), name (display, server-built),
  item_id (null for builder items and flat-price mini-menus),
  is_tacos: bool, tacos_config: {...},              # or is_bowl, is_pizza, etc.
  is_kids_menu: bool, kids_menu_config: {main_id, dessert_id, main_name, dessert_name, included_sides_label},
  formula: "seul" | "menu" | "menu_enfant" | ...,
  quantity, unit_price, line_total,
  sauces: [str], included_drink, included_drink_variant,
  selected_format, selected_variant, notes }
```

### `reviews` (optional)
`{ id, author_name, rating (1-5), comment, approved, created_at }`

---

## 3. Backend routes (all under `/api`)

**Auth**
- `POST /api/admin/login` → `{ token, admin: { email } }` (JWT, 24h)
- `POST /api/kitchen/login` → `{ token, kitchen: { email } }` (JWT, separate role claim)
- Dependencies `require_admin` / `require_kitchen` verify `Authorization: Bearer <token>` and the token's `role` claim — never share one dependency for both.

**Public**
- `GET /api/menu` — available items only (unavailable items filtered server-side)
- `GET /api/menu/{id}/image` — raw bytes, proper `Content-Type`
- `GET /api/categories`
- `GET /api/sauces`
- `GET /api/<builder>/config` — returns styles/sizes/meats/supplements/gratinages
- `GET /api/kids-menu` — full singleton (base_price, sides label, mains, desserts, images inline)
- `GET /api/restaurant/status` — returns 3-state opening status (see §5)
- `GET /api/settings` (public read; admin PUT)
- `GET /api/reviews` — approved only

**Checkout / Orders (public)**
- `POST /api/checkout/quote` — server-computes totals from cart items, no order created
- `POST /api/checkout/session` — creates order **immediately** (no online payment). Returns `{url, session_id: null, order_id, order_number, payment_method}`. `url` is `<origin>/order/success?order_id=<id>`.
- `GET /api/orders/lookup/{order_id}` — public safe subset (strip admin-only fields)

**Admin**
- `GET /api/orders?status=&customer_email=&limit=` — `customer_email` filter (exact, case-insensitive) powers the client-orders drawer, see §9b
- `GET /api/orders/{id}`
- `PUT /api/orders/{id}/status { status }`
- `DELETE /api/orders/{id}` — permanent hard delete (for scrubbing test orders that skew dashboard stats)
- `PUT /api/settings`
- Full CRUD on: `menu_items`, `categories`, `sauces`, `reviews`, `<builder>/*`
- `PUT /api/admin/kids-menu` — partial update (base_price, included_sides_label, mains, desserts)
- `GET /api/admin/stats` — dashboard metrics (see §6)
- `GET /api/admin/clients` — aggregates `orders` by customer email into one row per customer (see §9b)

**Kitchen (separate role, own JWT — see §7)**
- `GET /api/kitchen/me`
- `GET /api/kitchen/orders` (or reuse the admin `GET /api/orders` with `require_kitchen` on a scoped variant) — polled every ~4s by the dashboard, grouped into New / Accepted / Declined
- `POST /api/kitchen/orders/{id}/accept`
- `POST /api/kitchen/orders/{id}/decline { reason }`
- `POST /api/kitchen/orders/{id}/mark-printed` — best-effort telemetry only (drives a "Printed" badge), never gates order status; call it from the print flow's completion callback, wrapped so a failure here never blocks the kitchen UI

---

## 4. Order flow (end-to-end)

1. Customer builds cart on `/menu`. Cart lives in `localStorage.<prefix>_cart_v1`. Every line has a client-generated `line_id`. **Builder items (tacos, bowl, kids menu, …) always create new lines** — never merge. Normal items merge by `(item_id, formula, selected_format, selected_variant)`.
2. `Checkout.js` collects contact info + `fulfillment` (`delivery`/`pickup`) + `payment_method` (`cash`/`card_in_person`). It maps cart items to the API payload — **explicitly forward every flag/config** (`is_tacos`, `tacos_config`, `is_kids_menu`, `kids_menu_config`, …). Missing them = backend hits the wrong branch = "item_id manquant" errors.
3. `POST /api/checkout/session` calls `_ensure_accepting_orders(settings)` **first** → HTTP 423 if closed/after cutoff/force_closed. Then builds `OrderItemSnapshot` server-side using the pricing engine and item lookups — client prices are ignored.
4. Order inserted with `status='pending'`, `payment_status` set based on method, `pickup_code` (4-digit) generated for pickup orders.
5. Fire-and-forget (`try/except: pass` so an email failure never breaks the order): `send_order_email(order_id, 'order_confirmed')` via Resend. The order is now also immediately visible to the `/kitchen` dashboard on its next poll — no push/webhook needed, see §7.
6. Frontend navigates to `/order/success?order_id=...`. Success page fetches `/api/orders/lookup/{id}` and shows confirmation + pickup code.

**Status transitions (admin/kitchen actions):**
`pending → accepted → preparing → ready → (delivering →) delivered`
`pending → cancelled` at any point. No refund step — pay-on-arrival.

**Kitchen dashboard actions**: Accept / Decline (with reason) on a `pending` order, driven from the polling `/kitchen` screen — see §7 for the full pattern (tabs, audio alerts, printing).

---

## 5. Restaurant status engine (`restaurant_status.py`)

Pure function → 3-state result:
```
{ state: "open" | "closing_soon" | "closed",
  reason: "open" | "closing_soon" | "before_open" | "after_close" | "day_off" | "force_closed" | "after_cutoff",
  now_local_str: "18:34",
  next_open_at_local: "10:30", next_open_at_iso, next_open_day: "today" | "tomorrow" | "Lundi",
  eta_min, eta_max,
  too_busy: bool }
```

Logic:
1. If `settings.force_closed` → closed / `force_closed`.
2. Compute local time in `settings.timezone` (default `Europe/Paris`) via `zoneinfo.ZoneInfo`.
3. Look up `hours_per_day[weekday_key]`. Handle overnight ranges (`close < open` → close is next day).
4. If inside a range but `now + last_order_buffer_minutes >= close` → `after_cutoff` / closed.
5. If inside a range and within `closing_soon_window_minutes` of close → `closing_soon`.
6. Otherwise → open.
7. ETA: if `too_busy` use busy min/max, else default min/max.

Frontend `useRestaurantStatus()` hook polls this every 60s and drives banners on Home + Checkout. **Backend enforces the same rule on `POST /api/checkout/*`** — never trust the client.

Return **HTTP 423 (Locked)** — not 400 or 500 — from `/api/checkout/session` when the restaurant isn't accepting orders, so the frontend can distinguish "bad data" from "closed".

---

## 5b. Fulfillment-specific cutoff (delivery closes earlier than pickup)

A common ops need: stop **delivery** a while before actual closing (deliveries take longer to complete) while **pickup keeps accepting orders** right up to the normal cutoff.

- Add `delivery_cutoff_minutes` to `settings` (0 = disabled).
- `compute_restaurant_status()` computes a SECOND, independent cutoff for delivery only: `delivery_last_order_at = close_time - delivery_cutoff_minutes` (clamped to the range's open time). Expose on the status payload: `delivery_available: bool`, `delivery_last_order_at_local`, `delivery_last_order_at_iso`.
- This is orthogonal to the general `last_order_buffer_minutes` cutoff — the overall restaurant `state` can still be `"open"` (pickup works) while `delivery_available` is `false`.
- **Enforce server-side**: `_ensure_accepting_orders(settings, fulfillment)` raises HTTP 423 with `code: "delivery_unavailable"` if `fulfillment == "delivery"` and `delivery_available` is false — even though the restaurant itself is open.
- **Frontend**: disable the "Delivery" tab at checkout (grey out + tooltip), show an inline banner ("Delivery is closed right now — pickup only"), and auto-switch the customer to pickup with a toast if they had delivery selected when the cutoff hits.
- **Admin UI**: a toggle + amount/unit picker (minutes or hours) under Settings, with a live preview sentence showing the computed cutoff clock time.

---

## 6. Admin dashboard metrics

`GET /api/admin/stats` — for the pay-on-arrival flow:
```
{
  total_orders,        # every row
  paid_orders,         # every order the customer committed to that WASN'T cancelled/expired
  pending_orders,      # in-flight: status in {pending, accepted, preparing, ready, delivering, assigned_driver}
  revenue,             # sum of `total` over paid_orders
  avg_basket           # mean of `total` over paid_orders
}
```
Void statuses = `{cancelled, expired}`. Delete rows via the DELETE endpoint above to scrub test data — no soft-delete.

---

## 7. Kitchen tablet dashboard (order intake, alerts & thermal receipt printing)

A dedicated, protected `/kitchen` screen — separate login from admin — that the kitchen keeps open all day on an Android tablet. It replaces any chat-bot/webhook style notification with a simple polling UI, which is far more reliable across devices and needs zero webhook infrastructure.

**Core pattern**
- `GET /api/kitchen/orders` polled every ~4 seconds. Group results into tabs: **New** (`pending`), **Accepted**, **Declined**.
- Tapping a New order shows Accept / Decline (with a reason). Accept moves it to Accepted and (in the same click) fires the receipt print — see below. Decline requires a reason and moves it to Declined.
- Guard against double-processing: both accept/decline endpoints should be idempotent (accepting an already-accepted order just returns its current state instead of erroring) since staff may double-tap on a slow connection.
- `[TEST ORDER]` in `notes` → show a prominent banner directly on the order card (e.g. "⚠️ TEST ORDER — DO NOT PREPARE") and strip the sentinel from the visible notes text.

**Audio alert loop**
- Do NOT just play a sound once. Use the Web Audio API (or an `<audio>` element) to play a short beep the moment a new order is detected, THEN keep a repeating reminder (e.g. every 15–20s) for as long as there is still at least one unacknowledged (`New`) order. Clear the reminder interval the instant the order list's "New" count drops to zero (accepted or declined).
- Browsers block audio autoplay until a user gesture — gate the very first sound behind an explicit "Enable sound" button the staff taps once at the start of their shift; don't try to autoplay on page load.

**Printing an 80mm thermal receipt — the hard part**

This is the single trickiest piece of the whole dashboard, because kitchen tablets vary wildly in what their browser actually supports. Two device-local approaches work reliably; a vendor cloud-print API generally does not (see the warning below).

1. **RawBT Android app (recommended if you can install one extra app on the tablet)** — RawBT pairs with the thermal printer over Bluetooth/USB once, then any web page can hand it plain text to print via its Android Intent scheme:
   ```js
   function printOrder(receiptText) {
     const intentUrl =
       "intent:" + encodeURIComponent(receiptText) +
       "#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;";
     window.location.href = intentUrl;
   }
   ```
   Build `receiptText` as **plain text** (not HTML) — a simple line-by-line ticket with a dashed divider, item lines, total, customer/delivery block, and payment method. RawBT just spools whatever text it receives straight to the printer.
   **Critical gotcha**: use `encodeURIComponent`, never `encodeURI`. Receipt text almost always contains a literal `#` (e.g. "COMMANDE #AB-1234"), and `encodeURI` deliberately leaves `#` unescaped — which collides with the intent URI's own `#Intent;...;end;` delimiter and silently truncates or corrupts the print job.

2. **Browser-native `window.print()` (no extra app, but has real WebView caveats)** — build the receipt as HTML/CSS sized for 80mm paper. Two failure modes to design around from day one, both confirmed on real Android hardware after passing fine in desktop/headless testing:
   - A hidden `<iframe>` holding the receipt is **not reliably isolated** when you call `iframe.contentWindow.print()` on some Android browsers/WebViews — they rasterize whatever is on the top-level page instead, so you print the whole dashboard, not the receipt.
   - `@media print` CSS rules are **not reliably honoured** either on some of these WebViews — they can behave as if they just screenshot whatever is currently rendered on screen, ignoring print-specific stylesheets entirely.

   The robust fix that sidesteps both failure modes: don't rely on print-media CSS or an iframe at all. Right before calling `window.print()`, **swap what's actually on screen** — toggle a plain (NOT `@media print`-scoped) CSS class on `<html>` that hides the whole app root (and any full-screen decorative overlay) and shows only a receipt container (black text, white background, width matched to the paper, e.g. `76mm` for 80mm stock). Wait one or two `requestAnimationFrame` ticks so the swap actually paints, THEN call `window.print()`. Restore everything on the `afterprint` event, with a generous fallback `setTimeout` (~30s) in case that event never fires on that particular WebView. Because the receipt is the only thing in the visible DOM at the moment of printing, this works regardless of whether the browser respects print-media CSS at all.

3. **Whichever approach you pick, test it on the ACTUAL target tablet/browser before calling the feature done.** Desktop Chrome and headless testing tools will not catch either of the failure modes above — they only surface on real Android hardware.

**Avoid vendor "Cloud Print" APIs unless you have to.** Printer-manufacturer cloud print services usually require binding the specific printer's serial number to a merchant/partner account on the vendor's own portal — this activation step can block progress for days, has no code-level workaround, and is a poor fit for a fast-moving MVP. Prefer the two device-local approaches above; they need no vendor account and no external API calls at all.

---

## 7b. Kitchen "put order on hold" (warn customer of a short delay)

During a rush, the kitchen needs to tell a customer "we're a bit behind" without changing the order's actual status.

- On a **pending** order's card in the `/kitchen` dashboard, add a "⏳ Put on hold" action (kept separate from Accept/Decline).
- Tapping it opens a small duration picker: `5 / 10 / 15 / 20 / 30 min` + a Back option.
- Picking a duration:
  1. Sets `on_hold=true`, `hold_minutes`, `hold_until` (now + minutes), `hold_set_by` on the order.
  2. Shows a banner directly on the card: `⏳ ON HOLD until HH:MM (X min) — high order volume`.
  3. Accept/Decline remain available on a held order — hold never blocks acceptance.
  4. Sends the customer a new email template (`order_on_hold`) explaining the extra X-minute wait, reusing the pickup-code/order-summary blocks from other templates. Send with `force=True` so re-holding (extending the delay) always notifies again.
- Only show the hold banner while `status == "pending"` — once accepted, the delay context is stale and shouldn't linger in the UI.

---

## 8. Resend transactional email

Templates in `email_service.py` (inline-CSS HTML strings, no external deps):
- `order_confirmed` — sent immediately after order creation. Wording differs by `payment_method` (`cash` vs `card_in_person`). Include pickup code for pickup orders.
- `order_accepted` — kitchen accepted
- `order_ready` — pickup ready / driver picking up
- `out_for_delivery`
- `order_cancelled`
- `order_on_hold` — kitchen flagged extra delay (see §7b)

All templates share a wrapper (`_wrap()`) with header + status pill + footer. Format money via `_fmt_eur()`. Include an ETA block on `order_confirmed` from restaurant status. **Every send wrapped in `try/except`** — an email failure never breaks order creation.

Verify the sender domain in Resend BEFORE launch or email will silently bounce.

---

## 9. Admin panel

Sidebar nav:
- Dashboard (metric cards + recent orders + payment-method split — cash vs card-in-person counts/percentages)
- Orders (list + detail modal; status change; **delete button with confirmation dialog**; filters by status + payment method)
- Client List (derived from orders — see §9b)
- Menu (CRUD; sort within category; upload images; search filter; batch "save all" — see §9b)
- Categories (add / rename / reorder / deactivate)
- <Builder(s)> — one page per builder family (styles / sizes / meats / supplements / gratinages)
- Kids-menu-style flat mini-menu editor (if used)
- Sauces
- Reviews (approve / reject)
- Settings (opening hours per weekday, cutoff / closing-soon / too-busy toggles, ETA ranges, global soda flavours list, delivery fee, force_closed toggle)

Every admin action JWT-authenticated. Login at `/admin/login`. Token stored in `localStorage.<prefix>_admin_token`. `adminClient` injects the header. On 401 → redirect to login.

**The kitchen dashboard (`/kitchen`) is a SEPARATE protected surface** — its own login page, its own token key in `localStorage`, its own `require_kitchen` backend dependency. Never let a kitchen account reach `/admin/*` routes, and don't let the admin token double as a kitchen token even though the same person might hold both roles in a small operation.

**Flat mini-menu admin (specific requirements)**:
- Base price (number)
- Included sides / extras label (text)
- N main option rows: image upload + name input
- N dessert / secondary option rows: image upload + name input
- Save → partial-update PUT endpoint
- Reload button (refetch + reset local state)
- **Option IDs (`main_a`, `main_b`, `dessert_a`, `dessert_b`) are STABLE.** Even if admin renames, historical orders keep their snapshot names (denormalized at order-creation time in OrderItemSnapshot).

**Batch-save pattern for list-editor admin pages (Menu, builders, etc.)**:
Instead of persisting every field edit to the server immediately (forcing the admin to open-edit-save-close for each row, one at a time), stage edits client-side and commit them all in one action:
- Local state: `pendingEdits: { [itemId]: payload }` for edited existing rows, `pendingNew: [{ tempId, payload }]` for not-yet-created rows.
- The row's edit dialog writes into these staging maps instead of calling the API — closing the dialog never touches the server.
- Render a badge ("Modified · unsaved" / "New · unsaved") on any staged row, merged into the normal list for live preview.
- A sticky bar appears whenever `pendingCount > 0` with **"Save all (N)"** and **"Discard"** buttons. "Save all" fires the batched `PUT`/`POST` calls in parallel (`Promise.all`), then refetches and clears staging. "Discard" just clears local state.
- Deletes stay immediate (with a confirmation dialog) since they're destructive — only creates/edits are batched.

**Admin list search**: every long admin list (Menu, Clients, Orders) gets a simple client-side text filter input (`data-testid="admin-<page>-search"`) matching name/description/category/email/phone — no backend query param needed for small datasets.

**Client List admin page** (derived — no dedicated `customers` collection needed):
- `GET /api/admin/clients` groups `orders` by lowercased `customer_email` (the one guaranteed field on every order), keeping the MOST RECENT order's name/phone/address (sort by `created_at` desc before grouping) and summing `total` over non-void (`status NOT IN {cancelled, expired}`) orders for lifetime spend + order count.
- Admin page shows: search bar, "total clients" + "lifetime revenue" summary cards, then a list/table sorted by spend desc.
- Clicking the order-count badge opens a drawer (`GET /api/orders?customer_email=...`, returns ALL statuses so staff can also manage cancelled/expired rows) listing every order for that client with a delete icon per row.
- Deleting an order from that drawer calls the same hard-delete endpoint used elsewhere, then updates the client's `order_count`/`total_spent` locally (no full refetch needed) — and removes the client from the list entirely once their count hits zero.

---

## 10. i18n (FR / EN)

Bare-minimum custom context — no external i18next needed:
```js
// context/I18nContext.js
const messages = { fr: {...}, en: {...} };
const I18nContext = createContext();
export function I18nProvider({children}) {
  const [lang, setLang] = useState(() => localStorage.getItem('<prefix>_lang') || 'fr');
  useEffect(() => localStorage.setItem('<prefix>_lang', lang), [lang]);
  const t = (key, fallback='') => messages[lang]?.[key] ?? messages.fr[key] ?? fallback;
  return <I18nContext.Provider value={{lang, setLang, t}}>{children}</I18nContext.Provider>;
}
export const useI18n = () => useContext(I18nContext);
```
Header has an `FR / EN` toggle. All customer-facing strings go through `t()`. Admin panel can stay FR-only (staff will be French).

---

## 10b. Phone number: country code, formatting, validation & "remember me"

**Storage model — split the country code from the number:**
- `customer_phone` stores ONLY the national significant number the customer typed (no `+`, no country code baked in). The dial code, country name, and flag emoji are stored as separate sibling fields (`customer_phone_country_code`, `customer_phone_country_name`, `customer_phone_country_flag`) — this avoids ambiguous parsing later and lets every consumer (kitchen dashboard/receipt, admin, emails) format consistently.

**Country picker (checkout phone field):**
- Build a static list of countries `{ name, iso2, dial_code }` (no need to hand-write ~150 flag emoji — derive the flag from the ISO 3166-1 alpha-2 code programmatically: each letter maps to a Unicode "regional indicator symbol" via `codePointAt(letter) + 127397`, and the two-letter flag is just the two indicator symbols concatenated).
- Order the dropdown with the business's home country pinned first (default selection), then 1-2 neighboring countries the business explicitly wants prioritized, then the rest **A→Z** with a visual separator between the pinned group and the alphabetical list.
- Selected country renders as `flag + dial_code` in the trigger; each option shows `flag + dial_code + full name`.

**Display formatting (never mutate the stored value — format only at render time):**
- Most countries dial domestically with a leading trunk "0" that's dropped in the international `+CC` form (e.g. `+33 7 53 55 66 08` ↔ locally dialed as `07 53 55 66 08`). A small set of countries (NANP: `+1`) do NOT use a trunk zero.
- Formatter: strip non-digits → if the country uses a trunk zero and the number doesn't already start with `0`, prepend `0` → group the result by 2 digits with spaces.
- Implement this ONCE and reuse it everywhere a phone number is displayed: the kitchen dashboard/printed receipt, the admin orders list/detail, and the admin client list. Keep a backend (Python) and frontend (JS) copy that produce **identical** output.

**Completeness validation (reject incomplete numbers before checkout):**
- Maintain a small `{iso2 or dial_code: [minDigits, maxDigits]}` table for the countries you can be precise about (accept the number with OR without the trunk zero, e.g. France `[9, 10]`), and a lenient generic fallback range (e.g. `[6, 15]`) for every other country so you don't false-reject numbers you don't have exact data for.
- Validate on the frontend before allowing submission (inline error / toast: "Please enter a complete phone number.").
- **Mirror the exact same check server-side** in the checkout endpoint(s) and reject with HTTP 400 — a direct API call must not be able to bypass the frontend validation.

**"Remember me" at checkout (client-side only, no auth/accounts needed):**
- A checkbox: "Save my info for next time". On successful order submission, if checked, write `{ first_name, last_name, phone, phone_iso2, address_line1, address_line2, postal_code, city }` to `localStorage` on that device — **never send this anywhere beyond the order itself, and never store the email** (keep the remembered payload minimal/least-privilege).
- On a later visit, if a saved profile exists, show a small prompt inline in the contact section: **"Are you {Name}?"** with Yes/No.
  - Yes → autofill the form (including re-selecting the matching country from the saved `iso2`), and check the "save my info" box (continuing to opt in).
  - No → dismiss the prompt, leave the form empty.
- Checking the box again on a future order simply overwrites the saved profile — that's the entire "update" mechanism, no extra UI needed. Unchecking it leaves any previously saved profile untouched (don't silently delete data the customer didn't ask to remove).

---

## 11. Open Graph / social preview

In `public/index.html`, include a full OG + Twitter-card meta block so links look right on Discord, WhatsApp, iMessage, LinkedIn, Facebook, X, Slack:
```html
<meta property="og:type" content="website" />
<meta property="og:site_name" content="…" />
<meta property="og:locale" content="fr_FR" />
<meta property="og:url" content="https://…/" />
<meta property="og:title" content="…" />
<meta property="og:description" content="…" />
<meta property="og:image" content="https://…/images/preview.jpg" />
<meta property="og:image:secure_url" content="…" />
<meta property="og:image:type" content="image/jpeg" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="…" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="…" />
<meta name="twitter:description" content="…" />
<meta name="twitter:image" content="…" />
```
OG image: 1200×630 JPG, ≤ 300 KB, hosted at `/images/preview.jpg` in `public/`.

---

## 12. Gotchas & lessons learned (READ CAREFULLY — every item cost real bug-hunt time)

1. **Never forward flags implicitly.** When mapping cart → checkout payload, explicitly include every builder flag/config (`is_tacos`, `is_kids_menu`, `is_bowl`, …). Missing them = wrong backend branch = "item_id manquant".
2. **Builder items always create new cart lines.** Never merge two configured items by any hash of their fields. Only plain menu items merge (by `item_id + formula + format + variant`).
3. **Denormalize display names into `OrderItemSnapshot`.** If the admin renames a menu item after an order was placed, historical views must still show the name at time of order. Never fetch live names for old orders.
4. **HTTP 423 for closed restaurant, not 400.** Custom code so the frontend can distinguish "bad payload" from "we're closed" and render the correct UI.
5. **Timezone**: server timestamps in UTC ISO 8601; display conversions in the frontend or in `restaurant_status.py` via `ZoneInfo(settings.timezone)`. Never mix.
6. **No `image_base64` in list endpoints.** Menu list ballooned to ~5MB before we refactored. Only exception: singletons with a bounded number of options (~4 images) → inlining is fine. This isn't just a payload-size annoyance — under concurrent load it can genuinely exhaust a small container's memory (measured multi-MB peak allocation per request on a 40-item menu) and get pods OOMKilled in production. Always project image fields out of any query that isn't serving the image itself.
7. **Hidden-iframe printing is not reliably isolated on Android.** Some Android WebViews / mobile browsers do NOT isolate an `<iframe>`'s content when you call `iframe.contentWindow.print()` — they rasterize whatever is on the top-level page instead, so you end up printing the dashboard, not the receipt. This can pass fine in desktop/headless testing and only fail on the real device. Use the DOM-swap technique from §7 instead, and always do a final verification pass on the actual target hardware.
8. **`.env` doesn't sync to production automatically.** Every managed platform has its own prod env-var settings. Update them separately, then restart.
9. **Availability toggle**: filter unavailable items OUT of `GET /api/menu` **and** block them at checkout with HTTP 400. Frontend filter alone is insufficient — an attacker could POST arbitrary `item_id`.
10. **Server-side price is law.** The `unit_price` field on the frontend is display-only. Backend recomputes from `menu_items` / builder config. Never trust POSTed price.
11. **Idempotent seed.** `seed.py` must be safe to run multiple times. Every insert wrapped in `existing_check → insert only if missing`. Add a **backfill block** for schema evolutions (e.g. when adding `flat_price` to a builder, patch existing rows that don't have it — but only patch when field is missing, so admin overrides survive).
12. **Flat-price builder styles** (e.g. "Bowl = 10 € flat, no size, 1 meat"): the frontend modal must **dynamically skip** the size step, and `size_id` in the payload must be allowed to be null. The V2 pricing engine's "use V2" gate must trigger on `style_id` alone (not `style_id AND size_id`), or flat orders fall through to a legacy path.
13. **`data-testid` everywhere.** Without them, testing agents / QA automation can't drive the app reliably. Kebab-case, role-based (`kids-menu-add-to-cart-button` not `orange-btn-1`).
14. **Test-order banner.** Any order whose `notes` starts with `[TEST ORDER]` gets a `⚠️ TEST ORDER — DO NOT DELIVER` banner directly on its kitchen dashboard card, AND the sentinel is stripped from the visible notes line so it doesn't render twice. Re-usable for ops testing.
15. **RawBT intent encoding gotcha.** When building a RawBT print intent URL (see §7), use `encodeURIComponent(text)`, never `encodeURI(text)` — receipt text almost always contains a `#` (order number), and `encodeURI` deliberately leaves `#` unescaped, colliding with the intent's own `#Intent;scheme=...;end;` delimiter and silently truncating or corrupting the print job.
16. **Admin dashboard metrics after removing online payments.** Any query filtering by `payment_status='paid'` will return 0 forever in a pay-on-arrival system. Redefine "paid" as `status NOT IN {cancelled, expired}` for the stats endpoint.
17. **Deletion + stats coherence.** Provide `DELETE /api/orders/{id}` (admin-only, hard delete) so staff can scrub test orders that would otherwise inflate revenue.
18. **Order snapshot must denormalize builder option labels** (e.g. `kids_menu_config.main_name`, `dessert_name`, `included_sides_label`) at creation time, so renaming an option in admin doesn't rewrite history — but ALSO include a cleanup script that can normalize obviously-stale labels ("Test sides", placeholder values) into current admin values on demand.
19. **Summary / recap steps in multi-step builder modals**: guard EVERY `size.xxx` access with a null check when supporting flat-price styles. `size` will be `null` and any `size.label` / `size.nb_meats` access crashes the component tree. Use `size?.label` and branch the summary UI on `isFlatStyle`.
20. **Footer total gating**: a multi-step builder's footer total display often gates on `style && size`. For flat-price styles, this leaves the total as "—" forever. Gate should be `style && (isFlatStyle || size)`.
21. **Fulfillment-specific cutoffs stack, they don't replace.** Delivery's earlier cutoff is calculated independently from (not instead of) the general last-order cutoff — the restaurant can be `state: "open"` overall while `delivery_available: false`. Check BOTH at checkout, and gate the frontend UI (disabled tab + banner) on the specific one (`delivery_available`), not the overall `state`.
22. **Don't bake the country code into the stored phone number.** Keep `customer_phone` (national digits only) and `customer_phone_country_code` as separate fields. Baking them together forces fragile string-splitting everywhere they're displayed, and breaks the "format without mutating" rule.
23. **Phone formatting must be idempotent and read-only.** The formatter (add trunk zero + group by 2) is a pure display transform computed at render time in every consumer (kitchen dashboard, printed receipt, admin UI) — never write the formatted string back into the DB. Keep one canonical implementation per language (Python + JS) that produce byte-identical output, or admin/kitchen will show different spacing than the customer-facing app.
24. **Client list has no dedicated collection.** Don't create a `customers` table that can drift from `orders`. Aggregate on read (`$group` by lowercased email, `$sort` by `created_at` desc before grouping so `$first` gives the freshest name/phone) — it's always consistent with the order history by construction.
25. **Batch-save staging must merge into the live list for preview**, not replace it — compute a `displayItems = items.map(mergeIfPending)` so search/filter still works correctly on rows that have unsaved edits.
26. **Kitchen dashboard needs its own JWT role, checked server-side on every route.** Don't let convenience during development turn into an admin token that also happens to work on kitchen routes (or vice versa) — add a `require_kitchen` dependency distinct from `require_admin` from day one.
27. **A missing bare `/health` route can flag a healthy app as broken during deploy.** Kubernetes-style platform health probes commonly hit the container directly, bypassing your `/api` ingress prefix. If your only health endpoint lives under `/api/health`, the probe 404s. Expose an unprefixed `GET /health` on the app itself (fast, no DB call) in addition to any deep `/api/health` check.

---

## 13. Recommended build order

1. Scaffold FastAPI + Motor + React shells. Wire `/api` prefix and CORS. Add the bare `/health` + deep `/api/health` routes immediately — cheap now, painful to debug later during your first deploy.
2. Auth: admin user, login endpoint, JWT, `require_admin`, `AdminLogin` page.
3. Menu CRUD + admin page + customer `/menu`. No cart yet.
4. Cart (Context + localStorage) + Checkout page + `/api/checkout/session` (offline only).
5. Admin Orders page + status transitions + hard-delete button + confirmation dialog.
6. Kitchen tablet dashboard: separate `/kitchen` login + role (own JWT, never accepted on `/admin/*`), polling order list (New / Accepted / Declined tabs, ~4s interval), audio alert loop for unacknowledged orders, and thermal receipt printing (RawBT intent scheme OR the window.print DOM-swap technique — see §7). Test printing on the actual target device before moving on.
7. Opening hours engine + Home banner + Checkout gate (HTTP 423).
8. Resend emails.
9. First builder family (whatever the flagship customizable item is) — models, V2 pricing engine, modal, admin editor.
10. Flat mini-menu (singleton config, 3-step modal, admin page, Home featured card) — reuse the flat-price + max_meats pattern from builder styles.
11. Categories dynamic + global soda flavours + sauces cap.
12. i18n toggle + FR/EN strings.
13. Reviews (optional).
14. Open Graph meta tags + preview image + admin dashboard stats.
15. Country-aware phone: picker + formatting + validation (frontend AND backend) + "remember me" at checkout.
16. Fulfillment-specific cutoffs stack, they don't replace. Delivery's earlier cutoff is calculated independently from (not instead of) the general last-order cutoff — the restaurant can be `state: "open"` overall while `delivery_available: false`. Check BOTH at checkout, and gate the frontend UI (disabled tab + banner) on the specific one (`delivery_available`), not the overall `state`.
17. Kitchen dashboard "put on hold" action (duration picker on a pending order card) + matching email template.
18. Admin Client List page (derived aggregation) with per-client order drawer + delete.
19. Batch-save pattern retrofitted onto the Menu (and any other heavily-edited) admin list.
20. Polish, add `data-testid` everywhere, comprehensive testing pass.

---

## 14. Non-negotiable requirements checklist (paste at the top of every AI prompt in this project)

- [ ] Every backend route prefixed with `/api` — EXCEPT a bare, unprefixed `GET /health` for platform liveness/readiness probes.
- [ ] Every DB primary key is a UUID string (never ObjectId).
- [ ] All datetimes stored as UTC ISO 8601.
- [ ] All prices computed server-side. Client `unit_price` is ignored.
- [ ] All list endpoints exclude `image_base64`. Dedicated `/image` endpoints per resource.
- [ ] `settings` is a singleton at `id="singleton"`. Same for `kids_menu` / flat mini-menus.
- [ ] Payment methods are exactly `{"cash", "card_in_person"}`. Anything else → HTTP 400.
- [ ] Pickup orders always get a 4-digit `pickup_code`.
- [ ] Orders are created with `status='pending'` immediately (no external-payment gate).
- [ ] Kitchen dashboard has its OWN JWT auth (`/kitchen/login`), fully separate from admin — a kitchen token must never be accepted on `/admin/*` routes and vice versa.
- [ ] Flat mini-menu: main + dessert options have STABLE IDs; names denormalized to snapshot at creation.
- [ ] `[TEST ORDER]` in notes → shows a prominent "TEST ORDER — DO NOT PREPARE" banner on the kitchen dashboard order card; sentinel is stripped from the visible notes line.
- [ ] Phone numbers rendered anywhere staff-facing (kitchen dashboard, admin orders list, printed receipt) MUST use the same space-grouped formatter — one implementation, reused everywhere.
- [ ] Thermal receipt printing is verified on the ACTUAL target device/browser (not desktop/headless) before considering the feature done — iframe isolation and `@media print` CSS are unreliable across Android WebViews (see §7).
- [ ] RawBT/intent print URLs use `encodeURIComponent`, never `encodeURI` — receipt text routinely contains a literal `#` which `encodeURI` leaves unescaped, colliding with the intent URI's own delimiter.
- [ ] Every button / link / input has a `data-testid` in kebab-case describing its role.
- [ ] Restaurant closed / after-cutoff returns HTTP 423 from `/api/checkout/*` — not 400 or 500.
- [ ] Admin sidebar includes: Dashboard, Orders (with hard-delete), Menu, Categories, Builders, Flat mini-menu, Sauces, Reviews, Settings.
- [ ] Seed script is idempotent AND includes backfill blocks for schema evolutions.
- [ ] `GET /api/admin/stats` defines `paid_orders` and `revenue` over `status NOT IN {cancelled, expired}` — never over `payment_status='paid'` (that's obsolete Stripe-era filtering).
- [ ] Multi-step builder modals: flat-price styles skip the size step, allow `size_id=null` in the payload, and every `size.xxx` access is null-guarded.
- [ ] `DELETE /api/orders/{id}` admin-only endpoint exists so staff can scrub test orders.
- [ ] Frontend admin UI has a confirmation `AlertDialog` before hard-deleting an order.
- [ ] Open Graph + Twitter Card meta block in `public/index.html`, image 1200×630 JPG at `/images/preview.jpg`.
- [ ] `customer_phone` stores the national number ONLY — country dial code/name/flag are separate order fields, never concatenated into the phone string.
- [ ] Phone display formatting (trunk-zero + grouping) is implemented once per language and produces identical output in the kitchen dashboard, admin orders, and admin client list.
- [ ] Phone completeness is validated with a per-country digit-length table on BOTH the frontend (blocks submit) and backend (rejects with HTTP 400) — never trust the client alone.
- [ ] "Remember me" at checkout only ever writes to `localStorage` on the customer's device, never includes the email address, and never gets deleted just because the checkbox is unchecked on a later visit.
- [ ] `delivery_cutoff_minutes` (if used) is enforced server-side per-fulfillment-type at checkout — a delivery order is rejected (HTTP 423, `code: "delivery_unavailable"`) even while the restaurant's overall `state` is `"open"`.
- [ ] `GET /api/admin/clients` aggregates `orders` on read — no separate `customers` collection that could drift out of sync.
- [ ] Any list-style admin editor with more than a couple of rows offers a "Save all" batch-commit pattern instead of forcing one open→edit→save cycle per row.

---

## 15. Final note

Read the whole thing before writing code. The design decisions in §12 came from real bugs — cutting corners on any of them re-introduces the exact issue that was already fixed. Especially: flag forwarding, verifying thermal receipt printing on the ACTUAL target device (not just desktop/headless — see §7), null-guards for flat-price builder styles, and the pay-on-arrival stats redefinition.

Design (colors, fonts, layout, hero images, mood, tone) is left entirely to the builder AI or the designer — nothing in this document constrains it.
