import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.inline import get_gender_keyboard
from bot.services.user_limits import get_remaining_generations, is_admin
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
async def restart_generation(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки 'Создать ещё'"""
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "Выбери стиль фотографии:",
        reply_markup=get_gender_keyboard(),
    )
    await state.set_state(GenerationStates.selecting_gender)


@router.callback_query(F.data.startswith("gender:"), GenerationStates.selecting_gender)
async def select_gender(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора пола"""
    await callback.answer()

    gender = callback.data.split(":")[1]  # male или female
    await state.update_data(gender=gender)

    gender_text = "мужской" if gender == "male" else "женский"
    await callback.message.edit_text(
        f"Отлично! Выбран {gender_text} стиль.\n\n"
        "Теперь отправь мне своё фото (лучше всего портретное, где хорошо видно лицо)."
    )
    await state.set_state(GenerationStates.awaiting_photo)
