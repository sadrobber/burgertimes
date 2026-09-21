"""
Tests for the tablet_orders_when_closed override and Settings toggle persistence.

STRICT SAFETY: never POST /api/tablet/orders (would trigger physical print).
We validate:
  1. Settings API GET/PUT round-trip for tablet_orders_when_closed (persisted).
  2. Web checkout (POST /api/checkout/session) with force_closed=true is blocked (423).
  3. Static source-level verification that _quote_or_create bypasses
     _ensure_accepting_orders when order_source == "tablet" AND
     tablet_orders_when_closed is true, and does NOT bypass otherwise.
  4. Static source-level verification that tablet immediate orders call
     _push_print_job_background with copies=2 (no real call made).

The setting is restored to its original value at teardown.
"""
import inspect
import os
import pathlib
import re
import sys

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com"
).rstrip("/")

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
    body = r.json()
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def original_settings(hdr):
    r = requests.get(f"{BASE_URL}/api/settings", headers=hdr, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def restore_settings(hdr, original_settings):
    """Restore tablet_orders_when_closed AND force_closed to original values after the module."""
    yield
    payload = {
        "tablet_orders_when_closed": bool(
            original_settings.get("tablet_orders_when_closed", False)
        ),
        "force_closed": bool(original_settings.get("force_closed", False)),
    }
    r = requests.put(f"{BASE_URL}/api/settings", headers=hdr, json=payload, timeout=15)
    assert r.status_code == 200, f"Restore failed: {r.status_code} {r.text}"


class TestSettingsToggle:
    """PUT/GET round-trip and persistence of tablet_orders_when_closed."""

    def test_toggle_true_persists(self, hdr, original_settings):
        r = requests.put(
            f"{BASE_URL}/api/settings",
            headers=hdr,
            json={"tablet_orders_when_closed": True},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["tablet_orders_when_closed"] is True

        # Verify via GET
        r2 = requests.get(f"{BASE_URL}/api/settings", headers=hdr, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["tablet_orders_when_closed"] is True

    def test_toggle_false_persists(self, hdr):
        r = requests.put(
            f"{BASE_URL}/api/settings",
            headers=hdr,
            json={"tablet_orders_when_closed": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["tablet_orders_when_closed"] is False

        r2 = requests.get(f"{BASE_URL}/api/settings", headers=hdr, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["tablet_orders_when_closed"] is False


class TestWebBlockedWhenClosed:
    """When force_closed=true, public web /checkout/session is blocked with 423."""

    def test_web_checkout_blocked_when_force_closed(self, hdr):
        # Set force_closed
        r = requests.put(
            f"{BASE_URL}/api/settings",
            headers=hdr,
            json={"force_closed": True, "tablet_orders_when_closed": True},
            timeout=15,
        )
        assert r.status_code == 200
        try:
            # Grab any menu item to build a valid payload shape
            menu = requests.get(f"{BASE_URL}/api/menu", timeout=15).json()
            item = next((m for m in menu if m.get("available")), menu[0])
            payload = {
                "fulfillment": "pickup",
                "customer_first_name": "TEST",
                "customer_last_name": "WEBCLOSED",
                "customer_phone": "+33600000000",
                "payment_method": "cash",
                "items": [
                    {
                        "line_id": "l1",
                        "item_id": item["id"],
                        "is_burger": False,
                        "formula": "seul",
                        "quantity": 1,
                    }
                ],
            }
            r = requests.post(
                f"{BASE_URL}/api/checkout/session", json=payload, timeout=15
            )
            # Public web must be blocked with 423 even when tablet override is on
            assert r.status_code == 423, (
                f"Expected 423 for closed web checkout, got {r.status_code}: {r.text}"
            )
        finally:
            # Immediately unset force_closed so preview isn't left closed
            requests.put(
                f"{BASE_URL}/api/settings",
                headers=hdr,
                json={"force_closed": False},
                timeout=15,
            )


class TestSourceLevelBypassLogic:
    """Static source verification: no real orders, no printing invoked."""

    @pytest.fixture(scope="class")
    def server_src(self):
        # Try import (fast, exact function source)
        sys.path.insert(0, str(pathlib.Path("/app/backend")))
        try:
            import server  # type: ignore
            return inspect.getsource(server._quote_or_create) + "\n\n" + inspect.getsource(
                server.tablet_create_order
            )
        except Exception:
            # Fallback: read file
            return pathlib.Path("/app/backend/server.py").read_text()

    def test_bypass_when_tablet_and_override_true(self, server_src):
        # The bypass condition must reference both order_source=='tablet' AND
        # settings.tablet_orders_when_closed, and only skip _ensure_accepting_orders
        # when both are truthy.
        assert 'tablet_orders_when_closed' in server_src
        assert re.search(r"order_source\s*==\s*['\"]tablet['\"]", server_src), (
            "Expected explicit 'order_source == \"tablet\"' comparison in _quote_or_create"
        )
        # The skip should be gated by 'if not tablet_closed_override: await _ensure_accepting_orders'
        assert re.search(
            r"if\s+not\s+tablet_closed_override\s*:\s*\n\s*await\s+_ensure_accepting_orders",
            server_src,
        ), "Expected 'if not tablet_closed_override: await _ensure_accepting_orders(settings)'"

    def test_web_source_is_default_and_not_bypassed(self, server_src):
        # /checkout/session route calls _quote_or_create with create=True and
        # no order_source override -> default 'web' -> tablet_closed_override False
        # -> _ensure_accepting_orders is always called.
        full = pathlib.Path("/app/backend/server.py").read_text()
        assert re.search(
            r"@api\.post\(\"/checkout/session\"\)[\s\S]*?_quote_or_create\(payload,\s*create=True\)",
            full,
        ), "checkout/session must call _quote_or_create with create=True and no tablet override"

    def test_tablet_immediate_uses_two_print_copies(self, server_src):
        # Tablet immediate (non-scheduled) creation must invoke print job with copies=2.
        full = pathlib.Path("/app/backend/server.py").read_text()
        assert re.search(
            r"_push_print_job_background\([^)]*copies=2",
            full,
        ), "Tablet immediate accept path must call _push_print_job_background(..., copies=2)"


class TestSettingsUIExposesField:
    """GET admin settings must expose the tablet_orders_when_closed key so the UI can render it."""

    def test_admin_settings_exposes_field(self, hdr):
        r = requests.get(f"{BASE_URL}/api/settings", headers=hdr, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "tablet_orders_when_closed" in body
        assert isinstance(body["tablet_orders_when_closed"], bool)
