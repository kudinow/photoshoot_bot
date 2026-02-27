import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import STYLE_LABELS
from bot.keyboards.inline import (
    get_buy_keyboard,
    get_gender_keyboard,
    get_restart_keyboard,
    get_style_keyboard,
)
from bot.services.user_limits import (
    ADMIN_ID,
    can_generate,
    get_last_photo,
    get_paid_credits,
    get_referral_stats,
    get_remaining_generations,
    is_admin,
    is_new_user,
    save_referral,
)
from bot.states.generation import GenerationStates

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    """Обработчик команды /start"""
    await state.clear()

    user_id = message.from_user.id
    new_user = is_new_user(user_id)

    # Сохраняем источник перехода (диплинк)
    source = command.args
    if source:
        save_referral(user_id, source)
        logger.info(f"User {user_id} came from: {source}")

    # Уведомляем админа о новом пользователе
    if new_user and not is_admin(user_id):
        user = message.from_user
        name = user.full_name or ""
        username = f" (@{user.username})" if user.username else ""
        source_text = f"\nИсточник: {source}" if source else ""
        try:
            await message.bot.send_message(
                ADMIN_ID,
                f"👤 Новый пользователь!\n"
                f"{name}{username}\n"
                f"ID: {user_id}{source_text}",
            )
        except Exception as e:
            logger.error(f"Failed to notify admin about new user: {e}")

    remaining = get_remaining_generations(user_id)

    # Формируем текст о лимите
    if is_admin(user_id):
        limit_text = "👑 У тебя безлимитный доступ."
    elif remaining > 0:
        paid = get_paid_credits(user_id)
        if paid > 0:
            limit_text = f"💳 У тебя {remaining} генераций ({paid} оплаченных)."
        else:
            limit_text = "🎁 У тебя 1 бесплатная генерация."
    else:
        limit_text = (
            "⚠️ Генерации закончились. "
            "Купи пакет, чтобы продолжить!"
        )

    welcome_text = (
        "Привет! Я помогу превратить твоё фото "
        "в профессиональный студийный портрет.\n\n"
        "Как это работает:\n"
        "1. Выбери пол (мужской или женский)\n"
        "2. Выбери стиль одежды\n"
        "3. Отправь своё фото\n"
        "4. Получи профессиональный портрет!\n\n"
        f"{limit_text}\n\n"
        "Выбери пол:"
    )

    await message.answer(
        welcome_text, reply_markup=get_gender_keyboard()
    )
    await state.set_state(GenerationStates.selecting_gender)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика источников трафика (только для админа)"""
    if not is_admin(message.from_user.id):
        return

    stats = get_referral_stats()
    if not stats:
        await message.answer("Нет данных о переходах.")
        return

    total = sum(count for _, count in stats)
    lines = ["📊 *Источники трафика:*\n"]
    for source, count in stats:
        pct = round(count / total * 100)
        lines.append(f"• `{source}`: {count} чел. ({pct}%)")
    lines.append(f"\nВсего: {total}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.callback_query(F.data == "restart")
async def restart_generation(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик кнопки 'Создать ещё'"""
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "Выбери пол:",
        reply_markup=get_gender_keyboard(),
    )
    await state.set_state(GenerationStates.selecting_gender)


