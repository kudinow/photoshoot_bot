from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_gender_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора пола"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
                InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
            ]
        ]
    )


def get_restart_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для повторной генерации"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Создать ещё", callback_data="restart"),
            ]
        ]
    )
