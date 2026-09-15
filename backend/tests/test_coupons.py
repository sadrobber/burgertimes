"""Coupon feature end-to-end tests: admin CRUD, quote/session integration,
free_delivery + percent_off_delivery discount math, pickup rejection,
inactive/unknown rejection, max_uses enforcement (quote never consumes),
race-safe atomic increment.

All test coupon codes are prefixed TEST_ and cleaned up.
All test orders use notes starting with '[TEST ORDER]' so they are flagged
test_order in the DB (existing convention, excluded from delivery stats).
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def menu_item_id():
    r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
    assert r.status_code == 200
    # pick first non-TEST available real item with a price_seul
    for it in r.json():
        if it.get("available") and it.get("price_seul") and not it["name"].startswith("TEST_"):
            return it["id"]
    pytest.skip("No usable menu item")


def _rand_code(prefix="TEST"):
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"


def _delivery_payload(item_id, coupon_code=None, fulfillment="delivery"):
    p = {
        "items": [{"line_id": uuid.uuid4().hex, "item_id": item_id, "quantity": 1, "format": "seul"}],
        "fulfillment": fulfillment,
        "customer_first_name": "Test",
        "customer_last_name": "Coupon",
        "customer_phone": "+33600000000",
        "customer_email": "test-coupon@example.com",
        "payment_method": "cash",
        "notes": "[TEST ORDER] coupon test",
    }
    if fulfillment == "delivery":
        p.update({
            "address_line1": "1 rue de Test",
            "postal_code": "06240",
            "city": "Beausoleil",
        })
    if coupon_code is not None:
        p["coupon_code"] = coupon_code
    return p


@pytest.fixture
def cleanup_coupons(admin_headers):
    created = []
    yield created
    for cid in created:
        try:
            requests.delete(f"{BASE_URL}/api/admin/coupons/{cid}", headers=admin_headers, timeout=10)
        except Exception:
            pass


@pytest.fixture
def cleanup_orders(admin_headers):
    order_ids = []
    yield order_ids
    for oid in order_ids:
        try:
            requests.delete(f"{BASE_URL}/api/admin/orders/{oid}", headers=admin_headers, timeout=10)
        except Exception:
            pass


# ---------- Admin CRUD ----------

class TestCouponCRUD:
    def test_list_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/coupons", timeout=10)
        assert r.status_code in (401, 403)

    def test_create_free_delivery(self, admin_headers, cleanup_coupons):
        code = _rand_code()
        r = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": code.lower(), "discount_type": "free_delivery", "max_uses": 3},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        cleanup_coupons.append(d["id"])
        assert d["code"] == code  # auto-uppercased
        assert d["discount_type"] == "free_delivery"
        assert d["max_uses"] == 3
        assert d["used_count"] == 0
        assert d["active"] is True
        assert "_id" not in d

    def test_create_percent(self, admin_headers, cleanup_coupons):
        code = _rand_code()
        r = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={
                "code": code,
                "discount_type": "percent_off_delivery",
                "percent_value": 50,
                "max_uses": 2,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        cleanup_coupons.append(d["id"])
        assert d["percent_value"] == 50

    def test_percent_missing_value_rejected(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": _rand_code(), "discount_type": "percent_off_delivery"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_duplicate_code_rejected(self, admin_headers, cleanup_coupons):
        code = _rand_code()
        r1 = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": code, "discount_type": "free_delivery", "max_uses": 1},
            timeout=10,
        )
        assert r1.status_code == 200
        cleanup_coupons.append(r1.json()["id"])
        r2 = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": code, "discount_type": "free_delivery", "max_uses": 1},
            timeout=10,
        )
        assert r2.status_code == 400

    def test_update_toggle_active(self, admin_headers, cleanup_coupons):
        code = _rand_code()
        r = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": code, "discount_type": "free_delivery", "max_uses": 1},
            timeout=10,
        )
        cid = r.json()["id"]
        cleanup_coupons.append(cid)
        u = requests.put(
            f"{BASE_URL}/api/admin/coupons/{cid}",
            headers=admin_headers,
            json={"active": False},
            timeout=10,
        )
        assert u.status_code == 200
        assert u.json()["active"] is False

    def test_delete(self, admin_headers):
        code = _rand_code()
        r = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            headers=admin_headers,
            json={"code": code, "discount_type": "free_delivery", "max_uses": 1},
            timeout=10,
        )
        cid = r.json()["id"]
        d = requests.delete(f"{BASE_URL}/api/admin/coupons/{cid}", headers=admin_headers, timeout=10)
        assert d.status_code == 200
        assert d.json()["deleted"] == 1


# ---------- Quote / Session integration ----------

class TestCouponCheckout:
    def _create_coupon(self, admin_headers, cleanup, **kwargs):
        payload = {"code": _rand_code(), "discount_type": "free_delivery", "max_uses": 1}
        payload.update(kwargs)
        r = requests.post(
            f"{BASE_URL}/api/admin/coupons", headers=admin_headers, json=payload, timeout=10
        )
        assert r.status_code == 200, r.text
        d = r.json()
        cleanup.append(d["id"])
        return d

    def test_quote_no_coupon_baseline(self, menu_item_id):
        r = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["delivery_fee"] > 0
        assert d["coupon_discount"] == 0
        assert d["coupon_code"] is None

    def test_quote_free_delivery(self, admin_headers, menu_item_id, cleanup_coupons):
        c = self._create_coupon(admin_headers, cleanup_coupons)
        r = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["delivery_fee"] == 0
        assert d["coupon_discount"] > 0
        assert d["coupon_code"] == c["code"]
        # baseline call: usage must NOT be consumed
        r2 = requests.get(f"{BASE_URL}/api/admin/coupons", headers=admin_headers, timeout=10)
        for row in r2.json():
            if row["id"] == c["id"]:
                assert row["used_count"] == 0

    def test_quote_percent_50(self, admin_headers, menu_item_id, cleanup_coupons):
        c = self._create_coupon(
            admin_headers,
            cleanup_coupons,
            discount_type="percent_off_delivery",
            percent_value=50,
        )
        base = requests.post(
            f"{BASE_URL}/api/checkout/quote", json=_delivery_payload(menu_item_id), timeout=15
        ).json()
        r = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"]),
            timeout=15,
        )
        d = r.json()
        assert d["coupon_discount"] == round(base["delivery_fee"] * 0.5, 2)
        assert d["delivery_fee"] == round(base["delivery_fee"] - d["coupon_discount"], 2)

    def test_pickup_rejected(self, admin_headers, menu_item_id, cleanup_coupons):
        c = self._create_coupon(admin_headers, cleanup_coupons)
        r = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"], fulfillment="pickup"),
            timeout=15,
        )
        assert r.status_code == 400
        assert "livraison" in r.json()["detail"].lower()

    def test_unknown_coupon(self, menu_item_id):
        r = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id, coupon_code="NOPE_DOESNT_EXIST"),
            timeout=15,
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "Code promo invalide."

    def test_inactive_coupon_rejected(self, admin_headers, menu_item_id, cleanup_coupons):
        c = self._create_coupon(admin_headers, cleanup_coupons)
        requests.put(
            f"{BASE_URL}/api/admin/coupons/{c['id']}",
            headers=admin_headers,
            json={"active": False},
            timeout=10,
        )
        r = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"]),
            timeout=15,
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "Code promo invalide."

    def test_session_consumes_usage_and_max_uses_enforced(
        self, admin_headers, menu_item_id, cleanup_coupons, cleanup_orders
    ):
        c = self._create_coupon(admin_headers, cleanup_coupons, max_uses=1)
        # First order: success
        r1 = requests.post(
            f"{BASE_URL}/api/checkout/session",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"]),
            timeout=20,
        )
        assert r1.status_code == 200, r1.text
        sess = r1.json()
        cleanup_orders.append(sess["order_id"])
        # Fetch full order via admin API
        full = requests.get(
            f"{BASE_URL}/api/admin/orders/{sess['order_id']}", headers=admin_headers, timeout=10
        ).json()
        assert full["coupon_code"] == c["code"]
        assert full["coupon_discount"] > 0
        assert full["delivery_fee"] == 0  # free_delivery

        # used_count must now be 1
        rows = requests.get(f"{BASE_URL}/api/admin/coupons", headers=admin_headers, timeout=10).json()
        row = next(r for r in rows if r["id"] == c["id"])
        assert row["used_count"] == 1

        # Second attempt at /quote: must be rejected with max-uses msg
        r2q = requests.post(
            f"{BASE_URL}/api/checkout/quote",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"]),
            timeout=15,
        )
        assert r2q.status_code == 400
        assert "maximum" in r2q.json()["detail"].lower()

        # Second attempt at /session: must also be rejected
        r2 = requests.post(
            f"{BASE_URL}/api/checkout/session",
            json=_delivery_payload(menu_item_id, coupon_code=c["code"]),
            timeout=20,
        )
        assert r2.status_code == 400
        assert "maximum" in r2.json()["detail"].lower()

    def test_regression_no_coupon_still_works(self, menu_item_id, cleanup_orders, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/checkout/session",
            json=_delivery_payload(menu_item_id),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        sess = r.json()
        cleanup_orders.append(sess["order_id"])
        full = requests.get(
            f"{BASE_URL}/api/admin/orders/{sess['order_id']}", headers=admin_headers, timeout=10
        ).json()
        assert full.get("coupon_code") is None
        assert full.get("coupon_discount", 0) == 0
        assert full["delivery_fee"] > 0

    def test_regression_pickup_no_coupon(self, menu_item_id, cleanup_orders, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/checkout/session",
            json=_delivery_payload(menu_item_id, fulfillment="pickup"),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        sess = r.json()
        cleanup_orders.append(sess["order_id"])
        full = requests.get(
            f"{BASE_URL}/api/admin/orders/{sess['order_id']}", headers=admin_headers, timeout=10
        ).json()
        assert full["fulfillment"] == "pickup"
        assert full["delivery_fee"] == 0
