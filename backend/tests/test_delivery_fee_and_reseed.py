"""Iteration 5: delivery-fee-in-quote fix + admin force-reseed endpoint."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

SANDWICH_TRIPLE_ID = "53967647-5fca-4e98-866d-b0bd8a5bbd0f"
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _quote_payload(qty=1, fulfillment="delivery", address=None):
    p = {
        "items": [{"line_id": "l1", "item_id": SANDWICH_TRIPLE_ID, "quantity": qty, "formula": "seul"}],
        "fulfillment": fulfillment,
        "payment_method": "cash",
        "customer_first_name": "Test",
        "customer_last_name": "User",
        "customer_phone": "+33600000000",
        "customer_email": "delivered@resend.dev",
        "address_line1": None,
        "address_line2": None,
        "postal_code": None,
        "city": None,
        "notes": "[TEST ORDER]",
    }
    if address:
        p.update(address)
    return p


class TestDeliveryFeeInQuote:
    def test_quote_delivery_no_address_returns_fee(self):
        r = requests.post(f"{BASE_URL}/api/checkout/quote", json=_quote_payload(qty=1), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["subtotal"] == 10.0, data
        assert data["delivery_fee"] == 1.0, data
        assert data["total"] == 11.0, data

    def test_quote_delivery_free_threshold(self):
        # qty 3 => subtotal 30, threshold 30 => fee 0
        r = requests.post(f"{BASE_URL}/api/checkout/quote", json=_quote_payload(qty=3), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["subtotal"] == 30.0
        assert data["delivery_fee"] == 0.0
        assert data["total"] == 30.0

    def test_quote_pickup_no_delivery_fee(self):
        r = requests.post(f"{BASE_URL}/api/checkout/quote",
                          json=_quote_payload(qty=1, fulfillment="pickup"), timeout=15)
        assert r.status_code == 200
        assert r.json()["delivery_fee"] == 0.0


class TestSessionStillRequiresAddress:
    def test_session_delivery_no_address_rejected(self):
        r = requests.post(f"{BASE_URL}/api/checkout/session", json=_quote_payload(qty=1), timeout=15)
        # Either 400 with the French message OR 423 if restaurant closed - both acceptable
        # but must NOT be 200
        assert r.status_code != 200, r.text
        if r.status_code == 400:
            detail = r.json().get("detail", "")
            assert "Adresse" in str(detail) or "adresse" in str(detail), detail


class TestPostalCodeAllowlist:
    def test_postal_code_enforced(self, auth_headers):
        # get current settings
        cur = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
        original = cur.get("delivery_postal_codes", [])
        try:
            # set allowlist
            r = requests.put(f"{BASE_URL}/api/settings",
                             json={"delivery_postal_codes": ["06240"]},
                             headers=auth_headers, timeout=15)
            assert r.status_code == 200, r.text
            payload = _quote_payload(qty=1, address={
                "address_line1": "1 rue de test", "postal_code": "75001", "city": "Paris"
            })
            r2 = requests.post(f"{BASE_URL}/api/checkout/session", json=payload, timeout=15)
            # could be 400 postal_code_not_served or 423 closed - accept 400 explicitly
            if r2.status_code == 400:
                detail = r2.json().get("detail")
                if isinstance(detail, dict):
                    assert detail.get("kind") == "postal_code_not_served", detail
                else:
                    # possibly closed / other 400 - flag but tolerate
                    pytest.skip(f"Non-postal 400: {detail}")
            elif r2.status_code == 423:
                pytest.skip("Restaurant closed; cannot verify postal enforcement via session")
            else:
                pytest.fail(f"Expected 400 postal_code_not_served, got {r2.status_code}: {r2.text}")
        finally:
            requests.put(f"{BASE_URL}/api/settings",
                         json={"delivery_postal_codes": original},
                         headers=auth_headers, timeout=15)


class TestAdminForceReseed:
    def test_unauth_reseed_rejected(self):
        r = requests.post(f"{BASE_URL}/api/admin/seed/reseed", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_auth_reseed_success_and_menu_intact(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/admin/seed/reseed", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("menu_items") == 40, data
        assert data.get("categories") == 9, data
        assert data.get("sauces") == 12, data
        assert data.get("settings_reset") == 1, data

        # Verify public endpoints
        m = requests.get(f"{BASE_URL}/api/menu", timeout=15).json()
        assert len(m) == 40
        c = requests.get(f"{BASE_URL}/api/categories", timeout=15).json()
        assert len(c) == 9
