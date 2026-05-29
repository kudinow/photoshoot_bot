import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from bot.handlers.rating import send_rating_request
from bot.keyboards.inline import get_buy_keyboard, get_restart_keyboard
from bot.services.kie_client import KieClientError, kie_client
from bot.services.openai_client import OpenAIClientError, openai_client
from bot.services.user_limits import (
    can_generate,
    get_generations_count,
    get_remaining_generations,
    has_free_generations,
    has_user_rated,
    increment_generations,
    is_admin,
    log_generation,
    reward_referrer,
    save_last_photo,
)
from bot.services.watermark import apply_watermark, save_clean_copy
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()


@router.message(F.photo, GenerationStates.awaiting_photo)
async def handle_photo(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Обработчик получения фото"""
    user_id = message.from_user.id

    # Проверяем лимит генераций
    if not can_generate(user_id):
        await message.answer(
            "К сожалению, все генерации использованы 😔\n\n"
            "Пригласи друга — получи бесплатную генерацию!\n"
            "Или купи пакет генераций 👇",
            reply_markup=get_buy_keyboard(),
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
        style = data.get("style", "casual")

        logger.info(
            f"Starting generation for user {user_id}, "
            f"gender: {gender}, style: {style}"
        )

        # Генерируем промпт через OpenAI
        logger.info(f"Generating prompt for user {user_id}...")
        prompt = await openai_client.generate_prompt(gender, style)
        logger.info(
            f"Prompt generated for user {user_id}, "
            f"length: {len(prompt)}"
        )

        # Получаем файл фото (берём самое большое разрешение)
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)

        # Формируем URL для Telegram файла
        file_url = (
            f"https://api.telegram.org/file/bot"
            f"{bot.token}/{file.file_path}"
        )

        logger.info(
            f"Processing photo for user {user_id}, "
            f"file_path: {file.file_path}"
        )

        # Отправляем в kie.ai (GPT Image 2) и ждём результат.
        # Старый метод transform_photo() для nano-banana оставлен в kie_client
        # как fallback, но не используется в проде.
        result_url = await kie_client.transform_photo_gpt_image_2(
            image_url=file_url,
            prompt=prompt,
        )

        # Скачиваем результат
        result_image = await kie_client.download_image(result_url)

        # Водяной знак на первой бесплатной генерации (кроме админа)
        was_first_generation = get_generations_count(user_id) == 0
        watermarked = False
        if was_first_generation and not is_admin(user_id):
            try:
                save_clean_copy(user_id, result_image)
                result_image = apply_watermark(result_image)
                watermarked = True
            except Exception as e:
                logger.error(
                    f"Watermark failed for user {user_id}: {e}"
                )
                # Soft degradation: шлём чистое фото без кнопки разблокировки

        # Удаляем сообщение о обработке
        await processing_msg.delete()

        # Увеличиваем счётчик генераций
        is_paid = not has_free_generations(user_id)
        increment_generations(user_id)
        log_generation(user_id, gender, style, is_paid)

        # Реферальная награда: если это первая генерация пользователя
        if was_first_generation:
            referrer_id = reward_referrer(user_id)
            if referrer_id:
                try:
                    await bot.send_message(
                        referrer_id,
                        "🎉 Твой друг сделал первое фото!\n"
                        "Тебе начислена <b>1 бесплатная генерация</b>.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to notify referrer {referrer_id}: {e}"
                    )

        # Сохраняем URL фото, file_id оригинала, пол, стиль и URL результата
        save_last_photo(
            user_id,
            file_url,
            gender,
            style,
            photo_file_id=photo.file_id,
            result_url=result_url,
        )

        # Формируем caption с информацией об оставшихся генерациях
        remaining_after = get_remaining_generations(user_id)
        if watermarked:
            caption = (
                "Готово! Но фото пока с водяным знаком.\n\n"
                "Чистую версию без знака можно забрать за 50 ₽ 👇"
            )
        elif remaining_after == -1:
            caption = "Готово! Вот твой профессиональный портрет."
        elif remaining_after > 0:
            caption = (
                f"Готово! Вот твой профессиональный портрет.\n\n"
                f"📊 Осталось генераций: {remaining_after}"
            )
        else:
            caption = (
                "Готово! Вот твой профессиональный портрет.\n\n"
                "⚠️ Это была последняя генерация.\n"
                "Купи пакет генераций, чтобы продолжить!"
            )

        # Отправляем результат
        await message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="studio_portrait.jpg"
            ),
            caption=caption,
            reply_markup=get_restart_keyboard(
                has_last_photo=True,
                has_credits=(remaining_after != 0),
                has_watermarked=watermarked,
            ),
        )

        logger.info(
            f"Successfully generated photo for user {user_id}"
        )

        # После первой успешной генерации — запросить оценку (один раз в жизни)
        if was_first_generation and not has_user_rated(user_id):
            await send_rating_request(bot, message.chat.id)

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
            "Произошла ошибка при обработке фото. "
            "Попробуй ещё раз.\n\n"
            f"Ошибка: {e}",
            reply_markup=get_restart_keyboard(),
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error for user {message.from_user.id}: {e}"
        )
        await processing_msg.edit_text(
            "Произошла неожиданная ошибка. "
            "Попробуй ещё раз позже.",
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
        "Лучше всего подойдёт портретное фото, "
        "где хорошо видно лицо."
    )


@router.message(GenerationStates.processing)
async def handle_message_while_processing(
    message: Message,
) -> None:
    """Обработчик сообщений во время обработки"""
    await message.answer(
        "Подожди, я ещё обрабатываю предыдущее фото..."
    )
