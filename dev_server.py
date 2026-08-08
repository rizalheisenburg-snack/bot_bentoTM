"""Dev server — jalankan untuk test localhost tanpa bot Telegram."""
import asyncio
from aiohttp import web
from db import init_db
from server import AccessLogger, build_app

async def main():
    init_db()
    app = build_app(bot=None)
    runner = web.AppRunner(app, access_log_class=AccessLogger)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8080)
    await site.start()
    print("Server jalan di http://127.0.0.1:8080")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
