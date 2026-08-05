"""Tests for GET /api/admin/stats/delivery-fees."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


# --- Auth ---
def test_auth_required_no_token():
    r = requests.get(f"{API}/admin/stats/delivery-fees?days=30", timeout=15)
    assert r.status_code in (401, 403), r.status_code


# --- Shape ---
def test_shape_days_7(auth_headers):
    r = requests.get(f"{API}/admin/stats/delivery-fees?days=7", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    for key in ["range_days", "timezone", "totals", "counts", "subtotals", "daily"]:
        assert key in body, f"missing {key}"
    assert body["range_days"] == 7
    for k in ["today", "this_week", "this_month", "all_time", "in_range"]:
        assert k in body["totals"] and isinstance(body["totals"][k], (int, float))
    assert isinstance(body["daily"], list) and len(body["daily"]) == 7
    for i, d in enumerate(body["daily"]):
        assert set(d.keys()) >= {"date", "orders", "delivery_fees", "subtotal"}
        assert isinstance(d["orders"], int)
        # sorted asc
        if i > 0:
            assert d["date"] > body["daily"][i - 1]["date"]


# --- Range param validation ---
def test_range_days_1(auth_headers):
    r = requests.get(f"{API}/admin/stats/delivery-fees?days=1", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert len(r.json()["daily"]) == 1


def test_range_days_365(auth_headers):
    r = requests.get(f"{API}/admin/stats/delivery-fees?days=365", headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert len(r.json()["daily"]) == 365


def test_range_days_zero_invalid(auth_headers):
    r = requests.get(f"{API}/admin/stats/delivery-fees?days=0", headers=auth_headers, timeout=15)
    assert r.status_code == 422


def test_range_days_over_max_invalid(auth_headers):
    r = requests.get(f"{API}/admin/stats/delivery-fees?days=400", headers=auth_headers, timeout=15)
    assert r.status_code == 422


# --- Aggregation correctness with seeded orders ---
def test_aggregation_with_seed(auth_headers, db):
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat().replace("+00:00", "Z")
    yesterday_iso = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    two_days_ago_iso = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")

    import uuid
    def _on():
        return f"BT-TEST-{uuid.uuid4().hex[:8].upper()}"
    seed = [
        {"id": "test-stat-1", "order_number": _on(), "fulfillment": "delivery", "status": "delivered", "subtotal": 20, "delivery_fee": 2, "total": 22, "created_at": today_iso},
        {"id": "test-stat-2", "order_number": _on(), "fulfillment": "delivery", "status": "delivered", "subtotal": 15, "delivery_fee": 1.5, "total": 16.5, "created_at": yesterday_iso},
        {"id": "test-stat-3", "order_number": _on(), "fulfillment": "delivery", "status": "delivered", "subtotal": 25, "delivery_fee": 2.5, "total": 27.5, "created_at": yesterday_iso},
        {"id": "test-stat-4", "order_number": _on(), "fulfillment": "pickup", "status": "delivered", "subtotal": 12, "delivery_fee": 0, "total": 12, "created_at": today_iso},
        {"id": "test-stat-5", "order_number": _on(), "fulfillment": "delivery", "status": "cancelled", "subtotal": 10, "delivery_fee": 1, "total": 11, "created_at": two_days_ago_iso},
    ]
    # Clean prior + insert
    db.orders.delete_many({"id": {"$regex": "^test-stat-"}})
    db.orders.insert_many(seed)

    try:
        r = requests.get(f"{API}/admin/stats/delivery-fees?days=7", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()

        # NOTE: real orders may exist in preview but request says there are none.
        # We assert deltas relative to seeded data expectations.
        totals = body["totals"]
        counts = body["counts"]
        # Only delivered + delivery orders count. pickup and cancelled excluded.
        assert totals["all_time"] >= 6.0
        assert counts["all_time"] >= 3

        # Find today's & yesterday's rows
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(body.get("timezone") or "Europe/Paris")
        today_key = datetime.now(tz).strftime("%Y-%m-%d")
        yday_key = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")
        by_date = {d["date"]: d for d in body["daily"]}
        assert today_key in by_date
        assert yday_key in by_date
        # today seed contributes 2.0; yesterday seed contributes 4.0
        assert by_date[today_key]["delivery_fees"] >= 2.0
        assert by_date[yday_key]["delivery_fees"] >= 4.0
        # No seed contribution should exist for a day 5 days back (unless real data)
    finally:
        db.orders.delete_many({"id": {"$regex": "^test-stat-"}})
