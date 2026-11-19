"""Админский тест модели GPT Image 2 (/test_gpt).

Изолированный flow только для ADMIN_ID: gender → style → upload photo
→ короткий фиксированный промпт (build_prompt, без GPT-5.2) → kie.ai с моделью
`gpt-image-2-image-to-image` → результат. Не пишет в users.generations,
paid_credits, generations_log, ratings — чистый тест без побочных эффектов.
"""

import asyncio
import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramEntityTooLarge,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import (
    STYLE_LABELS,
    TEST_MODELS,
    TEST_MODELS_BY_KEY,
    build_prompt,
    build_test_model_input,
    fallback_outfit,
)
from bot.keyboards.inline import (
    get_test_gender_keyboard,
    get_test_models_keyboard,
    get_test_models_restart_keyboard,
    get_test_restart_keyboard,
    get_test_style_keyboard,
)
from bot.services.kie_client import KieClientError, kie_client
from bot.services.openai_client import openai_client
from bot.services.user_limits import is_admin
from bot.states.generation import AdminTestStates, ModelTestStates

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

        outfit = await openai_client.generate_outfit(gender, style)
        prompt = build_prompt(gender, style, outfit)
        logger.info(
            f"[test_gpt] outfit={'gpt' if outfit else 'fallback'} "
            f"prompt length={len(prompt)}"
        )

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


# --- /test_models: одно селфи → несколько моделей kie.ai параллельно ---
# Промпт тот же короткий (build_prompt). Ничего не пишет в БД.


@router.message(Command("test_models"))
async def cmd_test_models(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "🧪 Сравнение моделей\n\nВыбери пол:",
        reply_markup=get_test_gender_keyboard("tm"),
    )
    await state.set_state(ModelTestStates.selecting_gender)


@router.callback_query(F.data == "tm_restart")
async def tm_restart(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "🧪 Сравнение моделей\n\nВыбери пол:",
        reply_markup=get_test_gender_keyboard("tm"),
    )
    await state.set_state(ModelTestStates.selecting_gender)


