"""Dev helper — kirim 1 order test ke server lokal (dev_server.py) buat
verifikasi alur checkout -> print job -> print-agent -> printer fisik,
tanpa lewat Telegram sama sekali (aman, gak bentrok sama bot production).

Jalankan sementara dev_server.py & print_agent.py lagi jalan di terminal lain:
    python trigger_test_print.py
"""
import json
import urllib.request

from config import BOT_TOKEN
from get_initdata import generate_init_data

SERVER = "http://127.0.0.1:8080"
TEST_USER_ID = 999999

init_data = generate_init_data(BOT_TOKEN, TEST_USER_ID, first_name="Test Print")

body = json.dumps({
    "items": [{"item_id": 1, "qty": 1, "note": "test cetak struk"}],
    "note": "Order test print_agent",
    "payment_method": "CASH",
    "address": "",
}).encode()

req = urllib.request.Request(
    f"{SERVER}/api/checkout",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json", "X-Init-Data": init_data},
)

with urllib.request.urlopen(req) as resp:
    print(resp.status, resp.read().decode())
