"""
Iteration 37 — Global 'Sans' removal_options refactor.

Contract:
1. GET/PUT /api/settings supports removal_options (list[str]).
2. Adding & deleting an ephemeral TEST option persists, then original list restored.
3. Selecting a global option on a temporary item via PUT persists removable_ingredients
   without mutating the global list.
4. Image preservation regression stays fixed on the temporary item.
5. uses_sauces remains accepted end-to-end after the refactor.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"

TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
TINY_PNG_DATAURL = f"data:image/png;base64,{TINY_PNG_B64}"


@pytest.fixture(scope="module")
def hdr():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    token = body.get("access_token") or body.get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def original_removal_options(hdr):
    """Capture the original global removal_options and always restore after tests."""
    r = requests.get(f"{BASE_URL}/api/settings", timeout=15)
    assert r.status_code == 200
    original = list(r.json().get("removal_options") or [])
    yield original
    # Teardown: restore exact original list
    requests.put(f"{BASE_URL}/api/settings", headers=hdr, json={"removal_options": original}, timeout=15)
    verify = requests.get(f"{BASE_URL}/api/settings", timeout=15).json().get("removal_options") or []
    assert verify == original, f"failed to restore removal_options: {verify} vs {original}"


@pytest.fixture(scope="module")
def category_slug(hdr):
    r = requests.get(f"{BASE_URL}/api/admin/categories", headers=hdr, timeout=15)
    assert r.status_code == 200
    return r.json()[0]["slug"]


@pytest.fixture()
def temp_item(hdr, category_slug):
    payload = {
        "name": "TEST_REMOVAL_ARCH",
        "description": "temp",
        "category": category_slug,
        "price_seul": 1.0,
        "removable_ingredients": [],
        "uses_sauces": False,
        "available": True,
        "image_base64": TINY_PNG_DATAURL,
    }
    r = requests.post(f"{BASE_URL}/api/admin/menu", headers=hdr, json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    item = r.json()
    yield item
    requests.delete(f"{BASE_URL}/api/admin/menu/{item['id']}", headers=hdr, timeout=15)


class TestGlobalRemovalOptions:
    def test_settings_exposes_removal_options_list(self, original_removal_options):
        assert isinstance(original_removal_options, list)

    def test_add_then_delete_ephemeral_option(self, hdr, original_removal_options):
        ephemeral = "TEST_JALAPENOS_XYZ"
        # ADD
        new_list = original_removal_options + [ephemeral]
        r = requests.put(f"{BASE_URL}/api/settings", headers=hdr, json={"removal_options": new_list}, timeout=15)
        assert r.status_code == 200, r.text
        assert ephemeral in (r.json().get("removal_options") or [])
        # GET verifies persistence
        got = requests.get(f"{BASE_URL}/api/settings", timeout=15).json().get("removal_options") or []
        assert ephemeral in got

        # DELETE (remove ephemeral)
        pruned = [o for o in got if o != ephemeral]
        r2 = requests.put(f"{BASE_URL}/api/settings", headers=hdr, json={"removal_options": pruned}, timeout=15)
        assert r2.status_code == 200
        assert ephemeral not in (r2.json().get("removal_options") or [])
        got2 = requests.get(f"{BASE_URL}/api/settings", timeout=15).json().get("removal_options") or []
        assert ephemeral not in got2


class TestPerItemSelectionAutoSave:
    def test_selecting_global_option_persists_and_does_not_mutate_global(self, hdr, temp_item, original_removal_options):
        # If the global list is empty, temporarily seed with a value to select.
        seeded = False
        current = original_removal_options
        if not current:
            current = ["oignons"]
            requests.put(f"{BASE_URL}/api/settings", headers=hdr, json={"removal_options": current}, timeout=15)
            seeded = True

        pick = current[0]
        # Simulate MenuAdmin toggleCommonRemoval -> saveRemovals PUT
        r = requests.put(
            f"{BASE_URL}/api/admin/menu/{temp_item['id']}",
            headers=hdr,
            json={"removable_ingredients": [pick]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["removable_ingredients"] == [pick]
        assert body["has_image"] is True  # image preservation regression

        # Global list untouched
        got = requests.get(f"{BASE_URL}/api/settings", timeout=15).json().get("removal_options") or []
        assert got == current

        if seeded:
            requests.put(f"{BASE_URL}/api/settings", headers=hdr, json={"removal_options": original_removal_options}, timeout=15)


class TestImagePreservationRegression:
    def test_update_without_image_base64_keeps_image(self, hdr, temp_item):
        r = requests.put(
            f"{BASE_URL}/api/admin/menu/{temp_item['id']}",
            headers=hdr,
            json={"name": "TEST_REMOVAL_ARCH_v2"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["has_image"] is True
        img = requests.get(f"{BASE_URL}/api/menu/{temp_item['id']}/image", timeout=15)
        assert img.status_code == 200 and len(img.content) > 10


class TestUsesSaucesStillAccepted:
    def test_put_uses_sauces_true(self, hdr, temp_item):
        r = requests.put(
            f"{BASE_URL}/api/admin/menu/{temp_item['id']}",
            headers=hdr,
            json={"uses_sauces": True},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["uses_sauces"] is True
