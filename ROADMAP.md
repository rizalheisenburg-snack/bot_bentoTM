# Roadmap Development — pos-bento (miniAppBento)

**Owner:** Koh James
**Status:** Live, masa trial berjalan
**Base system:** Telegram Mini App (aiohttp backend + SQLite + PTB bot + vanilla JS frontend), forked dari `pos-babi`

**Requirement utama dari owner:** sistem harus gantiin 80% kerjaan admin manual, dan pas demo/trial harus lancar tanpa kendala.

> Dokumen ini direkonstruksi ulang berdasarkan kondisi source code aktual (bukan cuma rencana awal) — supaya jadi acuan yang bisa dipercaya, bukan cuma niat.

---

## Legend Status

| Status | Arti |
| --- | --- |
| ⬜ Belum mulai | Belum dikerjain |
| 🟨 In progress | Lagi dikerjain / perlu polish lanjutan |
| 🟥 Blocked | Nunggu keputusan/dependency lain |
| ✅ Done | Selesai & udah ditest |

---

## Fase 0 — Content & Setup

| Item | Status | Keterangan |
| --- | --- | --- |
| Nama brand final | ✅ | "Bento x Jago Masak" / "Warteg JAGO MASAK" |
| Menu list final (nama, harga, kategori) | ✅ | `seed_menu.py`, ~75 item / 8 kategori |
| Titik koordinat cafe (lat/lon) | ✅ | `.env` — `CAFE_LAT`, `CAFE_LON` |
| Clone repo base → repo project | ✅ | `rizalheisenburg-snack/bot_bentoTM` di GitHub |
| Strip fitur voucher dari base | ✅ | `state_machine.py`, `checkout_flow.py`, `owner_console.py`, `webapp/`, `schema.sql` |

---

## Fase 1 — Backend / Flow Logic

### 1.1 Catatan Custom per Item — ✅ Done

- Kolom `item_note` di `order_items`, diinput per item di cart (`webapp/app.js`), disimpan verbatim (gak diparsing).
- Tampil di kartu order (bot chat) dan detail order (Kanban + TMA customer).
- **Belum:** cetak struk fisik (lihat item terpisah di bawah — sengaja ditunda).

### 1.2 Minimal Order per Alamat — ✅ Done *(desain final beda dari rencana awal)*

**Keputusan final terbaru (beda dari rencana GPS awal):**
- Minimal order ditentuin dari **alamat yang dipilih customer di halaman cart** (chip: KD, Hp Tower, WON, The Rich, Hp Avenue, TM, atau custom), **bukan** dari GPS share.
- Alasan: pelanggan realistisnya milih dari lokasi yang udah dikenal (dorm/hotel sekitar), jadi tier per-alamat lebih akurat & simpel daripada hitung radius GPS live.
- **KD = 40.000៛** (jauh dari cafe), **semua alamat lain = 20.000៛** (default).
- Divalidasi **server-side** saat checkout (`checkout_flow.py`) — order di bawah minimal langsung ditolak (400), bukan cuma warning UI.
- Endpoint: `GET /api/address-tiers` (kasih tau frontend tier per alamat), `POST /api/checkout` terima field `address`.
- Fitur **share lokasi GPS via bot tetap ada** (`handle_location`, tombol "📍 Cek Lokasi Saya") — disimpan buat referensi/histori owner, tapi **gak lagi** dipakai buat enforce minimal order.

### 1.3 Ganti Metode Pembayaran — ✅ Done

- Tombol ganti metode tampil selama `payment_status == UNPAID`, dikunci begitu `PAID`.
- Notif pasif ke admin (chat bot) begitu customer ganti metode.
- File: `state_machine.py` (`change_payment_method`), `server.py`, `webapp/app.js`, `owner_console.py`.

### 1.4 Cancel Order — ✅ Done

- Customer cuma bisa cancel selama status `Diterima`.
- Admin bisa force-cancel dari kolom manapun, kapan aja, wajib pilih alasan (`Stok habis / Request customer / Kesalahan input / Lainnya`).
- Warning (bukan blocker) kalau order yang dibatalkan udah `PAID`.
- File: `state_machine.py` (`customer_can_cancel`, `admin_can_force_cancel`, `get_cancel_warning`, `force_cancel_order`).

### 1.5 Kanban `/admin` + WebSocket — ✅ Done *(scope lebih besar dari rencana awal)*

- **5 kolom** (nambah dari rencana awal yang 4): `Diterima → Diproses → Siap → Selesai → Dibatalkan`.
  - "Siap" = makanan udah jadi. "Selesai" = udah diambil/diantar ke customer (status terminal baru).
