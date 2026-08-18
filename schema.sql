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

    -- Harga (GENERATED supaya ga bisa drift manual)
    subtotal       INTEGER NOT NULL,       -- sum(line_total) sebelum voucher
    total          INTEGER GENERATED ALWAYS AS (subtotal) STORED,

    address        TEXT,                               -- alamat tujuan dari address picker di cart, field sendiri (bukan dicampur ke note)

    -- Kurir Express (opt-in per order). Status "menunggu lokasi" / "menunggu booking kurir"
    -- DIDERIVE dari delivery_type + timestamp di bawah, BUKAN kolom status baru — kolom
    -- `status` tetap murni kitchen state machine (state_machine.py tidak disentuh).
    delivery_type            TEXT NOT NULL DEFAULT 'internal',  -- 'internal' | 'express'
    customer_lat             REAL,
    customer_lng             REAL,
    location_requested_at    TEXT,    -- UTC, diisi pas bot minta share location
    location_received_at     TEXT,    -- UTC, diisi pas customer share location
    express_reminder_sent_at TEXT,    -- UTC, flag reminder sekali-kirim, survive restart bot

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
    modifiers_json TEXT,                   -- snapshot pilihan modifier (JSON), NULL kalau produk gak punya modifier group
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

-- Modifier group untuk produk komposit (mis. "Nasi Campur Pilih Sendiri").
-- Produk tanpa baris di modifier_groups berperilaku persis seperti sebelumnya (no-op).
CREATE TABLE IF NOT EXISTS modifier_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    min_select  INTEGER NOT NULL DEFAULT 1,
    max_select  INTEGER NOT NULL DEFAULT 1,
    is_required INTEGER NOT NULL DEFAULT 1,   -- 1=wajib, 0=opsional
    FOREIGN KEY (product_id) REFERENCES menu_items(id)
);

CREATE TABLE IF NOT EXISTS modifier_options (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id     INTEGER NOT NULL,
    name         TEXT    NOT NULL,
    price_delta  INTEGER NOT NULL DEFAULT 0,  -- riel, boleh 0
    image_url    TEXT,
    is_available INTEGER NOT NULL DEFAULT 1,  -- konvensi sama dengan menu_items.available
    FOREIGN KEY (group_id) REFERENCES modifier_groups(id)
);

-- Audit trail fitur Edit Order (partial edit). Satu baris per aksi edit sukses,
-- nyimpen snapshot isi order_items SEBELUM diubah — buat jejak kalau ada dispute
-- customer vs kasir ("lho tadi pesenannya bukan ini"). Tabel baru murni (bukan
-- ALTER kolom existing), jadi cukup CREATE TABLE IF NOT EXISTS di sini, aman
-- dijalankan ulang lewat init_db() baik buat instalasi baru maupun DB lama.
CREATE TABLE IF NOT EXISTS order_edits (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id             INTEGER NOT NULL,
    actor_user_id        INTEGER NOT NULL,   -- customer user_id ATAU OWNER_ID
    actor_role           TEXT    NOT NULL,   -- 'customer' | 'owner'
    old_subtotal         INTEGER NOT NULL,
    new_subtotal         INTEGER NOT NULL,
    items_snapshot_json  TEXT    NOT NULL,   -- isi order_items SEBELUM diedit (JSON)
    created_at           TEXT    DEFAULT (datetime('now')),  -- UTC
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
