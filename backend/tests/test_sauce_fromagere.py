"""Tests for the new 'Sauce fromagère' toggle on burger orders.

Verifies:
 - POST /api/checkout/session with burger_config.sauce_fromagere: false persists
   the boolean into the created order snapshot.
 - Default (sauce_fromagere omitted or true) => order item shows True.
 - GET /api/admin/orders/{id} returns items[0].burger_config.sauce_fromagere.
Cleans up created orders via DELETE /api/admin/orders/{id}.
"""
from __future__ import annotations

import os
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

pytestmark = pytest.mark.xdist_group(name="sauce_fromagere")

STATE: dict = {"created_order_ids": []}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def auth_headers(s):
    r = s.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def restaurant_open(s, auth_headers):
    always = {
        d: {"is_open": True, "ranges": [{"open": "00:00", "close": "23:59"}]}
        for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }
    cur = s.get(f"{API}/settings").json()
    original = cur.get("hours_per_day")
    s.put(f"{API}/settings", headers=auth_headers,
          json={"hours_per_day": always, "force_closed": False})
    yield
    if original:
        s.put(f"{API}/settings", headers=auth_headers,
              json={"hours_per_day": original, "force_closed": False})


@pytest.fixture(scope="module")
def burger_ids(s):
    r = s.get(f"{API}/burger/config")
    assert r.status_code == 200
    d = r.json()
    # Prefer a real (non-TEST_) flat style so pricing is straightforward.
    flat = next(
        (st for st in d["styles"] if st.get("flat_price") and not st["name"].startswith("TEST_")),
        None,
    ) or next((st for st in d["styles"] if st.get("flat_price")), None)
    assert flat, "no flat style available"
    meat = next((m for m in d["meats"] if not m["name"].startswith("TEST_")), None) or d["meats"][0]
    return {"style_id": flat["id"], "meat_id": meat["id"]}


def _payload(burger_config, note_suffix=""):
    return {
        "items": [{
            "line_id": "L1",
            "quantity": 1,
            "formula": "seul",
            "is_burger": True,
            "burger_config": burger_config,
        }],
        "fulfillment": "pickup",
        "customer_first_name": "TEST_FROM",
        "customer_last_name": "AGERE",
        "customer_phone": "0600000000",
        "payment_method": "cash",
        "notes": f"[TEST ORDER] sauce_fromagere {note_suffix}",
    }


class TestSauceFromagerePersistence:
    def test_create_order_sauce_fromagere_false(self, s, restaurant_open, burger_ids):
        cfg = {
            "style_id": burger_ids["style_id"],
            "meat_ids": [burger_ids["meat_id"]],
            "cheese_ids": [],
            "supplement_ids": [],
            "sauces": [],
            "sauce_fromagere": False,
        }
        r = s.post(f"{API}/checkout/session", json=_payload(cfg, "no"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["order_number"].startswith("BT-")
        STATE["order_no"] = d["order_id"]
        STATE["created_order_ids"].append(d["order_id"])

    def test_admin_fetch_persists_false(self, s, auth_headers):
        oid = STATE["order_no"]
        r = s.get(f"{API}/admin/orders/{oid}", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"][0]["is_burger"] is True
        bc = d["items"][0].get("burger_config") or {}
        assert bc.get("sauce_fromagere") is False, (
            f"expected sauce_fromagere False, got {bc.get('sauce_fromagere')!r} in {bc}"
        )

    def test_create_order_sauce_fromagere_default_true(self, s, restaurant_open, burger_ids):
        # Omit the field entirely to test the default True behaviour.
        cfg = {
            "style_id": burger_ids["style_id"],
            "meat_ids": [burger_ids["meat_id"]],
            "cheese_ids": [],
            "supplement_ids": [],
            "sauces": [],
        }
        r = s.post(f"{API}/checkout/session", json=_payload(cfg, "default"))
        assert r.status_code == 200, r.text
        d = r.json()
        STATE["order_yes"] = d["order_id"]
        STATE["created_order_ids"].append(d["order_id"])

    def test_admin_fetch_persists_true_default(self, s, auth_headers):
        oid = STATE["order_yes"]
        r = s.get(f"{API}/admin/orders/{oid}", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        bc = d["items"][0].get("burger_config") or {}
        assert bc.get("sauce_fromagere") is True, (
            f"expected default True, got {bc.get('sauce_fromagere')!r} in {bc}"
        )

    def test_create_order_sauce_fromagere_explicit_true(self, s, restaurant_open, burger_ids):
        cfg = {
            "style_id": burger_ids["style_id"],
            "meat_ids": [burger_ids["meat_id"]],
            "cheese_ids": [],
            "supplement_ids": [],
            "sauces": [],
            "sauce_fromagere": True,
        }
        r = s.post(f"{API}/checkout/session", json=_payload(cfg, "yes"))
        assert r.status_code == 200, r.text
        d = r.json()
        STATE["order_yes_explicit"] = d["order_id"]
        STATE["created_order_ids"].append(d["order_id"])

    def test_admin_fetch_explicit_true(self, s, auth_headers):
        r = s.get(f"{API}/admin/orders/{STATE['order_yes_explicit']}", headers=auth_headers)
        assert r.status_code == 200
        bc = r.json()["items"][0].get("burger_config") or {}
        assert bc.get("sauce_fromagere") is True

    def test_non_burger_item_untouched(self, s, restaurant_open, auth_headers):
        """Regression: plain menu items are not affected by the new field."""
        menu = s.get(f"{API}/menu").json()
        plain = next((m for m in menu if m.get("available")), None)
        assert plain, "no available menu item"
        p = {
            "items": [{
                "line_id": "L1", "item_id": plain["id"], "quantity": 1,
                "formula": "seul", "is_burger": False,
            }],
            "fulfillment": "pickup",
            "customer_first_name": "TEST_FROM",
            "customer_last_name": "PLAIN",
            "customer_phone": "0600000000",
            "payment_method": "cash",
            "notes": "[TEST ORDER] plain no burger",
        }
        r = s.post(f"{API}/checkout/session", json=p)
        assert r.status_code == 200, r.text
        oid = r.json()["order_id"]
        STATE["created_order_ids"].append(oid)
        got = s.get(f"{API}/admin/orders/{oid}", headers=auth_headers).json()
        assert got["items"][0]["is_burger"] is False
        # burger_config may be None/absent — either way no key error.
        assert not got["items"][0].get("burger_config")

    def test_cleanup_delete_orders(self, s, auth_headers):
        for oid in STATE["created_order_ids"]:
            r = s.delete(f"{API}/admin/orders/{oid}", headers=auth_headers)
            assert r.status_code in (200, 204), r.text
        STATE["created_order_ids"] = []