- Real-time via WebSocket (`/ws/admin`), auth pakai HMAC `initData` + cek `OWNER_ID`.
- Kartu order: ringkas di board, detail on-click. Highlight visual + timer badge kalau nyangkut >15 menit.
- Tab status quick-jump (scroll-spy) + kode warna per kolom, badge status bayar, empty-state placeholder, haptic + animasi highlight pas order baru masuk.
- Dibuka dari Telegram lewat command bot `/admin` → tombol `WebAppInfo` (bukan link browser biasa).
- File: `server.py` (routes + WS), `webapp/admin.html`, `webapp/admin.js`, `webapp/admin.css`.

### 1.6 Deteksi Keyword Chat Manual — ✅ Done

- Regex (`antar`, `delivery`, `bisa ke`, `sampe mana`) → arahkan ke tombol lokasi, bukan dijawab manual.
- File: `owner_console.py` (`_LOCATION_KEYWORD_RE`, `handle_text_fallback`).

---

## Fase 2 — UI Redesign

**Status:** 🟨 In progress — udah jalan duluan berbarengan sama Fase 1, bukan nunggu Fase 1 kelar semua.

- ✅ Theme "Dark Glass Blue" — konsisten dipakai di customer app & Kanban admin.
- ✅ Menu customer di-flatten dari 2-tingkat (kategori → item) jadi 1 scroll panjang + tab kategori quick-jump (scroll-spy).
- ✅ Foto per item menu (kolom `image_url`), ~29 dari 75 item udah ada foto, sisanya nyusul.
- ✅ Optimasi gambar (resize + compress) — total ukuran turun dari puluhan MB ke ~1MB.
- ✅ Kanban admin diredesign: tab status, kode warna kolom, badge, animasi order baru.
- 🟨 Sisa foto menu (~46 item, mostly Roti/Cemilan) masih nyusul manual.

---

## Fitur/Perubahan di luar rencana awal (worth dicatat)

| Perubahan | Alasan |
| --- | --- |
| Kanban 5 kolom (+ "Selesai") | Butuh bedain "makanan siap" vs "udah beneran diambil/diantar" |
| Minimal order berbasis alamat cart, bukan GPS | Lokasi customer realistisnya dari daftar dorm/hotel yang udah dikenal, bukan koordinat acak |
| Command `/admin` di bot buka Kanban sebagai Mini App | Biar gak perlu ketik URL manual, tetep dalam Telegram |
| Validasi minimal order pindah ke server-side | Sebelumnya cuma warning UI di frontend, bisa di-bypass |

---

## Keputusan yang Sudah Final (jangan diubah tanpa alasan kuat)

| Topik | Keputusan |
| --- | --- |
| Voucher | Tidak dipakai — dihapus dari base |
| Minimal order | Berbasis alamat pilihan di cart (KD=40k, lainnya=20k default), bukan GPS. Tiered, bukan blocking-per-lokasi (semua alamat tetap bisa order, cuma beda ambang) |
| Cancel by customer | Cuma bisa saat status `Diterima` |
| Cancel by admin | Bisa dari kolom manapun, warning muncul kalau `payment_status == PAID` |
| Aksi ubah state (status, lunas, force-cancel) | **Sengaja ada di 2 tempat**: Kanban (TMA) **dan** chat bot (inline button) — bukan cuma satu. Alasan: Kanban masih dianggap belum 100% reliable, chat bot jadi fallback operasional biar gak ada downtime kalau Kanban error |
| Upload bukti transfer | Tetap lewat chat, tidak dipindah ke TMA |
| Share lokasi GPS | Tetap ada di bot (informasional), tapi gak dipakai buat hitung minimal order lagi |
| Struk printer thermal (RawBT) | **Sengaja ditunda** — langkah lanjutan setelah lolos trial sama Koh James, bukan bug/kelupaan |

---

## Yang beneran belum dikerjain

| Item | Status | Keterangan |
| --- | --- | --- |
| Cetak struk thermal (RawBT) | 🟥 Blocked (sengaja) | Nunggu lolos trial dulu |
| Sisa foto menu (~46 item) | 🟨 In progress | Upload manual bertahap |

---

## Timeline

| Tanggal | Milestone |
| --- | --- |
| 7 Agustus 2026 | Live — sistem mulai dipakai |
| 7 Agustus – +2 minggu | Masa trial: sistem jalan real, admin ditraining sambil jalan |
| Setelah masa trial | Evaluasi bareng Koh James — lanjut/ada revisi, termasuk keputusan soal struk printer |
