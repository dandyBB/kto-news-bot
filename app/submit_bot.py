import asyncio
from uuid import uuid4

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from app.config import (
    ADMIN_ID,
    CHANNEL_ID,
    BOT_TOKEN,
    SUBMIT_BOT_TOKEN,
)
from app.ai import generate_news


# =========================================================
# БОТЫ
# =========================================================

submit_bot = Bot(token=SUBMIT_BOT_TOKEN)
main_bot = Bot(token=BOT_TOKEN)

submit_dp = Dispatcher()


# =========================================================
# ХРАНИЛИЩЕ
# =========================================================

pending_submissions = {}
pending_news = {}
edit_waiting = set()


# =========================================================
# КНОПКИ
# =========================================================

def moderation_keyboard(submission_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Взяти в роботу",
                    callback_data=f"submit_take:{submission_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Відхилити",
                    callback_data=f"submit_reject:{submission_id}",
                ),
            ]
        ]
    )


def news_keyboard():
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


def publish_keyboard():
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


# =========================================================
# ИМЯ ПОЛЬЗОВАТЕЛЯ
# =========================================================

def user_name(message: Message) -> str:
    user = message.from_user

    if not user:
        return "Невідомий користувач"

    if user.username:
        return f"@{user.username}"

    return user.full_name


# =========================================================
# START
# =========================================================

@submit_dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "📰 <b>Надіслати новину</b>\n\n"
        "Надішліть мені новину, фото або відео.\n\n"
        "Ми перевіримо інформацію та передамо її "
        "редактору."
    )


# =========================================================
# ПРИЁМ НОВОСТИ
# =========================================================

@submit_dp.message()
async def receive_news(message: Message):
    submission_id = uuid4().hex[:12]

    text = message.text or message.caption or ""

    submission = {
        "id": submission_id,
        "user_id": (
            message.from_user.id
            if message.from_user
            else 0
        ),
        "username": user_name(message),
        "text": text.strip(),
        "photo": None,
        "video": None,
        "document": None,
    }

    if message.photo:
        submission["photo"] = message.photo[-1].file_id

    if message.video:
        submission["video"] = message.video.file_id

    if message.document:
        submission["document"] = message.document.file_id

    pending_submissions[submission_id] = submission

    admin_text = (
        "📨 <b>НОВА НОВИНА</b>\n\n"
        f"👤 <b>Відправник:</b> "
        f"{submission['username']}\n"
        f"🆔 <b>ID:</b> "
        f"{submission['user_id']}\n\n"
    )

    if submission["text"]:
        admin_text += (
            "📝 <b>Повідомлення:</b>\n"
            f"{submission['text']}\n\n"
        )
    else:
        admin_text += (
            "📝 <b>Повідомлення:</b> "
            "без тексту\n\n"
        )

    admin_text += "Що зробити з цією новиною?"

    keyboard = moderation_keyboard(submission_id)

    try:
        if submission["photo"]:
            await submit_bot.send_photo(
                chat_id=ADMIN_ID,
                photo=submission["photo"],
                caption=admin_text,
                reply_markup=keyboard,
            )

        elif submission["video"]:
            await submit_bot.send_video(
                chat_id=ADMIN_ID,
                video=submission["video"],
                caption=admin_text,
                reply_markup=keyboard,
            )

        elif submission["document"]:
            await submit_bot.send_document(
                chat_id=ADMIN_ID,
                document=submission["document"],
                caption=admin_text,
                reply_markup=keyboard,
            )

        else:
            await submit_bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=keyboard,
            )

        await message.answer(
            "✅ <b>Новину отримано!</b>\n\n"
            "Дякуємо. Вона передана редактору."
        )

    except Exception as e:
        pending_submissions.pop(
            submission_id,
            None,
        )

        await message.answer(
            "❌ Не вдалося передати новину редактору."
        )

        print(
            f"[SUBMIT] Ошибка отправки админу: {e}"
        )


# =========================================================
# ОТКЛОНИТЬ
# =========================================================

@submit_dp.callback_query(
    F.data.startswith("submit_reject:")
)
async def reject_submission(callback: CallbackQuery):
    submission_id = callback.data.split(":", 1)[1]

    submission = pending_submissions.pop(
        submission_id,
        None,
    )

    if not submission:
        await callback.answer(
            "❌ Ця заявка вже оброблена.",
            show_alert=True,
        )
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.answer("Новину відхилено.")

    try:
        await submit_bot.send_message(
            chat_id=submission["user_id"],
            text=(
                "❌ <b>Вашу новину не було прийнято.</b>\n\n"
                "Дякуємо за повідомлення."
            ),
        )
    except Exception:
        pass


# =========================================================
# ВЗЯТЬ В РАБОТУ
# =========================================================

@submit_dp.callback_query(
    F.data.startswith("submit_take:")
)
async def take_submission(callback: CallbackQuery):
    submission_id = callback.data.split(":", 1)[1]

    submission = pending_submissions.pop(
        submission_id,
        None,
    )

    if not submission:
        await callback.answer(
            "❌ Ця заявка вже оброблена.",
            show_alert=True,
        )
        return

    await callback.answer(
        "🧠 Передаю нейромережі..."
    )

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    source_text = submission["text"]

    if not source_text:
        await callback.message.answer(
            "❌ У повідомленні немає тексту.\n\n"
            "Фото та відео без опису поки "
            "потрібно обробляти вручну."
        )
        return

    wait_message = await callback.message.answer(
        "🤖 <b>Нейромережа обробляє новину...</b>"
    )

    try:
        result = await generate_news(
            source_text,
            mode="normal",
        )

        user_id = callback.from_user.id

        pending_news[user_id] = {
            "original": source_text,
            "result": result,
            "mode": "normal",
            "source_user_id": submission["user_id"],
            "source_username": submission["username"],
        }

        await wait_message.edit_text(
            "📰 <b>Готовий варіант:</b>\n\n"
            f"{result}",
            reply_markup=news_keyboard(),
        )

    except Exception as e:
        await wait_message.edit_text(
            "❌ <b>Помилка нейромережі:</b>\n\n"
            f"<code>{e}</code>"
        )

        print(
            f"[SUBMIT] Gemini error: {e}"
        )


