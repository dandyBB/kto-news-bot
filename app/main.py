import asyncio

from aiogram import Bot, Dispatcher

from app.config import BOT_TOKEN
from app.handlers import router
from app.monitor import start_monitor
from app.alerts import alerts_worker
from app.submit_bot import start_submit_bot


async def main():
    bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher()
    dp.include_router(router)

    print("KTO News запущен.")

    try:
        await asyncio.gather(
            dp.start_polling(bot),
            start_monitor(bot),
            alerts_worker(bot),
            start_submit_bot(),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())