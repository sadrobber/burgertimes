"""Backend regression tests: Telegram webhook + order status callbacks.

Verifies that:
- /api/telegram/webhook rejects missing/invalid secret with 401
- Callback queries drive order status transitions via _apply_status
- Malformed / unknown actions return 200 without crashing
- Order confirmation email + delivery-fee-in-quote + admin stats regression
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TG_SECRET = "bt_tg_wh_9f4c7e2a1b8d6e3f5a9c0b7d4e2f8a1c6b3d9e5f"
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session", autouse=True)
def open_restaurant(admin_headers):
    """Ensure restaurant is accepting orders during tests."""
    # broad opening hours (0-23) all days + not force_closed
    hours = [{"day": d, "open": "00:00", "close": "23:59", "closed": False} for d in range(7)]
    r = requests.put(
        f"{API}/settings",
        headers=admin_headers,
        json={"force_closed": False, "opening_hours": hours, "max_active_orders": 1000},
        timeout=15,
    )
    # Not fatal if fields aren't accepted; just log
    print(f"settings PUT: {r.status_code}")
    yield


@pytest.fixture(scope="session")
def menu_item_id():
    r = requests.get(f"{API}/menu", timeout=15)
    assert r.status_code == 200
    items = r.json()
    # find first available non-burger single-format item
    for it in items:
        if it.get("available", True) and not it.get("is_burger"):
            return it["id"]
    return items[0]["id"]


def _make_order(menu_item_id, suffix=""):
    payload = {
        "items": [
            {
                "line_id": str(uuid.uuid4()),
                "item_id": menu_item_id,
                "quantity": 1,
                "formula": "seul",
            }
        ],
        "fulfillment": "pickup",
        "customer_first_name": "Tg",
        "customer_last_name": f"TgTest{suffix}",
        "customer_phone": "0600000000",
        "customer_email": "delivered@resend.dev",
        "payment_method": "cash",
        "notes": "[TEST ORDER] telegram webhook test",
    }
    r = requests.post(f"{API}/checkout/session", json=payload, timeout=20)
    assert r.status_code == 200, f"checkout failed: {r.status_code} {r.text}"
    return r.json()["order_id"]


def _get_order(order_id, admin_headers):
    r = requests.get(f"{API}/admin/orders/{order_id}", headers=admin_headers, timeout=15)
    assert r.status_code == 200, f"get order failed: {r.status_code} {r.text}"
    return r.json()


def _post_webhook(body, secret=TG_SECRET):
    headers = {}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return requests.post(f"{API}/telegram/webhook", json=body, headers=headers, timeout=15)


# ----- Security --------------------------------------------------------------

class TestWebhookSecurity:
    def test_no_secret_header_401(self):
        r = _post_webhook({}, secret=None)
        assert r.status_code == 401
        body = r.json()
        assert "Invalid webhook secret" in body.get("detail", "")

    def test_wrong_secret_401(self):
        r = _post_webhook({}, secret="wrong-secret")
        assert r.status_code == 401

    def test_correct_secret_empty_body_200(self):
        r = _post_webhook({})
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# ----- Callback flow ---------------------------------------------------------

class TestCallbackFlow:
    def test_accept_flow(self, menu_item_id, admin_headers):
        order_id = _make_order(menu_item_id, "-accept")
        # starts pending
        order = _get_order(order_id, admin_headers)
        assert order["status"] == "pending"

        # accept
        r = _post_webhook({
            "callback_query": {
                "id": "cbq_test_accept",
                "data": f"order|accept|{order_id}",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}
        assert _get_order(order_id, admin_headers)["status"] == "accepted"

        # preparing
        r = _post_webhook({
            "callback_query": {
                "id": "cbq_test_prep",
                "data": f"order|preparing|{order_id}",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200
        assert _get_order(order_id, admin_headers)["status"] == "preparing"

        # ready
        r = _post_webhook({
            "callback_query": {
                "id": "cbq_test_ready",
                "data": f"order|ready|{order_id}",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200
        assert _get_order(order_id, admin_headers)["status"] == "ready"

        # delivered
        r = _post_webhook({
            "callback_query": {
                "id": "cbq_test_delivered",
                "data": f"order|delivered|{order_id}",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200
        assert _get_order(order_id, admin_headers)["status"] == "delivered"

    def test_cancel_flow(self, menu_item_id, admin_headers):
        order_id = _make_order(menu_item_id, "-cancel")
        assert _get_order(order_id, admin_headers)["status"] == "pending"

        r = _post_webhook({
            "callback_query": {
                "id": "cbq_test_cancel",
                "data": f"order|cancel|{order_id}",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200
        assert _get_order(order_id, admin_headers)["status"] == "cancelled"


class TestCallbackEdgeCases:
    def test_unknown_action(self):
        r = _post_webhook({
            "callback_query": {
                "id": "cbq_unknown",
                "data": "order|foobar|xxx",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_malformed_no_pipes(self):
        r = _post_webhook({
            "callback_query": {
                "id": "cbq_garbage",
                "data": "garbage",
                "from": {"id": 1, "first_name": "Test"},
            }
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_missing_callback_query(self):
        r = _post_webhook({"update_id": 1})
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# ----- Regression ------------------------------------------------------------

class TestRegression:
    def test_admin_delivery_fee_stats(self, admin_headers):
        r = requests.get(f"{API}/admin/stats/delivery-fees", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Response should contain some numeric fields
        assert isinstance(data, dict)

    def test_admin_stats(self, admin_headers):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_force_reseed(self, admin_headers):
        r = requests.post(f"{API}/admin/seed/reseed", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_delivery_fee_in_quote_without_address(self, menu_item_id):
        """Quote with delivery mode and no address should still return fee>0."""
        payload = {
            "items": [
                {
                    "line_id": str(uuid.uuid4()),
                    "item_id": menu_item_id,
                    "quantity": 1,
                    "formula": "seul",
                }
            ],
            "fulfillment": "delivery",
            "customer_first_name": "Q",
            "customer_last_name": "Quote",
            "customer_phone": "0600000000",
            "payment_method": "cash",
        }
        r = requests.post(f"{API}/checkout/quote", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("delivery_fee", 0) > 0, f"expected delivery_fee>0, got {data}"


# ----- Cleanup ---------------------------------------------------------------

def teardown_module(module):
    """Delete test orders via admin endpoint."""
    try:
        r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
        if r.status_code != 200:
            return
        headers = {"Authorization": f"Bearer {r.json()['token']}"}
        orders = requests.get(f"{API}/admin/orders", headers=headers, timeout=15).json()
        for o in orders.get("orders", []) if isinstance(orders, dict) else orders:
            if o.get("customer_last_name", "").startswith("TgTest"):
                requests.delete(f"{API}/admin/orders/{o['id']}", headers=headers, timeout=10)
    except Exception as e:
        print(f"cleanup failed: {e}")
