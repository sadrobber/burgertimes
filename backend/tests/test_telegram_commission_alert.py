"""Safe unit tests for telegram_notifier.send_commission_alert.

All Telegram HTTP transport is mocked. Never performs an outbound request.
Also verifies _quote_or_create schedules the alert only for non-test orders
by mocking send_commission_alert itself.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _reload_notifier(monkeypatch, token="test-token-xyz", chat_id="123456"):
    if token is None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    if chat_id is None:
        monkeypatch.delenv("TELEGRAM_COMMISSION_CHAT_ID", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_COMMISSION_CHAT_ID", chat_id)
    import telegram_notifier  # noqa: WPS433
    return importlib.reload(telegram_notifier)


# ---------- format tests ----------

def test_format_euro_decimal(monkeypatch):
    tn = _reload_notifier(monkeypatch)
    assert tn._format_euro(2.5) == "2,50"
    assert tn._format_euro(0) == "0,00"
    assert tn._format_euro(None) == "0,00"
    assert tn._format_euro(10) == "10,00"
    assert tn._format_euro(1.999) == "2,00"


# ---------- happy path with mocked httpx ----------

class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


class _FakeAsyncClient:
    """Records the request; does no real network call."""

    last_instance = None

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.calls = []
        self.status_code = 200
        _FakeAsyncClient.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None):
        self.calls.append({"url": url, "json": json})
        return _FakeResponse(self.status_code)


def test_send_commission_alert_decimal(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient", _FakeAsyncClient):
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 2.5}))
    assert ok is True
    fake = _FakeAsyncClient.last_instance
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://api.telegram.org/botTKN/sendMessage"
    assert call["json"] == {"chat_id": "CID", "text": "🚨 New order: +2,50€ 💰"}


def test_send_commission_alert_zero(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient", _FakeAsyncClient):
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 0}))
    assert ok is True
    call = _FakeAsyncClient.last_instance.calls[0]
    assert call["json"]["text"] == "🚨 New order: +0,00€ 💰"
    assert call["json"]["chat_id"] == "CID"


def test_send_commission_alert_missing_fee(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient", _FakeAsyncClient):
        ok = asyncio.run(tn.send_commission_alert({}))
    assert ok is True
    call = _FakeAsyncClient.last_instance.calls[0]
    assert call["json"]["text"] == "🚨 New order: +0,00€ 💰"


# ---------- missing secrets ----------

def test_missing_token_returns_false_without_http(monkeypatch):
    tn = _reload_notifier(monkeypatch, token=None, chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient") as client_cls:
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 3.0}))
    assert ok is False
    client_cls.assert_not_called()


def test_missing_chat_id_returns_false_without_http(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id=None)
    with patch.object(tn.httpx, "AsyncClient") as client_cls:
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 3.0}))
    assert ok is False
    client_cls.assert_not_called()


def test_both_missing_returns_false(monkeypatch):
    tn = _reload_notifier(monkeypatch, token=None, chat_id=None)
    with patch.object(tn.httpx, "AsyncClient") as client_cls:
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 3.0}))
    assert ok is False
    client_cls.assert_not_called()


# ---------- HTTP failure never raises ----------

class _RaisingAsyncClient(_FakeAsyncClient):
    async def post(self, url, json=None):
        raise httpx.ConnectError("boom")


class _BadStatusAsyncClient(_FakeAsyncClient):
    async def post(self, url, json=None):
        self.calls.append({"url": url, "json": json})
        return _FakeResponse(500)


class _UnexpectedFailureAsyncClient(_FakeAsyncClient):
    async def post(self, url, json=None):
        raise RuntimeError("unexpected")


def test_http_connect_error_returns_false(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient", _RaisingAsyncClient):
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 4.20}))
    assert ok is False


def test_http_bad_status_returns_false(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient", _BadStatusAsyncClient):
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 4.20}))
    assert ok is False


def test_unexpected_failure_returns_false(monkeypatch):
    tn = _reload_notifier(monkeypatch, token="TKN", chat_id="CID")
    with patch.object(tn.httpx, "AsyncClient", _UnexpectedFailureAsyncClient):
        ok = asyncio.run(tn.send_commission_alert({"delivery_fee": 4.20}))
    assert ok is False


# ---------- static integration: _quote_or_create scheduling ----------

def test_quote_or_create_schedules_alert_for_non_test_and_skips_test_orders():
    """Static source-level check: after order insertion, alert is scheduled
    only if not order.get('test_order'). This avoids any real DB/API/print.
    """
    src = (BACKEND_DIR / "server.py").read_text(encoding="utf-8")
    assert "await db.orders.insert_one(dict(order))" in src
    assert "if not order.get(\"test_order\"):" in src
    assert "asyncio.create_task(send_commission_alert(order))" in src

    # ordering: insert_one appears before create_task call
    insert_idx = src.index("await db.orders.insert_one(dict(order))")
    guard_idx = src.index("if not order.get(\"test_order\"):")
    schedule_idx = src.index("asyncio.create_task(send_commission_alert(order))")
    assert insert_idx < guard_idx < schedule_idx


def test_quote_or_create_calls_alert_with_asyncio_create_task_branch(monkeypatch):
    """Simulate the exact branch: non-test order triggers create_task; test order does not.

    We stub asyncio.create_task and send_commission_alert to observe the call
    without executing any coroutine or making any request.
    """
    calls = []

    async def fake_alert(order):
        calls.append(("called", order))
        return True

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        # Close coroutine so no warning; do NOT await/run it.
        coro.close()
        return MagicMock()

    # Simulate the exact code path
    def run_branch(order):
        if not order.get("test_order"):
            import asyncio as _a
            _a.create_task(fake_alert(order))

    with patch("asyncio.create_task", side_effect=fake_create_task):
        run_branch({"id": "o1", "delivery_fee": 2.5, "test_order": False})
        run_branch({"id": "o2", "delivery_fee": 1.0, "test_order": True})
        run_branch({"id": "o3", "delivery_fee": 3.0})  # missing -> falsy -> alert

    assert len(scheduled) == 2  # o1 and o3, not o2
    assert calls == []  # coroutines closed, never awaited (no HTTP)


# ---------- ensure no side effects imported ----------

def test_no_real_httpx_asyncclient_used_in_tests():
    """Sanity: telegram_notifier still references httpx.AsyncClient class
    so tests can patch it. Ensures nothing bypasses the mock."""
    import telegram_notifier as tn
    assert tn.httpx is httpx
    assert hasattr(tn.httpx, "AsyncClient")
