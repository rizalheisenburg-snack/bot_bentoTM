"""initData verification + checkout logic."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
import urllib.parse

from config import BOT_TOKEN
from db import get_conn
from geo import get_min_order_by_address
from state_machine import auto_pay_if_free

MAX_AGE = 86_400  # 24 jam anti-replay
DUPLICATE_WINDOW = 15  # detik — order identik dari user yang sama dalam window ini dianggap double-tap/retry, bukan order baru


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


def _find_recent_duplicate(conn, user_id, valid_items, note, payment_method, address, delivery_type):
    """Cari order dari user yang sama, isinya identik, dalam DUPLICATE_WINDOW detik terakhir.
    Nangkep double-tap tombol order / retry otomatis karena koneksi putus-nyambung."""
    row = conn.execute(
        """SELECT * FROM orders
           WHERE user_id = ? AND datetime(created_at) >= datetime('now', ?)
           ORDER BY id DESC LIMIT 1""",
        (user_id, f"-{DUPLICATE_WINDOW} seconds"),
    ).fetchone()
    if not row:
        return None
    if (
        (row["note"] or "") != note
        or (row["payment_method"] or "") != payment_method
        or (row["address"] or None) != (address or None)
        or (row["delivery_type"] or "internal") != delivery_type
    ):
        return None
    existing_items = conn.execute(
        "SELECT item_id, qty, item_note, modifiers_json FROM order_items WHERE order_id = ?", (row["id"],)
    ).fetchall()
    existing_sig = sorted((r["item_id"], r["qty"], r["item_note"], r["modifiers_json"]) for r in existing_items)
    new_sig = sorted(
        (item_id, qty, item_note, modifiers_json)
        for item_id, _, qty, _, item_note, modifiers_json in valid_items
    )
    if existing_sig != new_sig:
        return None
    return dict(row)


def _load_modifier_groups_by_product(conn) -> dict[int, list[dict]]:
    """Return {product_id: [group_dict, ...]}, tiap group_dict punya key "options" (list opsi milik grup itu)."""
    options_by_group: dict[int, list[dict]] = {}
    for o in conn.execute("SELECT * FROM modifier_options").fetchall():
        options_by_group.setdefault(o["group_id"], []).append(dict(o))

    groups_by_product: dict[int, list[dict]] = {}
    for g in conn.execute("SELECT * FROM modifier_groups").fetchall():
        gd = dict(g)
        gd["options"] = options_by_group.get(gd["id"], [])
        groups_by_product.setdefault(gd["product_id"], []).append(gd)
    return groups_by_product


def _resolve_modifiers(product_name: str, groups: list[dict], selected: list[dict] | None):
    """
    groups: modifier_groups (+ "options") milik 1 produk. selected: pilihan dari client,
    [{"group_id": int, "option_id": int}, ...].
    Return (extra_price_delta, snapshot_list) kalau valid. Raise ValueError(pesan jelas)
    kalau ada grup wajib yang belum terisi lengkap atau opsi yang dikirim tidak valid.
    Produk tanpa modifier_groups (mayoritas menu) langsung return (0, []) tanpa validasi apa pun.
    """
    if not groups:
        return 0, []

    selections_by_group: dict[int, list[int]] = {}
    for sel in selected or []:
        try:
            gid = int(sel["group_id"])
            oid = int(sel["option_id"])
        except (KeyError, TypeError, ValueError):
            continue
        selections_by_group.setdefault(gid, []).append(oid)

    extra = 0
    snapshot = []
    problems = []
    for group in groups:
        option_ids = selections_by_group.get(group["id"], [])
        if len(option_ids) < group["min_select"]:
            if group["is_required"] or option_ids:
                problems.append(f"{group['name']} belum dipilih")
            continue
        if len(option_ids) > group["max_select"]:
            problems.append(f"{group['name']} cuma boleh pilih maksimal {group['max_select']}")
            continue
        for option_id in option_ids:
            option = next((o for o in group["options"] if o["id"] == option_id), None)
            if not option or not option["is_available"]:
                problems.append(f"pilihan di grup {group['name']} tidak valid")
                continue
            extra += option["price_delta"]
            snapshot.append({
                "group_name": group["name"],
                "option_name": option["name"],
                "price_delta": option["price_delta"],
            })

    if problems:
        raise ValueError(f"Pilihan untuk '{product_name}' belum lengkap: {'; '.join(problems)}.")

    return extra, snapshot


def checkout(
    user: dict,
    items: list[dict],
    note: str,
    payment_method: str = "CASH",
    address: str = "",
    delivery_type: str = "internal",
) -> dict:
    """
    items: [{"item_id": int, "qty": int, "note": str (optional, verbatim, tidak diparsing),
             "modifiers": [{"group_id": int, "option_id": int}, ...] (optional)}, ...]
    Item yang habis/tidak ada otomatis dibuang dari order, sisanya tetap lanjut.
    Produk dengan modifier group wajib yang belum lengkap/tidak valid akan menolak
    SELURUH checkout (bukan cuma dibuang) karena itu state client yang tidak lengkap,
    bukan stok habis yang legitimate.
    address: alamat tujuan yang dipilih customer di cart, nentuin tier minimal order.
    delivery_type: 'internal' (default, gratis) | 'express' (butuh ABA/Transfer, bukan Cash).

    Return:
      {"ok": True, "order_id": int, "total": int, "unavailable_items": list}
      {"ok": False, "error": str}
    """
    if delivery_type not in ("internal", "express"):
        delivery_type = "internal"

    if not items:
        return {"ok": False, "error": "Keranjang kosong"}

    # ── Baca menu LIVE dari DB (harga & stok dari server, bukan client) ────────
    with get_conn() as conn:
        menu_rows = conn.execute("SELECT * FROM menu_items").fetchall()
        groups_by_product = _load_modifier_groups_by_product(conn)
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

        try:
            modifier_extra, modifier_snapshot = _resolve_modifiers(
                m["name"], groups_by_product.get(item_id, []), entry.get("modifiers")
            )
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        item_note = (entry.get("note") or "").strip() or None
        unit_price = m["price"] + modifier_extra
        modifiers_json = json.dumps(modifier_snapshot, ensure_ascii=False) if modifier_snapshot else None
        subtotal += unit_price * qty
        valid_items.append((item_id, m["name"], qty, unit_price, item_note, modifiers_json))

    if not valid_items:
        return {"ok": False, "error": "Semua item tidak tersedia"}

    min_order = get_min_order_by_address(address) if address else 0
    if subtotal > 0 and subtotal < min_order:
        return {
            "ok": False,
            "error": f"Order minimal {min_order:,}៛ untuk tujuan '{address}' — kurang {min_order - subtotal:,}៛ lagi.",
        }

    # Voucher support is disabled; only Cash and ABA are accepted.
    if payment_method == "VOUCHER":
        return {
            "ok": False,
            "error": "Metode VOUCHER tidak tersedia. Pilih Cash atau ABA.",
        }

    if delivery_type == "express" and payment_method == "CASH":
        return {
            "ok": False,
            "error": "Kurir Express cuma bisa dipakai dengan pembayaran ABA/Transfer, bukan Cash.",
        }

    user_id = user["id"]
    username = user.get("username", "")
    full_name = (user.get("first_name", "") + " " + user.get("last_name", "")).strip()

    with get_conn() as conn:
        dup = _find_recent_duplicate(conn, user_id, valid_items, note, payment_method, address, delivery_type)
        if dup:
            return {
                "ok": True,
                "order_id": dup["id"],
                "subtotal": dup["subtotal"],
                "total": dup["total"],
                "auto_paid": dup["payment_status"] == "PAID",
                "unavailable_items": unavailable_items,
                "duplicate": True,
                "delivery_type": dup.get("delivery_type") or "internal",
            }
        cur = conn.execute(
            """INSERT INTO orders
               (user_id, username, full_name, status, subtotal, note, payment_method, address, delivery_type)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                username,
                full_name,
                "Diterima",
                subtotal,
                note,
                payment_method,
                address or None,
                delivery_type,
            ),
        )
        order_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO order_items
               (order_id, item_id, item_name, qty, unit_price, item_note, modifiers_json)
               VALUES (?,?,?,?,?,?,?)""",
            [(order_id, *row) for row in valid_items],
        )

    # Auto-pay kalau total = 0
    auto_paid = auto_pay_if_free(order_id)

    return {
        "ok": True,
        "order_id": order_id,
        "subtotal": subtotal,
        "total": subtotal,
        "auto_paid": auto_paid,
        "unavailable_items": unavailable_items,
        "delivery_type": delivery_type,
    }
