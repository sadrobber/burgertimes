"""Tablet-source isolation tests for admin reporting endpoints.

Uses direct MongoDB inserts (never POST /orders) to create TEST-prefixed orders,
one web (order_source missing) and one tablet (order_source='tablet').
Verifies admin listing + stats endpoints exclude/include correctly.
Cleans up TEST docs unconditionally in finally.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "chahineisgoated@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "BurgerTimes2026!")

TEST_TAG = "TEST_TABLET_ISOL"
WEB_ID = f"{TEST_TAG}_WEB_{uuid.uuid4().hex[:8]}"
TABLET_ID = f"{TEST_TAG}_TAB_{uuid.uuid4().hex[:8]}"
WEB_TOTAL = 42.42
TABLET_TOTAL = 77.77
WEB_FEE = 5.0
TABLET_FEE = 6.5


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup(mongo_db):
    """Insert TEST web + tablet delivery orders directly. Cleanup unconditionally."""
    now = datetime.now(timezone.utc).isoformat()
    web_doc = {
        "id": WEB_ID,
        "status": "delivered",
        "fulfillment": "delivery",
        "total": WEB_TOTAL,
        "subtotal": WEB_TOTAL - WEB_FEE,
        "delivery_fee": WEB_FEE,
        "created_at": now,
        "notes": "[TEST ORDER] web isolation",
        "items": [],
        "order_number": f"TEST-W-{uuid.uuid4().hex[:6]}",
        # deliberately no order_source (historic/web)
    }
    tablet_doc = {
        "id": TABLET_ID,
        "status": "delivered",
        "fulfillment": "delivery",
        "total": TABLET_TOTAL,
        "subtotal": TABLET_TOTAL - TABLET_FEE,
        "delivery_fee": TABLET_FEE,
        "created_at": now,
        "notes": "[TEST ORDER] tablet isolation",
        "items": [],
        "order_number": f"TEST-T-{uuid.uuid4().hex[:6]}",
        "order_source": "tablet",
    }
    try:
        mongo_db.orders.insert_one(web_doc)
        mongo_db.orders.insert_one(tablet_doc)
        yield
    finally:
        mongo_db.orders.delete_many({"id": {"$in": [WEB_ID, TABLET_ID]}})
        mongo_db.orders.delete_many({"notes": {"$regex": TEST_TAG}})


class TestTabletIsolation:
    def test_admin_orders_excludes_tablet_includes_web(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/orders?limit=500", headers=auth_headers)
        assert r.status_code == 200
        ids = {o.get("id") for o in r.json()}
        assert WEB_ID in ids, "web/historic order missing from /admin/orders"
        assert TABLET_ID not in ids, "tablet order leaked into /admin/orders"

    def test_admin_tablet_orders_includes_only_tablet(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/tablet/orders?limit=500", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        ids = {o.get("id") for o in data}
        assert TABLET_ID in ids
        assert WEB_ID not in ids
        for o in data:
            assert o.get("order_source") == "tablet"

    def test_admin_stats_excludes_tablet(self, auth_headers, mongo_db):
        # Baseline: sum of all non-tablet, non-void totals should include WEB_TOTAL and not TABLET_TOTAL
        r = requests.get(f"{BASE_URL}/api/admin/stats", headers=auth_headers)
        assert r.status_code == 200
        stats = r.json()
        assert "revenue" in stats and "total_orders" in stats
        # Ensure the tablet total is not double-counted: compute independent sum from DB
        docs = list(
            mongo_db.orders.find(
                {"order_source": {"$ne": "tablet"}, "test_order": {"$ne": True}}
            )
        )
        expected_rev = round(
            sum(float(d.get("total", 0.0)) for d in docs if d.get("status") not in {"cancelled", "expired"}),
            2,
        )
        assert abs(stats["revenue"] - expected_rev) < 0.01, (
            f"revenue mismatch stats={stats['revenue']} expected={expected_rev}"
        )

    def test_admin_stats_tablet_counts_tablet_only(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/stats/tablet", headers=auth_headers)
        assert r.status_code == 200
        stats = r.json()
        # Tablet stats endpoint filters test_order=True; our seed has no test_order flag so it should count
        assert stats["total_orders"] >= 1
        assert stats["revenue"] >= TABLET_TOTAL - 0.01
        assert stats["delivery_orders"] >= 1

    def test_admin_delivery_fee_stats_excludes_tablet(self, auth_headers, mongo_db):
        r = requests.get(f"{BASE_URL}/api/admin/stats/delivery-fees?days=30", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "totals" in data and "daily" in data
        # Ensure aggregated fees do not include the tablet fee
        # Independent DB check: exclude tablet & test_order & void
        docs = list(
            mongo_db.orders.find(
                {
                    "fulfillment": "delivery",
                    "status": {"$nin": ["cancelled", "expired"]},
                    "test_order": {"$ne": True},
                    "order_source": {"$ne": "tablet"},
                }
            )
        )
        expected_all_time = round(sum(float(d.get("delivery_fee", 0.0) or 0.0) for d in docs), 2)
        assert abs(data["totals"]["all_time"] - expected_all_time) < 0.01, (
            f"delivery-fees all_time mismatch api={data['totals']['all_time']} expected={expected_all_time}"
        )
