"""Print-agent — jalan di PC lokal yang nyolok printer thermal USB.

Connect OUT ke server (VPS) lewat WebSocket /ws/printer (bukan sebaliknya),
supaya gak kena masalah NAT/firewall jaringan lokal PC ini. Auto-reconnect
kalau koneksi putus. Jalankan: python print_agent.py

Environment (lihat print_agent.env.example):
  PRINT_SERVER_WS_URL   contoh: wss://domain-vps-lo.com/ws/printer
  PRINT_AGENT_TOKEN     harus sama persis dengan PRINTER_AGENT_TOKEN di server
  PRINTER_VID           default 0x0FE6 (APOS-P80A-BW)
  PRINTER_PID           default 0x811E
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

# Prioritaskan .env.printagent (dipakai kalau script ini numpuk di folder yang
# sama dengan main app, yang punya .env sendiri) — baru fallback ke .env biasa
# (dipakai kalau print_agent.py berdiri sendiri di PC/folder terpisah).
_agent_env = Path(__file__).parent / ".env.printagent"
load_dotenv(_agent_env if _agent_env.exists() else None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("print_agent")

WS_URL: str = os.environ["PRINT_SERVER_WS_URL"]
TOKEN: str = os.environ["PRINT_AGENT_TOKEN"]
PRINTER_VID: int = int(os.getenv("PRINTER_VID", "0x0FE6"), 16)
PRINTER_PID: int = int(os.getenv("PRINTER_PID", "0x811E"), 16)
RECONNECT_DELAY = 5  # detik


def _open_printer():
    """Buka koneksi USB ke printer. Raise kalau printer offline/gak kedetect."""
    import usb.backend.libusb1
    import libusb
    from escpos.printer import Usb

    backend = usb.backend.libusb1.get_backend(find_library=lambda x: libusb.dll._name)
    return Usb(PRINTER_VID, PRINTER_PID, backend=backend)


def _print_receipt(receipt: dict) -> None:
    """Format & cetak 1 struk, lalu potong kertas. Blocking (I/O USB) — sengaja
    dipanggil lewat asyncio.to_thread supaya gak nge-block event loop. Raise
    kalau ada error printer (offline/gak kedetect/dll), ditangkap di caller."""
    # Catatan: printer ini kebukti nge-ignore command bold/width/height dari
    # python-escpos (align doang yang keefek) — jadi sengaja gak dipaksain
    # lagi, semua dicetak ukuran/berat normal. p.set(...) sendiri tetap gak
    # incremental (tiap dipanggil, param yang gak disebutin balik ke default),
    # makanya align di-set ulang tiap ganti sisi.
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
    log.info("Print-agent starting, target=%s", WS_URL)
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
        log.info("Print-agent dihentikan (Ctrl+C).")
