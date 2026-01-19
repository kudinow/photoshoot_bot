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


def get_restart_keyboard(has_last_photo: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для повторной генерации"""
    buttons = []

    if has_last_photo:
        buttons.append([
            InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate"),
        ])

    buttons.append([
        InlineKeyboardButton(text="✨ Создать с новым фото", callback_data="restart"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
