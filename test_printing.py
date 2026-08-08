import asyncio
import sqlite3
from importlib import reload

import pytest
from aiohttp.test_utils import TestClient, TestServer

import config
import checkout_flow
import db
import printing
import server
import state_machine
from checkout_flow import checkout
from printing import (
    create_print_job,
    get_resendable_print_jobs,
    mark_job_failed,
    mark_job_printed,
    mark_job_sent,
)

PRINT_TOKEN = "test-print-token"


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("PRINTER_AGENT_TOKEN", PRINT_TOKEN)
    reload(config)
    reload(db)
    reload(checkout_flow)
    reload(state_machine)
    reload(printing)
    reload(server)

    with open("schema.sql") as f:
        sql = f.read()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(sql)
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def fake_user():
    return {"id": 111, "username": "testuser", "first_name": "Test", "last_name": "User"}


@pytest.fixture
def seeded_menu():
    from db import get_conn
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO menu_items (name, description, price, category, emoji) VALUES (?,?,?,?,?)",
            [
                ("Item A", "Desc", 5000, "Cat1", "🧾"),
                ("Item B", "Desc", 15000, "Cat2", "🍛"),
            ],
        )
        conn.commit()
    return True


def _make_order(fake_user):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 2, "note": "pedas"}],
        note="test order",
        payment_method="CASH",
    )
    assert result["ok"]
    return result["order_id"]


# ── Antrean job (DB layer) ──────────────────────────────────────────────────

def test_create_print_job_snapshots_order(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    job = create_print_job(order_id)
    assert job["status"] == "pending"
    assert job["payload"]["order_id"] == order_id
    assert job["payload"]["total"] == 10000
    assert job["payload"]["items"][0]["name"] == "Item A"
    assert job["payload"]["items"][0]["note"] == "pedas"


def test_create_print_job_missing_order_returns_none():
    assert create_print_job(9999) is None


def test_create_print_job_includes_address_as_own_field(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 2}],  # 30000, di atas tier default (20000)
        note="test order",
        payment_method="CASH",
        address="The Rich",
    )
    assert result["ok"]
    job = create_print_job(result["order_id"])
    assert job["payload"]["address"] == "The Rich"
    assert "The Rich" not in job["payload"]["note"]


def test_pending_job_is_resendable(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    create_print_job(order_id)
    jobs = get_resendable_print_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "pending"


def test_sent_job_not_resendable_until_failed(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    job = create_print_job(order_id)
    mark_job_sent(job["id"])
    assert get_resendable_print_jobs() == []


def test_failed_job_is_resendable_again(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    job = create_print_job(order_id)
    mark_job_sent(job["id"])
    mark_job_failed(job["id"], "printer offline")
    jobs = get_resendable_print_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["error"] == "printer offline"


def test_printed_job_not_resendable(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    job = create_print_job(order_id)
    mark_job_sent(job["id"])
    mark_job_printed(job["id"])
    assert get_resendable_print_jobs() == []


# ── /ws/printer (server layer) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ws_printer_rejects_without_token():
    app = server.build_app(bot=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/ws/printer")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_ws_printer_rejects_wrong_token():
    app = server.build_app(bot=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/ws/printer?token=salah")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_ws_printer_flushes_pending_job_on_connect(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    create_print_job(order_id)

    app = server.build_app(bot=None)
    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(f"/ws/printer?token={PRINT_TOKEN}") as ws:
            msg = await ws.receive_json(timeout=2)
            assert msg["type"] == "print_job"
            assert msg["order_id"] == order_id
            assert msg["receipt"]["total"] == 10000

    # Job udah dipush ("sent"), jadi gak boleh nongol lagi di antrean resend.
    assert get_resendable_print_jobs() == []


@pytest.mark.asyncio
async def test_ws_printer_ack_printed_marks_job_done(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    job = create_print_job(order_id)

    app = server.build_app(bot=None)
    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(f"/ws/printer?token={PRINT_TOKEN}") as ws:
            await ws.receive_json(timeout=2)  # push awal
            await ws.send_json({"type": "ack", "job_id": job["id"], "status": "printed"})
            await asyncio.sleep(0.05)  # kasih giliran server proses ack

    from db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM print_jobs WHERE id=?", (job["id"],)
        ).fetchone()
    assert row["status"] == "printed"


@pytest.mark.asyncio
async def test_ws_printer_ack_failed_marks_job_resendable(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    job = create_print_job(order_id)

    app = server.build_app(bot=None)
    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(f"/ws/printer?token={PRINT_TOKEN}") as ws:
            await ws.receive_json(timeout=2)  # push awal
            await ws.send_json(
                {"type": "ack", "job_id": job["id"], "status": "failed", "error": "printer offline"}
            )
            await asyncio.sleep(0.05)

    jobs = get_resendable_print_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["error"] == "printer offline"


@pytest.mark.asyncio
async def test_push_print_job_queues_when_no_agent_connected(fake_user, seeded_menu):
    order_id = _make_order(fake_user)
    await server.push_print_job(order_id)
    jobs = get_resendable_print_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_push_print_job_noop_without_order_id():
    await server.push_print_job(None)  # tidak boleh raise
