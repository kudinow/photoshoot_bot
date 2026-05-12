"""Админский тест модели GPT Image 2 (/test_gpt).

Изолированный flow только для ADMIN_ID: gender → style → upload photo
→ генерация промпта через GPT-5.2 (как в проде) → kie.ai с моделью
`gpt-image-2-image-to-image` → результат. Не пишет в users.generations,
paid_credits, generations_log, ratings — чистый тест без побочных эффектов.
"""

import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import STYLE_LABELS
from bot.keyboards.inline import (
    get_test_gender_keyboard,
    get_test_restart_keyboard,
    get_test_style_keyboard,
)
from bot.services.kie_client import KieClientError, kie_client
from bot.services.openai_client import OpenAIClientError, openai_client
from bot.services.user_limits import is_admin
from bot.states.generation import AdminTestStates

logger = logging.getLogger(__name__)

router = Router()


def _gender_text(gender: str) -> str:
    return "мужской" if gender == "male" else "женский"


@router.message(Command("test_gpt"))
async def cmd_test_gpt(message: Message, state: FSMContext) -> None:
    """Стартовая точка теста. Доступна только админу."""
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await message.answer(
        "🧪 Тест модели GPT Image 2\n\nВыбери пол:",
        reply_markup=get_test_gender_keyboard(),
    )
    await state.set_state(AdminTestStates.selecting_gender)


@router.callback_query(
    F.data.startswith("t_gender:"), AdminTestStates.selecting_gender
)
async def t_select_gender(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()

    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)

    await callback.message.edit_text(
        f"🧪 GPT Image 2 · Пол: {_gender_text(gender)}\n\nВыбери стиль:",
        reply_markup=get_test_style_keyboard(),
    )
    await state.set_state(AdminTestStates.selecting_style)


@router.callback_query(
    F.data.startswith("t_style:"), AdminTestStates.selecting_style
)
async def t_select_style(
    callback: CallbackQuery, state: FSMContext
) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()

    style = callback.data.split(":")[1]
    await state.update_data(style=style)

    data = await state.get_data()
    gender = data.get("gender", "male")
    style_text = STYLE_LABELS.get(style, style)

    await callback.message.edit_text(
        f"🧪 GPT Image 2 · {_gender_text(gender)}, {style_text}\n\n"
        "Теперь отправь фото."
    )
    await state.set_state(AdminTestStates.awaiting_photo)


@router.message(F.photo, AdminTestStates.awaiting_photo)
async def t_handle_photo(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    await state.set_state(AdminTestStates.processing)
    processing_msg = await message.answer(
        "🧪 Генерирую через GPT Image 2... Это может занять 1–3 минуты."
    )
    started_at = time.monotonic()

    try:
        data = await state.get_data()
        gender = data.get("gender", "male")
        style = data.get("style", "casual")

        logger.info(
            f"[test_gpt] user={message.from_user.id} "
            f"gender={gender} style={style}"
        )

        prompt = await openai_client.generate_prompt(gender, style)
        logger.info(f"[test_gpt] prompt length={len(prompt)}")

        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = (
            f"https://api.telegram.org/file/bot"
            f"{bot.token}/{file.file_path}"
        )

        result_url = await kie_client.transform_photo_gpt_image_2(
            image_url=file_url,
            prompt=prompt,
        )
        result_image = await kie_client.download_image(result_url)

        elapsed = round(time.monotonic() - started_at)
        await processing_msg.delete()

        style_text = STYLE_LABELS.get(style, style)
        caption = (
            f"🧪 GPT Image 2 · {_gender_text(gender)} · "
            f"{style_text} · {elapsed}с"
        )
        await message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="gpt_image_2_test.jpg"
            ),
            caption=caption,
            reply_markup=get_test_restart_keyboard(),
        )
        logger.info(
            f"[test_gpt] success user={message.from_user.id} "
            f"elapsed={elapsed}s"
        )

    except OpenAIClientError as e:
        logger.error(f"[test_gpt] OpenAI error: {e}")
        await processing_msg.edit_text(
            f"🧪 Ошибка генерации промпта: {e}",
            reply_markup=get_test_restart_keyboard(),
        )
    except KieClientError as e:
        logger.error(f"[test_gpt] Kie error: {e}")
        await processing_msg.edit_text(
            f"🧪 Ошибка kie.ai: {e}",
            reply_markup=get_test_restart_keyboard(),
        )
    except Exception as e:
        logger.exception(f"[test_gpt] unexpected error: {e}")
        await processing_msg.edit_text(
            f"🧪 Неожиданная ошибка: {e}",
            reply_markup=get_test_restart_keyboard(),
        )
    finally:
        await state.clear()


@router.callback_query(F.data == "test_gpt_restart")
async def t_restart(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()

    await state.clear()
    await callback.message.answer(
        "🧪 Тест модели GPT Image 2\n\nВыбери пол:",
        reply_markup=get_test_gender_keyboard(),
    )
    await state.set_state(AdminTestStates.selecting_gender)


@router.message(AdminTestStates.awaiting_photo)
async def t_handle_not_photo(message: Message) -> None:
    """Catch-all для не-фото в режиме ожидания фото (только админ)."""
    if not is_admin(message.from_user.id):
        return
    await message.answer("🧪 Жду фото для теста GPT Image 2.")


@router.message(AdminTestStates.processing)
async def t_handle_while_processing(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("🧪 Подожди, обрабатываю предыдущий тест...")
