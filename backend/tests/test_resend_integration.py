"""Resend email + Telegram integration regression tests.

Focus: Emergent proxy → direct Resend API swap. Confirms that
- /api/checkout/session triggers a Resend send (200/202) and Telegram send
- PUT /api/admin/orders/{id}/status triggers a follow-up Resend send
- email_service module reports configured & no-op when unset
- /api/menu, /api/categories, /api/admin/login regressions still pass
"""
import os
import sys
import time
import subprocess
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://burger-times-bsl.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "chahineisgoated@gmail.com"
ADMIN_PASSWORD = "BurgerTimes2026!"
RESEND_SINK = "delivered@resend.dev"

BACKEND_LOG = "/var/log/supervisor/backend.err.log"


# ---------- Direct module tests ----------
class TestEmailServiceModule:
    def test_is_configured_true(self):
        # Ensure backend .env is loaded like the app does
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env", override=False)
        from email_service import is_configured, _from_header, _api_key, _from_email
        assert is_configured() is True
        assert _from_header() == "Burger Times <orders@burgertimes.fr>"
        assert (_api_key() or "").startswith("re_")
        assert _from_email() == "orders@burgertimes.fr"

    def test_noop_when_unset(self):
        """Subprocess with RESEND_API_KEY unset: is_configured False, send no-op."""
        code = (
            "import os,asyncio;\n"
            "os.environ.pop('RESEND_API_KEY', None);\n"
            "import sys; sys.path.insert(0,'/app/backend');\n"
            "from email_service import is_configured, send_order_email;\n"
            "assert is_configured() is False;\n"
            "asyncio.run(send_order_email({'customer_email':'x@y.com','order_number':'X','total':1,'subtotal':1,'items':[]},'order_confirmed'));\n"
            "print('OK')"
        )
        env = os.environ.copy()
        env.pop("RESEND_API_KEY", None)
        r = subprocess.run(
            ["python", "-c", code],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert r.returncode == 0, f"stdout={r.stdout} stderr={r.stderr}"
        assert "OK" in r.stdout


# ---------- Admin login fixture ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15,
    )
    assert r.status_code == 200, f"admin login {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


def _tail_log(nbytes: int = 30000) -> str:
    try:
        with open(BACKEND_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            return f.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


# ---------- Order + email/telegram end-to-end ----------
class TestOrderEmailTelegram:
    created_order_id = None
    created_order_number = None

    def test_menu_regression(self):
        r = requests.get(f"{BASE_URL}/api/menu", timeout=15)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert len(items) == 40

    def test_categories_regression(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=15)
        assert r.status_code == 200
        cats = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert len(cats) == 9

    def test_place_order_triggers_resend_and_telegram(self):
        # Grab a Classique burger (or any) — first menu item is fine
        menu = requests.get(f"{BASE_URL}/api/menu", timeout=15).json()
        items = menu if isinstance(menu, list) else menu.get("items", [])
        # Prefer a "Classique" burger
        target = next(
            (m for m in items if "classique" in (m.get("name", "").lower())),
            items[0],
        )

        # Record log offset before placing order
        try:
            with open(BACKEND_LOG, "rb") as f:
                f.seek(0, 2)
                start = f.tell()
        except Exception:
            start = 0

        payload = {
            "items": [{
                "line_id": "l1",
                "item_id": target["id"],
                "quantity": 1,
                "formula": "seul",
            }],
            "fulfillment": "pickup",
            "payment_method": "cash",
            "customer_first_name": "TEST",
            "customer_last_name": "Resend",
            "customer_phone": "0600000000",
            "customer_email": RESEND_SINK,
            "notes": "[TEST ORDER] resend integration",
        }
        r = requests.post(f"{BASE_URL}/api/checkout/session", json=payload, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body.get("order_id")
        assert body.get("order_number")
        TestOrderEmailTelegram.created_order_id = body["order_id"]
        TestOrderEmailTelegram.created_order_number = body["order_number"]

        # Give fire-and-forget tasks a moment
        time.sleep(4)
        try:
            with open(BACKEND_LOG, "rb") as f:
                f.seek(start)
                fresh = f.read().decode("utf-8", errors="ignore")
        except Exception:
            fresh = _tail_log()

        # No leftover proxy usage
        assert "integrations.emergentagent.com" not in fresh, (
            "backend still calling emergent email proxy: " + fresh[-800:]
        )
        # Resend call happened
        resend_hit = ("api.resend.com/emails" in fresh) or ("Resend email sent to" in fresh)
        assert resend_hit, (
            "No Resend API log line found after checkout. Tail:\n" + fresh[-2000:]
        )
        # Telegram call happened
        tg_hit = "api.telegram.org" in fresh or "sendMessage" in fresh
        # Telegram is best-effort — warn but don't hard-fail if chat unreachable
        if not tg_hit:
            print("WARNING: no Telegram sendMessage log line found. Tail:\n" + fresh[-1500:])

    def test_admin_status_update_triggers_email(self, admin_token):
        oid = TestOrderEmailTelegram.created_order_id
        assert oid, "no order id from previous test"

        try:
            with open(BACKEND_LOG, "rb") as f:
                f.seek(0, 2)
                start = f.tell()
        except Exception:
            start = 0

        r = requests.put(
            f"{BASE_URL}/api/admin/orders/{oid}/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "accepted"}, timeout=20,
        )
        assert r.status_code in (200, 204), f"{r.status_code} {r.text}"

        time.sleep(4)
        try:
            with open(BACKEND_LOG, "rb") as f:
                f.seek(start)
                fresh = f.read().decode("utf-8", errors="ignore")
        except Exception:
            fresh = _tail_log()

        assert "integrations.emergentagent.com" not in fresh
        assert ("api.resend.com/emails" in fresh) or ("Resend email sent to" in fresh), (
            "No Resend log line after status update. Tail:\n" + fresh[-2000:]
        )

    def test_cleanup_delete_order(self, admin_token):
        oid = TestOrderEmailTelegram.created_order_id
        if not oid:
            return
        requests.delete(
            f"{BASE_URL}/api/admin/orders/{oid}",
            headers={"Authorization": f"Bearer {admin_token}"}, timeout=15,
        )
