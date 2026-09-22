import asyncio
import hashlib
import re
from collections import deque
from uuid import uuid4

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telethon import TelegramClient, events

from app.config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    ADMIN_ID,
)
from app.ai import analyze_and_generate_news


client = TelegramClient(
    "telegram_monitor",
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
)

monitor_bot: Bot | None = None

monitor_pending = {}

QUEUE_SIZE = 100

news_queue = asyncio.Queue(
    maxsize=QUEUE_SIZE
)


# ==================================================
# ДЕДУПЛИКАЦИЯ TELEGRAM-СООБЩЕНИЙ
# ==================================================

SEEN_LIMIT = 3000

seen_messages = set()
seen_order = deque(
    maxlen=SEEN_LIMIT
)


def was_seen(
    chat_id,
    message_id,
) -> bool:

    key = (
        chat_id,
        message_id,
    )

    if key in seen_messages:
        return True

    seen_messages.add(key)
    seen_order.append(key)

    if len(seen_messages) > SEEN_LIMIT:

        old_key = seen_order.popleft()

        seen_messages.discard(
            old_key
        )

    return False


# ==================================================
# ДЕДУПЛИКАЦИЯ ОДИНАКОВОГО ТЕКСТА
# ==================================================

TEXT_DUPLICATE_LIMIT = 1500

recent_texts = set()
recent_text_order = deque(
    maxlen=TEXT_DUPLICATE_LIMIT
)


def normalize_text(
    text: str,
) -> str:

    text = text.lower()

    text = re.sub(
        r"https?://\S+",
        " ",
        text,
    )

    text = re.sub(
        r"@\w+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def get_text_hash(
    text: str,
) -> str:

    normalized = normalize_text(
        text
    )

    return hashlib.sha256(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()


def is_duplicate_text(
    text: str,
) -> bool:

    text_hash = get_text_hash(
        text
    )

    if text_hash in recent_texts:
        return True

    recent_texts.add(
        text_hash
    )

    recent_text_order.append(
        text_hash
    )

    if len(recent_texts) > TEXT_DUPLICATE_LIMIT:

        old_hash = recent_text_order.popleft()

        recent_texts.discard(
            old_hash
        )

    return False


# ==================================================
# ЛОКАЛЬНЫЙ ФИЛЬТР
# ==================================================

ADVERTISEMENT_WORDS = (
    "реклама",
    "реклам",
    "промокод",
    "знижка",
    "скидка",
    "купити",
    "купля",
    "продам",
    "продаж",
    "замовляй",
    "заказывай",
    "ставки",
    "казино",
    "беттинг",
    "букмекер",
    "розіграш",
    "розыгрыш",
)


IMPORTANT_WORDS = (
    "тривога",
    "повітряна тривога",
    "відбій",
    "вибух",
    "вибухи",
    "пожежа",
    "горить",
    "дтп",
    "аварія",
    "ракета",
    "ракети",
    "бпла",
    "шахед",
    "дрон",
    "безпілотник",
    "обстріл",
    "прильот",
    "приліт",
    "київ",
    "київська область",
    "відключення",
)


def looks_like_ad(
    text: str,
) -> bool:

    normalized = normalize_text(
        text
    )

    links = re.findall(
        r"https?://\S+",
        text,
        flags=re.IGNORECASE,
    )

    if len(links) >= 4:
        return True

    found = 0

    for word in ADVERTISEMENT_WORDS:

        if word in normalized:
            found += 1

    return found >= 2


def should_skip_locally(
    text: str,
) -> tuple[bool, str]:

    normalized = normalize_text(
        text
    )

    if not normalized:
        return True, "пустой пост"

    # Короткие потенциально важные сообщения
    # обязательно отправляем Gemini.
    if any(
        word in normalized
        for word in IMPORTANT_WORDS
    ):
        return False, ""

    if len(normalized) < 10:
        return True, "слишком короткий пост"

    if looks_like_ad(text):
        return True, "похоже на рекламу"

    if re.fullmatch(
        r"(https?://\S+\s*)+",
        text.strip(),
        flags=re.IGNORECASE,
    ):
        return True, "только ссылки"

    return False, ""


# ==================================================
# КНОПКИ
# ==================================================

def monitor_keyboard(
    news_id: str,
) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Взять в работу",
                    callback_data=(
                        f"monitor_take:{news_id}"
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ Пропустить",
                    callback_data=(
                        f"monitor_skip:{news_id}"
                    ),
                ),
            ]
        ]
    )


# ==================================================
# ИСТОЧНИК
# ==================================================

def get_source_name(
    event,
) -> str:

    try:

        chat = event.chat

        if chat is not None:

            username = getattr(
                chat,
                "username",
                None,
            )

            if username:
                return f"@{username}"

            title = getattr(
                chat,
                "title",
                None,
            )

            if title:
                return title

    except Exception:
        pass

    return "невідоме джерело"





# ==================================================
# ОТПРАВКА АДМИНУ
# ==================================================

async def send_admin_message(
    bot: Bot,
    text: str,
    reply_markup=None,
):

    MAX_LENGTH = 3800

    if len(text) <= MAX_LENGTH:

        await bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            reply_markup=reply_markup,
        )

        return

    parts = []

    while text:

        parts.append(
            text[:MAX_LENGTH]
        )

        text = text[
            MAX_LENGTH:
        ]

    for index, part in enumerate(parts):

        if index == len(parts) - 1:

            await bot.send_message(
                chat_id=ADMIN_ID,
                text=part,
                reply_markup=reply_markup,
            )

        else:

            await bot.send_message(
                chat_id=ADMIN_ID,
                text=part,
            )


