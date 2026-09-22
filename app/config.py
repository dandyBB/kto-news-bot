import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
SUBMIT_BOT_TOKEN = os.getenv("SUBMIT_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@novinyKievTaOblast")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

SUBMIT_BOT_TOKEN = os.getenv("SUBMIT_BOT_TOKEN")

if not SUBMIT_BOT_TOKEN:
    raise RuntimeError(
        "SUBMIT_BOT_TOKEN не найден в .env"
    )

SOURCE_CHANNELS = [
    channel.strip()
    for channel in os.getenv("SOURCE_CHANNELS", "").split(",")
    if channel.strip()
]


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY не найден в .env")

if not TELEGRAM_API_ID:
    raise RuntimeError("TELEGRAM_API_ID не найден в .env")

if not TELEGRAM_API_HASH:
    raise RuntimeError("TELEGRAM_API_HASH не найден в .env")

if not SOURCE_CHANNELS:
    raise RuntimeError("SOURCE_CHANNELS не найден в .env")