import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import CREDIT_PACKAGES, get_package_by_id
from bot.keyboards.inline import (
    get_after_payment_keyboard,
    get_confirm_package_keyboard,
    get_gender_keyboard,
    get_packages_keyboard,
)
from bot.services.user_limits import (
    confirm_payment,
    create_payment,
    get_paid_credits,
    get_remaining_generations,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "buy_credits")
async def show_packages(callback: CallbackQuery) -> None:
    """Показывает доступные пакеты генераций"""
    await callback.answer()

    user_id = callback.from_user.id
    paid = get_paid_credits(user_id)

    text = "💳 <b>Пакеты генераций</b>\n\n"

    for pkg in CREDIT_PACKAGES:
        per_unit = pkg.price_rub / pkg.credits
        text += f"• <b>{pkg.label}</b> ({per_unit:.0f} ₽/шт)\n"

    if paid > 0:
        text += (
            f"\n📊 У тебя сейчас: {paid} оплаченных генераций"
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_packages_keyboard(),
    )


@router.callback_query(F.data.startswith("package:"))
async def select_package(callback: CallbackQuery) -> None:
    """Пользователь выбрал пакет — показываем подтверждение"""
    await callback.answer()

    package_id = callback.data.split(":")[1]
    pkg = get_package_by_id(package_id)

    if not pkg:
        await callback.message.edit_text(
            "Пакет не найден. Попробуй ещё раз."
        )
        return

    text = (
        f"📦 <b>Подтверждение покупки</b>\n\n"
        f"Пакет: <b>{pkg.credits} генераций</b>\n"
        f"Стоимость: <b>{pkg.price_rub} ₽</b>\n\n"
        f"Нажми «Оплатить» для продолжения."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_confirm_package_keyboard(package_id),
    )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(callback: CallbackQuery) -> None:
    """
    Подтверждение покупки.

    PLACEHOLDER: мгновенное подтверждение для тестирования.
    В Phase 2 здесь будет создание платежа в YooKassa
    и отправка ссылки на оплату.
    """
    await callback.answer()

    user_id = callback.from_user.id
    package_id = callback.data.split(":")[1]
    pkg = get_package_by_id(package_id)

    if not pkg:
        await callback.message.edit_text("Пакет не найден.")
        return

    # --- PLACEHOLDER: в Phase 2 заменить на YooKassa ---
    payment_id = create_payment(
        user_id=user_id,
        package_id=pkg.id,
        credits=pkg.credits,
        amount=pkg.price_kopecks,
    )
    success = confirm_payment(payment_id)
    # --- КОНЕЦ PLACEHOLDER ---

    if success:
        remaining = get_remaining_generations(user_id)
        text = (
            f"✅ <b>Оплата прошла успешно!</b>\n\n"
            f"Начислено: <b>{pkg.credits} генераций</b>\n"
            f"Доступно генераций: <b>{remaining}</b>\n\n"
            f"Теперь можешь создать профессиональный портрет!"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_after_payment_keyboard(),
        )
        logger.info(
            f"User {user_id} purchased {pkg.id} "
            f"({pkg.credits} credits for {pkg.price_rub} RUB)"
        )
    else:
        await callback.message.edit_text(
            "❌ Произошла ошибка при обработке платежа.\n"
            "Попробуй ещё раз или обратись в поддержку."
        )


@router.callback_query(F.data == "back_from_packages")
async def back_from_packages(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Возврат из экрана пакетов"""
    await callback.answer()

    await callback.message.edit_text(
        "Выбери стиль фотографии:",
        reply_markup=get_gender_keyboard(),
    )
    await state.set_state(GenerationStates.selecting_gender)
