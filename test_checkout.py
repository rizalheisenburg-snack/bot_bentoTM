import json
import sqlite3
from importlib import reload
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from aiohttp.test_utils import TestClient, TestServer

import config
import checkout_flow
import db
import server
import state_machine
from get_initdata import generate_init_data

from db import get_conn, get_user_min_order, set_user_min_order
from checkout_flow import checkout
from state_machine import (
    CANCEL_REASONS,
    change_payment_method,
    force_cancel_order,
    get_active_orders,
    get_cancel_warning,
    get_express_orders_awaiting_location_reminder,
    get_order,
    get_pending_express_location_order,
    mark_express_reminder_sent,
    mark_paid,
    save_express_location,
    set_admin_msg_id,
    set_express_location_requested,
    transition,
)

@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    reload(config)
    reload(db)
    reload(checkout_flow)
    reload(state_machine)
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

@pytest.fixture
def modifier_product():
    """Insert 1 produk komposit + 2 modifier group (masing-masing wajib pilih 1),
    tiap grup 2 opsi. Return dict berisi id-id yang dibutuhkan test."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO menu_items (name, description, price, category, emoji) VALUES (?,?,?,?,?)",
            ("Nasi Campur Test", "Desc", 10_000, "Menu Nasi", "🍱"),
        )
        product_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO modifier_groups (product_id, name, min_select, max_select, is_required) VALUES (?,?,?,?,?)",
            (product_id, "Nasi", 1, 1, 1),
        )
        nasi_group_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO modifier_options (group_id, name, price_delta) VALUES (?,?,?)",
            (nasi_group_id, "Nasi Putih", 0),
        )
        nasi_putih_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO modifier_options (group_id, name, price_delta) VALUES (?,?,?)",
            (nasi_group_id, "Nasi Merah", 4_000),
        )
        nasi_merah_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO modifier_groups (product_id, name, min_select, max_select, is_required) VALUES (?,?,?,?,?)",
            (product_id, "Sayur", 1, 1, 1),
        )
        sayur_group_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO modifier_options (group_id, name, price_delta) VALUES (?,?,?)",
            (sayur_group_id, "Capcay", 0),
        )
        capcay_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO modifier_options (group_id, name, price_delta) VALUES (?,?,?)",
            (sayur_group_id, "Jengkol", 5_000),
        )
        jengkol_id = cur.lastrowid
        conn.commit()

    return {
        "product_id": product_id,
        "nasi_group_id": nasi_group_id,
        "nasi_putih_id": nasi_putih_id,
        "nasi_merah_id": nasi_merah_id,
        "sayur_group_id": sayur_group_id,
        "capcay_id": capcay_id,
        "jengkol_id": jengkol_id,
    }

def test_checkout_cash_assigns_payment_method(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["payment_method"] == "CASH"
    assert order["total"] == 5000

def test_checkout_aba_assigns_payment_method(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 1}],
        note="[Transfer ABA] [KD] test",
        payment_method="ABA",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["payment_method"] == "ABA"
    assert order["note"].startswith("[Transfer ABA]")

def test_checkout_rejects_voucher_payment_method(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 1}],
        note="[KD] test",
        payment_method="VOUCHER",
    )
    assert not result["ok"]
    assert "Cash atau ABA" in result["error"]

def test_checkout_rejects_below_min_order_for_kd_tier(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 2}],  # 2x 15000 = 30000, di bawah tier KD (40000)
        note="test",
        payment_method="CASH",
        address="KD",
    )
    assert not result["ok"]
    assert "40.000" in result["error"] or "40,000" in result["error"]

def test_checkout_accepts_at_min_order_for_kd_tier(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 3}],  # 3x 15000 = 45000, di atas tier KD (40000)
        note="test",
        payment_method="CASH",
        address="KD",
    )
    assert result["ok"]

def test_checkout_rejects_below_default_tier_for_other_address(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],  # 5000, di bawah default tier (20000)
        note="test",
        payment_method="CASH",
        address="Hp Tower",
    )
    assert not result["ok"]

def test_checkout_accepts_at_default_tier_for_other_address(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 2}],  # 30000, di atas default tier (20000)
        note="test",
        payment_method="CASH",
        address="WON",
    )
    assert result["ok"]

def test_checkout_skips_min_order_check_when_address_blank(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],  # 5000, gak ada address dikirim
        note="test",
        payment_method="CASH",
    )
    assert result["ok"]

def test_checkout_stores_address_as_own_field_not_in_note(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 3}],
        note="tolong extra pedas",
        payment_method="CASH",
        address="The Rich",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["address"] == "The Rich"
    assert order["note"] == "tolong extra pedas"

def test_checkout_address_blank_stores_none(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="test",
        payment_method="CASH",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["address"] is None

def test_checkout_drops_unavailable_items_and_still_accepts_order(fake_user, seeded_menu):
    with get_conn() as conn:
        conn.execute("UPDATE menu_items SET available=0 WHERE id=2")
        conn.commit()

    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}, {"item_id": 2, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    assert result["total"] == 5000
    assert len(result["unavailable_items"]) == 1
    order = get_order(result["order_id"])
    assert order["status"] == "Diterima"

# ── Duplicate / double-tap guard ──────────────────────────────────────────────

def test_checkout_duplicate_within_window_returns_same_order(fake_user, seeded_menu):
    first = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 2}],
        note="[KD] test",
        payment_method="CASH",
    )
    second = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 2}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert first["ok"] and second["ok"]
    assert second["order_id"] == first["order_id"]
    assert second.get("duplicate") is True
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) c FROM orders WHERE user_id=?", (fake_user["id"],)
        ).fetchone()["c"]
    assert count == 1

def test_checkout_different_items_not_treated_as_duplicate(fake_user, seeded_menu):
    first = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    second = checkout(
        user=fake_user,
        items=[{"item_id": 2, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert first["ok"] and second["ok"]
    assert second["order_id"] != first["order_id"]
    assert not second.get("duplicate")

def test_checkout_duplicate_outside_window_creates_new_order(fake_user, seeded_menu):
    first = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET created_at = datetime('now', '-1 hour') WHERE id = ?",
            (first["order_id"],),
        )
        conn.commit()
    second = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert second["ok"]
    assert second["order_id"] != first["order_id"]
    assert not second.get("duplicate")


# ── Minimal order per lokasi ─────────────────────────────────────────────────

def test_get_user_min_order_returns_none_when_never_set():
    assert get_user_min_order(999) is None

def test_set_user_min_order_roundtrip():
    set_user_min_order(111, 20000, 1.2)
    row = get_user_min_order(111)
    assert row["min_order"] == 20000
    assert row["distance_km"] == pytest.approx(1.2)

def test_set_user_min_order_upserts_not_duplicates():
    set_user_min_order(111, 20000, 1.2)
    set_user_min_order(111, 40000, 8.5)
    row = get_user_min_order(111)
    assert row["min_order"] == 40000
    assert row["distance_km"] == pytest.approx(8.5)
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) c FROM users WHERE user_id=111").fetchone()["c"]
    assert count == 1


def test_cash_order_stays_unpaid(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 2}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    assert result["total"] == 10000
    assert result["auto_paid"] is False
    order = get_order(result["order_id"])
    assert order["payment_status"] == "UNPAID"


# ── Catatan custom per item ──────────────────────────────────────────────────

def test_checkout_saves_item_note(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1, "note": "gak pake bawang"}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["items"][0]["item_note"] == "gak pake bawang"

def test_checkout_trims_whitespace_only_note_to_none(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1, "note": "   "}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["items"][0]["item_note"] is None

def test_checkout_item_note_optional_backward_compat(fake_user, seeded_menu):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    order = get_order(result["order_id"])
    assert order["items"][0]["item_note"] is None

def test_checkout_drops_note_with_unavailable_item(fake_user, seeded_menu):
    with get_conn() as conn:
        conn.execute("UPDATE menu_items SET available=0 WHERE id=2")
        conn.commit()

    result = checkout(
        user=fake_user,
        items=[
            {"item_id": 1, "qty": 1},
            {"item_id": 2, "qty": 1, "note": "pedas ya"},
        ],
        note="[KD] test",
        payment_method="CASH",
    )
    assert result["ok"]
    assert len(result["unavailable_items"]) == 1
    order = get_order(result["order_id"])
    assert len(order["items"]) == 1
    assert order["items"][0]["item_id"] == 1


# ── Mirror order ke pelanggan (Task 2) ──────────────────────────────────────

class _FakeBot:
    """Bot palsu yang beneran baca isi file foto, biar ketauan kalau
    file-nya kepanggil sesudah closed (bug closed-file di _send_photo)."""
    def __init__(self):
        self.messages = []
        self.photos = []
        self.edits = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_to_message_id=None):
        self.messages.append(text)

    async def send_photo(self, chat_id, photo):
        self.photos.append(photo.read())

    async def edit_message_text(self, chat_id, message_id, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)


def _fake_request(bot):
    return SimpleNamespace(app={"bot": bot})


@pytest.fixture
def fake_qr_images(monkeypatch, tmp_path):
    aba_path = tmp_path / "aba.jpg"
    aba_path.write_bytes(b"ABA_QR_BYTES")
    monkeypatch.setattr(config, "ABA_QR_IMAGE_PATH", str(aba_path))


@pytest.mark.asyncio
async def test_mirror_aba_no_voucher_sends_aba_qr_only(fake_user, seeded_menu, fake_qr_images):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="[Transfer ABA] [KD] test", payment_method="ABA",
    )
    assert result["ok"] and not result["auto_paid"]

    bot = _FakeBot()
    await server._send_order_mirror_to_user(_fake_request(bot), result["order_id"])

    assert len(bot.messages) == 1
    assert "bukti transfer" in bot.messages[0]
    assert bot.photos == [b"ABA_QR_BYTES"]


@pytest.mark.asyncio
async def test_mirror_aba_sends_aba_qr_only(fake_user, seeded_menu, fake_qr_images):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="[Transfer ABA] [KD] test", payment_method="ABA",
    )
    assert result["ok"] and result["total"] == 15000 and not result["auto_paid"]

    bot = _FakeBot()
    await server._send_order_mirror_to_user(_fake_request(bot), result["order_id"])

    assert len(bot.messages) == 1
    assert "bukti transfer" in bot.messages[0]
    assert bot.photos == [b"ABA_QR_BYTES"]


@pytest.mark.asyncio
async def test_mirror_cash_sends_no_photo(fake_user, seeded_menu, fake_qr_images):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    assert result["ok"] and result["total"] == 15000 and not result["auto_paid"]

    bot = _FakeBot()
    await server._send_order_mirror_to_user(_fake_request(bot), result["order_id"])

    assert len(bot.messages) == 1
    assert "bukti transfer" not in bot.messages[0]
    assert bot.photos == []


@pytest.mark.asyncio
async def test_mirror_full_cash_no_voucher_sends_no_photo(fake_user, seeded_menu, fake_qr_images):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    assert result["ok"] and not result["auto_paid"]

    bot = _FakeBot()
    await server._send_order_mirror_to_user(_fake_request(bot), result["order_id"])

    assert len(bot.messages) == 1
    assert "bukti transfer" not in bot.messages[0]
    assert bot.photos == []


@pytest.mark.asyncio
async def test_mirror_cash_order_sends_no_photo(fake_user, seeded_menu, fake_qr_images):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    assert result["ok"] and result["total"] == 5000 and not result["auto_paid"]

    bot = _FakeBot()
    await server._send_order_mirror_to_user(_fake_request(bot), result["order_id"])

    assert len(bot.messages) == 1
    assert "bukti transfer" not in bot.messages[0]
    assert bot.photos == []


@pytest.mark.asyncio
async def test_mirror_includes_item_note(fake_user, seeded_menu, fake_qr_images):
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1, "note": "pedas banget ya"}],
        note="[KD] test", payment_method="CASH",
    )
    assert result["ok"] and not result["auto_paid"]

    bot = _FakeBot()
    await server._send_order_mirror_to_user(_fake_request(bot), result["order_id"])

    assert len(bot.messages) == 1
    assert "pedas banget ya" in bot.messages[0]


# ── Ganti metode pembayaran (Fase 1.3) ───────────────────────────────────────

def test_change_payment_method_switches_cash_to_aba(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    r = change_payment_method(result["order_id"], "ABA")
    assert r["ok"]
    assert r["old_method"] == "CASH" and r["new_method"] == "ABA"
    order = get_order(result["order_id"])
    assert order["payment_method"] == "ABA"


def test_change_payment_method_rejects_same_method(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    r = change_payment_method(result["order_id"], "CASH")
    assert not r["ok"]
    assert "sama" in r["error"]


def test_change_payment_method_rejects_invalid_method(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    r = change_payment_method(result["order_id"], "VOUCHER")
    assert not r["ok"]
    assert "tidak valid" in r["error"]


def test_change_payment_method_locked_after_paid(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    mark_paid(result["order_id"], "RIEL")
    r = change_payment_method(result["order_id"], "ABA")
    assert not r["ok"]
    assert "terkunci" in r["error"]
    order = get_order(result["order_id"])
    assert order["payment_method"] == "CASH"


def test_change_payment_method_allowed_regardless_of_kitchen_status(fake_user, seeded_menu):
    """Beda dari cancel: ganti metode boleh selama UNPAID, tidak peduli status dapur."""
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    assert transition(order_id, "Diproses", actor="owner")["ok"]
    assert transition(order_id, "Siap", actor="owner")["ok"]

    r = change_payment_method(order_id, "ABA")
    assert r["ok"], r.get("error")
    order = get_order(order_id)
    assert order["payment_method"] == "ABA"
    assert order["status"] == "Siap"


def test_change_payment_method_missing_order():
    r = change_payment_method(999999, "ABA")
    assert not r["ok"]
    assert "tidak ditemukan" in r["error"]


@pytest.mark.asyncio
async def test_notify_owner_payment_method_change_sends_text_and_edits_card(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    set_admin_msg_id(result["order_id"], 555)
    change_result = change_payment_method(result["order_id"], "ABA")
    assert change_result["ok"]

    bot = _FakeBot()
    await server._notify_owner_payment_method_change(_fake_request(bot), result["order_id"], change_result)

    assert len(bot.messages) == 1
    assert "CASH" in bot.messages[0] and "ABA" in bot.messages[0]
    assert len(bot.edits) == 1
    assert "ABA" in bot.edits[0]


# ── Cancel order / force-cancel (Fase 1.4) ───────────────────────────────────

def test_force_cancel_bypasses_transitions_from_siap(fake_user, seeded_menu):
    """Beda dari transition() biasa: force-cancel harus jalan walau TRANSITIONS['Siap'] kosong."""
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    assert transition(order_id, "Diproses", actor="owner")["ok"]
    assert transition(order_id, "Siap", actor="owner")["ok"]

    # transition() biasa tetap menolak (regresi check TRANSITIONS lama tidak berubah)
    blocked = transition(order_id, "Dibatalkan", actor="owner")
    assert not blocked["ok"]

    r = force_cancel_order(order_id, "Stok habis")
    assert r["ok"]
    order = get_order(order_id)
    assert order["status"] == "Dibatalkan"
    assert order["cancel_reason"] == "Stok habis"


def test_force_cancel_warning_when_paid(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    mark_paid(order_id, "RIEL")

    r = force_cancel_order(order_id, "Request customer")
    assert r["ok"]
    assert r["warning"] is not None
    assert "refund manual" in r["warning"]


def test_force_cancel_no_warning_when_unpaid(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    r = force_cancel_order(result["order_id"], "Kesalahan input")
    assert r["ok"]
    assert r["warning"] is None


def test_get_cancel_warning_matches_payment_status():
    assert get_cancel_warning("PAID") is not None
    assert get_cancel_warning("UNPAID") is None


def test_force_cancel_rejects_invalid_reason(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    r = force_cancel_order(result["order_id"], "Alasan ngasal")
    assert not r["ok"]
    assert "tidak valid" in r["error"]
    order = get_order(result["order_id"])
    assert order["status"] != "Dibatalkan"


def test_force_cancel_missing_order():
    r = force_cancel_order(999999, "Stok habis")
    assert not r["ok"]
    assert "tidak ditemukan" in r["error"]


def test_customer_cancel_still_blocked_outside_diterima(fake_user, seeded_menu):
    """Regresi: window cancel customer tidak boleh berubah dari fase sebelumnya."""
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    assert transition(order_id, "Diproses", actor="owner")["ok"]

    r = transition(order_id, "Dibatalkan", actor="customer")
    assert not r["ok"]
    assert "dikonfirmasi" in r["error"]


@pytest.mark.asyncio
async def test_notify_customer_force_cancel_sends_reason(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    cancel_result = force_cancel_order(order_id, "Stok habis")
    assert cancel_result["ok"]

    bot = _FakeBot()
    await server._notify_customer_force_cancel(_fake_request(bot), order_id, cancel_result)

    assert len(bot.messages) == 1
    assert "Stok habis" in bot.messages[0]
    assert f"#{order_id}" in bot.messages[0]


# ── Kanban /admin + WebSocket (Fase 1.5) ─────────────────────────────────────

def test_status_changed_at_defaults_to_created_at_on_checkout(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order = get_order(result["order_id"])
    assert order["status_changed_at"] == order["created_at"]


def test_status_changed_at_unaffected_by_mark_paid(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status_changed_at='2020-01-01 00:00:00' WHERE id=?", (order_id,)
        )
        conn.commit()

    mark_paid(order_id, "RIEL")
    order = get_order(order_id)
    assert order["status_changed_at"] == "2020-01-01 00:00:00"


def test_status_changed_at_unaffected_by_change_payment_method(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status_changed_at='2020-01-01 00:00:00' WHERE id=?", (order_id,)
        )
        conn.commit()

    change_payment_method(order_id, "ABA")
    order = get_order(order_id)
    assert order["status_changed_at"] == "2020-01-01 00:00:00"


def test_status_changed_at_updates_on_transition(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status_changed_at='2020-01-01 00:00:00' WHERE id=?", (order_id,)
        )
        conn.commit()

    transition(order_id, "Diproses", actor="owner")
    order = get_order(order_id)
    assert order["status_changed_at"] != "2020-01-01 00:00:00"


def test_status_changed_at_updates_on_force_cancel(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status_changed_at='2020-01-01 00:00:00' WHERE id=?", (order_id,)
        )
        conn.commit()

    force_cancel_order(order_id, "Stok habis")
    order = get_order(order_id)
    assert order["status_changed_at"] != "2020-01-01 00:00:00"


def test_get_active_orders_includes_diterima_regardless_of_age(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    with get_conn() as conn:
        conn.execute("UPDATE orders SET created_at='2020-01-01 00:00:00' WHERE id=?", (order_id,))
        conn.commit()

    active_ids = [o["id"] for o in get_active_orders()]
    assert order_id in active_ids


def test_get_active_orders_excludes_old_terminal_status(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    force_cancel_order(order_id, "Stok habis")
    with get_conn() as conn:
        conn.execute("UPDATE orders SET created_at='2020-01-01 00:00:00' WHERE id=?", (order_id,))
        conn.commit()

    active_ids = [o["id"] for o in get_active_orders()]
    assert order_id not in active_ids


def test_get_active_orders_includes_today_terminal_status(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="[KD] test", payment_method="CASH",
    )
    order_id = result["order_id"]
    force_cancel_order(order_id, "Stok habis")

    active_ids = [o["id"] for o in get_active_orders()]
    assert order_id in active_ids


def test_get_active_orders_attaches_items(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 2}],
        note="[KD] test", payment_method="CASH",
    )
    order = next(o for o in get_active_orders() if o["id"] == result["order_id"])
    assert len(order["items"]) == 1
    assert order["items"][0]["item_name"] == "Item A"
    assert order["items"][0]["qty"] == 2


def test_get_active_orders_empty_when_no_orders():
    assert get_active_orders() == []


@pytest.mark.asyncio
async def test_ws_admin_rejects_without_init_data():
    app = server.build_app(bot=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/ws/admin")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_ws_admin_rejects_non_owner():
    app = server.build_app(bot=None)
    init_data = generate_init_data(config.BOT_TOKEN, config.OWNER_ID + 1)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(f"/ws/admin?initData={quote(init_data, safe='')}")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_ws_admin_accepts_owner_and_broadcasts_order_update(fake_user, seeded_menu):
    app = server.build_app(bot=None)
    init_data = generate_init_data(config.BOT_TOKEN, config.OWNER_ID)
    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(f"/ws/admin?initData={quote(init_data, safe='')}") as ws:
            result = checkout(
                user=fake_user, items=[{"item_id": 1, "qty": 1}],
                note="[KD] test", payment_method="CASH",
            )
            order_id = result["order_id"]
            await server.broadcast_order_update(order_id)

            msg = await ws.receive_json(timeout=2)
            assert msg["type"] == "order_update"
            assert msg["order"]["id"] == order_id


@pytest.mark.asyncio
async def test_ws_admin_broadcast_noop_without_clients():
    # Tidak ada client connected — broadcast harus no-op, tidak boleh raise.
    await server.broadcast_order_update(None)
    await server.broadcast_order_update(999999)


# ── Modifier groups ──────────────────────────────────────────────────────────

def test_checkout_rejects_missing_required_modifier_group(fake_user, modifier_product):
    result = checkout(
        user=fake_user,
        items=[{
            "item_id": modifier_product["product_id"], "qty": 1,
            "modifiers": [
                {"group_id": modifier_product["nasi_group_id"], "option_id": modifier_product["nasi_putih_id"]},
                # Sayur belum dipilih sama sekali
            ],
        }],
        note="test",
        payment_method="CASH",
    )
    assert not result["ok"]
    assert "Sayur" in result["error"]

def test_checkout_rejects_when_no_modifiers_sent_at_all(fake_user, modifier_product):
    result = checkout(
        user=fake_user,
        items=[{"item_id": modifier_product["product_id"], "qty": 1}],
        note="test",
        payment_method="CASH",
    )
    assert not result["ok"]

def test_checkout_rejects_option_not_belonging_to_its_group(fake_user, modifier_product):
    result = checkout(
        user=fake_user,
        items=[{
            "item_id": modifier_product["product_id"], "qty": 1,
            "modifiers": [
                # capcay_id milik grup Sayur, dikirim seolah-olah pilihan grup Nasi
                {"group_id": modifier_product["nasi_group_id"], "option_id": modifier_product["capcay_id"]},
                {"group_id": modifier_product["sayur_group_id"], "option_id": modifier_product["capcay_id"]},
            ],
        }],
        note="test",
        payment_method="CASH",
    )
    assert not result["ok"]

def test_checkout_succeeds_with_all_required_modifiers_and_correct_price(fake_user, modifier_product):
    result = checkout(
        user=fake_user,
        items=[{
            "item_id": modifier_product["product_id"], "qty": 2,
            "modifiers": [
                {"group_id": modifier_product["nasi_group_id"], "option_id": modifier_product["nasi_merah_id"]},  # +4000
                {"group_id": modifier_product["sayur_group_id"], "option_id": modifier_product["jengkol_id"]},   # +5000
            ],
        }],
        note="test",
        payment_method="CASH",
    )
    assert result["ok"]
    # base 10000 + 4000 + 5000 = 19000 per unit, qty 2 => 38000
    assert result["subtotal"] == 38_000
    order = get_order(result["order_id"])
    item = order["items"][0]
    assert item["unit_price"] == 19_000
    mods = json.loads(item["modifiers_json"])
    assert sorted(m["option_name"] for m in mods) == ["Jengkol", "Nasi Merah"]

def test_checkout_zero_delta_combination_matches_base_price(fake_user, modifier_product):
    result = checkout(
        user=fake_user,
        items=[{
            "item_id": modifier_product["product_id"], "qty": 1,
            "modifiers": [
                {"group_id": modifier_product["nasi_group_id"], "option_id": modifier_product["nasi_putih_id"]},
                {"group_id": modifier_product["sayur_group_id"], "option_id": modifier_product["capcay_id"]},
            ],
        }],
        note="test",
        payment_method="CASH",
    )
    assert result["ok"]
    assert result["subtotal"] == 10_000

def test_checkout_duplicate_guard_ignores_orders_with_different_modifiers(fake_user, modifier_product):
    common_kwargs = dict(user=fake_user, note="test", payment_method="CASH")
    r1 = checkout(
        items=[{
            "item_id": modifier_product["product_id"], "qty": 1,
            "modifiers": [
                {"group_id": modifier_product["nasi_group_id"], "option_id": modifier_product["nasi_putih_id"]},
                {"group_id": modifier_product["sayur_group_id"], "option_id": modifier_product["capcay_id"]},
            ],
        }],
        **common_kwargs,
    )
    r2 = checkout(
        items=[{
            "item_id": modifier_product["product_id"], "qty": 1,
            "modifiers": [
                {"group_id": modifier_product["nasi_group_id"], "option_id": modifier_product["nasi_merah_id"]},
                {"group_id": modifier_product["sayur_group_id"], "option_id": modifier_product["capcay_id"]},
            ],
        }],
        **common_kwargs,
    )
    assert r1["ok"] and r2["ok"]
    assert r1["order_id"] != r2["order_id"]
    assert not r2.get("duplicate")

def test_checkout_plain_item_without_modifier_groups_is_unaffected(fake_user, seeded_menu):
    # Regresi: produk tanpa modifier_groups checkout normal, field "modifiers" gak perlu dikirim.
    result = checkout(
        user=fake_user,
        items=[{"item_id": 1, "qty": 1}],
        note="test",
        payment_method="CASH",
    )
    assert result["ok"]


# ── Kurir Express ──────────────────────────────────────────────────────────────

def test_checkout_defaults_to_internal_delivery(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="test", payment_method="CASH",
    )
    assert result["ok"]
    assert result["delivery_type"] == "internal"
    order = get_order(result["order_id"])
    assert order["delivery_type"] == "internal"


def test_checkout_express_with_cash_is_rejected(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="test", payment_method="CASH", delivery_type="express",
    )
    assert not result["ok"]
    assert "ABA" in result["error"]


def test_checkout_express_with_aba_succeeds_and_sets_delivery_type(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    assert result["ok"]
    assert result["delivery_type"] == "express"
    order = get_order(result["order_id"])
    assert order["delivery_type"] == "express"


def test_checkout_invalid_delivery_type_normalizes_to_internal(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="test", payment_method="CASH", delivery_type="rocket",
    )
    assert result["ok"]
    assert result["delivery_type"] == "internal"


def test_checkout_duplicate_detection_distinguishes_delivery_type(fake_user, seeded_menu):
    first = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="internal",
    )
    second = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    assert first["ok"] and second["ok"]
    assert second["order_id"] != first["order_id"]
    assert not second.get("duplicate")


def test_change_payment_method_rejects_cash_for_express_order(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    r = change_payment_method(result["order_id"], "CASH")
    assert not r["ok"]
    assert "Express" in r["error"]
    order = get_order(result["order_id"])
    assert order["payment_method"] == "ABA"


def test_get_pending_express_location_order_returns_none_when_no_express_order(fake_user, seeded_menu):
    checkout(
        user=fake_user, items=[{"item_id": 1, "qty": 1}],
        note="test", payment_method="CASH",
    )
    assert get_pending_express_location_order(fake_user["id"]) is None


def test_get_pending_express_location_order_returns_order_awaiting_location(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    pending = get_pending_express_location_order(fake_user["id"])
    assert pending is not None
    assert pending["id"] == result["order_id"]


def test_get_pending_express_location_order_none_after_location_saved(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    save_express_location(result["order_id"], 10.123, 103.456)
    assert get_pending_express_location_order(fake_user["id"]) is None
    order = get_order(result["order_id"])
    assert order["customer_lat"] == pytest.approx(10.123)
    assert order["customer_lng"] == pytest.approx(103.456)
    assert order["location_received_at"] is not None


def test_get_express_orders_awaiting_location_reminder_respects_threshold_and_one_time_flag(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    order_id = result["order_id"]

    # Belum diminta lokasi sama sekali -> tidak muncul di reminder list.
    assert get_express_orders_awaiting_location_reminder(15) == []

    set_express_location_requested(order_id)
    # Baru diminta barusan -> masih di bawah threshold, belum perlu reminder.
    assert get_express_orders_awaiting_location_reminder(15) == []

    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET location_requested_at = datetime('now', '-20 minutes') WHERE id=?",
            (order_id,),
        )
        conn.commit()
    due = get_express_orders_awaiting_location_reminder(15)
    assert [o["id"] for o in due] == [order_id]

    mark_express_reminder_sent(order_id)
    # Sudah pernah di-reminder -> tidak muncul lagi walau masih lewat threshold.
    assert get_express_orders_awaiting_location_reminder(15) == []


def test_get_express_orders_awaiting_location_reminder_skips_after_location_received(fake_user, seeded_menu):
    result = checkout(
        user=fake_user, items=[{"item_id": 2, "qty": 1}],
        note="test", payment_method="ABA", delivery_type="express",
    )
    order_id = result["order_id"]
    set_express_location_requested(order_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET location_requested_at = datetime('now', '-20 minutes') WHERE id=?",
            (order_id,),
        )
        conn.commit()
    save_express_location(order_id, 1.0, 2.0)
    assert get_express_orders_awaiting_location_reminder(15) == []
    order = get_order(result["order_id"])
    assert order["items"][0]["modifiers_json"] is None
