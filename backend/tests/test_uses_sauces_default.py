"""Iteration 40 — Verify uses_sauces auto-enabled for all menu items.

Printer-safe: uses /checkout/quote only, NEVER /checkout/session or /tablet/orders.
Cleans up all TEST_* items created.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def public_menu():
    r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def sauces():
    r = requests.get(f"{BASE_URL}/api/sauces", timeout=15)
    assert r.status_code == 200
    return r.json()


# ---- 1. All current public items have uses_sauces=True --------------------
def test_public_menu_all_uses_sauces_true(public_menu):
    assert len(public_menu) > 0, "no menu items returned"
    offenders = [(i["id"], i["name"], i.get("uses_sauces")) for i in public_menu if i.get("uses_sauces") is not True]
    assert offenders == [], f"items missing uses_sauces=True: {offenders}"


# ---- 2. New admin-created item defaults uses_sauces=True ------------------
def test_new_menu_item_defaults_uses_sauces_true(admin_headers, public_menu):
    category = public_menu[0]["category"]
    name = f"TEST_SAUCEDEF_{uuid.uuid4().hex[:8]}"
    payload = {"name": name, "category": category, "price_seul": 1.0}  # uses_sauces omitted
    r = requests.post(f"{BASE_URL}/api/admin/menu", headers=admin_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    doc = r.json()
    item_id = doc["id"]
    try:
        assert doc["uses_sauces"] is True, f"created doc uses_sauces={doc.get('uses_sauces')}"
        # Public reflects it
        r2 = requests.get(f"{BASE_URL}/api/menu", timeout=15)
        pub = [x for x in r2.json() if x["id"] == item_id]
        assert len(pub) == 1
        assert pub[0]["uses_sauces"] is True
    finally:
        requests.delete(f"{BASE_URL}/api/admin/menu/{item_id}", headers=admin_headers, timeout=15)


# ---- 3. Admin can explicitly set uses_sauces=False; public reflects -------
def test_admin_can_override_uses_sauces_false(admin_headers, public_menu):
    category = public_menu[0]["category"]
    name = f"TEST_SAUCEOFF_{uuid.uuid4().hex[:8]}"
    payload = {"name": name, "category": category, "price_seul": 1.0, "uses_sauces": False}
    r = requests.post(f"{BASE_URL}/api/admin/menu", headers=admin_headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    item_id = r.json()["id"]
    try:
        assert r.json()["uses_sauces"] is False
        # Public reflects
        r2 = requests.get(f"{BASE_URL}/api/menu", timeout=15)
        pub = [x for x in r2.json() if x["id"] == item_id]
        assert len(pub) == 1 and pub[0]["uses_sauces"] is False
    finally:
        d = requests.delete(f"{BASE_URL}/api/admin/menu/{item_id}", headers=admin_headers, timeout=15)
        assert d.status_code == 200


# ---- 4. Public menu exposes sauce chips via /sauces + uses_sauces ---------
def test_active_sauces_available_for_existing_item(public_menu, sauces):
    assert len(sauces) >= 2, f"need >=2 active sauces, got {len(sauces)}"
    # Any typical existing (non-TEST) item with uses_sauces=True
    normal = next((i for i in public_menu if i.get("uses_sauces") is True and not i["name"].startswith("TEST_")), None)
    assert normal is not None


# ---- 5. Two-sauce cap enforced by /checkout/quote --------------------------
def test_two_sauce_cap_enforced_via_quote(public_menu, sauces):
    item = next((i for i in public_menu if i.get("uses_sauces") is True and not i["name"].startswith("TEST_")), None)
    assert item is not None
    sauce_names = [s["name"] for s in sauces[:3]]
    assert len(sauce_names) == 3, "need >=3 sauces for cap test"

    def build(sauces_list):
        return {
            "items": [{
                "line_id": "L1",
                "item_id": item["id"],
                "quantity": 1,
                "formula": "seul",
                "sauces": sauces_list,
            }],
            "fulfillment": "pickup",
            "customer_first_name": "Test",
            "customer_last_name": "Cap",
            "customer_phone": "0600000000",
            "payment_method": "cash",
        }

    # 2 sauces => OK
    r_ok = requests.post(f"{BASE_URL}/api/checkout/quote", json=build(sauce_names[:2]), timeout=15)
    assert r_ok.status_code == 200, f"2 sauces should pass: {r_ok.status_code} {r_ok.text}"

    # 3 sauces => 400
    r_bad = requests.post(f"{BASE_URL}/api/checkout/quote", json=build(sauce_names[:3]), timeout=15)
    assert r_bad.status_code == 400, f"3 sauces should fail: {r_bad.status_code} {r_bad.text}"
    assert "sauces" in r_bad.text.lower()