# ==================================================
# ОБРАБОТКА
# ==================================================

async def process_news(
    item: dict,
):

    text = item["text"]
    chat_id = item["chat_id"]
    message_id = item["message_id"]
    source_name = item["source_name"]

    print(
        "[WORKER] Обработка "
        f"{source_name} "
        f"{chat_id}:{message_id}"
    )

    result = await analyze_and_generate_news(
        text,
        source_name=source_name,
    )

    if not result["interesting"]:

        print(
            "[WORKER] Пропущено: "
            f"{result['reason']}"
        )

        return

    generated_news = (
        result["news"]
        .strip()
    )

    if not generated_news:

        raise RuntimeError(
            "Gemini не вернул "
            "готовую новость."
        )

    priority = result.get(
        "priority",
        "NORMAL",
    )

    if priority == "HIGH":
        priority_text = "🔥 ВЫСОКИЙ"
    else:
        priority_text = "📰 ОБЫЧНЫЙ"

    news_id = uuid4().hex[:12]

    monitor_pending[news_id] = {
        "original": text,
        "result": generated_news,
        "reason": result["reason"],
        "priority": priority,
        "source_name": source_name,
        "source_chat_id": chat_id,
        "source_message_id": message_id,
    }

    if monitor_bot is None:

        print(
            "[WORKER] Бот ещё не готов."
        )

        return

    admin_text = (
        "📰 НАЙДЕНА НОВОСТЬ\n\n"
        f"📡 Источник: {source_name}\n"
        f"{priority_text}\n\n"
        "Причина:\n"
        f"{result['reason']}\n\n"
        "ГОТОВАЯ НОВОСТЬ:\n\n"
        f"{generated_news}\n\n"
        "ОРИГИНАЛ:\n\n"
        f"{text[:2500]}"
    )

    await send_admin_message(
        monitor_bot,
        admin_text,
        reply_markup=monitor_keyboard(
            news_id
        ),
    )

    print(
        "[WORKER] Новость отправлена админу."
    )


# ==================================================
# WORKER
# ==================================================

async def monitor_worker():

    print(
        "[WORKER] Worker запущен."
    )

    while True:

        item = await news_queue.get()

        try:

            try:

                await process_news(
                    item
                )

            except asyncio.CancelledError:

                raise

            except Exception as error:

                item["retries"] += 1

                error_text = str(
                    error
                )

                print(
                    f"[WORKER] Ошибка: "
                    f"{error_text}"
                )

                upper_error = (
                    error_text.upper()
                )

                # ----------------------------------
                # 400 — больше не повторяем
                # ----------------------------------

                if (
                    "400" in upper_error
                    or
                    "INVALID_ARGUMENT"
                    in upper_error
                    or
                    "BAD REQUEST"
                    in upper_error
                ):

                    print(
                        "[WORKER] 400: "
                        "пост отброшен без повтора."
                    )

                    continue

                # ----------------------------------
                # 503 / 500 / 429 / timeout
                # ----------------------------------
                # Не вызываем Gemini снова сразу.
                # Возвращаем пост в очередь спустя минуту.
                # Максимум 3 раза.
                # ----------------------------------

                temporary_error = (
                    "503" in upper_error
                    or
                    "500" in upper_error
                    or
                    "502" in upper_error
                    or
                    "504" in upper_error
                    or
                    "429" in upper_error
                    or
                    "TEMPORARY_GEMINI_ERROR"
                    in upper_error
                    or
                    "TIMEOUT"
                    in upper_error
                )

                if temporary_error:

                    if item["retries"] <= 3:

                        delay = 60 * item[
                            "retries"
                        ]

                        print(
                            "[WORKER] Gemini "
                            "временно недоступен."
                        )

                        print(
                            "[WORKER] Повтор "
                            f"через {delay} сек."
                        )

                        await asyncio.sleep(
                            delay
                        )

                        try:

                            news_queue.put_nowait(
                                item
                            )

                            print(
                                "[WORKER] Пост "
                                "возвращён в очередь."
                            )

                        except asyncio.QueueFull:

                            print(
                                "[WORKER] Очередь "
                                "переполнена."
                            )

                    else:

                        print(
                            "[WORKER] Пост "
                            "отброшен после "
                            "3 временных ошибок."
                        )

                    continue

                # ----------------------------------
                # Неизвестная ошибка
                # ----------------------------------

                if item["retries"] <= 2:

                    delay = 60

                    print(
                        "[WORKER] Неизвестная ошибка."
                    )

                    print(
                        f"[WORKER] Повтор через "
                        f"{delay} сек."
                    )

                    await asyncio.sleep(
                        delay
                    )

                    try:

                        news_queue.put_nowait(
                            item
                        )

                    except asyncio.QueueFull:

                        print(
                            "[WORKER] Не удалось "
                            "вернуть пост в очередь."
                        )

                else:

                    print(
                        "[WORKER] Пост отброшен."
                    )

        finally:

            news_queue.task_done()

            print(
                "[WORKER] Очередь: "
                f"{news_queue.qsize()}"
            )


# ==================================================
# ЗАПУСК
# ==================================================

async def start_monitor(
    bot: Bot,
):

    global monitor_bot

    monitor_bot = bot

    print(
        "Запуск Telegram-монитора..."
    )

    worker_task = asyncio.create_task(
        monitor_worker()
    )

    try:

        await client.start()

        print(
            "Telegram-монитор запущен."
        )

        await client.run_until_disconnected()

    finally:

        worker_task.cancel()

        try:

            await worker_task

        except asyncio.CancelledError:

            pass

        print(
            "[WORKER] Worker остановлен."
        )