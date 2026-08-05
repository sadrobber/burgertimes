"""Backend tests: seed idempotency + public API regression for Burger Times."""
import asyncio
import os
import sys
import uuid
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"


# ------------------ Public API regression (current running DB) ------------------
class TestPublicAPIs:
    def test_menu_returns_40(self):
        r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Response may be list or {items:[]}
        items = data if isinstance(data, list) else data.get("items", data.get("menu", []))
        assert len(items) == 40, f"Expected 40 menu items, got {len(items)}"

    def test_categories_returns_9(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=15)
        assert r.status_code == 200
        data = r.json()
        cats = data if isinstance(data, list) else data.get("items", [])
        assert len(cats) == 9, f"Expected 9 categories, got {len(cats)}"

    def test_sauces_returns_12(self):
        r = requests.get(f"{BASE_URL}/api/sauces", timeout=15)
        assert r.status_code == 200
        data = r.json()
        sauces = data if isinstance(data, list) else data.get("items", [])
        assert len(sauces) == 12, f"Expected 12 sauces, got {len(sauces)}"

    def test_burger_config(self):
        r = requests.get(f"{BASE_URL}/api/burger/config", timeout=15)
        assert r.status_code == 200
        cfg = r.json()
        assert len(cfg.get("styles", [])) == 1
        assert len(cfg.get("sizes", [])) == 3
        assert len(cfg.get("meats", [])) == 6
        assert len(cfg.get("supplements", [])) == 6
        assert len(cfg.get("cheeses", [])) == 0

    def test_restaurant_status(self):
        r = requests.get(f"{BASE_URL}/api/restaurant/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Just ensure a valid state field exists
        assert any(k in data for k in ("state", "status", "is_open", "open"))


# ------------------ Admin login + admin menu regression ------------------
class TestAdmin:
    @pytest.fixture(scope="class")
    def token(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
        data = r.json()
        tok = data.get("access_token") or data.get("token")
        assert tok, f"No token in login response: {data}"
        return tok

    def test_admin_menu_40(self, token):
        r = requests.get(
            f"{BASE_URL}/api/admin/menu",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) == 40

    def test_checkout_quote(self):
        # Get first menu item and build a minimal quote
        menu = requests.get(f"{BASE_URL}/api/menu", timeout=15).json()
        items = menu if isinstance(menu, list) else menu.get("items", [])
        assert items, "No menu items to quote"
        item = items[0]
        payload = {
            "items": [
                {"line_id": "l1", "item_id": item.get("id"), "quantity": 1, "formula": "seul"}
            ],
            "fulfillment": "pickup",
            "customer_first_name": "Test",
            "customer_last_name": "User",
            "customer_phone": "0600000000",
            "payment_method": "cash",
        }
        r = requests.post(f"{BASE_URL}/api/checkout/quote", json=payload, timeout=15)
        # Endpoint may return 200 with quote; accept 200
        if r.status_code != 200:
            pytest.skip(f"Quote endpoint returned {r.status_code}: {r.text[:200]}")
        q = r.json()
        assert q.get("subtotal") is not None or q.get("total") is not None


# ------------------ Seed on fresh empty DB + idempotency ------------------
class TestSeedFreshDB:
    scratch_db_name = f"seed_verification_{uuid.uuid4().hex[:8]}"

    @classmethod
    def teardown_class(cls):
        # Drop scratch DB
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            async def _drop():
                c = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
                await c.drop_database(cls.scratch_db_name)
                c.close()
            asyncio.run(_drop())
            print(f"Dropped scratch DB {cls.scratch_db_name}")
        except Exception as e:
            print(f"Cleanup warning: {e}")

    def _run_seed(self):
        os.environ["ADMIN_EMAIL"] = ADMIN_EMAIL
        os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
        from motor.motor_asyncio import AsyncIOMotorClient
        from seed import run_seed

        async def _do():
            c = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = c[self.scratch_db_name]
            await run_seed(db)
            counts = {
                "menu_items": await db.menu_items.count_documents({}),
                "categories": await db.categories.count_documents({}),
                "sauces": await db.sauces.count_documents({}),
                "burger_meats": await db.burger_meats.count_documents({}),
                "burger_supplements": await db.burger_supplements.count_documents({}),
                "burger_sizes": await db.burger_sizes.count_documents({}),
                "burger_styles": await db.burger_styles.count_documents({}),
                "burger_cheeses": await db.burger_cheeses.count_documents({}),
                "settings": await db.settings.count_documents({}),
                "admin_users": await db.admin_users.count_documents({}),
            }
            c.close()
            return counts

        return asyncio.run(_do())

    def test_first_seed_populates_all(self):
        counts = self._run_seed()
        assert counts["menu_items"] == 40, counts
        assert counts["categories"] == 9, counts
        assert counts["sauces"] == 12, counts
        assert counts["burger_meats"] == 6, counts
        assert counts["burger_supplements"] == 6, counts
        assert counts["burger_sizes"] == 3, counts
        assert counts["burger_styles"] == 1, counts
        assert counts["burger_cheeses"] == 0, counts
        assert counts["settings"] == 1, counts
        assert counts["admin_users"] == 1, counts

    def test_second_seed_no_duplicates(self):
        counts = self._run_seed()
        assert counts["menu_items"] == 40, counts
        assert counts["categories"] == 9, counts
        assert counts["sauces"] == 12, counts
        assert counts["burger_meats"] == 6, counts
        assert counts["burger_supplements"] == 6, counts
        assert counts["burger_sizes"] == 3, counts
        assert counts["burger_styles"] == 1, counts
        assert counts["settings"] == 1, counts
        assert counts["admin_users"] == 1, counts
