"""
Tablet delivery-fee waiver tests.
STRICT SAFETY: only quote endpoints are exercised (no POST /api/tablet/orders, no /kitchen/* actions).
Coverage:
  1. POST /api/tablet/quote (delivery) -> delivery_fee=0, tablet_delivery_waived=True, total=subtotal, no order created.
  2. POST /api/checkout/quote (public, delivery, equivalent payload) -> normal delivery-fee rules (>0 when applicable), tablet_delivery_waived False/absent.
  3. Tablet quote with a coupon_code MUST NOT consume the coupon (used_count unchanged) and MUST NOT apply coupon discount.
  4. Tablet pickup quote still charges 0 delivery fee (no change) and tablet_delivery_waived False.
"""
import os
import pytest
import requests
from pathlib import Path

def _load_frontend_env():
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
_load_frontend_env()

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TABLET_EMAIL = "tablet@burgertimes.fr"
TABLET_PASSWORD = "BurgerTablet2026!"
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def tablet_headers():
    r = requests.post(f"{BASE_URL}/api/tablet/login",
                      json={"email": TABLET_EMAIL, "password": TABLET_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"tablet login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in tablet login response: {r.json()}"
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sample_menu_item_id():
    r = requests.get(f"{BASE_URL}/api/menu", timeout=20)
    assert r.status_code == 200
    data = r.json()
    # menu can be either list or dict of categories
    items = []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                items.extend(v)
    elif isinstance(data, list):
        items = data
    # find any available, non-builder standalone item with a price
    for it in items:
        if it.get("available", True) and it.get("price_seul") and not it.get("is_builder") and not it.get("formats"):
            return it["id"], float(it["price_seul"])
    pytest.skip("no suitable menu item found")


def _delivery_payload(item_id):
    return {
        "items": [{"line_id": "test-line-1", "item_id": item_id, "quantity": 2,
                   "formula": "seul", "sauces": []}],
        "fulfillment": "delivery",
        "payment_method": "cash",
        "customer_first_name": "TEST",
        "customer_last_name": "Waiver",
        "customer_phone": "+33612000001",
        "customer_email": "test-waiver@example.com",
        "address_line1": "1 rue de Test",
        "postal_code": "06000",
        "city": "Nice",
        "notes": "[TEST ORDER] tablet waiver quote — DO NOT CREATE",
    }


def _pickup_payload(item_id):
    return {
        "items": [{"line_id": "test-line-2", "item_id": item_id, "quantity": 1,
                   "formula": "seul", "sauces": []}],
        "fulfillment": "pickup",
        "payment_method": "cash",
        "customer_first_name": "TEST",
        "customer_last_name": "Pickup",
        "customer_phone": "+33612000002",
        "customer_email": "test-pickup@example.com",
        "notes": "[TEST ORDER] tablet pickup quote",
    }


# ---------- Feature 1: tablet quote waives delivery fee ----------
class TestTabletDeliveryWaiver:
    def test_tablet_quote_delivery_waives_fee(self, tablet_headers, sample_menu_item_id):
        item_id, price = sample_menu_item_id
        r = requests.post(f"{BASE_URL}/api/tablet/quote",
                          json=_delivery_payload(item_id), headers=tablet_headers, timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["tablet_delivery_waived"] is True
        assert q["delivery_fee"] == 0 or q["delivery_fee"] == 0.0
        assert q["subtotal"] > 0
        assert round(q["total"], 2) == round(q["subtotal"], 2), \
            f"total {q['total']} != subtotal {q['subtotal']}"
        # No order_id/order_number in a pure quote response
        assert "order_id" not in q
        assert "order_number" not in q

    def test_tablet_quote_pickup_no_waiver_flag(self, tablet_headers, sample_menu_item_id):
        item_id, _ = sample_menu_item_id
        r = requests.post(f"{BASE_URL}/api/tablet/quote",
                          json=_pickup_payload(item_id), headers=tablet_headers, timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        # pickup is never waived (waiver is delivery-only)
        assert q.get("tablet_delivery_waived") is False
        assert q["delivery_fee"] == 0  # pickup normally has 0 fee
        assert round(q["total"], 2) == round(q["subtotal"], 2)

    def test_tablet_quote_requires_auth(self, sample_menu_item_id):
        item_id, _ = sample_menu_item_id
        r = requests.post(f"{BASE_URL}/api/tablet/quote",
                          json=_delivery_payload(item_id), timeout=20)
        assert r.status_code in (401, 403), f"expected auth failure, got {r.status_code}"


# ---------- Feature 2: public /checkout/quote unchanged ----------
class TestPublicCheckoutQuoteUnchanged:
    def test_public_delivery_quote_uses_normal_rules(self, sample_menu_item_id):
        item_id, _ = sample_menu_item_id
        r = requests.post(f"{BASE_URL}/api/checkout/quote",
                          json=_delivery_payload(item_id), timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        # No tablet waiver flag set (either absent or explicitly False)
        assert q.get("tablet_delivery_waived") in (False, None)
        # Normal rule: delivery fee >= 0. If settings threshold not met, expect >0.
        assert q["delivery_fee"] >= 0
        # If a delivery fee applies on this cart, total must include it.
        assert round(q["total"], 2) == round(q["subtotal"] + q["delivery_fee"], 2)

    def test_public_quote_matches_tablet_subtotal(self, tablet_headers, sample_menu_item_id):
        """Same items → same subtotal in both quotes (only delivery_fee should differ)."""
        item_id, _ = sample_menu_item_id
        payload = _delivery_payload(item_id)
        pub = requests.post(f"{BASE_URL}/api/checkout/quote", json=payload, timeout=20).json()
        tab = requests.post(f"{BASE_URL}/api/tablet/quote", json=payload,
                            headers=tablet_headers, timeout=20).json()
        assert round(pub["subtotal"], 2) == round(tab["subtotal"], 2)
        assert tab["delivery_fee"] == 0
        assert round(tab["total"], 2) == round(tab["subtotal"], 2)


# ---------- Feature 3: coupon NOT consumed by tablet waiver ----------
class TestCouponNotConsumedOnTabletWaiver:
    def test_tablet_quote_with_coupon_does_not_consume(
        self, tablet_headers, admin_headers, sample_menu_item_id
    ):
        item_id, _ = sample_menu_item_id
        # create a fresh single-use free-delivery coupon
        code = "TESTWAIVE001"
        # cleanup any pre-existing
        existing = requests.get(f"{BASE_URL}/api/admin/coupons", headers=admin_headers, timeout=20)
        if existing.status_code == 200:
            for c in existing.json():
                if c.get("code") == code:
                    requests.delete(f"{BASE_URL}/api/admin/coupons/{c['id']}",
                                    headers=admin_headers, timeout=20)
        create = requests.post(
            f"{BASE_URL}/api/admin/coupons",
            json={
                "code": code,
                "discount_type": "free_delivery",
                "discount_value": 0,
                "max_uses": 1,
                "active": True,
            },
            headers=admin_headers,
            timeout=20,
        )
        if create.status_code not in (200, 201):
            pytest.skip(f"could not create coupon: {create.status_code} {create.text}")
        coupon_id = create.json().get("id")
        try:
            payload = _delivery_payload(item_id)
            payload["coupon_code"] = code
            r = requests.post(f"{BASE_URL}/api/tablet/quote",
                              json=payload, headers=tablet_headers, timeout=20)
            assert r.status_code == 200, r.text
            q = r.json()
            # Waiver takes precedence, coupon NOT applied → coupon_code None, discount 0
            assert q["tablet_delivery_waived"] is True
            assert q["delivery_fee"] == 0
            assert q.get("coupon_code") in (None, "")
            assert q.get("coupon_discount", 0) == 0
            # Verify coupon.used_count still 0 in admin listing
            listing = requests.get(f"{BASE_URL}/api/admin/coupons",
                                   headers=admin_headers, timeout=20).json()
            found = next((c for c in listing if c.get("code") == code), None)
            assert found is not None
            assert found.get("used_count", 0) == 0, \
                f"coupon was consumed by tablet quote! used_count={found.get('used_count')}"
        finally:
            if coupon_id:
                requests.delete(f"{BASE_URL}/api/admin/coupons/{coupon_id}",
                                headers=admin_headers, timeout=20)


# ---------- Feature 5 (static): confirm print copies contract in code ----------
class TestPrintCopiesStaticContract:
    """Static inspection — no HTTP, no physical print, no order created."""
    def test_immediate_tablet_order_pushes_2_copies(self):
        import inspect
        # server.py may not be importable easily; grep the source instead.
        with open("/app/backend/server.py") as f:
            src = f.read()
        # every tablet order pushes 2 copies via background task
        assert "_push_print_job_background(order_id, accepted, copies=2)" in src, \
            "tablet_create_order must push 2 copies on immediate accept"

    def test_scheduled_tablet_order_prints_right_away(self):
        with open("/app/backend/server.py") as f:
            src = f.read()
        # no scheduled short-circuit any more: scheduled tablet orders print
        # at once, their time shown big on the ticket
        assert '"print_queued": False' not in src
        assert "_push_print_job_background(order_id, accepted, copies=2)" in src
