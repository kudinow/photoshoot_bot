import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import CREDIT_PACKAGES, get_package_by_id
from bot.keyboards.inline import (
    get_after_payment_keyboard,
    get_confirm_package_keyboard,
    get_gender_keyboard,
    get_packages_keyboard,
    get_payment_url_keyboard,
)
from bot.services.user_limits import (
    cancel_payment,
    confirm_payment,
    create_payment,
    get_paid_credits,
    get_payment,
    get_remaining_generations,
    update_payment_provider_id,
)
from bot.services.yookassa_client import (
    check_yookassa_payment,
    create_yookassa_payment,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()

# Интервал и макс. время polling статуса платежа
_POLL_INTERVAL = 15  # секунд
_POLL_MAX_DURATION = 15 * 60  # 15 минут


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

    # Если кнопка была на сообщении с фото — edit_text невозможен,
    # отправляем новое сообщение
    if callback.message.photo:
        await callback.message.answer(
            text,
            reply_markup=get_packages_keyboard(),
        )
    else:
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
async def confirm_buy(
    callback: CallbackQuery, bot: Bot
) -> None:
    """
    Подтверждение покупки — создаёт платёж в YooKassa
    и отправляет ссылку на оплату.
    """
    await callback.answer()

    user_id = callback.from_user.id
    package_id = callback.data.split(":")[1]
    pkg = get_package_by_id(package_id)

    if not pkg:
        await callback.message.edit_text("Пакет не найден.")
        return

    # Создаём запись в нашей БД
    internal_id = create_payment(
        user_id=user_id,
        package_id=pkg.id,
        credits=pkg.credits,
        amount=pkg.price_kopecks,
    )

    # Создаём платёж в YooKassa
    try:
        yookassa_id, payment_url = await create_yookassa_payment(
            amount_kopecks=pkg.price_kopecks,
            description=f"{pkg.credits} генераций фото",
            user_id=user_id,
            package_id=pkg.id,
            internal_payment_id=internal_id,
        )
    except Exception as e:
        logger.error(
            f"YooKassa payment creation failed "
            f"for user {user_id}: {e}"
        )
        cancel_payment(internal_id)
        await callback.message.edit_text(
            "❌ Не удалось создать платёж.\n"
            "Попробуй ещё раз позже."
        )
        return

    # Сохраняем ID платежа YooKassa
    update_payment_provider_id(internal_id, yookassa_id)

    text = (
        f"💳 <b>Оплата</b>\n\n"
        f"Пакет: <b>{pkg.credits} генераций</b>\n"
        f"Сумма: <b>{pkg.price_rub} ₽</b>\n\n"
        f"Нажми кнопку ниже, чтобы перейти к оплате.\n"
        f"После оплаты нажми «Проверить оплату»."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_payment_url_keyboard(
            payment_url, internal_id
        ),
    )

    logger.info(
        f"User {user_id}: payment {internal_id} created, "
        f"YooKassa ID: {yookassa_id}"
    )

    # Запускаем фоновую проверку статуса
    asyncio.create_task(
        _poll_payment(bot, internal_id, yookassa_id, user_id, pkg)
    )


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment_status(callback: CallbackQuery) -> None:
    """Ручная проверка статуса платежа по кнопке"""
    await callback.answer("Проверяю статус оплаты...")

    internal_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    payment = get_payment(internal_id)

    if not payment:
        await callback.message.edit_text(
            "❌ Платёж не найден."
        )
        return

    if payment["status"] == "confirmed":
        # Уже подтверждён (возможно фоновым polling)
        remaining = get_remaining_generations(user_id)
        await callback.message.edit_text(
            f"✅ <b>Оплата уже подтверждена!</b>\n\n"
            f"Доступно генераций: <b>{remaining}</b>",
            reply_markup=get_after_payment_keyboard(),
        )
        return

    if payment["status"] != "pending":
        await callback.message.edit_text(
            "❌ Платёж отменён или истёк.\n"
            "Попробуй оформить новый.",
            reply_markup=get_packages_keyboard(),
        )
        return

    yookassa_id = payment["payment_provider_id"]
    if not yookassa_id:
        await callback.message.edit_text(
            "❌ Ошибка: платёж не привязан к YooKassa."
        )
        return

    # Проверяем статус в YooKassa
    try:
        status = await check_yookassa_payment(yookassa_id)
    except Exception as e:
        logger.error(f"YooKassa check failed: {e}")
        await callback.answer(
            "Не удалось проверить статус. "
            "Попробуй через минуту.",
            show_alert=True,
        )
        return

    pkg = get_package_by_id(payment["package_id"])

    if status == "succeeded":
        success = confirm_payment(internal_id)
        if success and pkg:
            remaining = get_remaining_generations(user_id)
            await callback.message.edit_text(
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Начислено: <b>{pkg.credits} генераций</b>\n"
                f"Доступно генераций: "
                f"<b>{remaining}</b>\n\n"
                f"Теперь можешь создать "
                f"профессиональный портрет!",
                reply_markup=get_after_payment_keyboard(),
            )
            logger.info(
                f"User {user_id}: manual check confirmed "
                f"payment {internal_id}"
            )
    elif status == "canceled":
        cancel_payment(internal_id)
        await callback.message.edit_text(
            "❌ Платёж был отменён.\n"
            "Можешь попробовать ещё раз.",
            reply_markup=get_packages_keyboard(),
        )
    else:
        # pending / waiting_for_capture
        await callback.answer(
            "Оплата ещё не поступила. "
            "Заверши оплату и нажми кнопку снова.",
            show_alert=True,
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


async def _poll_payment(
    bot: Bot,
    internal_id: int,
    yookassa_id: str,
    user_id: int,
    pkg,
) -> None:
    """
    Фоновая задача: периодически проверяет статус платежа
    в YooKassa и при успехе зачисляет кредиты.
    """
    elapsed = 0

    while elapsed < _POLL_MAX_DURATION:
        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

        # Проверяем, не подтверждён ли уже (вручную)
        payment = get_payment(internal_id)
        if not payment or payment["status"] != "pending":
            logger.debug(
                f"Poll: payment {internal_id} "
                f"is no longer pending, stopping"
            )
            return

        try:
            status = await check_yookassa_payment(yookassa_id)
        except Exception as e:
            logger.warning(
                f"Poll: YooKassa check error "
                f"for {yookassa_id}: {e}"
            )
            continue

        if status == "succeeded":
            success = confirm_payment(internal_id)
            if success:
                remaining = get_remaining_generations(user_id)
                try:
                    await bot.send_message(
                        user_id,
                        f"✅ <b>Оплата прошла успешно!</b>"
                        f"\n\n"
                        f"Начислено: "
                        f"<b>{pkg.credits} генераций</b>\n"
                        f"Доступно генераций: "
                        f"<b>{remaining}</b>\n\n"
                        f"Нажми кнопку ниже, чтобы "
                        f"создать фото!",
                        reply_markup=(
                            get_after_payment_keyboard()
                        ),
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to notify user "
                        f"{user_id}: {e}"
                    )
                logger.info(
                    f"Poll: payment {internal_id} "
                    f"confirmed for user {user_id}"
                )
            return

        if status == "canceled":
            cancel_payment(internal_id)
            try:
                await bot.send_message(
                    user_id,
                    "❌ Платёж был отменён.\n"
                    "Можешь попробовать ещё раз.",
                    reply_markup=get_packages_keyboard(),
                )
            except Exception as e:
                logger.error(
                    f"Failed to notify user "
                    f"{user_id}: {e}"
                )
            return

    # Таймаут — помечаем как отменённый
    payment = get_payment(internal_id)
    if payment and payment["status"] == "pending":
        cancel_payment(internal_id)
        logger.info(
            f"Poll: payment {internal_id} timed out "
            f"after {_POLL_MAX_DURATION}s"
        )