@router.callback_query(
    F.data.startswith("tm_gender:"), ModelTestStates.selecting_gender
)
async def tm_select_gender(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    await callback.message.edit_text(
        f"🧪 Сравнение моделей · {_gender_text(gender)}\n\nВыбери стиль:",
        reply_markup=get_test_style_keyboard("tm"),
    )
    await state.set_state(ModelTestStates.selecting_style)


@router.callback_query(
    F.data.startswith("tm_style:"), ModelTestStates.selecting_style
)
async def tm_select_style(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    style = callback.data.split(":")[1]
    await state.update_data(style=style, models=[])
    await callback.message.edit_text(
        "🧪 Отметь модели для сравнения:",
        reply_markup=get_test_models_keyboard(set()),
    )
    await state.set_state(ModelTestStates.selecting_models)


@router.callback_query(
    F.data.startswith("tm_toggle:") | (F.data == "tm_all"),
    ModelTestStates.selecting_models,
)
async def tm_toggle_model(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await callback.answer()
    data = await state.get_data()
    selected = set(data.get("models", []))
    if callback.data == "tm_all":
        selected = {m.key for m in TEST_MODELS}
    else:
        selected ^= {callback.data.split(":")[1]}
    await state.update_data(models=sorted(selected))
    await callback.message.edit_reply_markup(
        reply_markup=get_test_models_keyboard(selected)
    )


@router.callback_query(F.data == "tm_done", ModelTestStates.selecting_models)
async def tm_models_done(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if not data.get("models"):
        await callback.answer("Отметь хотя бы одну модель", show_alert=True)
        return
    await callback.answer()
    labels = [
        TEST_MODELS_BY_KEY[k].label for k in data["models"]
        if k in TEST_MODELS_BY_KEY
    ]
    style_text = STYLE_LABELS.get(data.get("style"), data.get("style"))
    await callback.message.edit_text(
        f"🧪 {_gender_text(data.get('gender', 'male'))}, {style_text}\n"
        f"Модели: {', '.join(labels)}\n\nТеперь отправь фото."
    )
    await state.set_state(ModelTestStates.awaiting_photo)


async def _send_with_retry(send, attempts: int = 3):
    """Отправка в Telegram с ожиданием флуд-контроля.

    До 9 моделей заканчивают почти одновременно — Telegram может ответить
    429 retry_after. send — функция без аргументов, возвращающая корутину.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await send()
        except TelegramRetryAfter as e:
            if attempt == attempts:
                raise
            await asyncio.sleep(e.retry_after + 1)


async def _safe_answer(message: Message, text: str, **kwargs) -> None:
    """Текстовый ответ, который никогда не бросает (только лог)."""
    try:
        await _send_with_retry(lambda: message.answer(text, **kwargs))
    except Exception as e:
        logger.warning(f"[test_models] failed to send message: {e}")


async def _run_one_model(
    message: Message, test_model, image_url: str, prompt: str
) -> bool:
    """Генерирует одной моделью и сразу шлёт результат. True — успех.

    Никогда не бросает: иначе gather оборвал бы остальные модели.
    """
    started_at = time.monotonic()
    try:
        result_url, credits = await kie_client.transform_photo_with_model(
            test_model.model,
            build_test_model_input(test_model, image_url, prompt),
        )
        image = await kie_client.download_image(result_url)
    except Exception as e:
        elapsed = round(time.monotonic() - started_at)
        logger.warning(f"[test_models] {test_model.model} failed: {e}")
        await _safe_answer(
            message, f"🧪 {test_model.label} · {elapsed}с · ошибка: {e}"
        )
        return False

    elapsed = round(time.monotonic() - started_at)
    credits_text = f"{credits} кр." if credits is not None else "кр. ?"
    caption = f"🧪 {test_model.label} · {elapsed}с · {credits_text}"
    logger.info(
        f"[test_models] {test_model.model} ok {elapsed}s credits={credits}"
    )
    file = BufferedInputFile(image, filename=f"{test_model.key}.jpg")
    try:
        try:
            await _send_with_retry(
                lambda: message.answer_photo(photo=file, caption=caption)
            )
        except (TelegramBadRequest, TelegramEntityTooLarge):
            # Не подошло как фото (размер/пропорции) — шлём файлом
            await _send_with_retry(
                lambda: message.answer_document(document=file, caption=caption)
            )
    except Exception as e:
        # Генерация оплачена — не теряем результат, отдаём хотя бы ссылку
        logger.warning(f"[test_models] {test_model.model} delivery failed: {e}")
        await _safe_answer(
            message, f"{caption}\nНе удалось отправить фото, ссылка: {result_url}"
        )
    return True


@router.message(F.photo, ModelTestStates.awaiting_photo)
async def tm_handle_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.set_state(ModelTestStates.processing)
    data = await state.get_data()
    try:
        gender = data.get("gender", "male")
        style = data.get("style", "casual")
        models = [
            TEST_MODELS_BY_KEY[k] for k in data.get("models", [])
            if k in TEST_MODELS_BY_KEY
        ]
        # Один образ на весь прогон — иначе модели сравниваются нечестно
        outfit = await openai_client.generate_outfit(gender, style)
        outfit_text = (
            f"👕 Образ (GPT): {outfit}" if outfit
            else f"👕 Образ (запасной): {fallback_outfit(gender, style)}"
        )
        prompt = build_prompt(gender, style, outfit)

        file = await bot.get_file(message.photo[-1].file_id)
        image_url = (
            f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        )
        logger.info(
            f"[test_models] user={message.from_user.id} gender={gender} "
            f"style={style} models={[m.key for m in models]}"
        )
        await message.answer(
            f"🧪 Запустил {len(models)} моделей параллельно, результаты "
            "будут приходить по мере готовности (1–3 минуты).\n\n"
            f"{outfit_text}"
        )
        results = await asyncio.gather(
            *(_run_one_model(message, m, image_url, prompt) for m in models),
            return_exceptions=True,
        )
        await _safe_answer(
            message,
            f"🧪 Готово: {sum(r is True for r in results)} из {len(models)}.",
            reply_markup=get_test_models_restart_keyboard(),
        )
    except Exception as e:
        logger.exception(f"[test_models] unexpected error: {e}")
        await _safe_answer(
            message,
            f"🧪 Неожиданная ошибка: {e}",
            reply_markup=get_test_models_restart_keyboard(),
        )
    finally:
        # Чистим, только если админ за эти минуты не начал новый сценарий —
        # иначе сотрём его свежее состояние.
        if await state.get_state() == ModelTestStates.processing.state:
            await state.clear()


@router.message(ModelTestStates.processing)
async def tm_handle_while_processing(message: Message) -> None:
    """Перехватывает фото/текст во время прогона — иначе фото уйдёт
    в продовый catch-all photo.router и запустит обычное меню."""
    if not is_admin(message.from_user.id):
        return
    await message.answer("🧪 Подожди, модели ещё работают...")


@router.message(ModelTestStates.awaiting_photo)
async def tm_handle_not_photo(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("🧪 Жду фото для сравнения моделей.")
