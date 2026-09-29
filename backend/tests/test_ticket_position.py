"""Ticket position — per-item "Encadré noir à droite sur le ticket" flag.

The admin can flag a menu item so the kitchen print bridge boxes it on the
right of the ticket; the flag rides along in the order item snapshots.

Printer-safe: uses /checkout/quote only, NEVER /checkout/session or /tablet/orders.
Cleans up all TEST_* items created.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def category():
    r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
    assert r.status_code == 200 and r.json(), "public menu empty"
    return r.json()[0]["category"]


@pytest.fixture
def make_item(admin_headers, category):
    """Creates TEST_ items for one test and deletes them afterwards."""
    created = []

    def make(**extra):
        payload = {"name": f"TEST_TPOS_{uuid.uuid4().hex[:8]}", "category": category, "price_seul": 1.0, **extra}
        r = requests.post(f"{BASE_URL}/api/admin/menu", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        created.append(r.json()["id"])
        return r.json()

    yield make
    for item_id in created:
        requests.delete(f"{BASE_URL}/api/admin/menu/{item_id}", headers=admin_headers, timeout=15)


def _public(item_id):
    r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
    assert r.status_code == 200
    found = [x for x in r.json() if x["id"] == item_id]
    assert len(found) == 1, f"item {item_id} not on the public menu"
    return found[0]


# ---- 1. New items default to "left" ---------------------------------------
def test_new_item_defaults_to_left(make_item):
    doc = make_item()  # ticket_position omitted
    assert doc["ticket_position"] == "left"
    assert _public(doc["id"])["ticket_position"] == "left"


# ---- 2. Admin can set "right"; public menu and updates reflect it ----------
def test_admin_can_set_right(make_item, admin_headers):
    doc = make_item(ticket_position="right")
    assert doc["ticket_position"] == "right"
    assert _public(doc["id"])["ticket_position"] == "right"

    r = requests.put(f"{BASE_URL}/api/admin/menu/{doc['id']}", headers=admin_headers, json={"ticket_position": "left"}, timeout=15)
    assert r.status_code == 200, r.text
    assert _public(doc["id"])["ticket_position"] == "left"


# ---- 3. The order item snapshot carries the flag to the print bridge -------
def test_quote_snapshot_carries_ticket_position(make_item):
    right = make_item(ticket_position="right")
    left = make_item()
    payload = {
        "items": [
            {"line_id": "L1", "item_id": right["id"], "quantity": 1, "formula": "seul"},
            {"line_id": "L2", "item_id": left["id"], "quantity": 1, "formula": "seul"},
        ],
        "fulfillment": "pickup",
        "customer_first_name": "Test",
        "customer_last_name": "Pos",
        "customer_phone": "0600000000",
        "payment_method": "cash",
    }
    r = requests.post(f"{BASE_URL}/api/checkout/quote", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    assert [i["ticket_position"] for i in r.json()["items"]] == ["right", "left"]
