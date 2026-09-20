"""Backend tests for the customers/suggestions + tablet-print features.

Scope:
1. _upsert_customer helper — with a fake in-memory DB. Verifies:
   * test_order rows are skipped
   * non-test orders upsert on phone_key with only the whitelisted fields
   * repeat call bumps order_count and does NOT create a second row
2. _matching_customers — with fake DB. Verifies:
   * < 3 digits returns []
   * partial phone (last 3 digits) matches
   * response payload has only the 8 whitelisted fields (no _id, no
     order_number, no status, no password_hash, no phone_key, etc.)
3. /api/tablet/customers/suggestions — HTTP live:
   * requires auth (401 without token)
   * 4xx if phone < 3 chars
   * returns matches for a TEST_ prefixed customer we seeded via direct
     Mongo insert, then cleaned up.
4. Menu removable_ingredients default backfill on burger categories via
   /api/menu (public).
5. /tablet/orders code static check:
   * scheduled branch returns {"print_queued": False} without calling
     _push_print_job_background
   * non-scheduled branch calls _push_print_job_background(..., copies=1)

STRICT SAFETY: never POSTs /api/tablet/orders or /kitchen/accept/reprint/
test-print. Never queues a real print. Uses direct Mongo insert only for a
TEST_ prefixed customer and deletes it in fixture teardown.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import re
import sys
import time
from typing import Any, Dict, List

import pytest
import requests

sys.path.insert(0, "/app/backend")
import server as server_module  # noqa: E402
from server import _customer_payload, _matching_customers, _phone_key, _upsert_customer  # noqa: E402

def _load_backend_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return url.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

TABLET_EMAIL = "tablet@burgertimes.fr"
TABLET_PASSWORD = "BurgerTablet2026!"

TEST_PREFIX = "TEST_cust_"


# ---------- Fake DB scaffolding for unit tests ------------------------------


class FakeUpdateResult:
    def __init__(self, matched: int, upserted: bool):
        self.matched_count = matched
        self.upserted_id = "fake-id" if upserted else None


class FakeCollection:
    def __init__(self):
        self.docs: List[Dict[str, Any]] = []

    async def update_one(self, filt, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filt.items()):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v
                return FakeUpdateResult(1, False)
        if upsert:
            new = {}
            new.update(filt)
            new.update(update.get("$setOnInsert", {}))
            new.update(update.get("$set", {}))
            for k, v in update.get("$inc", {}).items():
                new[k] = v
            self.docs.append(new)
            return FakeUpdateResult(0, True)
        return FakeUpdateResult(0, False)

    def find(self, filt=None, projection=None):
        filt = filt or {}

        def _match(d):
            for k, v in filt.items():
                if isinstance(v, dict):
                    if "$ne" in v and d.get(k) == v["$ne"]:
                        return False
                    if "$exists" in v:
                        exists = k in d
                        if v["$exists"] != exists:
                            return False
                else:
                    if d.get(k) != v:
                        return False
            return True

        results = [dict(d) for d in self.docs if _match(d)]
        if projection and projection.get("_id") == 0:
            for r in results:
                r.pop("_id", None)

        class _Cur:
            def __init__(self, items):
                self._items = items

            def sort(self, *_args, **_kwargs):
                return self

            async def to_list(self, _n):
                return self._items

        return _Cur(results)


class FakeDB:
    def __init__(self):
        self.customers = FakeCollection()
        self.orders = FakeCollection()


@pytest.fixture
def fake_db(monkeypatch):
    fdb = FakeDB()
    monkeypatch.setattr(server_module, "db", fdb)
    return fdb


# ---------- _upsert_customer + _matching_customers unit tests ---------------


class TestUpsertCustomer:
    def test_skip_test_orders(self, fake_db):
        order = {
            "test_order": True,
            "customer_phone": "+33612345678",
            "customer_first_name": "Skip",
            "customer_last_name": "Me",
        }
        asyncio.run(_upsert_customer(order))
        assert fake_db.customers.docs == []

    def test_skip_missing_phone(self, fake_db):
        asyncio.run(_upsert_customer({"customer_first_name": "NoPhone"}))
        assert fake_db.customers.docs == []

    def test_upsert_creates_and_only_expected_fields(self, fake_db):
        order = {
            "id": "order-1",
            "order_number": "BT-DEADBEEF",
            "status": "accepted",
            "password_hash": "should-not-leak",
            "customer_first_name": "Alice",
            "customer_last_name": "Martin",
            "customer_phone": "+33 6 12 34 56 78",
            "customer_email": "alice@example.com",
            "address_line1": "1 rue de Test",
            "address_line2": "Apt 3",
            "postal_code": "98000",
            "city": "Monaco",
        }
        asyncio.run(_upsert_customer(order))
        assert len(fake_db.customers.docs) == 1
        doc = fake_db.customers.docs[0]
        # Whitelisted fields present
        assert doc["first"] == "Alice"
        assert doc["last"] == "Martin"
        assert doc["phone"] == "+33 6 12 34 56 78"
        assert doc["email"] == "alice@example.com"
        assert doc["address1"] == "1 rue de Test"
        assert doc["address2"] == "Apt 3"
        assert doc["postal"] == "98000"
        assert doc["city"] == "Monaco"
        assert doc["phone_key"] == "33612345678"
        assert doc["order_count"] == 1
        # Protected order metadata MUST NOT be copied over
        for leaked in ("order_number", "status", "password_hash", "_id"):
            assert leaked not in doc, f"{leaked} leaked into customers doc"

    def test_repeat_upsert_increments_count(self, fake_db):
        order = {
            "customer_phone": "+33612345678",
            "customer_first_name": "Alice",
            "customer_last_name": "Martin",
        }
        asyncio.run(_upsert_customer(order))
        asyncio.run(_upsert_customer(order))
        assert len(fake_db.customers.docs) == 1
        assert fake_db.customers.docs[0]["order_count"] == 2


class TestMatchingCustomers:
    def test_returns_empty_when_lt_3_digits(self, fake_db):
        fake_db.customers.docs.append(
            {"phone_key": "33612345678", "phone": "+33612345678", "first": "A", "last": "B"}
        )
        result = asyncio.run(_matching_customers("12"))
        assert result == []

    def test_partial_match_from_customers(self, fake_db):
        fake_db.customers.docs.append(
            {
                "phone_key": "33612345678",
                "phone": "+33612345678",
                "first": "Alice",
                "last": "Martin",
                "email": "a@x.com",
                "address1": "",
                "address2": "",
                "postal": "",
                "city": "",
                "updated_at": "z",
                # These MUST be filtered out by _customer_payload:
                "order_count": 5,
                "password_hash": "secret",
                "_id": "objid",
            }
        )
        # last 3 digits "678" should match phone_key end
        matches = asyncio.run(_matching_customers("678"))
        assert len(matches) == 1
        cust = matches[0]
        assert set(cust.keys()) == {
            "first",
            "last",
            "phone",
            "email",
            "address1",
            "address2",
            "postal",
            "city",
        }
        assert cust["first"] == "Alice"
        assert cust["phone"] == "+33612345678"

    def test_falls_back_to_legacy_orders(self, fake_db):
        # No customers doc — should look up legacy orders.
        fake_db.orders.docs.append(
            {
                "customer_phone": "+33698765432",
                "customer_first_name": "Bob",
                "customer_last_name": "Legacy",
                "customer_email": "bob@x.com",
                "test_order": False,
                "created_at": "2024-01-01",
                # Protected fields that must not leak:
                "status": "delivered",
                "order_number": "BT-LEGACY01",
            }
        )
        matches = asyncio.run(_matching_customers("432"))
        assert len(matches) == 1
        cust = matches[0]
        assert cust["first"] == "Bob"
        assert set(cust.keys()) == {
            "first",
            "last",
            "phone",
            "email",
            "address1",
            "address2",
            "postal",
            "city",
        }


# ---------- HTTP live tests -------------------------------------------------


@pytest.fixture(scope="module")
def tablet_token():
    r = requests.post(
        f"{API}/tablet/login", json={"email": TABLET_EMAIL, "password": TABLET_PASSWORD}, timeout=15
    )
    assert r.status_code == 200, f"tablet login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def tablet_headers(tablet_token):
    return {"Authorization": f"Bearer {tablet_token}"}


@pytest.fixture
def seeded_test_customer():
    """Insert a TEST_ prefixed customer straight into Mongo via a
    synchronous pymongo client. Deleted in teardown.

    We do not go through /tablet/orders (which would fire a real print).
    """
    from pymongo import MongoClient  # sync client

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        # Fall back to reading backend/.env
        try:
            with open("/app/backend/.env") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("MONGO_URL=") and not mongo_url:
                        mongo_url = line.split("=", 1)[1]
                    elif line.startswith("DB_NAME=") and not db_name:
                        db_name = line.split("=", 1)[1]
        except FileNotFoundError:
            pass
    assert mongo_url and db_name, "MONGO_URL/DB_NAME missing"
    sync_client = MongoClient(mongo_url)
    coll = sync_client[db_name].customers

    unique = f"999{int(time.time()) % 10_000_000:07d}"
    doc = {
        "phone_key": unique,
        "id": f"{TEST_PREFIX}{unique}",
        "first": f"{TEST_PREFIX}Suggest",
        "last": "Match",
        "phone": f"+{unique}",
        "email": f"{TEST_PREFIX}sug@test.local",
        "address1": "",
        "address2": "",
        "postal": "",
        "city": "",
        "order_count": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    coll.delete_many({"phone_key": unique})
    coll.insert_one(dict(doc))
    try:
        yield {"phone_key": unique, "phone": doc["phone"]}
    finally:
        coll.delete_many({"phone_key": unique})
        sync_client.close()


class TestSuggestionsEndpoint:
    def test_requires_auth(self):
        r = requests.get(f"{API}/tablet/customers/suggestions", params={"phone": "123"}, timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_rejects_short_phone(self, tablet_headers):
        r = requests.get(
            f"{API}/tablet/customers/suggestions",
            params={"phone": "12"},
            headers=tablet_headers,
            timeout=15,
        )
        # Query() min_length=3 -> 422
        assert r.status_code == 422

    def test_returns_partial_matches_and_only_safe_fields(
        self, tablet_headers, seeded_test_customer
    ):
        # Match on last 3 digits of the seeded phone_key
        last3 = seeded_test_customer["phone_key"][-3:]
        r = requests.get(
            f"{API}/tablet/customers/suggestions",
            params={"phone": last3},
            headers=tablet_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "customers" in data
        # Our seeded customer must be included.
        seeded_phone = seeded_test_customer["phone"]
        matching = [c for c in data["customers"] if c.get("phone") == seeded_phone]
        assert matching, f"seeded customer not returned in suggestions: {data}"
        cust = matching[0]
        # ONLY the 8 whitelisted fields.
        assert set(cust.keys()) == {
            "first",
            "last",
            "phone",
            "email",
            "address1",
            "address2",
            "postal",
            "city",
        }, f"unexpected fields exposed: {cust.keys()}"
        for leaked in ("_id", "id", "order_count", "phone_key", "order_number", "status", "password_hash"):
            assert leaked not in cust


# ---------- Menu default removals ------------------------------------------


class TestMenuDefaults:
    def test_burger_categories_have_default_removals(self):
        r = requests.get(f"{API}/menu", timeout=15)
        assert r.status_code == 200
        payload = r.json()
        items = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
        assert isinstance(items, list), f"unexpected /menu shape: {type(payload)}"
        burger_cats = {"signatures", "classiques", "smash-burgers"}
        burgers = [it for it in items if it.get("category") in burger_cats]
        assert burgers, "no burger items returned by /menu"
        expected = {"oignons", "cornichons", "salade", "tomate", "sauce"}
        offenders = []
        for it in burgers:
            rem = set(it.get("removable_ingredients") or [])
            if not expected.issubset(rem):
                offenders.append((it.get("name"), it.get("category"), sorted(rem)))
        assert not offenders, f"burger items missing default removals: {offenders}"


# ---------- /tablet/orders static (source-level) checks ---------------------


class TestTabletOrdersPrintCodePath:
    """Read the tablet_create_order source and assert it queues exactly
    one print copy for non-scheduled orders and skips print entirely for
    scheduled orders. NO real HTTP call is made to /api/tablet/orders."""

    def test_scheduled_branch_returns_print_queued_false(self):
        src = inspect.getsource(server_module.tablet_create_order)
        # scheduled branch must return print_queued False BEFORE the
        # _push_print_job_background call
        assert 'print_queued": False' in src or "'print_queued': False" in src, src
        # Must reference scheduled_delivery_start check
        assert "scheduled_delivery_start" in src

    def test_non_scheduled_queues_single_print_copy(self):
        src = inspect.getsource(server_module.tablet_create_order)
        # Exactly one call to _push_print_job_background in this function
        assert src.count("_push_print_job_background") == 1
        # Must pass copies=1 (not the default 3)
        assert re.search(r"_push_print_job_background\([^)]*copies=1", src), src
        # print_queued: True on the accepted branch
        assert 'print_queued": True' in src or "'print_queued': True" in src

    def test_scheduled_branch_precedes_print_queue(self):
        src = inspect.getsource(server_module.tablet_create_order)
        scheduled_idx = src.find("scheduled_delivery_start")
        print_idx = src.find("_push_print_job_background")
        assert scheduled_idx != -1 and print_idx != -1
        assert scheduled_idx < print_idx, (
            "scheduled check must short-circuit before print is queued"
        )

    def test_push_print_job_background_default_is_three(self):
        # Kitchen accept still defaults to 3 copies. tablet passes copies=1.
        sig = inspect.signature(server_module._push_print_job_background)
        assert sig.parameters["copies"].default == 3
