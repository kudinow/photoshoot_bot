"""Хендлеры флоу оценки генераций (звёзды + текстовый фидбек)."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import (
    get_feedback_skip_keyboard,
    get_five_star_keyboard,
    get_rating_keyboard,
)
from bot.services.user_limits import (
    ADMIN_ID,
    get_last_generation_context,
    has_user_rated,
    mark_as_rated,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()

STYLE_LABELS_RU = {
    "business": "деловой",
    "casual": "кежуал",
    "creative": "креативный",
}

GENDER_LABELS_RU = {
    "male": "мужской",
    "female": "женский",
}


async def send_rating_request(bot: Bot, chat_id: int) -> None:
    """Отправляет пользователю запрос на оценку генерации."""
    try:
        await bot.send_message(
            chat_id,
            "Как тебе результат? Оцени от 1 до 5:",
            reply_markup=get_rating_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to send rating request to {chat_id}: {e}")


async def _send_rating_to_admin_stage1(
    bot: Bot,
    user_id: int,
    username: str | None,
    first_name: str | None,
    rating: int,
) -> None:
    """Отправляет админу оценку + оба фото (первый этап, сразу после клика по звезде).

    При rating == 5 админу ничего не отправляется (обрабатывается на уровне вызова).
    """
    if user_id == ADMIN_ID:
        # Не спамим админу его собственные оценки
        return

    ctx = get_last_generation_context(user_id)
    if not ctx:
        logger.error(f"No generation context for user {user_id}, cannot notify admin")
        return

    username_str = f"@{username}" if username else "(нет username)"
    name_str = first_name or ""
    gender_ru = GENDER_LABELS_RU.get(ctx["gender"], ctx["gender"] or "?")
    style_ru = STYLE_LABELS_RU.get(ctx["style"], ctx["style"] or "?")

    caption = (
        f"⭐ Новая оценка: {rating}/5\n"
        f"User: {user_id} ({username_str}) {name_str}\n"
        f"Пол: {gender_ru}, стиль: {style_ru}"
    )

    # Сообщение 1: оригинальное фото (по file_id)
    if ctx["photo_file_id"]:
        try:
            await bot.send_photo(
                ADMIN_ID,
                photo=ctx["photo_file_id"],
                caption=caption,
            )
        except Exception as e:
            logger.error(f"Failed to send original photo to admin: {e}")
            # Фолбэк: хотя бы текстовое сообщение с оценкой
            try:
                await bot.send_message(ADMIN_ID, caption)
            except Exception as e2:
                logger.error(f"Fallback send_message to admin also failed: {e2}")
    else:
        # Нет file_id — отправляем только текст
        try:
            await bot.send_message(ADMIN_ID, caption)
        except Exception as e:
            logger.error(f"Failed to send text notification to admin: {e}")

    # Сообщение 2: сгенерированный результат (по URL)
    if ctx["result_url"]:
        try:
            await bot.send_photo(
                ADMIN_ID,
                photo=ctx["result_url"],
                caption="Результат генерации",
            )
        except Exception as e:
            logger.error(f"Failed to send result photo to admin: {e}")


async def _send_feedback_text_to_admin(
    bot: Bot, user_id: int, feedback_text: str
) -> None:
    """Отправляет админу текст фидбека (второй этап)."""
    if user_id == ADMIN_ID:
        return
    try:
        await bot.send_message(
            ADMIN_ID,
            f"Фидбек от {user_id}:\n{feedback_text}",
        )
    except Exception as e:
        logger.error(f"Failed to send feedback text to admin: {e}")


@router.callback_query(F.data.startswith("rate:"))
async def handle_rating(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    """Обработчик клика по звезде оценки."""
    await callback.answer()
    user_id = callback.from_user.id
    try:
        rating = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        logger.warning(f"Invalid rating callback: {callback.data}")
        return

    if not 1 <= rating <= 5:
        logger.warning(f"Rating out of range: {rating}")
        return

    # Race guard: если юзер уже оценивал (например, быстро кликнул по двум
    # звёздам подряд), не обрабатываем второй клик — иначе админу прилетит
    # дублирующееся уведомление.
    if has_user_rated(user_id):
        logger.info(f"User {user_id} already rated, ignoring extra click")
        return

    # Помечаем юзера как оценившего (один раз в жизни)
    mark_as_rated(user_id)

    if rating == 5:
        # 5 звёзд — благодарим и предлагаем поделиться
        try:
            await callback.message.edit_text(
                "🎉 Рад, что понравилось!\n\n"
                "Поделись ботом с другом — и получишь бесплатную "
                "генерацию за его первое фото.",
                reply_markup=get_five_star_keyboard(),
            )
        except Exception as e:
            logger.error(f"Failed to edit message after 5-star: {e}")
        return

    # 1–4 звезды — отправляем админу сразу, запрашиваем текстовый фидбек
    await _send_rating_to_admin_stage1(
        bot=bot,
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        rating=rating,
    )

    try:
        await callback.message.edit_text(
            "Жаль, что не идеально 😔\n\n"
            "Расскажи, что можно улучшить? Напиши в ответ "
            "или нажми «Пропустить».",
            reply_markup=get_feedback_skip_keyboard(),
        )
    except Exception as e:
        logger.error(f"Failed to edit message after low rating: {e}")

    await state.set_state(GenerationStates.awaiting_feedback_text)


@router.message(GenerationStates.awaiting_feedback_text, F.text)
async def handle_feedback_text(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Обработчик текстового фидбека после низкой оценки."""
    user_id = message.from_user.id
    feedback = message.text or ""

    # Игнорим команды — пусть они обрабатываются своими хендлерами
    if feedback.startswith("/"):
        await state.clear()
        return

    await _send_feedback_text_to_admin(bot, user_id, feedback)
    await message.answer("Спасибо за фидбек! Мы учтем его в следующем апдейте")
    await state.clear()


@router.callback_query(
    F.data == "feedback_skip", GenerationStates.awaiting_feedback_text
)
async def handle_feedback_skip(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик кнопки 'Пропустить' на запросе текстового фидбека."""
    await callback.answer()
    try:
        await callback.message.edit_text("Ок, спасибо за оценку!")
    except Exception as e:
        logger.error(f"Failed to edit message on feedback skip: {e}")
    await state.clear()


@router.message(GenerationStates.awaiting_feedback_text)
async def handle_non_text_in_feedback_state(message: Message) -> None:
    """Ловит любое НЕ-текстовое сообщение в состоянии ожидания фидбека.

    Без этого хендлера (менее специфичного, чем F.text выше, но более
    специфичного, чем фолбэк photo.handle_photo_without_state без стейта)
    фото/стикеры/GIF'ы провалились бы в handle_photo_without_state и
    прерывали бы флоу фидбека. Явно просим пользователя написать текст
    или нажать Пропустить.
    """
    await message.answer(
        "Напиши, пожалуйста, текстом что можно улучшить, "
        "или нажми «Пропустить» под предыдущим сообщением."
    )
