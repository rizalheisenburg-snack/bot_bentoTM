"""Edit order (partial edit) — tambah/kurangi qty/hapus/replace item pada order
yang masih aktif (Diterima/Diproses). Sengaja MIRROR gaya checkout_flow.py:
baca menu & modifier LIVE dari DB, bukan percaya harga/stok dari client."""
from __future__ import annotations
import json

# Reuse helper privat dari checkout_flow.py — biar resolusi modifier & harga
# selalu konsisten dengan logic checkout (satu sumber kebenaran, gak dobel-tulis).
from checkout_flow import _load_modifier_groups_by_product, _resolve_modifiers
from db import get_conn
from state_machine import EDITABLE_STATUSES, STATUS_LABEL


def edit_order(
    order_id: int,
    actor_id: int,
    actor_role: str,
    items: list[dict],
    note: str | None = None,
) -> dict:
    """
    items: campuran dari 2 bentuk entry, tergantung item-nya:

      1) {"item_id": int, "qty": int, "note": str (optional),
          "modifiers": [{"group_id": int, "option_id": int}, ...] (optional)}
         Item PLAIN (tanpa modifier) atau item BARU yang mau ditambah — harga &
         modifier di-resolve LIVE dari DB, sama seperti checkout_flow.checkout().

      2) {"order_item_id": int, "qty": int}
         "Carry-over" utuh baris order_items yang SUDAH ADA — dipakai KHUSUS
         buat item yang punya modifier (varian). Kenapa beda dari (1): begitu
         checkout selesai, order_items.modifiers_json cuma nyimpen NAMA grup/opsi
         buat ditampilkan (lihat _resolve_modifiers di checkout_flow.py), BUKAN
         group_id/option_id aslinya — jadi gak ada cara valid buat "resolve ulang"
         pilihan modifier lewat _resolve_modifiers() tanpa client kirim ulang
         pilihan itu dari awal. Carry-over ini cukup pertahankan
         item_id/item_name/unit_price/item_note/modifiers_json APA ADANYA dari
         baris lama, cuma qty yang boleh berubah (termasuk qty=0 buat menghapus
         baris ini). Tidak ada validasi availability ulang buat baris jenis ini
         karena ini bukan permintaan baru, cuma penyesuaian qty dari sesuatu yang
         sudah committed (menambah/menyisakan jumlahnya, bukan menambah demand
         baru terhadap stok).

    PENTING: `items` adalah DAFTAR LENGKAP isi order SETELAH diedit (bukan delta
    tambah/kurang) — format sama persis dengan `items` di checkout_flow.checkout(),
    ditambah bentuk (2) di atas. Backend yang men-diff terhadap order_items yang
    ada sekarang:
      - item baru di daftar tapi belum ada di order lama  -> efeknya "tambah item"
      - item lama tidak ada lagi di daftar baru            -> efeknya "hapus item"
      - qty item berubah                                   -> efeknya "kurangi/tambah qty"
      - item lama diganti item_id lain dengan qty sama      -> efeknya "replace item"

    actor_role: 'customer' | 'owner' — dicatat ke order_edits buat audit trail
    (siapa yang mengubah, kapan, apa isi SEBELUM diubah).

    Beda sengaja dari checkout(): kalau ADA SATU item bentuk (1) yang habis/tidak
    ada di menu, SELURUH edit ditolak (atomic) — bukan didiam-diamkan dibuang
    seperti checkout. Alasannya: di checkout user belum commit apa-apa jadi "skip
    item yang habis, lanjutkan sisanya" itu wajar; di edit, user/admin sudah punya
    ekspektasi spesifik ("ganti nasi goreng jadi mie goreng") — kalau item target
    diam-diam gagal, order_items yang tersisa bisa jadi sama sekali gak sesuai
    maksud siapa yang minta edit. Reject-dengan-pesan-jelas lebih aman.

    Return:
      {"ok": True, "order_id": int, "subtotal": int, "total": int}
      {"ok": False, "error": str}
    """
    if not items:
        return {
            "ok": False,
            "error": "Order tidak boleh kosong — gunakan Cancel Order kalau mau membatalkan seluruh order.",
        }

    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, payment_status, subtotal FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Order tidak ditemukan"}

        # ── Final check status di backend — TIDAK percaya state dari client.
        # Ini yang menutup race condition: status order divalidasi ulang di sini,
        # di dalam transaksi yang sama dengan penulisan, bukan hasil asumsi dari
        # payload request atau state yang di-cache di sisi client. ──────────────
        if row["status"] not in EDITABLE_STATUSES:
            return {
                "ok": False,
                "error": (
                    f"Order sudah '{STATUS_LABEL.get(row['status'], row['status'])}', "
                    "tidak bisa diedit lagi."
                ),
            }

        # ── Out of scope (sesuai keputusan): order yang sudah dibayar via ABA
        # tidak diotomasi — arahkan ke penyesuaian manual oleh admin. ──────────
        if row["payment_status"] == "PAID":
            return {
                "ok": False,
                "error": (
                    "Order ini sudah dibayar (LUNAS). Edit otomatis tidak tersedia untuk "
                    "order yang sudah lunas — hubungi admin buat penyesuaian manual."
                ),
            }

        old_subtotal = row["subtotal"]

        # ── Baca menu & modifier LIVE dari DB (harga & stok dari server) ───────
        menu_rows = conn.execute("SELECT * FROM menu_items").fetchall()
        menu_map = {r["id"]: dict(r) for r in menu_rows}
        groups_by_product = _load_modifier_groups_by_product(conn)

        # Baris order_items LAMA — dipakai buat (a) snapshot audit SEBELUM
        # dihapus, dan (b) lookup carry-over bentuk (2) di atas.
        old_rows = conn.execute(
            "SELECT * FROM order_items WHERE order_id=?", (order_id,)
        ).fetchall()
        old_items_by_id = {r["id"]: dict(r) for r in old_rows}
        old_items_snapshot = list(old_items_by_id.values())

        # ── Validasi tiap item — REJECT ATOMIC kalau ada yang invalid ──────────
        # Entry di-akumulasi ke `merged` dulu (bukan langsung append ke new_items)
        # supaya request yang (sengaja/tidak) ngirim item_id yang sama 2x, atau
        # order_item_id carry-over yang sama 2x, gak bikin baris order_items
        # ganda buat "produk" yang identik — qty-nya di-jumlah jadi 1 baris.
        # Entry item_id sama TAPI kombinasi modifier beda tetap dianggap baris
        # terpisah (itu varian yang berbeda, bukan duplikat).
        merged: dict = {}
        merge_order: list = []

        for entry in items:
            if not isinstance(entry, dict):
                return {"ok": False, "error": "Format item tidak valid."}

            # Bentuk (2): carry-over baris lama apa adanya, cuma qty yang berubah.
            if "order_item_id" in entry:
                try:
                    oi_id = int(entry["order_item_id"])
                    qty = int(entry["qty"])
                except (KeyError, TypeError, ValueError):
                    return {"ok": False, "error": "Format item tidak valid."}
                if qty <= 0:
                    continue  # qty 0/negatif = baris ini dianggap dihapus

                old = old_items_by_id.get(oi_id)
                if not old:
                    return {
                        "ok": False,
                        "error": f"Item order #{oi_id} tidak ditemukan di order ini.",
                    }
                key = ("carryover", oi_id)
                if key in merged:
                    merged[key]["qty"] += qty
                else:
                    merged[key] = {
                        "qty": qty,
                        "row": (
                            old["item_id"], old["item_name"], old["unit_price"],
                            old["item_note"], old["modifiers_json"],
                        ),
                    }
                    merge_order.append(key)
                continue

            # Bentuk (1): item plain/baru — resolve LIVE dari menu (pola checkout).
            try:
                item_id = int(entry["item_id"])
                qty = int(entry["qty"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "error": "Format item tidak valid."}
            if qty <= 0:
                continue  # qty 0/negatif = item ini dianggap dihapus dari order

            modifiers_input = entry.get("modifiers")
            if modifiers_input is not None and not isinstance(modifiers_input, list):
                return {"ok": False, "error": "Format modifiers tidak valid."}

            m = menu_map.get(item_id)
            if not m:
                return {"ok": False, "error": f"Item id {item_id} tidak ditemukan di menu."}
            if not m["available"]:
                return {
                    "ok": False,
                    "error": f"'{m['name']}' sudah habis, tidak bisa ditambahkan/dipertahankan di order.",
                }

            try:
                modifier_extra, modifier_snapshot = _resolve_modifiers(
                    m["name"], groups_by_product.get(item_id, []), modifiers_input
                )
            except ValueError as e:
                return {"ok": False, "error": str(e)}

            item_note = str(entry.get("note") or "").strip() or None
            unit_price = m["price"] + modifier_extra
            modifiers_json = (
                json.dumps(modifier_snapshot, ensure_ascii=False) if modifier_snapshot else None
            )

            # Kunci merge: item_id + kombinasi group_id/option_id yang diminta
            # (dinormalisasi & diurutkan) — bukan snapshot nama, biar entry yang
            # milih varian sama persis ke-merge, sementara varian berbeda tetap
            # baris terpisah. Entry yang gak valid di sini cukup diabaikan dari
            # signature (bukan crash) — _resolve_modifiers() di atas udah jadi
            # validator utama; kalau grup wajib jadi "belum lengkap" gara-gara
            # entry sampah, itu sudah ke-reject duluan sebelum baris ini.
            mod_sig_list = []
            for s in (modifiers_input or []):
                if not isinstance(s, dict):
                    continue
                try:
                    mod_sig_list.append((int(s["group_id"]), int(s["option_id"])))
                except (KeyError, TypeError, ValueError):
                    continue
            mod_sig = tuple(sorted(mod_sig_list))
            key = ("plain", item_id, mod_sig)
            if key in merged:
                merged[key]["qty"] += qty
            else:
                merged[key] = {
                    "qty": qty,
                    "row": (item_id, m["name"], unit_price, item_note, modifiers_json),
                }
                merge_order.append(key)

        new_items = []
        subtotal = 0
        for key in merge_order:
            qty = merged[key]["qty"]
            item_id, item_name, unit_price, item_note, modifiers_json = merged[key]["row"]
            subtotal += unit_price * qty
            new_items.append((item_id, item_name, qty, unit_price, item_note, modifiers_json))

        if not new_items:
            return {
                "ok": False,
                "error": "Order tidak boleh kosong — gunakan Cancel Order kalau mau membatalkan seluruh order.",
            }

        # TODO: re-validasi minimum order per address tier setelah edit
        # (geo.get_min_order_by_address) — SENGAJA belum diimplementasi, masih
        # nunggu klarifikasi kebijakan dari owner: apakah edit yang bikin
        # subtotal turun di bawah minimum harus ditolak, atau tetap dibiarkan
        # lolos karena order aslinya sudah lolos syarat minimum saat checkout.

        # ── Tulis ulang order_items (delete + insert, atomic 1 transaksi) ──────
        conn.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        conn.executemany(
            """INSERT INTO order_items
               (order_id, item_id, item_name, qty, unit_price, item_note, modifiers_json)
               VALUES (?,?,?,?,?,?,?)""",
            [(order_id, *item_row) for item_row in new_items],
        )

        set_clauses = ["subtotal=?", "updated_at=datetime('now')"]
        params: list = [subtotal]
        if note is not None:
            set_clauses.append("note=?")
            params.append(note)
        params.append(order_id)
        conn.execute(f"UPDATE orders SET {', '.join(set_clauses)} WHERE id=?", params)

        # ── Audit trail ─────────────────────────────────────────────────────────
        conn.execute(
            """INSERT INTO order_edits
               (order_id, actor_user_id, actor_role, old_subtotal, new_subtotal, items_snapshot_json)
               VALUES (?,?,?,?,?,?)""",
            (
                order_id,
                actor_id,
                actor_role,
                old_subtotal,
                subtotal,
                json.dumps(old_items_snapshot, ensure_ascii=False),
            ),
        )

    return {"ok": True, "order_id": order_id, "subtotal": subtotal, "total": subtotal}