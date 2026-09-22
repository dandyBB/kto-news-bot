import asyncio
import os

from aiohttp import web
from aiogram import Bot, Dispatcher

from app.config import BOT_TOKEN
from app.handlers import router
from app.alerts import alerts_worker
from app.submit_bot import start_submit_bot


async def health_handler(request):
    return web.Response(text="KTO News is running")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    print(f"[WEB] Сервер запущен на порту {port}")

    while True:
        await asyncio.sleep(3600)


async def main():
    bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher()
    dp.include_router(router)

    print("KTO News запущен.")

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            alerts_worker(bot),
            start_submit_bot(),
            start_web_server(),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())