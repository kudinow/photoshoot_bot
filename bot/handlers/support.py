"""Хендлеры внутрибот-поддержки (двусторонний диалог юзер ↔ админ).

Сессия хранится в БД (support_sessions). user_id зашит в текст/подпись
уведомления админу с маркером 🆘 — нативный Reply админа роутится обратно
парсингом id из reply_to_message. Маппинг-таблицы нет, переживает рестарт.
"""

from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.filters.base import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    get_support_admin_keyboard,
    get_support_invite_keyboard,
)
from bot.services.user_limits import (
    ADMIN_ID,
    close_support_session,
    is_admin,
    is_in_support_session,
    open_support_session,
)

logger = logging.getLogger(__name__)
router = Router()

# Маркер + якорь user_id в уведомлениях админу (для роутинга Reply)
_SUPPORT_MARKER = "🆘"
_UID_RE = re.compile(r"id\s+(\d+)")

_INVITE_TEXT = (
    "🆘 Опиши проблему одним или несколькими сообщениями — я передам в "
    "поддержку. Можно приложить скриншот.\n\n"
    "Когда закончишь — нажми «Завершить»."
)
_FIRST_ACK = "✅ Передал в поддержку, скоро отвечу."
_ACK_KEY = "support_acked"


class InSupportSession(Filter):
    """Пропускает сообщение, только если юзер в активной сессии поддержки."""

    async def __call__(self, message: Message) -> bool:
        if message.from_user is None:
            return False
        return is_in_support_session(message.from_user.id)


def _user_label(message: Message) -> str:
    user = message.from_user
    name = user.full_name or ""
    username = f" (@{user.username})" if user.username else ""
    return f"{name}{username}".strip()


async def _acked(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get(_ACK_KEY))


async def _set_acked(state: FSMContext, value: bool) -> None:
    await state.update_data(**{_ACK_KEY: value})


def _extract_uid(reply: Message | None) -> int | None:
    """Достаёт user_id из reply_to_message, только если это саппорт-уведомление."""
    if reply is None:
        return None
    body = reply.text or reply.caption or ""
    if _SUPPORT_MARKER not in body:
        return None
    m = _UID_RE.search(body)
    return int(m.group(1)) if m else None


# --- Вход в саппорт ---


async def _enter_support(message: Message, state: FSMContext, user_id: int) -> None:
    """Открывает сессию и показывает приглашение."""
    if is_admin(user_id):
        await message.answer("Ты админ — поддержка тебе не нужна 🙂")
        return
    await state.clear()
    open_support_session(user_id)
    await _set_acked(state, False)
    await message.answer(_INVITE_TEXT, reply_markup=get_support_invite_keyboard())


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext) -> None:
    await _enter_support(message, state, message.from_user.id)


@router.callback_query(F.data == "support_open")
async def open_support(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _enter_support(callback.message, state, callback.from_user.id)


# --- Юзер → админ (только в активной сессии) ---
# ВАЖНО: passthrough определён ДО support_user_text (порядок проверки хендлеров).


@router.message(InSupportSession(), F.text.startswith("/"))
async def support_command_passthrough(message: Message, state: FSMContext) -> None:
    """Команда внутри сессии → закрываем сессию и просим повторить команду."""
    close_support_session(message.from_user.id)
    await _set_acked(state, False)
    await message.answer(
        "Диалог с поддержкой завершён. Отправь команду ещё раз, чтобы продолжить."
    )


@router.message(InSupportSession(), F.text)
async def support_user_text(message: Message, bot: Bot, state: FSMContext) -> None:
    uid = message.from_user.id
    first = not await _acked(state)
    await bot.send_message(
        ADMIN_ID,
        f"{_SUPPORT_MARKER} <b>Поддержка</b>\n"
        f"От {_user_label(message)}, id <code>{uid}</code>:\n\n"
        f"{message.text}",
        reply_markup=get_support_admin_keyboard(uid),
    )
    if first:
        await _set_acked(state, True)
        await message.answer(_FIRST_ACK)


@router.message(InSupportSession(), F.photo)
async def support_user_photo(message: Message, bot: Bot, state: FSMContext) -> None:
    uid = message.from_user.id
    first = not await _acked(state)
    caption = message.caption or ""
    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=(
            f"{_SUPPORT_MARKER} <b>Поддержка</b>\n"
            f"От {_user_label(message)}, id <code>{uid}</code>:\n\n{caption}"
        ),
        reply_markup=get_support_admin_keyboard(uid),
    )
    if first:
        await _set_acked(state, True)
        await message.answer(_FIRST_ACK)


# --- Админ → юзер (нативный Reply на уведомление саппорта) ---


@router.message(F.from_user.id == ADMIN_ID, F.reply_to_message, F.text)
async def admin_reply_text(message: Message, bot: Bot) -> None:
    uid = _extract_uid(message.reply_to_message)
    if uid is None:
        return  # не саппорт-реплай — не трогаем
    if message.text.startswith("/"):
        return  # команды не пересылаем
    try:
        await bot.send_message(uid, f"💬 <b>Поддержка:</b>\n\n{message.text}")
        await message.answer("✅ Отправлено.")
    except TelegramForbiddenError:
        await message.answer(f"Пользователь {uid} заблокировал бота.")
    except Exception as e:
        await message.answer(f"Не удалось отправить: {e}")


@router.message(F.from_user.id == ADMIN_ID, F.reply_to_message, F.photo)
async def admin_reply_photo(message: Message, bot: Bot) -> None:
    uid = _extract_uid(message.reply_to_message)
    if uid is None:
        return
    caption = message.caption or ""
    try:
        await bot.send_photo(
            uid,
            message.photo[-1].file_id,
            caption=f"💬 <b>Поддержка:</b>\n\n{caption}" if caption else "💬 Поддержка",
        )
        await message.answer("✅ Отправлено.")
    except TelegramForbiddenError:
        await message.answer(f"Пользователь {uid} заблокировал бота.")
    except Exception as e:
        await message.answer(f"Не удалось отправить: {e}")


# --- Закрытие диалога ---


@router.callback_query(F.data == "support_close_user")
async def close_by_user(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    uid = callback.from_user.id
    close_support_session(uid)
    await callback.message.answer("Диалог завершён.")
    if not is_admin(uid):
        try:
            await bot.send_message(ADMIN_ID, f"Юзер {uid} закрыл диалог поддержки.")
        except Exception:
            pass


@router.callback_query(F.data.startswith("support_close:"))
async def close_by_admin(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    try:
        uid = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    close_support_session(uid)
    try:
        await bot.send_message(uid, "Диалог с поддержкой завершён. Спасибо! 🙏")
    except Exception:
        pass
    await callback.message.answer(f"Диалог с {uid} завершён.")
