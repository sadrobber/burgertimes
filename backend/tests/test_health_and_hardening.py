"""Iteration 13 - Health endpoint + Motor timeout hardening regression tests."""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fall back to reading frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---- Health endpoint ----
class TestHealth:
    def test_health_shape_and_speed(self):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/health", timeout=6)
        dur = time.time() - t0
        assert r.status_code == 200
        assert dur < 4.0, f"Health took {dur:.2f}s"
        d = r.json()
        for key in ("api", "mongo", "menu_items_count", "integrations"):
            assert key in d, f"Missing key {key}"
        assert d["api"] == "ok"
        assert d["mongo"] == "ok", f"mongo not ok: {d['mongo']}"
        assert isinstance(d["menu_items_count"], int) and d["menu_items_count"] > 0
        integ = d["integrations"]
        for k in ("resend_configured", "resend_from"):
            assert k in integ, f"Missing integration key {k}"
        assert integ["resend_configured"] is True
        assert integ["resend_from"]  # non-null string

    def test_health_does_not_leak_secrets(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=6)
        body = r.text
        # No Resend API key (re_...) should ever leak in a public response
        assert not re.search(r"re_[A-Za-z0-9]{10,}", body), "Resend API key leaked"

    def test_health_no_auth_required(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=6)
        assert r.status_code == 200


# ---- Menu fast-path ----
class TestMenuFastPath:
    def test_menu_speed_and_count(self):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/menu", timeout=5)
        dur = time.time() - t0
        assert r.status_code == 200
        assert dur < 2.0, f"Menu took {dur:.2f}s"  # loose from <1s to account for network
        items = r.json()
        assert len(items) == 40, f"Expected 40 items got {len(items)}"

    def test_categories_count(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=5)
        assert r.status_code == 200
        assert len(r.json()) == 9

    def test_settings_singleton(self):
        r = requests.get(f"{BASE_URL}/api/settings", timeout=5)
        assert r.status_code == 200
        d = r.json()
        assert d.get("id") == "singleton"


# ---- Startup code path (static verification of asyncio.wait_for) ----
class TestStartupResilience:
    def test_seed_wrapped_in_wait_for(self):
        with open("/app/backend/server.py") as f:
            src = f.read()
        assert "asyncio.wait_for(run_seed(db)" in src
        assert "timeout=12.0" in src
        assert "except asyncio.TimeoutError" in src

    def test_motor_client_has_explicit_timeouts(self):
        with open("/app/backend/server.py") as f:
            src = f.read()
        assert "serverSelectionTimeoutMS=4000" in src
        assert "connectTimeoutMS=4000" in src
        assert "socketTimeoutMS=8000" in src


# ---- Regression flows ----
class TestRegression:
    def test_admin_login(self, admin_token):
        assert admin_token
        r = requests.get(f"{BASE_URL}/api/admin/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=5)
        assert r.status_code == 200

    def test_checkout_session_pickup(self):
        # get a burger menu item
        menu = requests.get(f"{BASE_URL}/api/menu", timeout=5).json()
        item = next((m for m in menu if m.get("type") == "menu_item"), menu[0])
        payload = {
            "fulfillment": "pickup",
            "payment_method": "cash",
            "customer_first_name": "TEST",
            "customer_last_name": "Iter13",
            "customer_phone": "+33600000000",
            "notes": "[TEST ORDER] iter13 regression",
            "items": [{"line_id": "l1", "kind": "menu_item", "item_id": item["id"], "qty": 1}],
        }
        r = requests.post(f"{BASE_URL}/api/checkout/session", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("order_id") and d.get("order_number")

    def test_delivery_fee_stats(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/stats/delivery-fees",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ("totals", "counts", "daily"):
            assert k in d

    def test_force_reseed(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/admin/seed/reseed",
                          headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True
