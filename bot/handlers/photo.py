import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from bot.keyboards.inline import get_restart_keyboard
from bot.services.kie_client import KieClientError, kie_client
from bot.services.openai_client import OpenAIClientError, openai_client
from bot.services.user_limits import (
    can_generate,
    get_last_photo,
    get_remaining_generations,
    increment_generations,
    save_last_photo,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.photo, GenerationStates.awaiting_photo)
async def handle_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    """Обработчик получения фото"""
    user_id = message.from_user.id

    # Проверяем лимит генераций
    if not can_generate(user_id):
        await message.answer(
            "К сожалению, бесплатная генерация уже использована 😔\n\n"
            "Скоро появится возможность приобрести дополнительные генерации. "
            "Следи за обновлениями!"
        )
        await state.clear()
        return

    await state.set_state(GenerationStates.processing)

    # Показываем оставшиеся генерации
    remaining = get_remaining_generations(user_id)
    remaining_text = (
        ""
        if remaining == -1
        else f"\n(Осталось генераций: {remaining - 1})"
    )

    # Отправляем сообщение о начале обработки
    processing_msg = await message.answer(
        "Фото получено! Создаю профессиональный портрет...\n"
        f"Это может занять 1-2 минуты.{remaining_text}"
    )

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        gender = data.get("gender", "male")

        logger.info(
            f"Starting generation for user {user_id}, gender: {gender}"
        )

        # Генерируем промпт через OpenAI
        logger.info(f"Generating prompt for user {user_id}...")
        prompt = await openai_client.generate_prompt(gender)
        logger.info(
            f"Prompt generated for user {user_id}, length: {len(prompt)}"
        )

        # Получаем файл фото (берём самое большое разрешение)
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)

        # Формируем URL для Telegram файла
        file_url = (
            f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        )

        logger.info(
            f"Processing photo for user {user_id}, "
            f"file_path: {file.file_path}"
        )

        # Отправляем в kie.ai и ждём результат
        result_url = await kie_client.transform_photo(
            image_url=file_url,
            prompt=prompt,
        )

        # Скачиваем результат
        result_image = await kie_client.download_image(result_url)

        # Удаляем сообщение о обработке
        await processing_msg.delete()

        # Увеличиваем счётчик генераций
        increment_generations(user_id)

        # Сохраняем URL фото и пол для возможности регенерации
        save_last_photo(user_id, file_url, gender)

        # Формируем caption с информацией об оставшихся генерациях
        remaining_after = get_remaining_generations(user_id)
        if remaining_after == -1:
            caption = "Готово! Вот твой профессиональный портрет."
        elif remaining_after > 0:
            caption = (
                f"Готово! Вот твой профессиональный портрет.\n\n"
                f"📊 Осталось бесплатных генераций: {remaining_after}"
            )
        else:
            caption = (
                "Готово! Вот твой профессиональный портрет.\n\n"
                "⚠️ Это была последняя бесплатная генерация.\n"
                "Скоро появится возможность приобрести дополнительные!"
            )

        # Отправляем результат
        await message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="studio_portrait.jpg"
            ),
            caption=caption,
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

        logger.info(
            f"Successfully generated photo for user {user_id}"
        )

    except OpenAIClientError as e:
        logger.error(
            f"OpenAI error for user {message.from_user.id}: {e}"
        )
        await processing_msg.edit_text(
            "Ошибка генерации стиля. Попробуй ещё раз.",
            reply_markup=get_restart_keyboard(),
        )

    except KieClientError as e:
        logger.error(
            f"KieClient error for user {message.from_user.id}: {e}"
        )
        await processing_msg.edit_text(
            "Произошла ошибка при обработке фото. Попробуй ещё раз.\n\n"
            f"Ошибка: {e}",
            reply_markup=get_restart_keyboard(),
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error for user {message.from_user.id}: {e}"
        )
        await processing_msg.edit_text(
            "Произошла неожиданная ошибка. Попробуй ещё раз позже.",
            reply_markup=get_restart_keyboard(),
        )

    finally:
        await state.clear()


@router.message(F.photo)
async def handle_photo_without_state(
    message: Message, state: FSMContext
) -> None:
    """Обработчик фото без выбранного стиля"""
    from bot.keyboards.inline import get_gender_keyboard

    await message.answer(
        "Сначала выбери стиль фотографии:",
        reply_markup=get_gender_keyboard(),
    )
    await state.set_state(GenerationStates.selecting_gender)


@router.message(GenerationStates.awaiting_photo)
async def handle_not_photo(message: Message) -> None:
    """Обработчик не-фото сообщений в состоянии ожидания фото"""
    await message.answer(
        "Пожалуйста, отправь фотографию.\n"
        "Лучше всего подойдёт портретное фото, где хорошо видно лицо."
    )


@router.message(GenerationStates.processing)
async def handle_message_while_processing(message: Message) -> None:
    """Обработчик сообщений во время обработки"""
    await message.answer(
        "Подожди, я ещё обрабатываю предыдущее фото..."
    )
