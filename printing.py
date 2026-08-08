"""Antrean print job struk — dikirim ke print-agent lokal lewat WebSocket."""
from __future__ import annotations
import json

from db import get_conn
from state_machine import get_order


def _build_receipt(order: dict) -> dict:
    return {
        "order_id": order["id"],
        "created_at": order["created_at"],
        "customer": order.get("full_name") or order.get("username") or str(order["user_id"]),
        "payment_method": order.get("payment_method") or "CASH",
        "address": order.get("address") or "",
        "note": order.get("note") or "",
        "items": [
            {
                "name": i["item_name"],
                "qty": i["qty"],
                "unit_price": i["unit_price"],
                "line_total": i["line_total"],
                "note": i.get("item_note") or "",
            }
            for i in order.get("items", [])
        ],
        "subtotal": order["subtotal"],
        "total": order["total"],
    }


def create_print_job(order_id: int) -> dict | None:
    """Bikin print job baru buat 1 order, status 'pending'. None kalau order gak ketemu."""
    order = get_order(order_id)
    if not order:
        return None
    receipt = _build_receipt(order)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO print_jobs (order_id, payload, status) VALUES (?, ?, 'pending')",
            (order_id, json.dumps(receipt, ensure_ascii=False)),
        )
        conn.commit()
        job_id = cur.lastrowid
    return {"id": job_id, "order_id": order_id, "status": "pending", "payload": receipt}


def get_resendable_print_jobs() -> list[dict]:
    """Job yang belum pernah kekirim ('pending') atau udah dikonfirmasi gagal cetak
    ('failed') — dikirim ulang begitu agent connect. Job berstatus 'sent' sengaja
    TIDAK di-resend di sini: agent udah nerima job itu dan ambigu apa udah sempat
    kecetak sebelum putus, jadi resend otomatis berisiko cetak dobel struk yang sama."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM print_jobs WHERE status IN ('pending','failed') ORDER BY created_at ASC"
        ).fetchall()
    jobs = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        jobs.append(d)
    return jobs


def mark_job_sent(job_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE print_jobs SET status='sent', attempts=attempts+1, updated_at=datetime('now') WHERE id=?",
            (job_id,),
        )
        conn.commit()


def mark_job_printed(job_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE print_jobs SET status='printed', updated_at=datetime('now') WHERE id=?",
            (job_id,),
        )
        conn.commit()


def mark_job_failed(job_id: int, error: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE print_jobs SET status='failed', error=?, updated_at=datetime('now') WHERE id=?",
            (error, job_id),
        )
        conn.commit()
