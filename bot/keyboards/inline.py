from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import CREDIT_PACKAGES


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


def get_style_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора стиля одежды"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👔 Деловой", callback_data="style:business")],
            [InlineKeyboardButton(text="👕 Кежуал", callback_data="style:casual")],
            [InlineKeyboardButton(text="🎨 Креативный", callback_data="style:creative")],
        ]
    )


def get_restart_keyboard(
    has_last_photo: bool = False, has_credits: bool = True
) -> InlineKeyboardMarkup:
    """Клавиатура для повторной генерации"""
    buttons = []

    if has_last_photo:
        buttons.append([
            InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate"),
        ])

    buttons.append([
        InlineKeyboardButton(text="✨ Создать с новым фото", callback_data="restart"),
    ])

    if not has_credits:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить генерации", callback_data="buy_credits"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_buy_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой покупки (когда лимит исчерпан)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить генерации", callback_data="buy_credits")],
            [InlineKeyboardButton(text="✨ Создать с новым фото", callback_data="restart")],
        ]
    )


def get_packages_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора пакета генераций"""
    buttons = []
    for pkg in CREDIT_PACKAGES:
        buttons.append([
            InlineKeyboardButton(
                text=pkg.label,
                callback_data=f"package:{pkg.id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="« Назад", callback_data="back_from_packages"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirm_package_keyboard(package_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения покупки пакета"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Оплатить",
                callback_data=f"confirm_buy:{package_id}",
            )],
            [InlineKeyboardButton(
                text="« Выбрать другой пакет",
                callback_data="buy_credits",
            )],
        ]
    )


def get_payment_url_keyboard(
    payment_url: str, payment_id: int
) -> InlineKeyboardMarkup:
    """Клавиатура со ссылкой на оплату и кнопкой проверки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💳 Перейти к оплате",
                url=payment_url,
            )],
            [InlineKeyboardButton(
                text="✅ Проверить оплату",
                callback_data=f"check_payment:{payment_id}",
            )],
            [InlineKeyboardButton(
                text="« Отмена",
                callback_data="buy_credits",
            )],
        ]
    )


def get_after_payment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после успешной оплаты"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📸 Создать фото",
                callback_data="restart",
            )],
        ]
    )
