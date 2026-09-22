import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
SUBMIT_BOT_TOKEN = os.getenv("SUBMIT_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@novinyKievTaOblast")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SUBMIT_BOT_TOKEN = os.getenv("SUBMIT_BOT_TOKEN")

if not SUBMIT_BOT_TOKEN:
    raise RuntimeError(
        "SUBMIT_BOT_TOKEN не найден в .env"
    )



if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY не найден в .env")

