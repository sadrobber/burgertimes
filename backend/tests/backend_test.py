"""Burger Times · comprehensive backend test suite.

Covers: admin auth, seed defaults, categories CRUD, menu CRUD, burger builder CRUD,
sauces CRUD, pricing engine (quote), checkout session (BT- number + pickup_code),
force_closed → 423, order lifecycle, admin stats, order lookup safe subset.

Uses module-level shared state (STATE) so tests can share IDs across classes even
under pytest-xdist loadscope (all pinned to one worker via loadfile).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = None
if os.environ.get("REACT_APP_BACKEND_URL"):
    BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
else:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"

# Force all tests in this file onto ONE xdist worker so module-level state is shared.
# (pytest.ini uses --dist loadscope which groups by class; we want by file.)
# Trick: set an xdist_group.
pytestmark = pytest.mark.xdist_group(name="burger_times_backend")

STATE: dict = {
    "cat_id": None,
    "sauce_id": None,
    "style_size_id": None,
    "style_flat_id": None,
    "size_id": None,
    "meat_id": None,
    "cheese_id": None,
    "supplement_id": None,
    "item_id": None,
    "order_id": None,
    "order_number": None,
    "original_hours": None,
}

ALWAYS_OPEN_HOURS = {
    d: {"is_open": True, "ranges": [{"open": "00:00", "close": "23:59"}]}
    for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
}


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session", autouse=True)
def open_restaurant(s, admin_token):
    """Force restaurant open (all days 00:00-23:59) for the whole test session.

    Restores original hours + force_closed at the end.
    """
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    cur = s.get(f"{API}/settings").json()
    STATE["original_hours"] = cur.get("hours_per_day")
    s.put(f"{API}/settings", headers=headers, json={"hours_per_day": ALWAYS_OPEN_HOURS, "force_closed": False})
    yield
    # restore
    if STATE["original_hours"]:
        s.put(f"{API}/settings", headers=headers, json={"hours_per_day": STATE["original_hours"], "force_closed": False})


# ----- Auth ----------------------------------------------------------------


class TestAdminAuth:
    def test_login_bad_password(self, s):
        r = s.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_login_ok(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_admin_me(self, s, auth_headers):
        r = s.get(f"{API}/admin/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_admin_me_unauth(self, s):
        r = s.get(f"{API}/admin/me")
        assert r.status_code in (401, 403)


# ----- Seed defaults -------------------------------------------------------


class TestSeedDefaults:
    def test_settings_singleton(self, s):
        r = s.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        assert d["timezone"] == "Europe/Paris"
        assert isinstance(d.get("soda_flavours"), list) and len(d["soda_flavours"]) > 0
        assert "hours_per_day" in d and "mon" in d["hours_per_day"]

    def test_categories_seeded(self, s):
        r = s.get(f"{API}/categories")
        assert r.status_code == 200
        slugs = {c["slug"] for c in r.json()}
        expected = {"burgers", "sandwiches", "wraps", "sides", "drinks", "desserts"}
        assert expected.issubset(slugs), f"missing: {expected - slugs}"

    def test_menu_endpoint_shape(self, s):
        r = s.get(f"{API}/menu")
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_burger_config_shape(self, s):
        r = s.get(f"{API}/burger/config")
        assert r.status_code == 200
        d = r.json()
        for k in ["styles", "sizes", "meats", "cheeses", "supplements"]:
            assert k in d and isinstance(d[k], list)

    def test_restaurant_status(self, s):
        r = s.get(f"{API}/restaurant/status")
        assert r.status_code == 200
        d = r.json()
        assert d["state"] in ("open", "closing_soon", "closed")
        assert isinstance(d.get("eta_min"), int)
        assert isinstance(d.get("eta_max"), int)


# ----- Categories ----------------------------------------------------------


class TestCategories:
    def test_create(self, s, auth_headers):
        slug = f"test-cat-{uuid.uuid4().hex[:6]}"
        r = s.post(
            f"{API}/admin/categories", headers=auth_headers,
            json={"slug": slug, "label": {"fr": "TEST", "en": "TEST"}, "sort_order": 99},
        )
        assert r.status_code == 200, r.text
        STATE["cat_id"] = r.json()["id"]
        STATE["cat_slug"] = slug

    def test_duplicate_slug(self, s, auth_headers):
        r = s.post(f"{API}/admin/categories", headers=auth_headers,
                   json={"slug": STATE["cat_slug"], "label": {"fr": "X", "en": "X"}})
        assert r.status_code == 400

    def test_update(self, s, auth_headers):
        r = s.put(f"{API}/admin/categories/{STATE['cat_id']}", headers=auth_headers,
                  json={"sort_order": 42})
        assert r.status_code == 200 and r.json()["sort_order"] == 42

    def test_delete(self, s, auth_headers):
        r = s.delete(f"{API}/admin/categories/{STATE['cat_id']}", headers=auth_headers)
        assert r.status_code == 200 and r.json()["deleted"] == 1


# ----- Sauces --------------------------------------------------------------


class TestSauces:
    def test_create(self, s, auth_headers):
        r = s.post(f"{API}/admin/sauces", headers=auth_headers, json={"name": "TEST_Ketchup"})
        assert r.status_code == 200
        STATE["sauce_id"] = r.json()["id"]

    def test_list_public(self, s):
        r = s.get(f"{API}/sauces")
        assert r.status_code == 200
        assert any(x["id"] == STATE["sauce_id"] for x in r.json())

    def test_delete(self, s, auth_headers):
        r = s.delete(f"{API}/admin/sauces/{STATE['sauce_id']}", headers=auth_headers)
        assert r.status_code == 200


# ----- Burger builder + menu items (seeded once, used by pricing/orders) ---


class TestSeedBuilderAndMenu:
    def test_style_size(self, s, auth_headers):
        r = s.post(f"{API}/admin/burger/styles", headers=auth_headers,
                   json={"name": "TEST_Classic", "price_modifier": 0.0})
        assert r.status_code == 200
        STATE["style_size_id"] = r.json()["id"]

    def test_style_flat(self, s, auth_headers):
        r = s.post(f"{API}/admin/burger/styles", headers=auth_headers,
                   json={"name": "TEST_Flat", "flat_price": 12.5, "flat_price_menu": 15.0, "max_meats": 1})
        assert r.status_code == 200
        STATE["style_flat_id"] = r.json()["id"]

    def test_size(self, s, auth_headers):
        r = s.post(f"{API}/admin/burger/sizes", headers=auth_headers,
                   json={"code": "s1", "label": "Simple", "price_simple": 8.0, "price_menu": 11.0, "nb_meats": 1})
        assert r.status_code == 200
        STATE["size_id"] = r.json()["id"]

    def test_meat(self, s, auth_headers):
        r = s.post(f"{API}/admin/burger/meats", headers=auth_headers,
                   json={"name": "TEST_Beef", "base_price": 0.0})
        assert r.status_code == 200
        STATE["meat_id"] = r.json()["id"]

    def test_cheese(self, s, auth_headers):
        r = s.post(f"{API}/admin/burger/cheeses", headers=auth_headers,
                   json={"name": "TEST_Cheddar", "base_price": 1.0})
        assert r.status_code == 200
        STATE["cheese_id"] = r.json()["id"]

    def test_supplement(self, s, auth_headers):
        r = s.post(f"{API}/admin/burger/supplements", headers=auth_headers,
                   json={"name": "TEST_Bacon", "base_price": 1.5})
        assert r.status_code == 200
        STATE["supplement_id"] = r.json()["id"]

    def test_config_public_reflects(self, s):
        r = s.get(f"{API}/burger/config")
        d = r.json()
        assert any(x["id"] == STATE["style_size_id"] for x in d["styles"])
        assert any(x["id"] == STATE["size_id"] for x in d["sizes"])

    def test_unknown_part_404(self, s, auth_headers):
        r = s.get(f"{API}/admin/burger/unknown", headers=auth_headers)
        assert r.status_code == 404

    def test_create_menu_item(self, s, auth_headers):
        r = s.post(f"{API}/admin/menu", headers=auth_headers, json={
            "name": "TEST_Cheeseburger", "category": "burgers",
            "price_seul": 9.0, "price_menu": 12.0, "available": True,
        })
        assert r.status_code == 200
        STATE["item_id"] = r.json()["id"]

    def test_menu_update(self, s, auth_headers):
        r = s.put(f"{API}/admin/menu/{STATE['item_id']}", headers=auth_headers,
                  json={"description": "TEST_desc"})
        assert r.status_code == 200 and r.json()["description"] == "TEST_desc"

    def test_public_menu_includes(self, s):
        r = s.get(f"{API}/menu")
        assert any(x["id"] == STATE["item_id"] for x in r.json())


# ----- Pricing / quote -----------------------------------------------------


def _base_payload(extra=None):
    p = {
        "items": [],
        "fulfillment": "pickup",
        "customer_first_name": "T", "customer_last_name": "U",
        "customer_phone": "0600000000", "payment_method": "cash",
    }
    if extra:
        p.update(extra)
    return p


class TestPricingQuote:
    def test_quote_plain_menu_seul(self, s):
        p = _base_payload()
        p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 2,
                       "formula": "seul", "is_burger": False}]
        r = s.post(f"{API}/checkout/quote", json=p)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subtotal"] == 18.0
        assert d["delivery_fee"] == 0.0

    def test_quote_plain_menu_formula(self, s):
        p = _base_payload()
        p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 1,
                       "formula": "menu", "included_drink": "Coca-Cola", "is_burger": False}]
        r = s.post(f"{API}/checkout/quote", json=p)
        assert r.status_code == 200, r.text
        assert r.json()["subtotal"] == 12.0

    def test_quote_size_based_burger(self, s):
        p = _base_payload()
        p["items"] = [{
            "line_id": "L1", "quantity": 1, "formula": "seul", "is_burger": True,
            "burger_config": {
                "style_id": STATE["style_size_id"], "size_id": STATE["size_id"],
                "meat_ids": [STATE["meat_id"]],
                "cheese_ids": [STATE["cheese_id"]],
                "supplement_ids": [STATE["supplement_id"]],
                "sauces": [],
            },
        }]
        r = s.post(f"{API}/checkout/quote", json=p)
        assert r.status_code == 200, r.text
        # 8.0 base + 0 meat + 1.0 cheese + 1.5 supp = 10.5
        assert r.json()["subtotal"] == 10.5

    def test_quote_flat_style(self, s):
        p = _base_payload()
        p["items"] = [{
            "line_id": "L1", "quantity": 1, "formula": "seul", "is_burger": True,
            "burger_config": {"style_id": STATE["style_flat_id"], "meat_ids": [STATE["meat_id"]]},
        }]
        r = s.post(f"{API}/checkout/quote", json=p)
        assert r.status_code == 200, r.text
        assert r.json()["subtotal"] == 12.5

    def test_quote_meat_count_mismatch(self, s):
        p = _base_payload()
        p["items"] = [{
            "line_id": "L1", "quantity": 1, "formula": "seul", "is_burger": True,
            "burger_config": {
                "style_id": STATE["style_size_id"], "size_id": STATE["size_id"],
                "meat_ids": [STATE["meat_id"], STATE["meat_id"]],
            },
        }]
        r = s.post(f"{API}/checkout/quote", json=p)
        assert r.status_code == 400

    def test_quote_delivery_fee(self, s):
        p = _base_payload({
            "fulfillment": "delivery", "address_line1": "1 rue",
            "postal_code": "06240", "city": "Beausoleil",
        })
        p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 1,
                       "formula": "seul", "is_burger": False}]
        r = s.post(f"{API}/checkout/quote", json=p)
        assert r.status_code == 200, r.text
        assert r.json()["delivery_fee"] == 3.0


# ----- Checkout session + order lifecycle ----------------------------------


class TestCheckoutAndOrders:
    def test_create_pickup_order(self, s):
        p = _base_payload({"notes": "[TEST ORDER] pytest"})
        p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 1,
                       "formula": "seul", "is_burger": False}]
        p["customer_first_name"] = "TEST"
        r = s.post(f"{API}/checkout/session", json=p)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["order_number"].startswith("BT-")
        STATE["order_id"] = d["order_id"]
        STATE["order_number"] = d["order_number"]

    def test_lookup_public_safe_subset(self, s):
        r = s.get(f"{API}/orders/lookup/{STATE['order_id']}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["order_number"].startswith("BT-")
        assert d.get("pickup_code") and len(d["pickup_code"]) == 4 and d["pickup_code"].isdigit()
        assert "customer_phone" not in d
        assert "kitchen_message_id" not in d
        assert "[TEST ORDER]" not in (d.get("notes") or "")

    def test_invalid_payment_method(self, s):
        p = _base_payload({"payment_method": "stripe_online"})
        p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 1,
                       "formula": "seul", "is_burger": False}]
        r = s.post(f"{API}/checkout/session", json=p)
        assert r.status_code == 400

    def test_delivery_missing_address(self, s):
        p = _base_payload({"fulfillment": "delivery"})
        p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 1,
                       "formula": "seul", "is_burger": False}]
        r = s.post(f"{API}/checkout/session", json=p)
        assert r.status_code == 400

    def test_admin_orders_list(self, s, auth_headers):
        r = s.get(f"{API}/admin/orders", headers=auth_headers)
        assert r.status_code == 200
        assert any(o["id"] == STATE["order_id"] for o in r.json())

    def test_status_transitions(self, s, auth_headers):
        for st in ["accepted", "preparing", "ready", "delivered"]:
            r = s.put(f"{API}/admin/orders/{STATE['order_id']}/status",
                      headers=auth_headers, json={"status": st})
            assert r.status_code == 200, f"{st}: {r.text}"
            assert r.json()["status"] == st

    def test_invalid_status(self, s, auth_headers):
        r = s.put(f"{API}/admin/orders/{STATE['order_id']}/status",
                  headers=auth_headers, json={"status": "unknown_state"})
        assert r.status_code == 400

    def test_admin_stats(self, s, auth_headers):
        r = s.get(f"{API}/admin/stats", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ["total_orders", "paid_orders", "pending_orders", "revenue"]:
            assert k in d
        assert d["total_orders"] >= 1

    def test_delete_order(self, s, auth_headers):
        r = s.delete(f"{API}/admin/orders/{STATE['order_id']}", headers=auth_headers)
        assert r.status_code == 200
        r2 = s.get(f"{API}/orders/lookup/{STATE['order_id']}")
        assert r2.status_code == 404


# ----- Force closed → 423 --------------------------------------------------


class TestForceClosed:
    def test_force_closed_returns_423(self, s, auth_headers):
        s.put(f"{API}/settings", headers=auth_headers, json={"force_closed": True})
        try:
            p = _base_payload()
            p["items"] = [{"line_id": "L1", "item_id": STATE["item_id"], "quantity": 1,
                           "formula": "seul", "is_burger": False}]
            r = s.post(f"{API}/checkout/session", json=p)
            assert r.status_code == 423, f"expected 423 got {r.status_code}: {r.text}"
            # Quote does NOT enforce closed
            r2 = s.post(f"{API}/checkout/quote", json=p)
            assert r2.status_code == 200
        finally:
            s.put(f"{API}/settings", headers=auth_headers, json={"force_closed": False})


# ----- Cleanup -------------------------------------------------------------


class TestZCleanup:
    def test_delete_menu_item(self, s, auth_headers):
        if STATE.get("item_id"):
            s.delete(f"{API}/admin/menu/{STATE['item_id']}", headers=auth_headers)

    def test_delete_builder(self, s, auth_headers):
        for part, iid in [
            ("styles", STATE.get("style_size_id")),
            ("styles", STATE.get("style_flat_id")),
            ("sizes", STATE.get("size_id")),
            ("meats", STATE.get("meat_id")),
            ("cheeses", STATE.get("cheese_id")),
            ("supplements", STATE.get("supplement_id")),
        ]:
            if iid:
                s.delete(f"{API}/admin/burger/{part}/{iid}", headers=auth_headers)
