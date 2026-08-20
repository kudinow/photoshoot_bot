"""Админские команды по чекам НПД: просмотр и добивка незакрытых."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.npd_receipts import retry_pending_receipts
from bot.services.npd_storage import get_unfinished_receipts
from bot.services.user_limits import is_admin

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("receipts_failed"))
async def cmd_receipts_failed(message: Message) -> None:
    """Список незакрытых чеков (только для админа)"""
    if not is_admin(message.from_user.id):
        return

    rows = get_unfinished_receipts()
    if not rows:
        await message.answer("✅ Незакрытых чеков нет.")
        return

    lines = [f"🧾 <b>Незакрытые чеки: {len(rows)}</b>\n"]
    for row in rows[:20]:
        lines.append(
            f"• Платёж {row['payment_id']} — "
            f"{row['amount'] / 100:.2f} ₽, "
            f"{row['status']}, попыток {row['attempts']}\n"
            f"  <i>{row['service_name']}</i>"
        )
    if len(rows) > 20:
        lines.append(f"\n…и ещё {len(rows) - 20}")
    lines.append("\nДобить: /receipts_retry")

    await message.answer("\n".join(lines))


@router.message(Command("receipts_retry"))
async def cmd_receipts_retry(message: Message, bot: Bot) -> None:
    """Принудительная добивка незакрытых чеков (только для админа)"""
    if not is_admin(message.from_user.id):
        return

    pending = len(get_unfinished_receipts())
    if not pending:
        await message.answer("✅ Незакрытых чеков нет.")
        return

    await message.answer(f"⏳ Пробую добить {pending} чеков...")
    healed = await retry_pending_receipts(bot)
    await message.answer(
        f"Готово: пробито {healed} из {pending}.\n"
        f"Остаток смотри в /receipts_failed"
    )