@router.callback_query(F.data == "regenerate")
async def regenerate_photo(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик кнопки 'Сгенерировать заново'"""
    await callback.answer()

    user_id = callback.from_user.id

    # Проверяем лимит генераций
    if not can_generate(user_id):
        await callback.message.answer(
            "К сожалению, все генерации использованы 😔\n\n"
            "Купи пакет генераций, чтобы продолжить!",
            reply_markup=get_buy_keyboard(),
        )
        await state.clear()
        return

    # Получаем последнюю фотографию
    photo_url, gender, style = get_last_photo(user_id)

    if not photo_url or not gender:
        await callback.message.answer(
            "У меня нет сохранённой фотографии. "
            "Пожалуйста, отправь новое фото.",
            reply_markup=get_gender_keyboard(),
        )
        await state.set_state(GenerationStates.selecting_gender)
        return

    style = style or "casual"

    # Импортируем здесь, чтобы избежать циклических импортов
    from aiogram.types import BufferedInputFile

    from bot.services.kie_client import KieClientError, kie_client
    from bot.services.openai_client import (
        OpenAIClientError,
        openai_client,
    )
    from bot.services.user_limits import (
        has_free_generations,
        increment_generations,
        log_generation,
    )

    await state.set_state(GenerationStates.processing)

    # Показываем оставшиеся генерации
    remaining = get_remaining_generations(user_id)
    remaining_text = (
        ""
        if remaining == -1
        else f"\n(Осталось генераций: {remaining - 1})"
    )

    # Отправляем сообщение о начале обработки
    processing_msg = await callback.message.answer(
        "Генерирую новый вариант твоей фотографии...\n"
        f"Это может занять 1-2 минуты.{remaining_text}"
    )

    try:
        logger.info(
            f"Regenerating for user {user_id}, "
            f"gender: {gender}, style: {style}"
        )

        # Генерируем новый промпт
        prompt = await openai_client.generate_prompt(gender, style)
        logger.info(
            f"Prompt generated for user {user_id}, "
            f"length: {len(prompt)}"
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
        is_paid = not has_free_generations(user_id)
        increment_generations(user_id)
        log_generation(user_id, gender, style, is_paid)

        # Формируем caption с информацией об оставшихся генерациях
        remaining_after = get_remaining_generations(user_id)
        if remaining_after == -1:
            caption = "Готово! Вот новый вариант твоего портрета."
        elif remaining_after > 0:
            caption = (
                f"Готово! Вот новый вариант твоего портрета.\n\n"
                f"📊 Осталось генераций: {remaining_after}"
            )
        else:
            caption = (
                "Готово! Вот новый вариант твоего портрета.\n\n"
                "⚠️ Это была последняя генерация.\n"
                "Купи пакет генераций, чтобы продолжить!"
            )

        # Отправляем результат
        await callback.message.answer_photo(
            photo=BufferedInputFile(
                result_image, filename="studio_portrait.jpg"
            ),
            caption=caption,
            reply_markup=get_restart_keyboard(
                has_last_photo=True,
                has_credits=(remaining_after != 0),
            ),
        )

        logger.info(
            f"Successfully regenerated photo for user {user_id}"
        )

    except OpenAIClientError as e:
        logger.error(f"OpenAI error for user {user_id}: {e}")
        await processing_msg.edit_text(
            "Ошибка генерации стиля. Попробуй ещё раз.",
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

    except KieClientError as e:
        logger.error(f"KieClient error for user {user_id}: {e}")
        await processing_msg.edit_text(
            "Произошла ошибка при обработке фото. "
            "Попробуй ещё раз.\n\n"
            f"Ошибка: {e}",
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error for user {user_id}: {e}"
        )
        await processing_msg.edit_text(
            "Произошла неожиданная ошибка. "
            "Попробуй ещё раз позже.",
            reply_markup=get_restart_keyboard(has_last_photo=True),
        )

    finally:
        await state.clear()


@router.callback_query(
    F.data.startswith("gender:"), GenerationStates.selecting_gender
)
async def select_gender(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик выбора пола → переход к выбору стиля"""
    await callback.answer()

    gender = callback.data.split(":")[1]  # male или female
    await state.update_data(gender=gender)

    gender_text = "мужской" if gender == "male" else "женский"
    await callback.message.edit_text(
        f"Пол: {gender_text}\n\n"
        "Теперь выбери стиль одежды:",
        reply_markup=get_style_keyboard(),
    )
    await state.set_state(GenerationStates.selecting_style)


@router.callback_query(
    F.data.startswith("style:"), GenerationStates.selecting_style
)
async def select_style(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Обработчик выбора стиля одежды → переход к загрузке фото"""
    await callback.answer()

    style = callback.data.split(":")[1]  # business, casual, creative
    await state.update_data(style=style)

    data = await state.get_data()
    gender = data.get("gender", "male")
    gender_text = "мужской" if gender == "male" else "женский"
    style_text = STYLE_LABELS.get(style, style)

    await callback.message.edit_text(
        f"Пол: {gender_text}, стиль: {style_text}\n\n"
        "Теперь отправь мне своё фото "
        "(лучше всего портретное, где хорошо видно лицо)."
    )
    await state.set_state(GenerationStates.awaiting_photo)
