"""State machine dapur + payment logic."""
from __future__ import annotations
from db import get_conn

# ── State dapur ───────────────────────────────────────────────────────────────
# Diterima   : order masuk, nunggu owner — window cancel customer masih BUKA
# Diproses   : owner terima & mulai masak — window cancel customer TUTUP
# Siap       : selesai [terminal]
# Dibatalkan : ditolak/dibatalkan (owner atau customer) [terminal]

TRANSITIONS: dict[str, list[str]] = {
    "Diterima":   ["Diproses", "Dibatalkan"],
    "Diproses":   ["Siap", "Dibatalkan"],
    "Siap":       [],
    "Dibatalkan": [],
}

TERMINAL = {"Siap", "Dibatalkan"}

STATUS_LABEL: dict[str, str] = {
    "Diterima":   "⏳ Diterima",
    "Diproses":   "👨‍🍳 Diproses",
    "Siap":       "🎉 Siap",
    "Dibatalkan": "🚫 Dibatalkan",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def can_customer_cancel(status: str) -> bool:
    """Customer hanya boleh cancel selagi Diterima."""
    return status == "Diterima"


def can_owner_cancel(status: str) -> bool:
    return status not in TERMINAL


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
        conn.commit()


def add_payment_proof(order_id: int, file_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO payment_proofs (order_id, file_id) VALUES (?, ?)",
            (order_id, file_id),
        )
        conn.commit()


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
            if not can_customer_cancel(current):
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
            "UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?",
            (new_status, order_id),
        )
        conn.commit()

    return {"ok": True, "status": new_status, "label": STATUS_LABEL[new_status]}


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
        conn.commit()

    return {"ok": True, "total": row["total"]}


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
            conn.commit()
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
