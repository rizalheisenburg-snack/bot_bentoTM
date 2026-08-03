"""Entry point — jalankan ini: python main.py"""
import asyncio
import logging

from aiohttp import web

from config import PORT
from db import get_conn, init_db
from owner_console import build_application
from seed_menu import seed_menu
from server import build_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main():
    # Init DB + seed (cuma sekali, hindari duplikat menu tiap restart)
    init_db()
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        if count == 0:
            seed_menu(conn)

    # Bot di-init dulu supaya bot.send_message bisa dipakai HTTP server
    tg_app = build_application()
    await tg_app.initialize()

    # HTTP server (aiohttp)
    http_app = build_app(bot=tg_app.bot)
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"HTTP server jalan di http://0.0.0.0:{PORT}")

    # Telegram bot mulai polling
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot polling aktif")

    # Jaga supaya program tetap hidup
    try:
        await asyncio.Event().wait()
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
