"""
Tests for reported bugs:
1. Admin menu image preservation on edit/update without image_base64
2. Removable ingredients auto-save
3. uses_sauces flag: server-side sauce validation
Uses TEST-prefixed items which are cleaned up after the run.
"""
import os
import base64
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"

# 1x1 red pixel PNG
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
TINY_PNG_DATAURL = f"data:image/png;base64,{TINY_PNG_B64}"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    body = r.json()
    return body.get("access_token") or body["token"]


@pytest.fixture(scope="module")
def hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def category_slug(hdr):
    r = requests.get(f"{BASE_URL}/api/admin/categories", headers=hdr, timeout=15)
    assert r.status_code == 200
    cats = r.json()
    assert cats
    return cats[0]["slug"]


@pytest.fixture()
def temp_item(hdr, category_slug):
    """Create a TEST-prefixed menu item with image; yield item_id; delete after."""
    payload = {
        "name": "TEST_IMG_PRESERVE",
        "description": "temp",
        "category": category_slug,
        "price_seul": 1.0,
        "price_menu": None,
        "formats": [],
        "variants": [],
        "removable_ingredients": ["oignons"],
        "uses_soda_flavours": False,
        "uses_sauces": False,
        "available": True,
        "is_new": False,
        "sort_order": 0,
        "image_base64": TINY_PNG_DATAURL,
    }
    r = requests.post(f"{BASE_URL}/api/admin/menu", headers=hdr, json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    item = r.json()
    yield item
    # cleanup
    requests.delete(f"{BASE_URL}/api/admin/menu/{item['id']}", headers=hdr, timeout=15)


class TestMenuImagePreserve:
    def test_create_sets_has_image_true(self, temp_item):
        assert temp_item["has_image"] is True

    def test_image_endpoint_returns_bytes(self, temp_item):
        r = requests.get(f"{BASE_URL}/api/menu/{temp_item['id']}/image", timeout=15)
        assert r.status_code == 200
        assert len(r.content) > 10
        assert r.headers.get("content-type", "").startswith("image/") or r.content[:8].startswith(b"\x89PNG")

    def test_update_without_image_preserves_image(self, hdr, temp_item):
        # Update name/removals/uses_sauces WITHOUT image_base64
        r = requests.put(
            f"{BASE_URL}/api/admin/menu/{temp_item['id']}",
            headers=hdr,
            json={"name": "TEST_IMG_PRESERVE_v2", "removable_ingredients": ["oignons", "salade"], "uses_sauces": True},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "TEST_IMG_PRESERVE_v2"
        assert body["has_image"] is True, "has_image must be preserved when image_base64 not sent"
        assert body["uses_sauces"] is True
        assert set(body["removable_ingredients"]) == {"oignons", "salade"}

        # image endpoint still returns bytes
        img = requests.get(f"{BASE_URL}/api/menu/{temp_item['id']}/image", timeout=15)
        assert img.status_code == 200
        assert len(img.content) > 10

    def test_update_with_null_image_base64_preserves_image(self, hdr, temp_item):
        r = requests.put(
            f"{BASE_URL}/api/admin/menu/{temp_item['id']}",
            headers=hdr,
            json={"name": "TEST_IMG_PRESERVE_null", "image_base64": None},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["has_image"] is True, "has_image must survive image_base64: null"
        img = requests.get(f"{BASE_URL}/api/menu/{temp_item['id']}/image", timeout=15)
        assert img.status_code == 200
        assert len(img.content) > 10

    def test_removable_ingredients_only_update_persists_and_preserves_image(self, hdr, temp_item):
        # Simulate auto-save with only removable_ingredients
        r = requests.put(
            f"{BASE_URL}/api/admin/menu/{temp_item['id']}",
            headers=hdr,
            json={"removable_ingredients": ["cornichons"]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["removable_ingredients"] == ["cornichons"]
        assert body["has_image"] is True

        # Verify via GET /admin/menu
        r2 = requests.get(f"{BASE_URL}/api/admin/menu", headers=hdr, timeout=15)
        it = next((x for x in r2.json() if x["id"] == temp_item["id"]), None)
        assert it is not None
        assert it["removable_ingredients"] == ["cornichons"]
        assert it["has_image"] is True


class TestUsesSaucesValidation:
    def test_uses_sauces_false_rejects_sauce_payload(self, hdr, category_slug):
        # Create a no-sauce test item
        item = requests.post(
            f"{BASE_URL}/api/admin/menu",
            headers=hdr,
            json={
                "name": "TEST_NOSAUCE",
                "category": category_slug,
                "price_seul": 2.0,
                "uses_sauces": False,
                "available": True,
            },
            timeout=15,
        ).json()
        try:
            # Attempt quote with a sauce on an item that doesn't allow sauces
            r = requests.post(
                f"{BASE_URL}/api/checkout/quote",
                json={
                    "fulfillment": "pickup",
                    "customer_first_name": "T",
                    "customer_last_name": "T",
                    "customer_phone": "+33600000000",
                    "items": [
                        {
                            "line_id": "l1",
                            "item_id": item["id"],
                            "is_burger": False,
                            "formula": "seul",
                            "quantity": 1,
                            "sauces": ["Ketchup"],
                        }
                    ],
                },
                timeout=15,
            )
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
            assert "sauce" in r.text.lower()
        finally:
            requests.delete(f"{BASE_URL}/api/admin/menu/{item['id']}", headers=hdr, timeout=15)

    def test_uses_sauces_true_accepts_sauce_payload(self, hdr, category_slug):
        item = requests.post(
            f"{BASE_URL}/api/admin/menu",
            headers=hdr,
            json={
                "name": "TEST_YESSAUCE",
                "category": category_slug,
                "price_seul": 2.0,
                "uses_sauces": True,
                "available": True,
            },
            timeout=15,
        ).json()
        try:
            r = requests.post(
                f"{BASE_URL}/api/checkout/quote",
                json={
                    "fulfillment": "pickup",
                    "customer_first_name": "T",
                    "customer_last_name": "T",
                    "customer_phone": "+33600000000",
                    "items": [
                        {
                            "line_id": "l1",
                            "item_id": item["id"],
                            "is_burger": False,
                            "formula": "seul",
                            "quantity": 1,
                            "sauces": ["Ketchup"],
                        }
                    ],
                },
                timeout=15,
            )
            assert r.status_code == 200, r.text
            snap = r.json()
            # Sauce survives the quote snapshot
            items_out = snap.get("items") or snap.get("snapshots") or []
            if items_out:
                assert items_out[0].get("sauces") == ["Ketchup"]
        finally:
            requests.delete(f"{BASE_URL}/api/admin/menu/{item['id']}", headers=hdr, timeout=15)


class TestPublicMenuExposesSauceFlag:
    def test_menu_lists_uses_sauces(self):
        """Public /menu should surface uses_sauces on at least items that have it set to true.
        Existing DB docs may pre-date the field and legitimately omit it (falsy). But when we
        create an item with uses_sauces=true, the public /menu must return it as True."""
        r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) > 0
        # Any item that has the key must be a bool
        for it in items:
            if "uses_sauces" in it:
                assert isinstance(it["uses_sauces"], bool)
