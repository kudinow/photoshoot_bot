import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import get_gender_keyboard, get_restart_keyboard
from bot.services.user_limits import (
    can_generate,
    get_last_photo,
    get_remaining_generations,
    is_admin,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Обработчик команды /start"""
    await state.clear()

    user_id = message.from_user.id
    remaining = get_remaining_generations(user_id)

    # Формируем текст о лимите
    if is_admin(user_id):
        limit_text = "👑 У тебя безлимитный доступ."
    elif remaining > 0:
        limit_text = f"🎁 У тебя {remaining} бесплатных генераций."
    else:
        limit_text = "⚠️ Бесплатные генерации закончились."

    welcome_text = (
        "Привет! Я помогу превратить твоё фото "
        "в профессиональный студийный портрет.\n\n"
        "Как это работает:\n"
        "1. Выбери стиль (мужской или женский)\n"
        "2. Отправь своё фото\n"
        "3. Получи профессиональный портрет!\n\n"
        f"{limit_text}\n\n"
        "Выбери стиль фотографии:"
    )

    await message.answer(welcome_text, reply_markup=get_gender_keyboard())
    await state.set_state(GenerationStates.selecting_gender)


@router.callback_query(F.data == "restart")
async def restart_generation(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик кнопки 'Создать ещё'"""
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "Выбери стиль фотографии:",
        reply_markup=get_gender_keyboard(),
    )
    await state.set_state(GenerationStates.selecting_gender)


@router.callback_query(F.data == "regenerate")
async def regenerate_photo(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки 'Сгенерировать заново'"""
    await callback.answer()

    user_id = callback.from_user.id

    # Проверяем лимит генераций
    if not can_generate(user_id):
        await callback.message.answer(
            "К сожалению, ты использовал все 3 бесплатные генерации 😔\n\n"
            "Скоро появится возможность приобрести дополнительные генерации. "
            "Следи за обновлениями!"
        )
        await state.clear()
        return

    # Получаем последнюю фотографию
    photo_url, gender = get_last_photo(user_id)

    if not photo_url or not gender:
        await callback.message.answer(
            "У меня нет сохранённой фотографии. "
            "Пожалуйста, отправь новое фото.",
            reply_markup=get_gender_keyboard(),
        )
        await state.set_state(GenerationStates.selecting_gender)
        return

    # Импортируем здесь, чтобы избежать циклических импортов
    from aiogram.types import BufferedInputFile

    from bot.services.kie_client import KieClientError, kie_client
    from bot.services.openai_client import (
        OpenAIClientError,
        openai_client,
    )
    from bot.services.user_limits import increment_generations

    await state.set_state(GenerationStates.processing)

    # Показываем оставшиеся генерации
    remaining = get_remaining_generations(user_id)
    remaining_text = (
        "" if remaining == -1 else f"\n(Осталось генераций: {remaining - 1})"
    )

    # Отправляем сообщение о начале обработки
    processing_msg = await callback.message.answer(
        "Генерирую новый вариант твоей фотографии...\n"
        f"Это может занять 1-2 минуты.{remaining_text}"
    )

    try:
        logger.info(f"Regenerating for user {user_id}, gender: {gender}")

        # Генерируем новый промпт
        prompt = await openai_client.generate_prompt(gender)
        logger.info(
            f"Prompt generated for user {user_id}, length: {len(prompt)}"
        )

        # Отправляем в kie.ai и ждём результат
        result_url = await kie_client.transform_photo(
            image_url=photo_url,
            prompt=prompt,
        )

        # Скачиваем результат
        result_image = await kie_client.download_image(result_url)

        # Удаляем сообщение о обработке
        await processing_msg.delete()

        # Увеличиваем счётчик генераций
        increment_generations(user_id)

        # Формируем caption с информацией об оставшихся генерациях
        remaining_after = get_remaining_generations(user_id)
        if remaining_after == -1:
            caption = "Готово! Вот новый вариант твоего портрета."
        elif remaining_after > 0:
            caption = (
                f"Готово! Вот новый вариант твоего портрета.\n\n"
                f"📊 Осталось бесплатных генераций: {remaining_after}"
            )
        else:
            caption = (
                "Готово! Вот новый вариант твоего портрета.\n\n"
                "⚠️ Это была последняя бесплатная генерация.\n"
                "Скоро появится возможность приобрести дополнительные!"
            )

        # Отправляем результат
        await callback.message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="studio_portrait.jpg"
            ),
            caption=caption,
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

        logger.info(f"Successfully regenerated photo for user {user_id}")

    except OpenAIClientError as e:
        logger.error(f"OpenAI error for user {user_id}: {e}")
        await processing_msg.edit_text(
            "Ошибка генерации стиля. Попробуй ещё раз.",
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

    except KieClientError as e:
        logger.error(f"KieClient error for user {user_id}: {e}")
        await processing_msg.edit_text(
            "Произошла ошибка при обработке фото. Попробуй ещё раз.\n\n"
            f"Ошибка: {e}",
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

    except Exception as e:
        logger.exception(f"Unexpected error for user {user_id}: {e}")
        await processing_msg.edit_text(
            "Произошла неожиданная ошибка. Попробуй ещё раз позже.",
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

    finally:
        await state.clear()


@router.callback_query(
    F.data.startswith("gender:"), GenerationStates.selecting_gender
)
async def select_gender(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора пола"""
    await callback.answer()

    gender = callback.data.split(":")[1]  # male или female
    await state.update_data(gender=gender)

    gender_text = "мужской" if gender == "male" else "женский"
    await callback.message.edit_text(
        f"Отлично! Выбран {gender_text} стиль.\n\n"
        "Теперь отправь мне своё фото "
        "(лучше всего портретное, где хорошо видно лицо)."
    )
    await state.set_state(GenerationStates.awaiting_photo)
