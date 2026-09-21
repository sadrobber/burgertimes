"""
Backend limit-enforcement tests for the new full-page product configuration modal.

Uses /api/checkout/quote (does NOT create orders, does NOT touch the printer)
against a temporary TEST menu item with uses_sauces=True and 5 removable ingredients.

Verifies:
  * >2 sauces  -> 400
  * >2 removable_ingredients -> 400
  * removals work for both menu and sans-menu formulas
  * allowed-at-limit selection returns 200 and snapshots notes as "Sans X · Sans Y"
"""
import os
import uuid
import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    if not v:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return v.rstrip("/")


BASE_URL = _load_base_url()
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in admin login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def test_item(admin_token):
    """Create a temporary TEST menu item with uses_sauces + 5 removable ingredients."""
    payload = {
        "name": f"TEST_CFGMODAL_{uuid.uuid4().hex[:6]}",
        "category": "classiques",
        "description": "TEST item for config-modal limit tests. Safe to delete.",
        "price_seul": 8.0,
        "price_menu": 11.0,
        "available": True,
        "uses_sauces": True,
        "removable_ingredients": ["oignons", "cornichons", "salade", "tomate", "sauce"],
        "formats": [],
    }
    r = requests.post(
        f"{BASE_URL}/api/admin/menu",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )
    assert r.status_code in (200, 201), f"create TEST item failed: {r.status_code} {r.text}"
    doc = r.json()
    assert doc.get("uses_sauces") is True
    assert doc.get("removable_ingredients") == ["oignons", "cornichons", "salade", "tomate", "sauce"]
    yield doc
    # teardown - always delete
    requests.delete(
        f"{BASE_URL}/api/admin/menu/{doc['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=15,
    )


def _quote(item_id, *, formula, sauces=None, removals=None, drink=None):
    line = {
        "line_id": uuid.uuid4().hex,
        "item_id": item_id,
        "quantity": 1,
        "formula": formula,
        "sauces": sauces or [],
        "removable_ingredients": removals or [],
    }
    if drink:
        line["included_drink"] = drink
    payload = {
        "items": [line],
        "fulfillment": "pickup",
        "customer_first_name": "TEST",
        "customer_last_name": "Quote",
        "customer_phone": "+33600000000",
        "payment_method": "cash",
    }
    return requests.post(f"{BASE_URL}/api/checkout/quote", json=payload, timeout=15)


def test_more_than_2_sauces_rejected(test_item):
    r = _quote(test_item["id"], formula="seul", sauces=["Ketchup", "Mayo", "BBQ"])
    assert r.status_code == 400, r.text
    assert "sauces" in r.text.lower()


def test_more_than_2_removals_rejected(test_item):
    r = _quote(
        test_item["id"],
        formula="menu",
        drink="Coca-Cola",
        removals=["oignons", "cornichons", "salade"],
    )
    assert r.status_code == 400, r.text
    assert "ingr" in r.text.lower() or "retir" in r.text.lower()


def test_removals_on_non_menu_are_allowed(test_item):
    r = _quote(test_item["id"], formula="seul", removals=["oignons", "cornichons"])
    assert r.status_code == 200, r.text
    notes = (r.json().get("items") or [])[0].get("notes") or ""
    assert "Sans oignons" in notes and "Sans cornichons" in notes


def test_at_limit_menu_selection_snapshots_notes(test_item):
    # Get a valid soda flavour from settings
    s = requests.get(f"{BASE_URL}/api/settings", timeout=10).json()
    sodas = s.get("soda_flavours") or []
    drink = sodas[0] if sodas else "Coca-Cola"
    r = _quote(
        test_item["id"],
        formula="menu",
        drink=drink,
        sauces=["Ketchup", "Mayo"],  # exactly 2
        removals=["oignons", "cornichons"],  # exactly 2
    )
    assert r.status_code == 200, r.text
    data = r.json()
    snaps = data.get("items") or data.get("snapshots") or []
    assert snaps, f"no snapshots returned: {data}"
    snap = snaps[0]
    # notes should be "Sans oignons · Sans cornichons"
    notes = snap.get("notes") or ""
    assert "Sans oignons" in notes and "Sans cornichons" in notes, f"notes={notes!r}"
    # sauces preserved
    assert set(snap.get("sauces") or []) == {"Ketchup", "Mayo"}
    # included_drink preserved
    assert snap.get("included_drink") == drink


def test_sauces_rejected_when_item_does_not_use_sauces(admin_token, test_item):
    """Toggle uses_sauces=False and confirm sauces are rejected."""
    tok = admin_token
    requests.put(
        f"{BASE_URL}/api/admin/menu/{test_item['id']}",
        json={"uses_sauces": False},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    try:
        r = _quote(test_item["id"], formula="seul", sauces=["Ketchup"])
        assert r.status_code == 400, r.text
        assert "sauce" in r.text.lower()
    finally:
        requests.put(
            f"{BASE_URL}/api/admin/menu/{test_item['id']}",
            json={"uses_sauces": True},
            headers={"Authorization": f"Bearer {tok}"},
            timeout=15,
        )
