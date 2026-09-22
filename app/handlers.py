from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from app.config import ADMIN_ID, CHANNEL_ID
from app.ai import generate_news
from app.keyboards import (
    main_keyboard,
    generation_modes_keyboard,
    news_keyboard,
    publish_keyboard,
)
from app.monitor import monitor_pending

router = Router()


pending_news = {}

user_modes = {}

edit_waiting = set()

def submit_news_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Опублікувати",
                    callback_data="submit_publish",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Переделать",
                    callback_data="submit_rewrite",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="submit_edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="submit_cancel",
                )
            ],
        ]
    )


def submit_publish_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, опубликовать",
                    callback_data="submit_publish_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="submit_publish_back",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="submit_cancel",
                ),
            ],
        ]
    )

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_mode(user_id: int) -> str:
    return user_modes.get(user_id, "normal")


@router.message(CommandStart())
async def start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "🤖 <b>KTO NEWS</b>\n\n"
        "Панель управления каналом.\n\n"
        "Выбери действие:",
        reply_markup=main_keyboard(),
    )


# =========================
# ГЛАВНОЕ МЕНЮ
# =========================

@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 <b>KTO NEWS</b>\n\n"
        "Панель управления каналом.",
        reply_markup=main_keyboard(),
    )

    await callback.answer()


