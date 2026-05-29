"""Хендлер кнопки «🔓 Убрать знак — 50₽» под фото первой генерации."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.config import WATERMARK_UNLOCK_ID, get_package_by_id
from bot.handlers.payment import _poll_payment
from bot.keyboards.inline import get_payment_url_keyboard
from bot.services.user_limits import (
    cancel_payment,
    create_payment,
    has_pending_unlock_payment,
    has_unlocked_watermark,
    update_payment_provider_id,
)
from bot.services.watermark import get_clean_copy
from bot.services.yookassa_client import create_yookassa_payment

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "unlock_watermark")
async def handle_unlock_watermark(
    callback: CallbackQuery, bot: Bot
) -> None:
    """По кнопке под WM-фото: отдать чистое фото (если оплачено) или начать оплату 50₽."""
    await callback.answer()
    user_id = callback.from_user.id

    clean_bytes = get_clean_copy(user_id)
    if clean_bytes is None:
        await callback.message.answer("Чистая версия больше недоступна.")
        return

    # Уже оплачено ранее — отдаём бесплатно (идемпотентно)
    if has_unlocked_watermark(user_id):
        await callback.message.answer_photo(
            photo=BufferedInputFile(
                clean_bytes, filename="studio_portrait.jpg"
            ),
            caption="🎁 Готово! Вот твоё фото без водяного знака.",
        )
        return

    # Защита от двойного списания: уже есть незавершённый платёж — не создаём второй
    if has_pending_unlock_payment(user_id):
        await callback.message.answer(
            "💳 У тебя уже есть незавершённая оплата на 50 ₽ — заверши её 👆\n"
            "Чистое фото придёт автоматически после оплаты.\n"
            "Если ссылка потерялась — подожди пару минут и нажми кнопку снова."
        )
        return

    # Создаём платёж 50₽ и стартуем фоновую проверку статуса
    pkg = get_package_by_id(WATERMARK_UNLOCK_ID)
    internal_id = create_payment(
        user_id=user_id,
        package_id=pkg.id,
        credits=pkg.credits,
        amount=pkg.price_kopecks,
    )

    try:
        yookassa_id, payment_url = await create_yookassa_payment(
            amount_kopecks=pkg.price_kopecks,
            description="Фото без водяного знака",
            user_id=user_id,
            package_id=pkg.id,
            internal_payment_id=internal_id,
        )
    except Exception as e:
        logger.error(
            f"YooKassa unlock payment creation failed "
            f"for user {user_id}: {e}"
        )
        cancel_payment(internal_id)
        await callback.message.answer(
            "❌ Не удалось создать платёж.\nПопробуй ещё раз позже."
        )
        return

    update_payment_provider_id(internal_id, yookassa_id)

    await callback.message.answer(
        "💳 <b>Оплата 50 ₽</b> — фото без водяного знака.\n\n"
        "Нажми «Перейти к оплате», после оплаты — «Проверить оплату».\n"
        "Чистое фото придёт автоматически.",
        reply_markup=get_payment_url_keyboard(payment_url, internal_id),
    )

    logger.info(
        f"User {user_id}: unlock payment {internal_id} created, "
        f"YooKassa ID: {yookassa_id}"
    )

    asyncio.create_task(
        _poll_payment(bot, internal_id, yookassa_id, user_id, pkg)
    )