# =========================================================
# ПЕРЕДЕЛАТЬ
# =========================================================

@submit_dp.callback_query(
    F.data == "submit_rewrite"
)
async def rewrite_news(callback: CallbackQuery):
    user_id = callback.from_user.id

    data = pending_news.get(user_id)

    if not data:
        await callback.answer(
            "❌ Чернетку не знайдено.",
            show_alert=True,
        )
        return

    await callback.answer(
        "🔄 Переделываю..."
    )

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
            "📰 <b>Новий варіант:</b>\n\n"
            f"{result}",
            reply_markup=news_keyboard(),
        )

    except Exception as e:
        await callback.message.answer(
            f"❌ Помилка:\n<code>{e}</code>"
        )


# =========================================================
# ИЗМЕНИТЬ
# =========================================================

@submit_dp.callback_query(
    F.data == "submit_edit"
)
async def edit_news(callback: CallbackQuery):
    user_id = callback.from_user.id

    if user_id not in pending_news:
        await callback.answer(
            "❌ Чернетку не знайдено.",
            show_alert=True,
        )
        return

    edit_waiting.add(user_id)

    await callback.message.answer(
        "✏️ <b>Що змінити?</b>\n\n"
        "Напиши звичайним текстом, наприклад:\n\n"
        "• Зроби коротше\n"
        "• Додай заголовок\n"
        "• Прибери емодзі\n"
        "• Зроби офіційніше\n"
        "• Зроби цікавіше\n"
        "• Додай більше деталей"
    )

    await callback.answer()


# =========================================================
# ТЕКСТ РЕДАКТИРОВАНИЯ
# =========================================================

@submit_dp.message(F.text)
async def edit_text(message: Message):
    user_id = message.from_user.id

    if user_id not in edit_waiting:
        return

    edit_waiting.remove(user_id)

    data = pending_news.get(user_id)

    if not data:
        await message.answer(
            "❌ Чернетку не знайдено."
        )
        return

    wait_message = await message.answer(
        "✏️ Застосовую зміни..."
    )

    try:
        result = await generate_news(
            data["original"],
            mode=data["mode"],
            edit_request=message.text,
        )

        data["result"] = result

        await wait_message.edit_text(
            "📰 <b>Оновлений варіант:</b>\n\n"
            f"{result}",
            reply_markup=news_keyboard(),
        )

    except Exception as e:
        await wait_message.edit_text(
            f"❌ Помилка:\n<code>{e}</code>"
        )


# =========================================================
# ОПУБЛИКОВАТЬ
# =========================================================

@submit_dp.callback_query(
    F.data == "submit_publish"
)
async def publish_question(callback: CallbackQuery):
    user_id = callback.from_user.id

    data = pending_news.get(user_id)

    if not data:
        await callback.answer(
            "❌ Чернетку не знайдено.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "📢 <b>Опублікувати цей пост?</b>\n\n"
        f"{data['result']}",
        reply_markup=publish_keyboard(),
    )

    await callback.answer()


# =========================================================
# ПОДТВЕРЖДЕНИЕ ПУБЛИКАЦИИ
# =========================================================

@submit_dp.callback_query(
    F.data == "submit_publish_confirm"
)
async def publish_confirm(callback: CallbackQuery):
    user_id = callback.from_user.id

    data = pending_news.get(user_id)

    if not data:
        await callback.answer(
            "❌ Чернетку не знайдено.",
            show_alert=True,
        )
        return

    try:
        await main_bot.send_message(
            chat_id=CHANNEL_ID,
            text=data["result"],
        )

        text = data["result"]

        del pending_news[user_id]

        await callback.message.edit_text(
            "✅ <b>Пост опубліковано!</b>\n\n"
            f"{text}"
        )

        await callback.answer(
            "Опубліковано!"
        )

    except Exception as e:
        await callback.answer(
            "❌ Не вдалося опублікувати.",
            show_alert=True,
        )

        await callback.message.answer(
            f"Помилка:\n<code>{e}</code>"
        )


# =========================================================
# НАЗАД
# =========================================================

@submit_dp.callback_query(
    F.data == "submit_publish_back"
)
async def publish_back(callback: CallbackQuery):
    user_id = callback.from_user.id

    data = pending_news.get(user_id)

    if not data:
        await callback.answer(
            "❌ Чернетку не знайдено.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "📰 <b>Готовий варіант:</b>\n\n"
        f"{data['result']}",
        reply_markup=news_keyboard(),
    )

    await callback.answer()


# =========================================================
# ОТМЕНА
# =========================================================

@submit_dp.callback_query(
    F.data == "submit_cancel"
)
async def cancel_news(callback: CallbackQuery):
    user_id = callback.from_user.id

    pending_news.pop(user_id, None)
    edit_waiting.discard(user_id)

    await callback.message.edit_text(
        "❌ <b>Чернетку видалено.</b>"
    )

    await callback.answer(
        "Скасовано"
    )


# =========================================================
# ЗАПУСК
# =========================================================

async def start_submit_bot():
    print(
        "[SUBMIT] Бот приёма новостей запускается..."
    )

    try:
        await submit_dp.start_polling(
            submit_bot,
            allowed_updates=(
                submit_dp.resolve_used_update_types()
            ),
        )
    finally:
        await submit_bot.session.close()
        await main_bot.session.close()