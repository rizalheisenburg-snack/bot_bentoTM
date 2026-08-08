"""State machine dapur + payment logic."""
from __future__ import annotations
from db import get_conn

# ── State dapur ───────────────────────────────────────────────────────────────
# Diterima   : order masuk, nunggu owner — window cancel customer masih BUKA
# Diproses   : owner terima & mulai masak — window cancel customer TUTUP
# Siap       : makanan udah jadi, nunggu diambil/diantar customer
# Selesai    : udah diambil/diantar customer [terminal]
# Dibatalkan : ditolak/dibatalkan (owner atau customer) [terminal]

TRANSITIONS: dict[str, list[str]] = {
    "Diterima":   ["Diproses", "Dibatalkan"],
    "Diproses":   ["Siap", "Dibatalkan"],
    "Siap":       ["Selesai"],
    "Selesai":    [],
    "Dibatalkan": [],
}

TERMINAL = {"Selesai", "Dibatalkan"}

STATUS_LABEL: dict[str, str] = {
    "Diterima":   "⏳ Diterima",
    "Diproses":   "👨‍🍳 Diproses",
    "Siap":       "🎉 Siap",
    "Selesai":    "✅ Selesai",
    "Dibatalkan": "🚫 Dibatalkan",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

CANCEL_REASONS = ["Stok habis", "Request customer", "Kesalahan input", "Lainnya"]


def customer_can_cancel(status: str, payment_status: str) -> bool:
    """Customer hanya boleh cancel selagi Diterima."""
    return status == "Diterima"


def get_cancel_warning(payment_status: str) -> str | None:
    """Warning informational (bukan blocker) kalau order sudah PAID."""
    if payment_status == "PAID":
        return "⚠️ Order ini sudah dibayar (uang masuk). Kalau tetap dibatalkan, perlu refund manual ke customer."
    return None


def get_order(order_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return None
        items = conn.execute(
            "SELECT * FROM order_items WHERE order_id=?", (order_id,)
        ).fetchall()
    order = dict(row)
    order["items"] = [dict(i) for i in items]
    order["status_label"] = STATUS_LABEL.get(order["status"], order["status"])
    return order


def get_user_orders(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            (user_id,),
        ).fetchall()
    result = []
    for r in rows:
        o = dict(r)
        o["status_label"] = STATUS_LABEL.get(o["status"], o["status"])
        result.append(o)
    return result


def get_pending_orders() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status='Diterima' ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_active_orders() -> list[dict]:
    """
    Order buat kanban /admin: Diterima/Diproses/Siap selalu tampil apapun umurnya
    (masih actionable, nunggu ditandain Selesai), Selesai/Dibatalkan (terminal)
    cuma yang hari ini — supaya kolom terminal tidak numpuk order lama selamanya.
    """
    with get_conn() as conn:
        orders = conn.execute("""
            SELECT * FROM orders
            WHERE status IN ('Diterima', 'Diproses', 'Siap')
               OR (status IN ('Selesai', 'Dibatalkan') AND date(created_at) = date('now'))
            ORDER BY created_at ASC
        """).fetchall()
        if not orders:
            return []
        ids = [o["id"] for o in orders]
        placeholders = ",".join("?" * len(ids))
        items = conn.execute(
            f"SELECT * FROM order_items WHERE order_id IN ({placeholders})", ids
        ).fetchall()

    items_by_order: dict[int, list] = {}
    for i in items:
        items_by_order.setdefault(i["order_id"], []).append(dict(i))

    result = []
    for o in orders:
        d = dict(o)
        d["items"] = items_by_order.get(d["id"], [])
        d["status_label"] = STATUS_LABEL.get(d["status"], d["status"])
        result.append(d)
    return result


def get_latest_unpaid_order(user_id: int) -> dict | None:
    """Order UNPAID terbaru milik user, buat matching bukti transfer."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM orders
               WHERE user_id=? AND payment_status='UNPAID'
                 AND status != 'Dibatalkan'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def set_admin_msg_id(order_id: int, message_id: int) -> None:
    """Simpen message_id kartu order di chat admin, buat reply bukti transfer."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET admin_msg_id=? WHERE id=?", (message_id, order_id)
        )


def add_payment_proof(order_id: int, file_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO payment_proofs (order_id, file_id) VALUES (?, ?)",
            (order_id, file_id),
        )


# ── Transisi ──────────────────────────────────────────────────────────────────

def transition(order_id: int, new_status: str, actor: str = "owner") -> dict:
    """
    actor: 'owner' | 'customer' | 'system'
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, payment_status FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Order tidak ditemukan"}

        current = row["status"]

        # Validasi cancel customer
        if new_status == "Dibatalkan" and actor == "customer":
            if not customer_can_cancel(current, row["payment_status"]):
                return {
                    "ok": False,
                    "error": "Order sudah dikonfirmasi, tidak bisa dibatalkan",
                }

        if new_status not in TRANSITIONS.get(current, []):
            return {
                "ok": False,
                "error": f"Tidak bisa dari '{current}' ke '{new_status}'",
            }

        conn.execute(
            """UPDATE orders SET status=?, updated_at=datetime('now'),
                   status_changed_at=datetime('now') WHERE id=?""",
            (new_status, order_id),
        )

    return {"ok": True, "status": new_status, "label": STATUS_LABEL[new_status]}


def force_cancel_order(order_id: int, reason: str) -> dict:
    """
    Admin force-cancel: bisa dari kolom manapun, tanpa syarat status
    (bypass TRANSITIONS sama sekali). Wajib pilih alasan dari CANCEL_REASONS.
    """
    if reason not in CANCEL_REASONS:
        return {"ok": False, "error": "Alasan tidak valid"}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, payment_status FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Order tidak ditemukan"}

        conn.execute(
            """UPDATE orders SET status='Dibatalkan', cancel_reason=?,
                   updated_at=datetime('now'), status_changed_at=datetime('now')
                   WHERE id=?""",
            (reason, order_id),
        )

    return {
        "ok": True,
        "status": "Dibatalkan",
        "label": STATUS_LABEL["Dibatalkan"],
        "reason": reason,
        "warning": get_cancel_warning(row["payment_status"]),
    }


# ── Payment ───────────────────────────────────────────────────────────────────

def mark_paid(order_id: int, paid_currency: str = "RIEL") -> dict:
    """
    paid_currency: 'RIEL' | 'USD'
    Omzet hanya ngitung order yang PAID.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, payment_status, total FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Order tidak ditemukan"}
        if row["payment_status"] == "PAID":
            return {"ok": False, "error": "Order sudah lunas"}
        if row["status"] == "Dibatalkan":
            return {"ok": False, "error": "Order tidak valid untuk dilunasi"}

        conn.execute(
            """UPDATE orders
               SET payment_status='PAID', paid_currency=?, paid_at=datetime('now'),
                   updated_at=datetime('now')
               WHERE id=?""",
            (paid_currency.upper(), order_id),
        )

    return {"ok": True, "total": row["total"]}


def change_payment_method(order_id: int, new_method: str) -> dict:
    """
    new_method: 'CASH' | 'ABA'.
    Ditolak kalau order sudah PAID (payment_method terkunci begitu lunas).
    """
    if new_method not in ("CASH", "ABA"):
        return {"ok": False, "error": "Metode tidak valid"}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT payment_method, payment_status FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Order tidak ditemukan"}
        if row["payment_status"] == "PAID":
            return {"ok": False, "error": "Order sudah lunas, metode bayar terkunci"}

        old_method = row["payment_method"] or "CASH"
        if old_method == new_method:
            return {"ok": False, "error": "Metode bayar sudah sama"}

        conn.execute(
            "UPDATE orders SET payment_method=?, updated_at=datetime('now') WHERE id=?",
            (new_method, order_id),
        )

    return {"ok": True, "old_method": old_method, "new_method": new_method}


def auto_pay_if_free(order_id: int) -> bool:
    """Kalau total=0, langsung PAID otomatis. Return True kalau di-auto."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT total, payment_status FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row or row["payment_status"] == "PAID":
            return False
        if row["total"] == 0:
            conn.execute(
                """UPDATE orders
                   SET payment_status='PAID', paid_currency='RIEL',
                       paid_at=datetime('now'), updated_at=datetime('now')
                   WHERE id=?""",
                (order_id,),
            )
            return True
    return False


# ── Omzet ─────────────────────────────────────────────────────────────────────

def get_omzet(bulan: int, tahun: int) -> dict:
    """
    Omzet = SUM(total) WHERE payment_status='PAID'.
    paid_at disimpan UTC → date(paid_at) = hari kerja yang bener.
    Shift: UTC hour < 12 = siang, >= 12 = malam.
    """
    periode = f"{tahun}-{bulan:02d}"
    with get_conn() as conn:
        summary = conn.execute("""
            SELECT
                COUNT(*)                                          AS total_order,
                COALESCE(SUM(total), 0)                          AS omzet_riel,
                SUM(CASE WHEN payment_status='PAID' THEN 1 ELSE 0 END) AS lunas,
                SUM(CASE WHEN status='Dibatalkan'   THEN 1 ELSE 0 END) AS batal,
                SUM(CASE WHEN paid_currency='USD'   THEN 1 ELSE 0 END) AS bayar_usd
            FROM orders
            WHERE strftime('%Y-%m', paid_at) = ?
              AND payment_status = 'PAID'
        """, (periode,)).fetchone()

        top_items = conn.execute("""
            SELECT oi.item_name, SUM(oi.qty) AS total_qty
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE strftime('%Y-%m', o.paid_at) = ?
              AND o.payment_status = 'PAID'
            GROUP BY oi.item_name
            ORDER BY total_qty DESC
            LIMIT 5
        """, (periode,)).fetchall()

    return {
        "periode": periode,
        "total_order": summary["total_order"],
        "omzet_riel": summary["omzet_riel"],
        "lunas": summary["lunas"],
        "batal": summary["batal"],
        "bayar_usd": summary["bayar_usd"],
        "top_items": [dict(r) for r in top_items],
    }
