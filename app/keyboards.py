from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📰 Создать новость",
                    callback_data="create_news",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧠 Режим генерации",
                    callback_data="generation_mode",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="statistics",
                ),
            ],
        ]
    )


def generation_modes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📰 Обычная",
                    callback_data="mode_normal",
                ),
                InlineKeyboardButton(
                    text="📱 Короткая",
                    callback_data="mode_short",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Срочная",
                    callback_data="mode_urgent",
                ),
                InlineKeyboardButton(
                    text="📋 Подробная",
                    callback_data="mode_detailed",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_main",
                )
            ],
        ]
    )


def news_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Опубликовать",
                    callback_data="news_publish",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Переделать",
                    callback_data="news_rewrite",
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data="news_edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="news_cancel",
                )
            ],
        ]
    )


def publish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, опубликовать",
                    callback_data="publish_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="publish_back",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="news_cancel",
                ),
            ],
        ]
    )