@router.callback_query(F.data == "create_news")
async def create_news(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    await callback.message.edit_text(
        "📰 <b>Создание новости</b>\n\n"
        "Просто отправь мне исходный текст новости.\n\n"
        "Я обработаю его и подготовлю готовую публикацию."
    )

    await callback.answer()


# =========================
# РЕЖИМЫ
# =========================

@router.callback_query(F.data == "generation_mode")
async def generation_mode(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    current = get_mode(callback.from_user.id)

    names = {
        "normal": "📰 Обычная",
        "short": "📱 Короткая",
        "urgent": "⚡ Срочная",
        "detailed": "📋 Подробная",
    }

    await callback.message.edit_text(
        "🧠 <b>Режим генерации</b>\n\n"
        f"Сейчас: <b>{names[current]}</b>\n\n"
        "Выбери режим:",
        reply_markup=generation_modes_keyboard(),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("mode_"))
async def set_mode(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    mode = callback.data.replace("mode_", "")

    user_modes[callback.from_user.id] = mode

    names = {
        "normal": "📰 Обычная",
        "short": "📱 Короткая",
        "urgent": "⚡ Срочная",
        "detailed": "📋 Подробная",
    }

    await callback.message.edit_text(
        f"✅ Режим изменён.\n\n"
        f"Теперь используется: <b>{names[mode]}</b>",
        reply_markup=main_keyboard(),
    )

    await callback.answer()


# =========================
# ПОЛУЧЕНИЕ НОВОСТИ
# =========================

@router.message(F.text)
async def process_news(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    user_id = message.from_user.id

    # Если пользователь сейчас редактирует текст
    if user_id in edit_waiting:
        edit_waiting.remove(user_id)

        data = pending_news.get(user_id)

        if not data:
            await message.answer(
                "❌ Черновик не найден.",
                reply_markup=main_keyboard(),
            )
            return

        wait_message = await message.answer(
            "✏️ Применяю изменения..."
        )

        try:
            result = await generate_news(
                data["original"],
                mode=data["mode"],
                edit_request=message.text,
            )

            data["result"] = result

            await wait_message.edit_text(
                f"📰 <b>Обновлённый вариант:</b>\n\n"
                f"{result}",
                reply_markup=news_keyboard(),
            )

        except Exception as e:
            await wait_message.edit_text(
                f"❌ Ошибка:\n<code>{e}</code>"
            )

        return

    # Обычная новая новость
    wait_message = await message.answer(
        "🤖 Обрабатываю новость..."
    )

    try:
        mode = get_mode(user_id)

        result = await generate_news(
            message.text,
            mode=mode,
        )

        pending_news[user_id] = {
            "original": message.text,
            "result": result,
            "mode": mode,
        }

        await wait_message.edit_text(
            f"📰 <b>Готовый вариант:</b>\n\n"
            f"{result}",
            reply_markup=news_keyboard(),
        )

    except Exception as e:
        await wait_message.edit_text(
            f"❌ Ошибка при обращении к нейросети:\n"
            f"<code>{e}</code>"
        )


# =========================
# РЕДАКТИРОВАНИЕ
# =========================

@router.callback_query(F.data == "news_edit")
async def edit_news(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    user_id = callback.from_user.id

    if user_id not in pending_news:
        await callback.answer(
            "❌ Черновик не найден.",
            show_alert=True,
        )
        return

    edit_waiting.add(user_id)

    await callback.message.answer(
        "✏️ <b>Что изменить?</b>\n\n"
        "Напиши обычным текстом, например:\n\n"
        "• Сделай короче\n"
        "• Добавь заголовок\n"
        "• Убери эмодзи\n"
        "• Сделай более официально\n"
        "• Сделай интереснее\n"
        "• Добавь больше деталей"
    )

    await callback.answer()


# =========================
# ПЕРЕДЕЛАТЬ
# =========================

@router.callback_query(F.data == "news_rewrite")
async def rewrite_news(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    user_id = callback.from_user.id
    data = pending_news.get(user_id)

    if not data:
        await callback.answer(
            "❌ Черновик больше недоступен.",
            show_alert=True,
        )
        return

    await callback.answer("🔄 Переделываю...")

    try:
        result = await generate_news(
            data["original"]
            + "\n\n"
            "Сделай другой вариант этой новости. "
            "Полностью измени формулировки и структуру, "
            "но не меняй факты.",
            mode=data["mode"],
        )

        data["result"] = result

        await callback.message.edit_text(
            f"📰 <b>Новый вариант:</b>\n\n"
            f"{result}",
            reply_markup=news_keyboard(),
        )

    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка:\n<code>{e}</code>"
        )


# =========================
# НАЖАЛИ ОПУБЛИКОВАТЬ
# =========================

@router.callback_query(F.data == "news_publish")
async def publish_question(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    data = pending_news.get(callback.from_user.id)

    if not data:
        await callback.answer(
            "❌ Черновик не найден.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "📢 <b>Опубликовать этот пост?</b>\n\n"
        f"{data['result']}",
        reply_markup=publish_keyboard(),
    )

    await callback.answer()


# =========================
# ПОДТВЕРЖДЕНИЕ
# =========================

@router.callback_query(F.data == "publish_confirm")
async def publish_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    user_id = callback.from_user.id
    data = pending_news.get(user_id)

    if not data:
        await callback.answer(
            "❌ Черновик не найден.",
            show_alert=True,
        )
        return

    try:
        await callback.bot.send_message(
            chat_id=CHANNEL_ID,
            text=data["result"],
        )

        text = data["result"]

        del pending_news[user_id]

        await callback.message.edit_text(
            "✅ <b>Пост опубликован!</b>\n\n"
            f"{text}",
        )

        await callback.answer("Опубликовано!")

    except Exception as e:
        await callback.answer(
            "❌ Не удалось опубликовать.",
            show_alert=True,
        )

        await callback.message.answer(
            f"Ошибка:\n<code>{e}</code>"
        )


# =========================
# НАЗАД К ПОСТУ
# =========================

@router.callback_query(F.data == "publish_back")
async def publish_back(callback: CallbackQuery):
    data = pending_news.get(callback.from_user.id)

    if not data:
        await callback.answer(
            "❌ Черновик не найден.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        f"📰 <b>Готовый вариант:</b>\n\n"
        f"{data['result']}",
        reply_markup=news_keyboard(),
    )

    await callback.answer()


# =========================
# ОТМЕНА
# =========================

@router.callback_query(F.data == "news_cancel")
async def cancel_news(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    pending_news.pop(callback.from_user.id, None)
    edit_waiting.discard(callback.from_user.id)

    await callback.message.edit_text(
        "❌ Черновик удалён.\n\n"
        "Возвращаюсь в главное меню.",
        reply_markup=main_keyboard(),
    )

    await callback.answer("Отменено")


# =========================
# СТАТИСТИКА
# =========================

@router.callback_query(F.data == "statistics")
async def statistics(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        "Пока статистика не сохраняется в базе данных.\n\n"
        "Добавим её следующим этапом.",
        reply_markup=main_keyboard(),
    )

    await callback.answer()

# =========================
# МОНИТОРИНГ TELEGRAM
# =========================

@router.callback_query(F.data.startswith("monitor_take:"))
async def monitor_take(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён.",
            show_alert=True,
        )
        return

    news_id = callback.data.split(":", 1)[1]

    data = monitor_pending.get(news_id)

    if not data:
        await callback.answer(
            "❌ Эта новость уже недоступна.",
            show_alert=True,
        )
        return

    pending_news[callback.from_user.id] = {
        "original": data["original"],
        "result": data["result"],
        "mode": "normal",
    }

    del monitor_pending[news_id]

    await callback.message.edit_text(
        "📰 <b>Новость взята в работу</b>\n\n"
        f"{data['result']}",
        reply_markup=news_keyboard(),
    )

    await callback.answer("Готово")


@router.callback_query(F.data.startswith("monitor_skip:"))
async def monitor_skip(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(
            "⛔ Доступ запрещён.",
            show_alert=True,
        )
        return

    news_id = callback.data.split(":", 1)[1]

    if news_id in monitor_pending:
        del monitor_pending[news_id]

    await callback.message.edit_text(
        "❌ Новость пропущена."
    )

    await callback.answer("Пропущено")