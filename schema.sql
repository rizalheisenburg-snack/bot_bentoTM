-- Semua harga dalam RIEL (integer, ga ada desimal)

CREATE TABLE IF NOT EXISTS menu_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    price       INTEGER NOT NULL,          -- riel
    category    TEXT    NOT NULL,
    emoji       TEXT    DEFAULT '☕',
    image_url   TEXT,
    available   INTEGER DEFAULT 1          -- 1=ada, 0=habis
);

CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    username       TEXT,
    full_name      TEXT,

    -- State dapur
    status         TEXT    NOT NULL DEFAULT 'Diterima',
    -- Diterima | Diproses | Siap | Selesai | Dibatalkan

    -- Payment (terpisah dari state dapur)
    payment_status TEXT    NOT NULL DEFAULT 'UNPAID',  -- UNPAID | PAID
    paid_currency  TEXT,                               -- 'RIEL' | 'USD' (apa yang masuk laci)
    paid_at        TEXT,                               -- UTC datetime, wajib UTC
    payment_method TEXT,                               -- 'CASH' | 'ABA' 

    -- -- Voucher
    -- voucher_used   INTEGER DEFAULT 0,      -- 1 = voucher dipakai
    -- voucher_value  INTEGER DEFAULT 0,      -- riel yang dipotong voucher (maks 10000)

    -- Harga (GENERATED supaya ga bisa drift manual)
    subtotal       INTEGER NOT NULL,       -- sum(line_total) sebelum voucher
    -- discount       INTEGER GENERATED ALWAYS AS (voucher_value) STORED,
    total          INTEGER GENERATED ALWAYS AS (subtotal) STORED,

    address        TEXT,                               -- alamat tujuan dari address picker di cart, field sendiri (bukan dicampur ke note)
    note           TEXT,
    cancel_reason  TEXT,                               -- alasan force-cancel admin (Stok habis/Request customer/Kesalahan input/Lainnya)
    admin_msg_id   INTEGER,                            -- message_id kartu order di chat admin
    created_at     TEXT DEFAULT (datetime('now')),     -- UTC
    updated_at     TEXT DEFAULT (datetime('now')),     -- UTC
    status_changed_at TEXT DEFAULT (datetime('now'))   -- UTC, cuma berubah saat kolom `status` berubah (buat timer kanban)
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    item_id    INTEGER NOT NULL,
    item_name  TEXT    NOT NULL,
    qty        INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,           -- riel, snapshot saat checkout
    line_total INTEGER GENERATED ALWAYS AS (qty * unit_price) STORED,
    item_note  TEXT,                       -- catatan custom per item, verbatim, tidak diparsing
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    min_order   INTEGER NOT NULL,        -- ambang minimal order (riel) dari tier jarak terakhir
    distance_km REAL,                    -- jarak snapshot saat share lokasi, buat referensi
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payment_proofs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL,
    file_id      TEXT    NOT NULL,                     -- Telegram file_id, ga download fisik
    submitted_at TEXT DEFAULT (datetime('now')),       -- UTC
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS print_jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    payload    TEXT    NOT NULL,                       -- JSON snapshot struk (item, qty, harga, total, dll)
    status     TEXT    NOT NULL DEFAULT 'pending',      -- pending | sent | printed | failed
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    created_at TEXT DEFAULT (datetime('now')),          -- UTC
    updated_at TEXT DEFAULT (datetime('now')),          -- UTC
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
