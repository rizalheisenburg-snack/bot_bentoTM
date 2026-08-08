"""
Seed menu — JAGOMASAKKPS (Bento x Jago Masak)
Ditranscribe dari daftar menu final (~80 item, 8 kategori).
Harga dalam Riel Kamboja (KHR), integer, tanpa desimal.

CATATAN: struktur dict di bawah ini generik (category/name/price).
Sesuaikan key-nya (misal "name" -> "nama") dan cara insert-nya
(loop + INSERT INTO items ...) supaya match sama schema.sql /
fungsi seed yang sudah ada di project bento .
"""
import config
MENU: list[dict] = [
    # ── Paket Spesial ─────────────────────────────────────────────
    {"category": "Paket Spesial", "name": "Paket Ayam Crispy Booster (Ayam+Telur) + Sambal Bawang", "price": 10_000},
    {"category": "Paket Spesial", "name": "Ayam Crispy + Sambal Bawang (Tanpa Nasi)", "price": 8_000},
    {"category": "Paket Spesial", "name": "Nasi Ayam Keprabon + Mozzarella", "price": 12_000},
    {"category": "Paket Spesial", "name": "Nasi Ayam Keprabon", "price": 10_000},

    # ── Menu Nasi ─────────────────────────────────────────────────
    {"category": "Menu Nasi", "name": "Nasi + Chicken Katsu", "price": 10_000},
    {"category": "Menu Nasi", "name": "Nasi + Egg Chicken Roll 5pcs", "price": 10_000},
    {"category": "Menu Nasi", "name": "Nasi + Chicken Teriyaki", "price": 10_000},
    {"category": "Menu Nasi", "name": "Nasi + Chicken Blackpepper", "price": 10_000},
    {"category": "Menu Nasi", "name": "Nasi + Beef Teriyaki", "price": 16_000},
    {"category": "Menu Nasi", "name": "Nasi + Ebi Furai", "price": 13_000},
    {"category": "Menu Nasi", "name": "Nasi + Shrimp Roll", "price": 15_000},
    {"category": "Menu Nasi", "name": "Katsu Curry Rice", "price": 12_000},
    {"category": "Menu Nasi", "name": "Nasi Mentai", "price": 10_000},

    # ── Paket Hoki ────────────────────────────────────────────────
    # Catatan: nomor loncat di sumber asli (1,2,3,5,6,7,8,9,10 — "Hoki 4" tidak ada).
    # Perlu dikonfirmasi ke Koh James: sengaja skip atau ada yang kelewat kecatet.
    {"category": "Paket Hoki", "name": "Hoki 1 (Egg Roll 3pcs + Chicken Teriyaki)", "price": 15_000},
    {"category": "Paket Hoki", "name": "Hoki 2 (Katsu + Chicken Teriyaki)", "price": 18_000},
    {"category": "Paket Hoki", "name": "Hoki 3 (Egg Roll 3pcs + Beef Teriyaki)", "price": 20_000},
    {"category": "Paket Hoki", "name": "Hoki 5 (Katsu + Beef Teriyaki)", "price": 23_000},
    {"category": "Paket Hoki", "name": "Hoki 6 (Katsu + Egg Roll 5pcs)", "price": 18_000},
    {"category": "Paket Hoki", "name": "Hoki 7 (Katsu + Shrimp Roll 3pc)", "price": 20_000},
    {"category": "Paket Hoki", "name": "Hoki 8 (Shrimp Roll 3pc + Chicken Teriyaki)", "price": 18_000},
    {"category": "Paket Hoki", "name": "Hoki 9 (Shrimp Roll 3pc + Beef Teriyaki)", "price": 23_000},
    {"category": "Paket Hoki", "name": "Hoki 10 (Ebi Furai 2pc + Chicken Teriyaki)", "price": 20_000},

    # ── Ala Carte (Tanpa Nasi) ───────────────────────────────────
    {"category": "Ala Carte", "name": "Chicken Katsu", "price": 8_000},
    {"category": "Ala Carte", "name": "Egg Chicken Roll (5pcs)", "price": 8_000},
    {"category": "Ala Carte", "name": "Chicken Teriyaki", "price": 8_000},
    {"category": "Ala Carte", "name": "Chicken Blackpepper", "price": 8_000},
    {"category": "Ala Carte", "name": "Beef Teriyaki", "price": 14_000},
    {"category": "Ala Carte", "name": "Shrimp Roll (5pc)", "price": 13_000},
    {"category": "Ala Carte", "name": "Saos Curry", "price": 2_000},

    # ── Rice Bowl ─────────────────────────────────────────────────
    {"category": "Rice Bowl", "name": "Katsu Blackpepper", "price": 10_000},
    {"category": "Rice Bowl", "name": "Katsu Salted Egg", "price": 10_000},
    {"category": "Rice Bowl", "name": "Katsu Sambel Geprek", "price": 10_000},
    {"category": "Rice Bowl", "name": "Chicken Karage Blackpepper", "price": 10_000},
    {"category": "Rice Bowl", "name": "Chicken Karage Sambel Bawang", "price": 10_000},

    # ── Roti / Cemilan ───────────────────────────────────────────
    {"category": "Roti/Cemilan", "name": "Roti Pisang Keju", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Pisang Coklat", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Coffeebun", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Cheesebun", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Chocoraisin", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Cokelat", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Pizza", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Kelapa", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Srikaya", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Abon", "price": 6_000},
    {"category": "Roti/Cemilan", "name": "Roti Belah Keju", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Belah Mix", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Roti Belah Mesis", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Bolu Kukus", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Bolu Marmer", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Sarang Semut", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Brownies", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Brownies Mini", "price": 8_000},
    {"category": "Roti/Cemilan", "name": "Brownies Box", "price": 15_000},
    {"category": "Roti/Cemilan", "name": "Dorayaki", "price": 6_000},
    {"category": "Roti/Cemilan", "name": "Long Cheese", "price": 6_000},
    {"category": "Roti/Cemilan", "name": "Longjohn Misis", "price": 6_000},
    {"category": "Roti/Cemilan", "name": "Donat Gula", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Donat Keju", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Donat Oreo", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Donat Mocca Misis", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Donat Misis Keju", "price": 5_000},
    {"category": "Roti/Cemilan", "name": "Lidah Kucing", "price": 10_000},
    {"category": "Roti/Cemilan", "name": "Lumpia Pedas", "price": 8_000},
    {"category": "Roti/Cemilan", "name": "Tahu Walik", "price": 6_000},

    # ── Kerupuk / Keripik ────────────────────────────────────────
    {"category": "Kerupuk/Keripik", "name": "Krupuk Udang", "price": 6_000},
    {"category": "Kerupuk/Keripik", "name": "Kerupuk Rafael", "price": 5_000},
    {"category": "Kerupuk/Keripik", "name": "Kerupuk Pelangi", "price": 5_000},
    {"category": "Kerupuk/Keripik", "name": "Kripik Tempe Pedas", "price": 10_000},
    {"category": "Kerupuk/Keripik", "name": "Kripik Pisang", "price": 8_000},
    {"category": "Kerupuk/Keripik", "name": "Kripik Tempe", "price": 6_000},
    {"category": "Kerupuk/Keripik", "name": "Emping", "price": 6_000},
    {"category": "Kerupuk/Keripik", "name": "Peyek", "price": 6_000},
    {"category": "Kerupuk/Keripik", "name": "Usus Crispy", "price": 8_000},

    # ── Minuman ───────────────────────────────────────────────────
    {"category": "Minuman", "name": "Mineral Besar", "price": 4_000},
    {"category": "Minuman", "name": "Mineral Kecil", "price": 2_000},
]


def seed_menu(conn):
    """
    Insert semua item MENU ke database (tabel menu_items).
    """
    cur = conn.cursor()
    for item in MENU:
        cur.execute(
            """
            INSERT INTO menu_items (name, description, price, category, emoji, image_url, available)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["name"],
                None,       # description — belum ada di data MENU
                item["price"],
                item["category"],
                "☕",        # emoji default (sesuai default schema)
                None,       # image_url — belum ada
                1,          # available = 1 (ada stok)
            ),
        )
    conn.commit()
    print(f"Seeded {len(MENU)} menu items.")


# ── Produk komposit: "Nasi Campur Pilih Sendiri" ────────────────────────────
# 4 modifier group, masing-masing wajib pilih tepat 1 opsi.

NASI_CAMPUR_PRODUCT = {
    "name": "Nasi Campur Pilih Sendiri",
    "description": None,
    "price": 10_000,
    "category": "Menu Nasi",
    "emoji": "🍱",
    "image_url": None,
}

NASI_CAMPUR_GROUPS = [
    {
        "name": "Nasi",
        "min_select": 1, "max_select": 1, "is_required": 1,
        "options": [
            {"name": "Nasi Putih", "price_delta": 0},
            {"name": "Nasi Merah", "price_delta": 4_000},
            {"name": "Nasi Uduk", "price_delta": 4_000},
        ],
    },
    {
        "name": "Telur",
        "min_select": 1, "max_select": 1, "is_required": 1,
        "options": [
            {"name": "Telor Bulat Balado", "price_delta": 0},
            {"name": "Telor Dadar", "price_delta": 1_000},
            {"name": "Telor Krispy", "price_delta": 4_000},
        ],
    },
    {
        "name": "Sayur",
        "min_select": 1, "max_select": 1, "is_required": 1,
        "options": [
            {"name": "Capcay", "price_delta": 0},
            {"name": "Brokoli Tahu", "price_delta": 0},
            {"name": "Sawi Putih", "price_delta": 0},
            {"name": "Kangkung", "price_delta": 0},
            {"name": "Jengkol", "price_delta": 5_000},
        ],
    },
    {
        "name": "Lauk/Daging",
        "min_select": 1, "max_select": 1, "is_required": 1,
        "options": [
            {"name": "Ayam Goreng Bawang Putih", "price_delta": 0},
            {"name": "Ayam Wijen", "price_delta": 0},
            {"name": "Ayam Asam Manis", "price_delta": 0},
            {"name": "Ayam Goreng Mentega", "price_delta": 0},
            {"name": "Rendang", "price_delta": 1_000},
        ],
    },
]


def seed_nasi_campur_modifiers(conn):
    """
    Insert produk "Nasi Campur Pilih Sendiri" + 4 modifier group + semua opsinya.
    Idempotent (cek by name sebelum insert) -- aman dipanggil tanpa syarat tiap
    restart, termasuk di production di mana menu_items sudah tidak pernah kosong
    lagi (jadi seed_menu() di atas tidak akan jalan ulang untuk nge-seed ini).
    """
    cur = conn.cursor()

    row = cur.execute(
        "SELECT id FROM menu_items WHERE name = ?", (NASI_CAMPUR_PRODUCT["name"],)
    ).fetchone()
    if row:
        product_id = row[0]
    else:
        cur.execute(
            """
            INSERT INTO menu_items (name, description, price, category, emoji, image_url, available)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                NASI_CAMPUR_PRODUCT["name"],
                NASI_CAMPUR_PRODUCT["description"],
                NASI_CAMPUR_PRODUCT["price"],
                NASI_CAMPUR_PRODUCT["category"],
                NASI_CAMPUR_PRODUCT["emoji"],
                NASI_CAMPUR_PRODUCT["image_url"],
                1,
            ),
        )
        product_id = cur.lastrowid

    for group in NASI_CAMPUR_GROUPS:
        grow = cur.execute(
            "SELECT id FROM modifier_groups WHERE product_id = ? AND name = ?",
            (product_id, group["name"]),
        ).fetchone()
        if grow:
            continue
        cur.execute(
            """
            INSERT INTO modifier_groups (product_id, name, min_select, max_select, is_required)
            VALUES (?, ?, ?, ?, ?)
            """,
            (product_id, group["name"], group["min_select"], group["max_select"], group["is_required"]),
        )
        group_id = cur.lastrowid
        for opt in group["options"]:
            cur.execute(
                """
                INSERT INTO modifier_options (group_id, name, price_delta, image_url, is_available)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_id, opt["name"], opt["price_delta"], opt.get("image_url"), 1),
            )

    conn.commit()
    print("Seeded 'Nasi Campur Pilih Sendiri' modifier groups.")


if __name__ == "__main__":
    import sqlite3
    # Sesuaikan path db & import config kalau perlu
    conn = sqlite3.connect(config.DB_PATH)
    seed_menu(conn)
    seed_nasi_campur_modifiers(conn)
    conn.close()