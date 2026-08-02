"""initData verification + checkout logic."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
import urllib.parse

from config import BOT_TOKEN
from db import get_conn
from state_machine import auto_pay_if_free

MAX_AGE = 86_400  # 24 jam anti-replay


def verify_init_data(init_data: str) -> dict | None:
    """Return parsed user dict kalau initData valid, else None."""
    params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    # Anti-replay: tolak kalau lebih tua dari 24 jam
    auth_date = int(params.get("auth_date", 0))
    if time.time() - auth_date > MAX_AGE:
        return None

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        return None

    return json.loads(params.get("user", "{}"))


def checkout(
    user: dict,
    items: list[dict],
    note: str,
    payment_method: str = "CASH",
) -> dict:
    """
    items: [{"item_id": int, "qty": int}, ...]
    Item yang habis/tidak ada otomatis dibuang dari order, sisanya tetap lanjut.

    Return:
      {"ok": True, "order_id": int, "total": int, "unavailable_items": list}
      {"ok": False, "error": str}
    """
    if not items:
        return {"ok": False, "error": "Keranjang kosong"}

    # ── Baca menu LIVE dari DB (harga & stok dari server, bukan client) ────────
    with get_conn() as conn:
        menu_rows = conn.execute("SELECT * FROM menu_items").fetchall()
    menu_map = {r["id"]: dict(r) for r in menu_rows}

    valid_items = []
    unavailable_items = []
    subtotal = 0

    for entry in items:
        item_id = int(entry["item_id"])
        qty = int(entry["qty"])
        if qty <= 0:
            continue
        m = menu_map.get(item_id)
        if not m:
            unavailable_items.append({"item_id": item_id, "reason": "tidak ada"})
            continue
        if not m["available"]:
            unavailable_items.append({"item_id": item_id, "item_name": m["name"], "reason": "habis"})
            continue
        subtotal += m["price"] * qty
        valid_items.append((item_id, m["name"], qty, m["price"]))

    if not valid_items:
        return {"ok": False, "error": "Semua item tidak tersedia"}

    # Voucher support is disabled; only Cash and ABA are accepted.
    if payment_method == "VOUCHER":
        return {
            "ok": False,
            "error": "Metode VOUCHER tidak tersedia. Pilih Cash atau ABA.",
        }

    user_id = user["id"]
    username = user.get("username", "")
    full_name = (user.get("first_name", "") + " " + user.get("last_name", "")).strip()

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO orders
               (user_id, username, full_name, status, subtotal, note, payment_method)
               VALUES (?,?,?,?,?,?,?)""",
            (
                user_id,
                username,
                full_name,
                "Diterima",
                subtotal,
                note,
                payment_method,
            ),
        )
        order_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_items (order_id, item_id, item_name, qty, unit_price) VALUES (?,?,?,?,?)",
            [(order_id, *row) for row in valid_items],
        )
        conn.commit()

    # Auto-pay kalau total = 0
    auto_paid = auto_pay_if_free(order_id)

    return {
        "ok": True,
        "order_id": order_id,
        "subtotal": subtotal,
        "total": subtotal,
        "auto_paid": auto_paid,
        "unavailable_items": unavailable_items,
    }
