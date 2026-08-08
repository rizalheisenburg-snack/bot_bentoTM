"""Entry point — jalankan ini: python main.py"""
import asyncio
import contextlib
import logging

from aiohttp import web

from config import PORT, EXPRESS_LOCATION_REMINDER_MINUTES, EXPRESS_REMINDER_CHECK_INTERVAL_SECONDS
from db import get_conn, init_db
from owner_console import build_application
from seed_menu import seed_menu, seed_nasi_campur_modifiers
from server import AccessLogger, build_app
from state_machine import get_express_orders_awaiting_location_reminder, mark_express_reminder_sent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def _express_reminder_loop(bot) -> None:
    """Tiap EXPRESS_REMINDER_CHECK_INTERVAL_SECONDS detik, cek order Express yang lewat
    EXPRESS_LOCATION_REMINDER_MINUTES menit tanpa lokasi, kirim reminder SEKALI
    (express_reminder_sent_at di DB, bukan in-memory — survive restart bot)."""
    try:
        while True:
            await asyncio.sleep(EXPRESS_REMINDER_CHECK_INTERVAL_SECONDS)
            try:
                for o in get_express_orders_awaiting_location_reminder(EXPRESS_LOCATION_REMINDER_MINUTES):
                    try:
                        await bot.send_message(
                            chat_id=o["user_id"],
                            text=(
                                f"⏰ Order #{o['id']} masih menunggu *Share Location* kamu ya, "
                                "biar Kurir Express-nya bisa segera di-booking 🙏"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception:
                        log.warning("gagal kirim reminder express order #%s", o["id"])
                    finally:
                        # Ditandai terkirim walau gagal (mis. user belum /start) — sengaja,
                        # supaya loop tidak coba² kirim ke user yang sama tiap tick selamanya.
                        mark_express_reminder_sent(o["id"])
            except Exception:
                log.exception("error di express reminder loop")
    except asyncio.CancelledError:
        pass


async def main():
    # Init DB + seed (cuma sekali, hindari duplikat menu tiap restart)
    init_db()
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        if count == 0:
            seed_menu(conn)
        seed_nasi_campur_modifiers(conn)

    # Bot di-init dulu supaya bot.send_message bisa dipakai HTTP server
    tg_app = build_application()
    await tg_app.initialize()

    # HTTP server (aiohttp)
    http_app = build_app(bot=tg_app.bot)
    runner = web.AppRunner(http_app, access_log_class=AccessLogger)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"HTTP server jalan di http://0.0.0.0:{PORT}")

    # Telegram bot mulai polling
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot polling aktif")

    reminder_task = asyncio.create_task(_express_reminder_loop(tg_app.bot))

    # Jaga supaya program tetap hidup
    try:
        await asyncio.Event().wait()
    finally:
        reminder_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminder_task
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
