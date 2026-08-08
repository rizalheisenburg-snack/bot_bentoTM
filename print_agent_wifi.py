"""Print-agent (WiFi) — versi EKSPERIMENTAL print_agent.py yang connect ke
printer lewat jaringan (WiFi), bukan USB. File ini SENGAJA terpisah dari
print_agent.py yang udah jalan production — supaya eksperimen ini gak
ganggu itu sama sekali.

PENTING sebelum dijalanin: server cuma nerima 1 print-agent aktif dalam
satu waktu (lihat server.py, variabel _printer_agent) — begitu ada koneksi
baru yang berhasil auth, socket lama langsung ditutup. JANGAN arahin
PRINT_SERVER_WS_URL di bawah ke server production (wss://app.bentotm.cloud/...)
selama masih eksperimen, soalnya bakal nendang keluar agent USB yang lagi
jalan beneran. Tes dulu pake dev_server.py lokal:
  PRINT_SERVER_WS_URL=ws://127.0.0.1:8080/ws/printer

Environment (.env.printagent-wifi di folder yang sama, lihat
print_agent_wifi.env.example):
  PRINT_SERVER_WS_URL   ws://127.0.0.1:8080/ws/printer (testing) atau wss://... (production)
  PRINT_AGENT_TOKEN     harus sama persis dengan PRINTER_AGENT_TOKEN di server
  PRINTER_IP            IP printer di jaringan WiFi (cek DHCP client list router)
  PRINTER_PORT          default 9100 (port raw ESC/POS standar / JetDirect)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

_agent_env = Path(__file__).parent / ".env.printagent-wifi"
load_dotenv(_agent_env if _agent_env.exists() else None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("print_agent_wifi")

WS_URL: str = os.environ["PRINT_SERVER_WS_URL"]
TOKEN: str = os.environ["PRINT_AGENT_TOKEN"]
PRINTER_IP: str = os.environ["PRINTER_IP"]
PRINTER_PORT: int = int(os.getenv("PRINTER_PORT", "9100"))
RECONNECT_DELAY = 5  # detik


def _open_printer():
    """Buka koneksi network ke printer. Raise kalau printer gak kejangkau
    (mati/beda jaringan/IP salah/dll)."""
    from escpos.printer import Network

    return Network(PRINTER_IP, port=PRINTER_PORT, timeout=10)


def _print_receipt(receipt: dict) -> None:
    """Format & cetak — sama persis formatnya kayak print_agent.py (USB),
    cuma cara buka printernya beda (network socket, bukan USB). Printer ini
    kebukti nge-ignore command bold/width/height ESC-POS, jadi tetep plain
    text semua + nomor urut per item."""
    p = _open_printer()
    try:
        p.set(align="center")
        p.text("BENTO X JAGO MASAK\n")
        p.text(f"Order #{receipt.get('order_id', '-')}\n")
        p.text(f"{receipt.get('created_at', '')}\n")
        p.text("-" * 32 + "\n")

        p.set(align="left")
        p.text(f"Pelanggan : {receipt.get('customer', '-')}\n")
        if receipt.get("address"):
            p.text(f"Alamat    : {receipt['address']}\n")
        p.text(f"Bayar     : {receipt.get('payment_method', 'CASH')}\n")
        if receipt.get("note"):
            p.text(f"Note      : {receipt['note']}\n")
        p.text("-" * 32 + "\n")

        for i, item in enumerate(receipt.get("items", []), start=1):
            p.set(align="left")
            p.text(f"{i}. {item['name']} x{item['qty']}\n")
            if item.get("note"):
                p.text(f"   * {item['note']}\n")
            p.set(align="right")
            p.text(f"{item['line_total']:,}\n")

        p.set(align="left")
        p.text("-" * 32 + "\n")
        p.set(align="right")
        p.text(f"TOTAL {receipt.get('total', 0):,}\n")
        p.set(align="left")
        p.text("\n\n")
        p.cut()
    finally:
        try:
            p.close()
        except Exception:
            pass


async def _handle_print_job(ws: aiohttp.ClientWebSocketResponse, job: dict) -> None:
    job_id = job.get("job_id")
    order_id = job.get("order_id")
    receipt = job.get("receipt", {})
    try:
        await asyncio.to_thread(_print_receipt, receipt)
        log.info("Order #%s (job #%s) berhasil dicetak", order_id, job_id)
        await ws.send_json({"type": "ack", "job_id": job_id, "status": "printed"})
    except Exception as e:
        log.error("Gagal cetak order #%s (job #%s): %s", order_id, job_id, e)
        try:
            await ws.send_json(
                {"type": "ack", "job_id": job_id, "status": "failed", "error": str(e)}
            )
        except Exception:
            log.exception("Gagal kirim ack 'failed' ke server")


async def _run_once() -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            WS_URL, params={"token": TOKEN}, heartbeat=30
        ) as ws:
            log.info("Terhubung ke server: %s", WS_URL)
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "print_job":
                        await _handle_print_job(ws, data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break


async def main() -> None:
    log.info(
        "Print-agent (WiFi) starting, target=%s, printer=%s:%s",
        WS_URL, PRINTER_IP, PRINTER_PORT,
    )
    while True:
        try:
            await _run_once()
        except aiohttp.ClientError as e:
            log.warning("Gagal connect / koneksi putus (%s)", e)
        except Exception:
            log.exception("Error tak terduga di print-agent")
        log.info("Reconnect dalam %ss...", RECONNECT_DELAY)
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Print-agent (WiFi) dihentikan (Ctrl+C).")