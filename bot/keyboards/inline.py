from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import CREDIT_PACKAGES
from bot.services.user_limits import SEGMENT_LABELS, get_segment_count


def get_gender_keyboard(with_support: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура выбора пола (опционально с кнопкой поддержки)"""
    rows = [
        [
            InlineKeyboardButton(text="👨 Мужской", callback_data="gender:male"),
            InlineKeyboardButton(text="👩 Женский", callback_data="gender:female"),
        ]
    ]
    if with_support:
        rows.append([
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_open"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    has_last_photo: bool = False,
    has_credits: bool = True,
    has_watermarked: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура для повторной генерации"""
    buttons = []

    if has_watermarked:
        buttons.append([
            InlineKeyboardButton(text="🔓 Убрать знак — 50 ₽", callback_data="unlock_watermark"),
        ])

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

    buttons.append([
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_open"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_buy_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой покупки и реферальной ссылкой (когда лимит исчерпан)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Пригласить друга", callback_data="referral_link")],
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


def get_segment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора сегмента для рассылки"""
    buttons = []
    for segment_id, label in SEGMENT_LABELS.items():
        count = get_segment_count(segment_id)
        buttons.append([InlineKeyboardButton(
            text=f"{label} ({count})",
            callback_data=f"segment:{segment_id}",
        )])
    buttons.append([InlineKeyboardButton(
        text="Отмена",
        callback_data="broadcast_cancel",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Отправить",
                callback_data="broadcast_confirm",
            )],
            [InlineKeyboardButton(
                text="Отмена",
                callback_data="broadcast_cancel",
            )],
        ]
    )


def get_rating_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура оценки генерации (5 пронумерованных звёзд в один ряд)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1⭐", callback_data="rate:1"),
                InlineKeyboardButton(text="2⭐", callback_data="rate:2"),
                InlineKeyboardButton(text="3⭐", callback_data="rate:3"),
                InlineKeyboardButton(text="4⭐", callback_data="rate:4"),
                InlineKeyboardButton(text="5⭐", callback_data="rate:5"),
            ]
        ]
    )


def get_feedback_skip_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Пропустить' для пропуска текстового фидбека"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data="feedback_skip",
                )
            ]
        ]
    )


def get_test_gender_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора пола для админского теста GPT Image 2"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужской", callback_data="t_gender:male"),
                InlineKeyboardButton(text="👩 Женский", callback_data="t_gender:female"),
            ]
        ]
    )


def get_test_style_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора стиля для админского теста GPT Image 2"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👔 Деловой", callback_data="t_style:business")],
            [InlineKeyboardButton(text="👕 Кежуал", callback_data="t_style:casual")],
            [InlineKeyboardButton(text="🎨 Креативный", callback_data="t_style:creative")],
        ]
    )


def get_test_restart_keyboard() -> InlineKeyboardMarkup:
    """Кнопка повторного запуска теста GPT Image 2"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ещё тест", callback_data="test_gpt_restart")],
        ]
    )


def get_support_invite_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура приглашения в саппорт (кнопка завершения для юзера)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить диалог",
                callback_data="support_close_user",
            )]
        ]
    )


def get_support_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура под уведомлением саппорта у админа (завершить диалог с юзером)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ Завершить диалог",
                callback_data=f"support_close:{user_id}",
            )]
        ]
    )


def get_five_star_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после оценки 5 звёзд — предложение поделиться реферальной ссылкой.

    Переиспользует существующий callback 'referral_link' (см. bot/handlers/start.py).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Получить реферальную ссылку",
                    callback_data="referral_link",
                )
            ]
        ]
    )
