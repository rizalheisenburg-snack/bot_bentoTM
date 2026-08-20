import sqlite3
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_settings(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        _ensure_settings(conn)
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        _ensure_settings(conn)
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def set_user_min_order(user_id: int, min_order: int, distance_km: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO users (user_id, min_order, distance_km, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                 min_order=excluded.min_order,
                 distance_km=excluded.distance_km,
                 updated_at=excluded.updated_at""",
            (user_id, min_order, distance_km),
        )


def get_user_min_order(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT min_order, distance_km FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def reset_orders() -> dict:
    """Hapus SEMUA data transaksi (order, item, edit history, print job, bukti
    bayar) — menu_items, modifier_groups/options, users, dan settings TIDAK
    disentuh. Dipakai buat bersihin data test/trial sebelum omzet mulai
    dihitung serius. ID order di-reset balik ke 1 (AUTOINCREMENT counter).
    """
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
        conn.execute("DELETE FROM order_edits")
        conn.execute("DELETE FROM print_jobs")
        conn.execute("DELETE FROM payment_proofs")
        conn.execute("DELETE FROM order_items")
        conn.execute("DELETE FROM orders")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('orders','order_items','order_edits','print_jobs','payment_proofs')"
        )
    return {"orders_deleted": count}


def init_db() -> None:
    with open("schema.sql") as f:
        sql = f.read()
    with get_conn() as conn:
        conn.executescript(sql)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(orders)").fetchall()]
        if "admin_msg_id" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN admin_msg_id INTEGER")
        if "payment_method" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT")
        if "cancel_reason" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN cancel_reason TEXT")
        if "status_changed_at" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN status_changed_at TEXT")
            conn.execute(
                "UPDATE orders SET status_changed_at = created_at WHERE status_changed_at IS NULL"
            )
        if "address" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN address TEXT")
        if "delivery_type" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN delivery_type TEXT NOT NULL DEFAULT 'internal'")
        if "customer_lat" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN customer_lat REAL")
        if "customer_lng" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN customer_lng REAL")
        if "location_requested_at" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN location_requested_at TEXT")
        if "location_received_at" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN location_received_at TEXT")
        if "express_reminder_sent_at" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN express_reminder_sent_at TEXT")
        conn.execute(
            "UPDATE orders SET payment_method='ABA' WHERE note LIKE '[Transfer ABA]%'"
        )
        conn.execute(
            "UPDATE orders SET payment_method='CASH' WHERE payment_method IS NULL OR payment_method = ''"
        )
        cols_oi = [r[1] for r in conn.execute("PRAGMA table_info(order_items)").fetchall()]
        if "item_note" not in cols_oi:
            conn.execute("ALTER TABLE order_items ADD COLUMN item_note TEXT")
        if "modifiers_json" not in cols_oi:
            conn.execute("ALTER TABLE order_items ADD COLUMN modifiers_json TEXT")
