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


if __name__ == "__main__":
    import sqlite3
    # Sesuaikan path db & import config kalau perlu
    conn = sqlite3.connect(config.DB_PATH)
    seed_menu(conn)
    conn.close()