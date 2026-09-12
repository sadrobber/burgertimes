"""End-to-end backend tests for the /kitchen tablet feature.

Covers:
- Kitchen auth (login success/failure, /me)
- Route protection (kitchen token forbidden on admin routes)
- Order creation via customer checkout (with temporary hours-widening if closed)
- /kitchen/orders listing tabs (new/accepted/declined)
- Accept flow (moves to accepted; the backend fire-and-forget-pushes the
  ticket to the restaurant's Raspberry Pi print-bridge — no more client-side
  window.print(). kitchen_print_status ends up "printed" if the Pi/tunnel
  was reachable, "pending" otherwise — either is a valid outcome in CI since
  the Pi lives outside this environment's network)
- mark-printed: manual override endpoint (staff can flag printed even if
  the automated push failed) + reprint: manually re-push the ticket
- Decline flow (with reason)
- Idempotency of accept/decline
- Admin PUT /admin/orders/{id}/status still works (regression via shared helper)
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

def _load_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # fallback: read from frontend .env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()

# Force pytest-xdist to schedule EVERY test in this module onto the SAME
# worker process. This module widens the shared /api/settings opening-hours
# singleton for its session-scoped `ensure_open` fixture — if two xdist
# workers each ran their own copy of that fixture against the same shared
# backend/DB, one worker's teardown (restoring "original" hours it captured
# BEFORE the other worker widened them) could permanently clobber the real
# restaurant hours. Co-locating on one worker eliminates that race entirely.
pytestmark = pytest.mark.xdist_group(name="kitchen_flow_serial")

ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"
KITCHEN_EMAIL = "cuisine@burgertimes.fr"
KITCHEN_PASSWORD = "CuisineBT2026!"


# ---------- fixtures ---------------------------------------------------------


@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def kitchen_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/kitchen/login",
        json={"email": KITCHEN_EMAIL, "password": KITCHEN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Kitchen login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["user"]["role"] == "kitchen"
    return data["token"]


@pytest.fixture(scope="session")
def hdr_admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def hdr_kitchen(kitchen_token):
    return {"Authorization": f"Bearer {kitchen_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def ensure_open(hdr_admin):
    """Widen today's opening hours so checkout doesn't get blocked. Restore after.

    Safe to widen/restore unconditionally: `pytestmark = xdist_group(...)`
    above guarantees this whole module (and therefore this fixture) only
    ever runs inside a single worker process, so there is no other worker
    racing on the shared /api/settings singleton.
    """
    s = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
    original_hours = s.get("hours_per_day", {}) or {}
    wide = {}
    for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
        wide[day] = {"is_open": True, "ranges": [{"open": "00:00", "close": "23:59"}]}
    r = requests.put(
        f"{BASE_URL}/api/settings",
        headers=hdr_admin,
        json={"hours_per_day": wide},
        timeout=15,
    )
    assert r.status_code == 200, f"Could not widen hours: {r.status_code} {r.text}"
    yield
    try:
        requests.put(
            f"{BASE_URL}/api/settings",
            headers=hdr_admin,
            json={"hours_per_day": original_hours},
            timeout=15,
        )
    except Exception as e:
        print(f"WARN: failed to restore hours: {e}")


def _pick_simple_menu_item():
    r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    # prefer a non-burger, non-tacos, no-format item with price_seul
    for it in items:
        if it.get("is_burger") or it.get("category") in ("burgers", "tacos"):
            continue
        if it.get("available") is False:
            continue
        if it.get("formats"):
            continue
        if it.get("price_seul"):
            return it
    for it in items:
        if it.get("price_seul") or it.get("price"):
            return it
    return None


@pytest.fixture(scope="session")
def created_order_ids(ensure_open, hdr_admin):
    """Track order ids to clean up at teardown."""
    ids = []
    yield ids
    for oid in ids:
        try:
            requests.delete(f"{BASE_URL}/api/admin/orders/{oid}", headers=hdr_admin, timeout=15)
        except Exception:
            pass


def _create_test_order(created_order_ids) -> str:
    item = _pick_simple_menu_item()
    assert item is not None, "No suitable menu item found for test order"
    payload = {
        "items": [
            {
                "line_id": str(uuid.uuid4()),
                "item_id": item["id"],
                "quantity": 1,
                "formula": "seul",
                "sauces": [],
                "notes": "TEST item note - extra pickle",
                "is_burger": False,
            }
        ],
        "fulfillment": "pickup",
        "customer_first_name": "Test",
        "customer_last_name": "Kitchen",
        "customer_phone": "+33600000000",
        "customer_email": "kitchen-test@example.com",
        "notes": "[TEST ORDER] Kitchen flow automated test",
        "payment_method": "cash",
    }
    r = requests.post(f"{BASE_URL}/api/checkout/session", json=payload, timeout=20)
    assert r.status_code == 200, f"Checkout failed: {r.status_code} {r.text}"
    body = r.json()
    # Response could nest order under different keys — try common shapes
    order = body.get("order") or body
    oid = order.get("id") or order.get("order_id")
    assert oid, f"No order id in response: {body}"
    created_order_ids.append(oid)
    return oid


# ---------- all tests below share ONE class so pytest-xdist's default ------
# ---------- "loadscope" strategy keeps them on the same worker -------------
#
# (loadscope groups test METHODS by class and free functions by module — with
# 6 separate classes, different classes could land on different xdist
# workers, and the session-scoped `ensure_open` fixture below would then race
# across workers on the shared /api/settings singleton, permanently
# clobbering real opening hours. One class == one scope == one worker.)


class TestKitchenFlow:
    def test_kitchen_login_success(self, kitchen_token):
        assert isinstance(kitchen_token, str) and len(kitchen_token) > 20

    def test_kitchen_login_wrong_password(self):
        r = requests.post(
            f"{BASE_URL}/api/kitchen/login",
            json={"email": KITCHEN_EMAIL, "password": "wrong"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_kitchen_me(self, hdr_kitchen):
        r = requests.get(f"{BASE_URL}/api/kitchen/me", headers=hdr_kitchen, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == KITCHEN_EMAIL
        assert d["role"] == "kitchen"

    def test_admin_can_login_via_kitchen(self):
        r = requests.post(
            f"{BASE_URL}/api/kitchen/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "admin"

    def test_kitchen_token_rejected_on_admin_routes(self, hdr_kitchen):
        r = requests.get(f"{BASE_URL}/api/admin/orders", headers=hdr_kitchen, timeout=15)
        assert r.status_code == 403

    def test_no_auth_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/kitchen/orders", timeout=15)
        assert r.status_code == 401


# ---------- listing ----------------------------------------------------------

    def test_list_shape(self, hdr_kitchen):
        r = requests.get(f"{BASE_URL}/api/kitchen/orders", headers=hdr_kitchen, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ("new", "accepted", "declined", "server_time"):
            assert key in d, f"Missing key {key} in {d.keys()}"
        assert isinstance(d["new"], list)


# ---------- accept flow ------------------------------------------------------

    def test_accept_moves_to_accepted(self, hdr_kitchen, created_order_ids):
        oid = _create_test_order(created_order_ids)

        # verify it appears in new tab
        listing = requests.get(f"{BASE_URL}/api/kitchen/orders", headers=hdr_kitchen).json()
        assert any(o["id"] == oid for o in listing["new"]), "New order not in 'new' tab"

        r = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen, timeout=20
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["already_decided"] is False
        order = body["order"]
        assert order["kitchen_decision"] == "accepted"
        assert order["status"] == "accepted"
        assert order["kitchen_print_status"] in ("pending", "printed")  # depends on Pi/tunnel reachability

        # verify it moved
        listing = requests.get(f"{BASE_URL}/api/kitchen/orders", headers=hdr_kitchen).json()
        assert not any(o["id"] == oid for o in listing["new"])
        assert any(o["id"] == oid for o in listing["accepted"])

    def test_accept_idempotent(self, hdr_kitchen, created_order_ids):
        oid = _create_test_order(created_order_ids)
        r1 = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen, timeout=20
        )
        r2 = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen, timeout=20
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["already_decided"] is False
        assert r2.json()["already_decided"] is True

    def test_mark_printed_after_accept(self, hdr_kitchen, created_order_ids):
        """Manual override — staff can flag an order printed by hand even if
        the automated Pi push failed."""
        oid = _create_test_order(created_order_ids)
        requests.post(f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen)
        r = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/mark-printed", headers=hdr_kitchen, timeout=20
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["order"]["kitchen_print_status"] == "printed"

        # Idempotent — calling it again just re-stamps, no error
        r2 = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/mark-printed", headers=hdr_kitchen, timeout=20
        )
        assert r2.status_code == 200
        assert r2.json()["order"]["kitchen_print_status"] == "printed"

    def test_mark_printed_unknown_order_404(self, hdr_kitchen):
        r = requests.post(
            f"{BASE_URL}/api/kitchen/orders/does-not-exist/mark-printed",
            headers=hdr_kitchen,
            timeout=20,
        )
        assert r.status_code == 404

    def test_reprint_pushes_again(self, hdr_kitchen, created_order_ids):
        """Reprint re-sends the ticket to the Pi print-bridge without
        touching order status. Since the Pi lives outside this test
        environment's network, we only assert the endpoint responds
        sanely (ok True/False) and never mutates status/decision."""
        oid = _create_test_order(created_order_ids)
        requests.post(f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen)
        r = requests.post(f"{BASE_URL}/api/kitchen/orders/{oid}/reprint", headers=hdr_kitchen, timeout=20)
        assert r.status_code == 200, r.text
        assert "ok" in r.json()
        listing = requests.get(f"{BASE_URL}/api/kitchen/orders", headers=hdr_kitchen).json()
        assert any(o["id"] == oid for o in listing["accepted"]), "Reprint must not move the order out of accepted"

    def test_reprint_unknown_order_404(self, hdr_kitchen):
        r = requests.post(
            f"{BASE_URL}/api/kitchen/orders/does-not-exist/reprint",
            headers=hdr_kitchen,
            timeout=20,
        )
        assert r.status_code == 404


# ---------- decline flow -----------------------------------------------------

    def test_decline_with_reason(self, hdr_kitchen, created_order_ids):
        oid = _create_test_order(created_order_ids)
        r = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/decline",
            headers=hdr_kitchen,
            json={"reason": "Rupture de stock"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["already_decided"] is False
        order = body["order"]
        assert order["kitchen_decision"] == "declined"
        assert order["kitchen_decline_reason"] == "Rupture de stock"
        assert order["status"] == "cancelled"

        listing = requests.get(f"{BASE_URL}/api/kitchen/orders", headers=hdr_kitchen).json()
        assert any(o["id"] == oid for o in listing["declined"])

    def test_decline_idempotent(self, hdr_kitchen, created_order_ids):
        oid = _create_test_order(created_order_ids)
        r1 = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/decline",
            headers=hdr_kitchen,
            json={"reason": "test"},
        )
        r2 = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/decline",
            headers=hdr_kitchen,
            json={"reason": "test2"},
        )
        assert r1.json()["already_decided"] is False
        assert r2.json()["already_decided"] is True

    def test_cannot_accept_after_decline(self, hdr_kitchen, created_order_ids):
        oid = _create_test_order(created_order_ids)
        requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/decline",
            headers=hdr_kitchen,
            json={"reason": "no"},
        )
        r = requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen, timeout=20
        )
        # should be idempotent-no-op with already_decided true
        assert r.status_code == 200
        assert r.json()["already_decided"] is True


# ---------- regression: admin dashboard status update still works ------------

    def test_admin_status_update_after_kitchen_accept(
        self, hdr_admin, hdr_kitchen, created_order_ids
    ):
        oid = _create_test_order(created_order_ids)
        requests.post(f"{BASE_URL}/api/kitchen/orders/{oid}/accept", headers=hdr_kitchen)

        # Admin dashboard should show status=accepted
        r = requests.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=hdr_admin, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"

        # Progress through pipeline via existing admin endpoint
        r = requests.put(
            f"{BASE_URL}/api/admin/orders/{oid}/status",
            headers=hdr_admin,
            json={"status": "ready"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ready"

    def test_kitchen_decline_reflects_in_admin(
        self, hdr_admin, hdr_kitchen, created_order_ids
    ):
        oid = _create_test_order(created_order_ids)
        requests.post(
            f"{BASE_URL}/api/kitchen/orders/{oid}/decline",
            headers=hdr_kitchen,
            json={"reason": "Test decline"},
        )
        r = requests.get(f"{BASE_URL}/api/admin/orders/{oid}", headers=hdr_admin)
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"


# ---------- restaurant status regression -------------------------------------

    def test_menu_still_public(self):
        r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
        assert r.status_code == 200

    def test_restaurant_status_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/restaurant/status", timeout=15)
        assert r.status_code == 200
        assert "state" in r.json()
