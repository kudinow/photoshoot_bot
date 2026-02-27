"""Хендлеры рассылки сообщений (только для администратора)"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    get_broadcast_confirm_keyboard,
    get_segment_keyboard,
)
from bot.services.user_limits import (
    SEGMENT_LABELS,
    create_broadcast_log,
    finish_broadcast_log,
    get_segment_count,
    get_segment_user_ids,
    is_admin,
)
from bot.states.broadcast import BroadcastStates

logger = logging.getLogger(__name__)
router = Router()

_BROADCAST_BATCH_SIZE = 25
_BROADCAST_BATCH_DELAY = 1.0


# --- Команда /broadcast ---


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "Выберите сегмент для рассылки:",
        reply_markup=get_segment_keyboard(),
    )
    await state.set_state(BroadcastStates.choosing_segment)


# --- Выбор сегмента ---


@router.callback_query(
    F.data.startswith("segment:"),
    BroadcastStates.choosing_segment,
)
async def select_segment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    segment = callback.data.split(":")[1]

    if segment not in SEGMENT_LABELS:
        await callback.message.edit_text("Неизвестный сегмент.")
        await state.clear()
        return

    count = get_segment_count(segment)
    label = SEGMENT_LABELS[segment]

    if count == 0:
        await callback.message.edit_text(
            f"Сегмент <b>{label}</b> пуст — некому отправлять."
        )
        await state.clear()
        return

    await state.update_data(segment=segment)
    await callback.message.edit_text(
        f"Сегмент: <b>{label}</b> ({count} чел.)\n\n"
        "Введите текст сообщения (HTML-теги поддерживаются).\n"
        "Отправьте /cancel для отмены.",
    )
    await state.set_state(BroadcastStates.composing_message)


# --- Ввод текста сообщения ---


@router.message(BroadcastStates.composing_message, F.text)
async def compose_message(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    if message.text.startswith("/"):
        await state.clear()
        await message.answer("Рассылка отменена.")
        return

    text = message.text
    data = await state.get_data()
    segment = data["segment"]
    count = get_segment_count(segment)
    label = SEGMENT_LABELS[segment]

    await state.update_data(message_text=text)

    await message.answer(
        f"--- ПРЕДПРОСМОТР ---\n\n"
        f"Сегмент: <b>{label}</b> ({count} чел.)\n\n"
        f"{text}\n\n"
        f"--- КОНЕЦ ---",
        reply_markup=get_broadcast_confirm_keyboard(),
    )
    await state.set_state(BroadcastStates.confirming)


# --- Подтверждение и отправка ---


@router.callback_query(
    F.data == "broadcast_confirm",
    BroadcastStates.confirming,
)
async def confirm_broadcast(
    callback: CallbackQuery, state: FSMContext, bot: Bot,
) -> None:
    await callback.answer()
    data = await state.get_data()
    segment = data["segment"]
    text = data["message_text"]

    await callback.message.edit_text("Рассылка запущена...")
    await state.clear()

    asyncio.create_task(
        _run_broadcast(bot, callback.from_user.id, segment, text)
    )


# --- Отмена ---


@router.callback_query(F.data == "broadcast_cancel")
async def cancel_broadcast_callback(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")


# --- Фоновая отправка ---


async def _run_broadcast(
    bot: Bot,
    admin_id: int,
    segment: str,
    text: str,
) -> None:
    """Рассылает сообщение пользователям сегмента (фоновая задача)"""
    user_ids = get_segment_user_ids(segment)
    total = len(user_ids)
    sent = 0
    blocked = 0
    failed = 0

    broadcast_id = create_broadcast_log(segment, text, total)
    logger.info(
        f"Broadcast #{broadcast_id} started: segment={segment}, "
        f"total={total}"
    )

    for i in range(0, total, _BROADCAST_BATCH_SIZE):
        batch = user_ids[i : i + _BROADCAST_BATCH_SIZE]
        for user_id in batch:
            try:
                await bot.send_message(user_id, text)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    blocked += 1
                else:
                    failed += 1
                    logger.warning(f"Broadcast: bad request for {user_id}: {e}")
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast: error for {user_id}: {e}")

        if i + _BROADCAST_BATCH_SIZE < total:
            await asyncio.sleep(_BROADCAST_BATCH_DELAY)

    finish_broadcast_log(broadcast_id, sent, blocked, failed)
    logger.info(
        f"Broadcast #{broadcast_id} finished: "
        f"sent={sent}, blocked={blocked}, failed={failed}"
    )

    summary = (
        f"Рассылка завершена.\n\n"
        f"Всего адресатов: {total}\n"
        f"Отправлено: {sent}\n"
        f"Заблокировали бота: {blocked}\n"
        f"Ошибок: {failed}"
    )
    try:
        await bot.send_message(admin_id, summary)
    except Exception:
        logger.error("Failed to send broadcast summary to admin")
