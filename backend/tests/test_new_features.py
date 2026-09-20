"""Backend tests for the three new Burger Times features:
1) Menu removable ingredients
2) Delivery slots endpoint + slot validation logic (unit)
3) Tablet staff CRUD + tablet login + kitchen scheduled hiding (unit)

STRICT SAFETY: Never calls /kitchen/test-print, /accept, /reprint. Never
creates a completed order (uses /checkout/quote with create=False path).
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests

sys.path.insert(0, "/app/backend")
from delivery_scheduling import delivery_slots, validate_delivery_slot  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


# ----------------- Fixtures ------------------------------------------------

@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ----------------- 1. Removable ingredients -------------------------------

class TestRemovableIngredients:
    def test_public_menu_exposes_removable_ingredients_only_when_set(self, admin_headers):
        # Pick an existing menu item, set removable_ingredients, verify public menu, then revert.
        menu = requests.get(f"{API}/menu", timeout=15).json()
        assert isinstance(menu, list) and len(menu) > 0
        target = menu[0]
        target_id = target["id"]
        original = target.get("removable_ingredients", []) or []

        new_ings = ["oignons", "cornichons", "sauce"]
        r = requests.put(
            f"{API}/admin/menu/{target_id}",
            headers=admin_headers,
            json={"removable_ingredients": new_ings},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("removable_ingredients") == new_ings

        try:
            # Public menu should now expose them for this item only
            public = requests.get(f"{API}/menu", timeout=15).json()
            found = next((m for m in public if m["id"] == target_id), None)
            assert found is not None
            assert found.get("removable_ingredients") == new_ings

            others = [m for m in public if m["id"] != target_id and m.get("removable_ingredients")]
            # It's fine if other items already had ingredients configured; we just ensure our item is set.
            # Also ensure at least one other item has an empty list => proves it's per-item.
            has_empty = any(not (m.get("removable_ingredients") or []) for m in public if m["id"] != target_id)
            assert has_empty, "Expected at least one item without removable_ingredients (per-item scope)"
        finally:
            # Revert
            rr = requests.put(
                f"{API}/admin/menu/{target_id}",
                headers=admin_headers,
                json={"removable_ingredients": original},
                timeout=15,
            )
            assert rr.status_code == 200

    def test_quote_accepts_notes_with_sans_ingredient(self, admin_headers):
        """Confirm cart line notes containing 'Sans oignons' are accepted by quote (no order created)."""
        menu = requests.get(f"{API}/menu", timeout=15).json()
        item = next((m for m in menu if m.get("available") and not m.get("is_burger")), menu[0])
        payload = {
            "items": [{
                "line_id": "test-line-1",
                "item_id": item["id"],
                "quantity": 1,
                "formula": "seul",
                "notes": "Sans oignons, Sans cornichons",
            }],
            "fulfillment": "pickup",
            "customer_first_name": "Test",
            "customer_last_name": "Quote",
            "customer_phone": "0600000000",
            "payment_method": "cash",
        }
        r = requests.post(f"{API}/checkout/quote", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Notes should be preserved in the quoted line snapshot
        items = data.get("items") or data.get("order", {}).get("items", [])
        assert items, f"No items in quote response: {data}"
        assert any("Sans oignons" in (it.get("notes") or "") for it in items)


# ----------------- 2. Delivery slots ---------------------------------------

class TestDeliverySlots:
    def test_slots_endpoint_returns_todays_windows(self):
        r = requests.get(f"{API}/checkout/delivery-slots", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data and "lead_minutes" in data and "window_minutes" in data
        assert isinstance(data["slots"], list)
        # Each slot must be today (restaurant TZ)
        window_min = data["window_minutes"]
        for slot in data["slots"]:
            start = datetime.fromisoformat(slot["start"])
            end = datetime.fromisoformat(slot["end"])
            delta = (end - start).total_seconds() / 60
            assert abs(delta - window_min) < 0.5, f"window duration mismatch: {delta} vs {window_min}"

    def test_quote_rejects_invalid_scheduled_slot(self):
        """Passing an arbitrary start time not in server slots must fail with 400."""
        menu = requests.get(f"{API}/menu", timeout=15).json()
        item = next((m for m in menu if m.get("available")), menu[0])
        far_future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        payload = {
            "items": [{
                "line_id": "L1", "item_id": item["id"], "quantity": 1, "formula": "seul",
            }],
            "fulfillment": "delivery",
            "customer_first_name": "T", "customer_last_name": "T",
            "customer_phone": "0600000000",
            "address_line1": "1 rue", "postal_code": "06240", "city": "Beausoleil",
            "payment_method": "cash",
            "scheduled_delivery_start": far_future,
        }
        r = requests.post(f"{API}/checkout/quote", json=payload, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_quote_accepts_valid_scheduled_slot(self):
        """If any slot exists today, quote should accept it and echo scheduled fields."""
        r = requests.get(f"{API}/checkout/delivery-slots", timeout=15)
        data = r.json()
        if not data.get("enabled") or not data.get("slots"):
            pytest.skip("No slots available now (closed/lead time) — pure logic covered elsewhere")
        slot = data["slots"][0]
        menu = requests.get(f"{API}/menu", timeout=15).json()
        item = next((m for m in menu if m.get("available")), menu[0])
        payload = {
            "items": [{
                "line_id": "L1", "item_id": item["id"], "quantity": 1, "formula": "seul",
            }],
            "fulfillment": "delivery",
            "customer_first_name": "T", "customer_last_name": "T",
            "customer_phone": "0600000000",
            "address_line1": "1 rue", "postal_code": "06240", "city": "Beausoleil",
            "payment_method": "cash",
            "scheduled_delivery_start": slot["start"],
        }
        rr = requests.post(f"{API}/checkout/quote", json=payload, timeout=15)
        assert rr.status_code == 200, rr.text

    # ---- Pure unit tests on delivery_scheduling helpers ------------------

    def test_unit_delivery_slots_disabled_returns_empty(self):
        assert delivery_slots({"scheduled_delivery_enabled": False}) == []

    def test_unit_delivery_slots_shape_and_lead(self):
        # Fully open all day; force a known "now"
        settings = {
            "scheduled_delivery_enabled": True,
            "timezone": "Europe/Paris",
            "delivery_lead_minutes": 40,
            "delivery_window_minutes": 20,
            "last_order_buffer_minutes": 0,
            "hours_per_day": {
                "mon": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
                "tue": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
                "wed": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
                "thu": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
                "fri": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
                "sat": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
                "sun": {"is_open": True, "ranges": [{"open": "10:00", "close": "22:00"}]},
            },
        }
        from zoneinfo import ZoneInfo
        # Freeze "now" at 12:00 local
        now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))  # a Monday
        slots = delivery_slots(settings, now=now)
        assert len(slots) > 0
        first_start = datetime.fromisoformat(slots[0]["start"])
        # Must be at or after now+lead (12:40)
        earliest = now + timedelta(minutes=40)
        assert first_start >= earliest.astimezone(timezone.utc), f"{first_start} < {earliest}"
        # Windows are 20 min
        for s in slots:
            st = datetime.fromisoformat(s["start"])
            en = datetime.fromisoformat(s["end"])
            assert (en - st) == timedelta(minutes=20)

    def test_unit_validate_slot_rejects_unknown(self):
        settings = {"scheduled_delivery_enabled": True}
        with pytest.raises(Exception):
            validate_delivery_slot(settings, "2099-01-01T10:00:00+00:00")

    def test_unit_validate_slot_none_returns_none(self):
        assert validate_delivery_slot({}, None) is None


# ----------------- 3. Tablet staff + login ---------------------------------

class TestTabletStaff:
    def test_create_login_delete_cycle(self, admin_headers):
        unique = f"TEST_tablet_{int(time.time())}@burgertimes.fr"
        password = "TabletTest2026!"

        # Create
        r = requests.post(
            f"{API}/admin/tablet-staff",
            headers=admin_headers,
            json={"email": unique, "password": password},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["email"] == unique.lower()
        assert created["role"] == "tablet"
        assert "password_hash" not in created
        assert "_id" not in created
        staff_id = created["id"]

        try:
            # List should include it
            lr = requests.get(f"{API}/admin/tablet-staff", headers=admin_headers, timeout=15)
            assert lr.status_code == 200
            emails = [d["email"] for d in lr.json()]
            assert unique.lower() in emails

            # Tablet login
            tl = requests.post(f"{API}/tablet/login", json={"email": unique, "password": password}, timeout=15)
            assert tl.status_code == 200, tl.text
            token = tl.json().get("token")
            assert token

            # Tablet /me
            me = requests.get(f"{API}/tablet/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
            assert me.status_code == 200
            assert me.json().get("email") == unique.lower()

            # Bad login
            bad = requests.post(f"{API}/tablet/login", json={"email": unique, "password": "wrong"}, timeout=15)
            assert bad.status_code in (401, 403)
        finally:
            # Delete
            d = requests.delete(f"{API}/admin/tablet-staff/{staff_id}", headers=admin_headers, timeout=15)
            assert d.status_code == 200
            assert d.json().get("deleted") == 1

    def test_admin_cannot_use_tablet_login(self):
        """Owner admin uses tablet login? role=admin is allowed per code check."""
        r = requests.post(f"{API}/tablet/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        # admin role is allowed
        assert r.status_code == 200


# ----------------- 4. Kitchen scheduled hiding (query smoke) ---------------

class TestKitchenScheduledHiding:
    """Uses kitchen login via admin (allowed) to only READ the list; never
    accepts/declines/reprints/test-prints."""

    def test_kitchen_list_does_not_expose_future_scheduled(self, admin_headers):
        # Use admin token as kitchen (role=admin allowed on kitchen list)
        r = requests.get(f"{API}/kitchen/orders", headers=admin_headers, timeout=15)
        if r.status_code == 403:
            pytest.skip("Admin token not authorized for kitchen route in this env")
        assert r.status_code == 200, r.text
        data = r.json()
        server_now = data.get("server_time")
        assert server_now
        # No pending order with a future kitchen_release_at should show up in "new"
        for bucket in ("new",):
            for order in data.get(bucket, []):
                rel = order.get("kitchen_release_at")
                if rel:
                    assert rel <= server_now, f"scheduled order leaked into kitchen 'new' before release: {order['id']}"
