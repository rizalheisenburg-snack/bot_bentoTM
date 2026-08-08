# Bento x Jago Masak — POS System via Telegram Mini App

Sistem kasir & pemesanan digital untuk warung makan **Bento x Jago Masak** ("Warteg JAGO MASAK"), dibangun sebagai Telegram Mini App (TMA) — customer pesan lewat Mini App, owner kelola order dari chat bot Telegram. Repo ini di-fork dari base project `pos-babi` dan dikustomisasi ulang total sesuai kebutuhan warung ini.

> **Status:** Live, sedang masa trial berjalan bareng owner (Koh James) sejak 7 Agustus 2026.

---

## Project Overview

`bot_bentoTM` menggantikan sebagian besar workflow kasir manual: customer scan/klik Mini App, pilih menu, checkout, dan owner tinggal kelola dari HP-nya lewat chat bot — tanpa perlu install app terpisah, semua di dalam Telegram.

**Dua aktor utama:**

| Aktor | Lewat apa | Ngapain |
|---|---|---|
| **Customer** | Mini App (webview di Telegram) | Lihat menu, isi cart, checkout, pilih metode bayar, track status order |
| **Owner** | Bot Telegram (chat) + Kanban `/admin` | Terima/proses/selesaikan order, toggle stok, cek omzet, tandai lunas, force-cancel |

---

## Fitur Utama

- **Menu & Kategori** — ~77 item di 8 kategori (Paket Spesial, Menu Nasi, Rice Bowl, Ala Carte, Paket Hoki, Roti/Cemilan, Kerupuk/Keripik, Minuman), lengkap dengan foto per item
- **Checkout & Cart** — cart hidup di client-side, row order baru dibuat di database saat checkout; item yang kehabisan stok otomatis di-skip, sisanya tetap lanjut
- **State Machine Dapur** — 4 status order (`Diterima → Diproses → Siap → Selesai`), dengan `Dibatalkan` sebagai jalur keluar; customer cuma bisa cancel selagi `Diterima`, owner bisa force-cancel kapan saja dengan alasan wajib
- **Payment terpisah dari status dapur** — `payment_status` (UNPAID/PAID) berjalan independen dari status masak; ganti metode bayar (CASH ↔ ABA) bisa dilakukan customer sendiri lewat Mini App selama order belum lunas
- **Minimal order berbasis alamat** — tier minimal order ditentukan dari alamat yang dipilih customer di cart (bukan GPS), divalidasi server-side saat checkout
- **Kanban Admin (`/admin`)** — board real-time via WebSocket, 5 kolom status, timer highlight untuk order yang nyangkut, badge status bayar, dibuka langsung dari command bot sebagai Mini App
- **Cetak Struk Otomatis** — order baru langsung dicetak ke printer thermal USB lewat print-agent lokal (`print_agent.py`) yang connect ke server via WebSocket (`/ws/printer`); kalau agent lagi offline, print job diantre di database dan otomatis dicetak begitu agent reconnect
- **Order Mirror ke Customer** — begitu checkout sukses, detail order otomatis dikirim ke chat customer; kalau customer belum pernah `/start` bot, sistem mendeteksi dan mengarahkan customer untuk chat bot dulu (bukan silent fail)
- **Chat Pelanggan dari Kanban** — tombol deep-link langsung ke chat Telegram customer di setiap card order, tanpa perlu keluar dari panel admin
- **Dual-path admin actions** — perubahan status/lunas/cancel sengaja tersedia di **dua tempat**: Kanban (TMA) *dan* chat bot (inline button), supaya operasional owner tetap jalan walau salah satu sisi bermasalah
- **Laporan Omzet** — rekap harian/bulanan lewat command bot, dengan "hari kerja" mengikuti jam shift (bukan tengah malam)
- **Lokasi & Delivery** — share lokasi GPS via bot untuk referensi owner, deteksi keyword chat manual (`antar`, `delivery`, dll) yang otomatis diarahkan ke tombol lokasi

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python (aiohttp) |
| Database | SQLite |
| Bot Layer | python-telegram-bot (PTB) v21 |
| Frontend | Vanilla JavaScript (Telegram Mini App), WebSocket untuk realtime |
| Hosting | VPS, systemd service, HTTPS via Let's Encrypt/certbot |

---

## Keputusan Desain Penting

- **Semua uang dalam Riel (integer)** — base currency Riel Kamboja, tanpa subunit, jadi tidak ada masalah pembulatan desimal. USD dikonversi pakai rate statis 4000/$1 hanya untuk pembayaran fisik, pembukuan tetap Riel.
- **Payment tidak menghambat dapur** — order tetap diproses walau belum dibayar; risiko customer tidak bayar ditanggung sebagai risiko bisnis, bukan dijaga lewat kode.
- **Voucher tidak dipakai** — fitur voucher dari base project `pos-babi` sengaja dihapus total.
- **Struk printer thermal otomatis** — order baru langsung dicetak lewat print-agent lokal (`print_agent.py`) yang connect ke server via WebSocket, bukan RawBT seperti rencana awal. Detail di [`ROADMAP.md`](./ROADMAP.md).

Detail lengkap keputusan & histori pengembangan ada di [`ROADMAP.md`](./ROADMAP.md).

---

## Repository Structure

```
bot_bentoTM/
├── main.py              # Entry point — jalanin HTTP server + bot polling
├── server.py            # aiohttp routes: checkout, order status, kanban API, WebSocket
├── owner_console.py      # Bot command & inline button handlers (owner-facing)
├── checkout_flow.py     # Logic checkout & validasi initData
├── state_machine.py     # State machine dapur + payment + cancel
├── db.py / schema.sql   # SQLite schema & migrasi ringan
├── geo.py               # Minimal order per-alamat
├── seed_menu.py         # Seed data menu awal
├── config.py            # Environment/config
├── printing.py          # Antrean print job (SQLite queue) + format data struk
├── print_agent.py       # Script terpisah — jalan di PC dengan printer USB, requirements-print-agent.txt sendiri
├── webapp/
│   ├── index.html, app.js, style.css     # Mini App customer-facing
│   ├── admin.html, admin.js, admin.css   # Kanban admin
│   └── img/                              # Foto menu
├── test_checkout.py, test_geo.py, test_printing.py   # Unit test
└── ROADMAP.md            # Histori & keputusan pengembangan
```

---

## Catatan

Repo ini awalnya di-scaffold dari base project bernama `pos-babi` (test plan lama di `test_plan/` masih menyebut nama itu) — sudah tidak relevan dengan brand & menu aktual (`Bento x Jago Masak`) dan akan diperbarui menyusul.
