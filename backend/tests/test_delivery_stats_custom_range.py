"""Regression tests for GET /api/admin/stats/delivery-fees custom range + by_payment.

Tests the new features:
- Custom start_date/end_date query params override `days`
- Response contains is_custom_range, range_start, range_end
- by_payment breakdown with cash / card_in_person keys
- Validation errors on invalid ranges
- Backward compatibility with ?days= only
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_custom_range_returns_ok_with_expected_keys(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/admin/stats/delivery-fees",
        params={"start_date": "2026-01-01", "end_date": "2026-01-14"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_custom_range"] is True
    assert data["range_start"] == "2026-01-01"
    assert data["range_end"] == "2026-01-14"
    assert "by_payment" in data
    assert "cash" in data["by_payment"]
    assert "card_in_person" in data["by_payment"]
    for key in ("cash", "card_in_person"):
        assert "delivery_fees" in data["by_payment"][key]
        assert "subtotal" in data["by_payment"][key]
        assert "orders" in data["by_payment"][key]


def test_end_date_before_start_date_returns_400(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/admin/stats/delivery-fees",
        params={"start_date": "2026-02-14", "end_date": "2026-02-01"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 400
    assert "postérieure" in r.text or "start_date" in r.text.lower() or "date" in r.text.lower()


def test_invalid_date_format_returns_400(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/admin/stats/delivery-fees",
        params={"start_date": "not-a-date", "end_date": "2026-02-01"},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 400


def test_backward_compat_days_only(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/admin/stats/delivery-fees",
        params={"days": 7},
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_custom_range"] is False
    assert data["range_days"] == 7
    # Backward compat now ALSO returns by_payment key
    assert "by_payment" in data
    assert "cash" in data["by_payment"]
    assert "card_in_person" in data["by_payment"]


def test_no_auth_returns_401(auth_headers):
    r = requests.get(
        f"{BASE_URL}/api/admin/stats/delivery-fees",
        params={"days": 7},
        timeout=30,
    )
    assert r.status_code in (401, 403)


def test_kitchen_test_print_requires_auth():
    """Verify the endpoint EXISTS and rejects unauth requests. Do NOT auth+call (would fire a real print)."""
    r = requests.post(f"{BASE_URL}/api/kitchen/test-print", timeout=30)
    # Must not be 404 (endpoint exists) and must not be 200 (no unauth prints).
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}: {r.text}"
