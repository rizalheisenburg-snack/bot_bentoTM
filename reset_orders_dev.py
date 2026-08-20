"""Reset semua data order (order/item/edit-history/print-job/bukti-bayar) —
menu & setting TIDAK disentuh. BUAT DEV DOANG, gak ada konfirmasi apa-apa
karena ini bukan DB prod, pakai .env lokal lo sendiri (lihat DB_PATH di
config.py). Kalau ragu itu DB apa, jalanin check_db.py atau cek DB_PATH
di .env dulu sebelum run ini.

Usage: python reset_orders_dev.py
"""
from db import reset_orders

result = reset_orders()
print(f"Done — {result['orders_deleted']} order dihapus. Menu/setting aman.")
